"""Configurable compatible model, evidence budgets and durable attempt accounting."""
import asyncio
import json
import re
from dataclasses import replace
from datetime import datetime, UTC
from zoneinfo import ZoneInfo
from typing import Literal, Union
from pydantic import create_model, Field
from openai import AsyncOpenAI, APIStatusError, APITimeoutError
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.alibaba import AlibabaProvider
from pydantic_ai.usage import UsageLimits
from pydantic_ai.settings import ToolOrOutput
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.exceptions import UsageLimitExceeded, ModelHTTPError
from pydantic_ai import Agent, PromptedOutput, NativeOutput
from pydantic_ai.messages import ToolReturnPart
from fastapi import HTTPException
from sqlmodel import select
from app.core.config import settings
from app.models import ModelUsage, ModelAttempt
from app.knowledge import sections, model_sections, evidence_sections
from app.execution import current_execution
from app.evaluation_budget import current_budget, BudgetExceeded
from app.answer_quality import evidence_rules, has_disallowed_health_claim, unsupported_advice
from app.model_runtime import acquire_client, RequestClient, MeteredStream, section_sink, request_observer
from app.answer_sections import generate_sections, check_text


class CareChatModel(OpenAIChatModel):
    """Keep the wire schema aligned with the server's allowed tools per step.

    A named output-tool choice can otherwise retain every function schema for
    provider caching. Hide those schemas when finishing, not just in a prompt.
    """
    def prepare_request(self, model_settings, model_request_parameters):
        choice = (model_settings or {}).get("tool_choice")
        if isinstance(choice, ToolOrOutput):
            allowed = set(choice.function_tools)
            model_request_parameters = replace(model_request_parameters,
                function_tools=[tool for tool in model_request_parameters.function_tools if tool.name in allowed])
        return super().prepare_request(model_settings, model_request_parameters)


class FinishAnswer(Exception):
    """Internal phase transition before another provider request, not a retry."""


def provider_options(selection):
    if selection.provider == "alibaba":
        return {"extra_body": {"enable_thinking": False}}
    if selection.provider == "deepseek":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}


def native_schema(selection):
    from app.alibaba_models import supports_schema
    return selection.provider == 'alibaba' and supports_schema(selection.name)


def remember_evidence(ctx, article_id, passages):
    if not passages:
        return
    target = ctx.sent_evidence.setdefault(article_id, {})
    for passage in passages:
        target[passage["heading"]] = passage["text"]


def remember_tool_evidence(ctx, value):
    """Read only actual serialized tool returns, never assume full DB was sent."""
    if isinstance(value, dict):
        article_id = value.get("id")
        if isinstance(article_id, str) and article_id in ctx.retrieved and value.get("body") == ctx.retrieved[article_id].get("body"):
            remember_evidence(ctx, article_id, sections(value))
        elif isinstance(article_id, str) and article_id in ctx.retrieved:
            canonical = {s['heading']: s['text'] for s in sections(ctx.retrieved[article_id])}
            passages = [s for s in value.get('matched_sections', []) if isinstance(s, dict)
                        and isinstance(s.get('heading'), str) and s['heading'] in canonical
                        and canonical[s['heading']] == s.get('text')]
            remember_evidence(ctx, article_id, passages)
        for child in value.values():
            remember_tool_evidence(ctx, child)
    elif isinstance(value, list):
        for child in value:
            remember_tool_evidence(ctx, child)


def compact_tool_evidence(ctx, value, supplied, query):
    """One copy of each canonical passage in the actual provider request."""
    if isinstance(value, list):
        return [compact_tool_evidence(ctx, child, supplied, query) for child in value]
    if not isinstance(value, dict):
        return value
    article_id = value.get('id')
    if isinstance(article_id, str) and article_id in ctx.retrieved and value.get('body') == ctx.retrieved[article_id].get('body'):
        passages = model_sections({**value, 'matched_sections': evidence_sections(value, query)})
        known = supplied.setdefault(article_id, set())
        additional = [s for s in passages if s['heading'] not in known]
        known.update(s['heading'] for s in passages)
        return {k:v for k,v in value.items() if k not in ('body','matched_sections')} | {
            'matched_sections':additional, 'evidence_already_provided':not additional}
    return {k:compact_tool_evidence(ctx, child, supplied, query) for k,child in value.items()}


def grounded_output(ctx):
    """Constrain identifiers and exact article/heading pairs on the provider wire.

    Server validation remains authoritative; this prevents avoidable paid JSON
    failures without accepting renamed fields, invented IDs or chapter titles.
    """
    from app.schemas import AgentAnswer, CitationSection
    ids = tuple(ctx.sent_evidence)
    # Ordinary prose/Markdown is allowed; square brackets are reserved for
    # server-known article IDs. Chapter names stay in the constrained metadata.
    marker = '|'.join(re.escape(article_id) for article_id in ids)
    answer_pattern = r'^[^\[\]]*(?:\[(?:' + marker + r')\][^\[\]]*)*$' if ids else r'^[^\[\]]+$'
    if not ids:
        return create_model('GroundedAnswer', __base__=AgentAnswer,
            answer=(str, Field(min_length=1, pattern=answer_pattern)),
            citation_ids=(list[str], Field(default_factory=list, max_length=0)),
            citation_sections=(list[CitationSection], Field(default_factory=list, max_length=0)),
            draft=(type(None), None))
    choices = []
    for index, article_id in enumerate(ids):
        choices.append(create_model(f'EvidenceSection{index}', __base__=CitationSection,
            article_id=(Literal[article_id], ...),
            heading=(Literal[tuple(ctx.sent_evidence[article_id])], ...)))
    section_type = Union[tuple(choices)] if len(choices) > 1 else choices[0]
    return create_model('GroundedAnswer', __base__=AgentAnswer,
        answer=(str, Field(min_length=1, pattern=answer_pattern)),
        citation_ids=(list[Literal[ids]], Field(default_factory=list)),
        citation_sections=(list[section_type], Field(default_factory=list, max_length=30)),
        draft=(type(None), None))


def available_read_tools(ctx):
    supplied = ctx.analysis.get("tool_results", {})
    fulfilled = {"get_pet_profile", "search_nearby_hospitals"}
    if getattr(ctx, 'foreign_species', False):
        fulfilled.update({'get_care_history', 'get_current_care_plans', 'assess_nutrition',
                          'assess_pet_products', 'get_care_review', 'build_vet_visit_summary'})
    for field, tool in (("recent_care", "get_care_history"), ("active_plans", "get_current_care_plans"),
                        ("nutrition", "assess_nutrition"), ("products", "assess_pet_products"),
                        ("visit_summary", "build_vet_visit_summary")):
        if field in supplied:
            fulfilled.add(tool)
    if not ctx.breed_scope or any(a.get("content_kind") == "breed" for a in ctx.retrieved.values()):
        fulfilled.add("get_breed_knowledge")
    from app.agent import agent
    return [name for name in agent._function_toolset.tools
            if name not in fulfilled and name not in {"save_care_plan", "create_reminder", "record_care_log"}]


def day_start():
    current = datetime.now(ZoneInfo("Asia/Shanghai"))
    return current.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat()


def quota_status(session, user_id):
    attempts = session.exec(select(ModelAttempt).where(ModelAttempt.user_id == user_id, ModelAttempt.created_at >= day_start())).all()
    enabled = settings.MODEL_LIMITS_ENABLED
    return {"limits_enabled": enabled, "daily_limit": settings.MODEL_TURNS_PER_DAY if enabled else None, "attempted_turns": len(attempts),
        "failed_turns": sum(a.status == "failed" for a in attempts),
        "remaining_turns": max(0, settings.MODEL_TURNS_PER_DAY - len(attempts)) if enabled else None, "timezone": "Asia/Shanghai",
        "request_limit": min(settings.MODEL_MAX_REQUESTS, 4) if enabled else None,
        "tool_calls_limit": 8 if enabled else None,
        "output_token_limit": settings.MODEL_MAX_OUTPUT_TOKENS,
        "note": "应用真实问答尝试数，含失败；token为成功取得的供应商用量，不是账单或余额。"}


def assemble_prompt(ctx, text, history, profile, articles):
    tools = dict(ctx.analysis.get("tool_results", {}))
    if "recent_care" in tools:
        tools["recent_care"] = tools["recent_care"][:10]
    payload = {
        "current_profile": profile,
        "user_message": text,
        "supplemental_context": ctx.effective_context,
        "answer_depth": ctx.resolved_depth,
        "subquestions": ctx.analysis.get("questions", [text]),
        "context_conflicts": ctx.analysis.get("conflicts", []),
        "answer_context": ctx.analysis.get('answer_context', {}),
        "response_focus": ctx.analysis.get('response_focus', {}),
        "source_specific_rules": evidence_rules(a["id"] for a in articles),
        'quantitative_policy': '只有tool_results.nutrition.status为ready时才能引用其计算数值；否则不输出任何建议克数、每日热量、区间或假设计算示例。每100克可作为索取标签的单位。',
        'profile_unknown_fields': [key for key in ('age_months', 'weight', 'neutered', 'allergies', 'medical_history', 'vet_advice') if profile is not None and profile.get(key) is None],
        "missing_health_information": ctx.analysis.get("health_questions"),
        "tool_results": tools,
        "history_summary": ctx.memory,
        "history": [{"id": m["id"], "role": m["role"],
                     "content": re.sub(r'\[[a-zA-Z][a-zA-Z0-9#_-]*\]', '', m['content']) if m['role'] == 'assistant' else m['content'],
                     "date": m["created_at"]} for m in history[-4:]],
        "retrieved_data": [{k: a[k] for k in ("id", "title", "species", "life_stages", "topic", "review_status")} |
                           {"matched_sections": model_sections(a), "matched_questions": a.get("matched_questions", []),
                            "section_questions": a.get('section_questions', {}),
                            } for a in articles],
    }
    supplied = {a['id']:{s['heading'] for s in a['matched_sections']} for a in payload['retrieved_data']}
    payload['tool_results'] = compact_tool_evidence(ctx, payload['tool_results'], supplied, text)
    notes = []
    def length():
        return len(json.dumps(payload, ensure_ascii=False))
    budget = max(16000, settings.MODEL_CONTEXT_CHARS)
    while length() > budget and payload["history"]:
        payload["history"].pop(0)
        if "较早完整消息已由带来源摘要替代" not in notes:
            notes.append("较早完整消息已由带来源摘要替代")
    while length() > budget and len(payload["tool_results"].get("recent_care", [])) > 1:
        payload["tool_results"]["recent_care"].pop()
        if "近期记录按时间选取，完整记录仍可由工具读取" not in notes:
            notes.append("近期记录按时间选取，完整记录仍可由工具读取")
    if length() > budget:
        raise HTTPException(422, "当前资料超过服务端上下文预算；请分次提供补充资料。本次未截断问题或保存回答。")
    ctx.context_budget_notes = notes
    for article in payload["retrieved_data"]:
        remember_evidence(ctx, article["id"], article["matched_sections"])
    remember_tool_evidence(ctx, payload['tool_results'])
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


async def run_model(ctx, text, history, profile, articles):
    from app.agent import agent, SYSTEM, AgentContext
    from app.schemas import AgentAnswer
    selection = ctx.selected_model
    ctx.current_text = text
    if selection.demo or not selection.key:
        raise HTTPException(503, "真实模型密钥未配置，本次未完成。请检查服务端配置。")
    prompt = assemble_prompt(ctx, text, history, profile, articles)
    attempt = ModelAttempt(user_id=ctx.user.id)
    if settings.MODEL_LIMITS_ENABLED and quota_status(ctx.session, ctx.user.id)["attempted_turns"] >= settings.MODEL_TURNS_PER_DAY:
        raise HTTPException(429, "今日真实问答次数已达上限，尚未调用模型。可以查看知识或明日重试。")
    ctx.model_attempt = attempt
    client = None
    pooled = False
    last_finish_reason = None
    try:
        client, pooled = acquire_client(AsyncOpenAI, selection, settings.MODEL_TIMEOUT_SECONDS)
        provider_type = {"deepseek": DeepSeekProvider, "alibaba": AlibabaProvider}.get(selection.provider, OpenAIProvider)
        provider = provider_type(openai_client=client)
        # Installed profiles predate Qwen 3.7. Declare its verified JSON mode
        # and DashScope's max_tokens wire parameter without changing other providers.
        model_profile = {"supports_json_object_output": True, "supports_json_schema_output": native_schema(selection),
                   "openai_chat_supports_max_completion_tokens": False} if selection.provider == "alibaba" else None
        model = CareChatModel(selection.name, provider=provider, profile=model_profile)
        create = client.chat.completions.create

        async def measured_create(**kwargs):
            nonlocal last_finish_reason, selection
            budget = current_budget.get()
            trace = current_execution.get()
            supplied, queries = {}, {}
            for message in kwargs.get("messages", []):
                if message.get('role') == 'user' and isinstance(message.get('content'), str):
                    try:
                        initial = json.loads(message['content'])
                        for article in initial.get('retrieved_data', []) if isinstance(initial, dict) else []:
                            supplied.setdefault(article['id'], set()).update(s['heading'] for s in article.get('matched_sections', []))
                    except (ValueError, TypeError):
                        pass
                for call in message.get('tool_calls') or []:
                    try:
                        arguments = json.loads(call['function']['arguments'])
                        queries[call['id']] = arguments.get('query', text)
                    except (ValueError, TypeError, KeyError):
                        pass
                if message.get("role") == "tool" and isinstance(message.get("content"), str):
                    try:
                        compact = compact_tool_evidence(ctx, json.loads(message['content']), supplied,
                                                        queries.get(message.get('tool_call_id'), text))
                        message['content'] = json.dumps(compact, ensure_ascii=False)
                        remember_tool_evidence(ctx, compact)
                    except (ValueError, TypeError):
                        pass
            tried = set()
            free_receipt = None
            from app import alibaba_quota
            while True:
                kwargs['model'] = selection.name
                if kwargs.get('stream') and getattr(ctx, 'segment_schema', None):
                    if native_schema(selection):
                        kwargs['response_format'] = {'type': 'json_schema', 'json_schema': {
                            'name': 'CareAnswerSections', 'strict': True, 'schema': ctx.segment_schema}}
                    else:
                        kwargs['response_format'] = {'type': 'json_object'}
                        schema_hint = ('输出正文对象，不输出JSON Schema或字段定义。格式：'
                            '{"sections":[{"text":"完整正文","evidence_ids":["本轮证据编号"],"question_ids":[1]}]}')
                        if schema_hint not in kwargs['messages'][0]['content']:
                            kwargs['messages'][0]['content'] += '\n' + schema_hint
                elif not native_schema(selection) and isinstance(kwargs.get('response_format'), dict) and kwargs['response_format'].get('type') == 'json_schema':
                    # A fallback can change provider capabilities while the
                    # current Pydantic run still expects the same JSON body.
                    schema = kwargs['response_format']['json_schema']['schema']
                    kwargs['response_format'] = {'type': 'json_object'}
                    kwargs['messages'][0]['content'] += '\nJSON结构：' + json.dumps(schema, ensure_ascii=False)
                guarded = selection.provider == 'alibaba' and settings.DASHSCOPE_FREE_ONLY
                if guarded:
                    try:
                        free_receipt = alibaba_quota.reserve(kwargs, automatic=selection.id == 'alibaba-auto')
                    except HTTPException:
                        if selection.id != 'alibaba-auto':
                            raise
                        tried.add(selection.name)
                        selection = replace(selection, name=alibaba_quota.choose_model(exclude=tried))
                        ctx.model_selection = selection
                        continue
                try:
                    reservation = budget.reserve(kwargs) if budget else None
                except BaseException:
                    alibaba_quota.settle(free_receipt, not_sent=True)
                    raise
                if trace:
                    trace.model_requests += 1
                    trace.mark('model_request', once=True)
                try:
                    if observer := request_observer.get():
                        observer('request', kwargs, ctx.sent_evidence)
                    response = await create(**kwargs)
                    break
                except Exception as error:
                    if observer := request_observer.get():
                        observer('error', error, None)
                    body = getattr(error, 'body', {})
                    detail = body.get('error', body) if isinstance(body, dict) else {}
                    exhausted = isinstance(detail, dict) and detail.get('code') == 'AllocationQuota.FreeTierOnly'
                    if exhausted and guarded:
                        alibaba_quota.mark_exhausted(selection.name)
                    if exhausted and guarded and selection.id == 'alibaba-auto' and not getattr(ctx, 'sections_emitted', 0):
                        tried.add(selection.name)
                        selection = replace(selection, name=alibaba_quota.choose_model(exclude=tried))
                        ctx.model_selection = selection
                        continue
                    if trace:
                        trace.error_type = type(error).__name__
                    raise
            if kwargs.get('stream'):
                settled = False
                def consume(chunk):
                    nonlocal last_finish_reason, settled
                    if observer := request_observer.get():
                        observer('chunk', chunk, None)
                    for choice in chunk.choices:
                        if choice.finish_reason:
                            last_finish_reason = choice.finish_reason
                    if chunk.usage and not settled:
                        settled = True
                        if budget:
                            budget.settle(reservation, chunk.usage)
                        alibaba_quota.settle(free_receipt, chunk.usage)
                        if trace:
                            trace.input_tokens += chunk.usage.prompt_tokens or 0
                            trace.output_tokens += chunk.usage.completion_tokens or 0
                            trace.cached_input_tokens += getattr(chunk.usage.prompt_tokens_details, 'cached_tokens', 0) or 0
                return MeteredStream(response, consume)
            reasons = {choice.finish_reason for choice in response.choices}
            if observer := request_observer.get():
                observer('response', response, None)
            last_finish_reason = "length" if "length" in reasons else "content_filter" if "content_filter" in reasons else None
            if budget:
                budget.settle(reservation, response.usage)
            alibaba_quota.settle(free_receipt, response.usage)
            if trace and response.usage:
                trace.input_tokens += response.usage.prompt_tokens or 0
                trace.output_tokens += response.usage.completion_tokens or 0
                trace.cached_input_tokens += getattr(response.usage.prompt_tokens_details, 'cached_tokens', 0) or 0
            return response

        provider._client = RequestClient(client, measured_create)
        # Dedicated evaluations retain their separately authorized budget.
        limited = settings.MODEL_LIMITS_ENABLED or current_budget.get() is not None
        request_limit = min(settings.MODEL_MAX_REQUESTS, 4) if limited else None
        depth_limit = {"brief": 1024, "standard": 2048, "detailed": 4096}.get(ctx.resolved_depth, 2048)
        output_limit = min(settings.MODEL_MAX_OUTPUT_TOKENS, depth_limit)
        if budget := current_budget.get():
            output_limit = min(output_limit, budget.output_token_limit)
        read_tools = available_read_tools(ctx)
        phase_usage = None
        def finish_collection(run):
            if limited:
                return run.usage.requests >= min(2, request_limit - 1) or run.usage.tool_calls >= 4
            # Unlimited local mode has no fixed turn/tool cutoff. End genuine
            # repeated reads instead; different queries may keep gathering facts.
            seen = set()
            writes = {"save_care_plan", "create_reminder", "record_care_log"}
            for message in run.messages:
                for part in message.parts:
                    if isinstance(part, ToolCallPart) and part.tool_name not in writes:
                        key = (part.tool_name, json.dumps(part.args_as_dict(), sort_keys=True, ensure_ascii=False))
                        if key in seen:
                            return True
                        seen.add(key)
            return False
        def step_settings(run):
            nonlocal phase_usage
            options = {"max_tokens": output_limit, "temperature": .2,
                **provider_options(selection), "tool_choice": ToolOrOutput(function_tools=read_tools)}
            # Reserve a request for the structured answer. More retrieval must
            # never spend the entire budget and leave the user with no answer.
            finish = finish_collection(run)
            if finish:
                phase_usage = run.usage
                reads = [{"tool": part.tool_name, "result": part.content}
                    for message in run.messages for part in message.parts
                    if isinstance(part, ToolReturnPart) and part.tool_name != "search_pet_knowledge"]
                ctx.analysis.setdefault("tool_results", {})["agent_read_results"] = reads
                if trace := current_execution.get():
                    trace.model_finalization_forced = True
                raise FinishAnswer()
            elif limited and run.usage.requests:
                counts = {}
                for message in run.messages:
                    for part in message.parts:
                        if isinstance(part, ToolCallPart):
                            counts[part.tool_name] = counts.get(part.tool_name, 0) + 1
                available = [name for name in read_tools
                    if counts.get(name, 0) < (2 if name == "search_pet_knowledge" else 1)]
                options["tool_choice"] = ToolOrOutput(function_tools=available)
            return options
        def step_instructions(run):
            if finish_collection(run):
                return "补充检索阶段已结束。使用已有真实资料立即返回完整的结构化回答，不再调用照护工具；资料不足时说明缺口并追问最重要的1—3项，不编造事实或声称写入成功。"
            return "已提供档案与检索资料；仅补充缺失且直接影响答案的信息。不要重复读取或检索相同资料，及时返回结构化回答。"
        limits = UsageLimits(request_limit=request_limit, tool_calls_limit=8 if limited else None,
            input_tokens_limit=settings.MODEL_MAX_INPUT_TOKENS,
            output_tokens_limit=output_limit * request_limit if request_limit is not None else None)
        async def complete_turn():
            async def answer_only(usage=None):
                final_prompt = assemble_prompt(ctx, text, history, profile, list(ctx.retrieved.values()))
                if section_sink.get():
                    return await generate_sections(ctx, final_prompt, profile, measured_create,
                        {'max_tokens': output_limit, 'temperature': .2, **provider_options(selection)}, SYSTEM, usage)
                output = NativeOutput(grounded_output(ctx), strict=True) if native_schema(selection) else PromptedOutput(AgentAnswer)
                answer_agent = Agent(deps_type=AgentContext, output_type=output,
                    system_prompt=SYSTEM + '\n本轮适用边界：\n' + '\n'.join(evidence_rules(ctx.sent_evidence)), retries=0)
                return await answer_agent.run(final_prompt, model=model, deps=ctx,
                    instructions="只返回完整JSON回答；落实source_specific_rules，覆盖所有子问题，使用已提供章节及本地计算，缺失资料保持未知，不调用工具或声称保存。正文仅用[article-id]标记，准确章节放在citation_sections，每章只列一次。evidence_text通常留空，draft返回null。",
                    model_settings={"max_tokens": output_limit, "temperature": .2, **provider_options(selection)},
                    usage=usage, usage_limits=limits)
            if ctx.analysis.get("evidence_ready"):
                if trace := current_execution.get():
                    trace.answer_path = "direct"
                return await answer_only()
            if trace := current_execution.get():
                trace.answer_path = "agent"
            try:
                return await agent.run(prompt, model=model, deps=ctx,
                    model_settings=step_settings, instructions=step_instructions, usage_limits=limits)
            except FinishAnswer:
                # A fresh, tool-free JSON answer avoids replaying the provider's
                # tool-call chain. Both phases share cumulative usage and limits.
                return await answer_only(phase_usage)
        result = await asyncio.wait_for(complete_turn(), timeout=settings.MODEL_TIMEOUT_SECONDS)
        usage = result.usage
        trace = current_execution.get()
        row = ModelUsage(user_id=ctx.user.id, model=selection.name,
            input_tokens=trace.input_tokens if trace else usage.input_tokens,
            output_tokens=trace.output_tokens if trace else usage.output_tokens,
            requests=trace.model_requests if trace else usage.requests)
        ctx.known_model_usage = row
        ctx.session.add(row)
        if last_finish_reason == 'length' or any(getattr(m, "finish_reason", None) == "length" for m in result.all_messages()):
            raise HTTPException(502, "模型输出达到上限，回答未完成。本次未保存，可以缩小问题或调整服务端输出预算。")
        answer = result.output
        # Reconcile redundant metadata only for sources actually supplied.
        # Invented IDs and chapter names still fail the shared checks below.
        for article_id, _ in re.findall(r"\[([a-z][a-z0-9-]*)(?:#([^\]\n]+))?\]", answer.answer):
            if article_id in ctx.sent_evidence and article_id not in answer.citation_ids:
                answer.citation_ids.append(article_id)
        if not answer.answer.strip() or any(i not in ctx.sent_evidence for i in answer.citation_ids):
            raise HTTPException(502, "模型未返回完整回答或返回了未检索来源，本次回答未保存")
        check_text(answer.answer, profile, ctx)
        for cite in answer.citation_sections:
            article = ctx.retrieved.get(cite.article_id)
            sent = ctx.sent_evidence.get(cite.article_id, {})
            if not article or cite.article_id not in answer.citation_ids or cite.heading not in sent:
                raise HTTPException(502, "模型引用了未提供的知识章节，本次回答未保存")
            if cite.evidence_text:
                passage = sent[cite.heading]
                normalize = lambda value: re.sub(r"\s+", "", value)
                if not normalize(cite.evidence_text) or normalize(cite.evidence_text) not in normalize(passage):
                    raise HTTPException(502, "模型提供的核对片段不在实际知识章节内，本次回答未保存")
            headings = getattr(ctx, "citation_headings", {})
            headings.setdefault(cite.article_id, []).append(cite.heading)
            ctx.citation_headings = headings
        for article_id, heading in re.findall(r"\[([a-z][a-z0-9-]*)(?:#([^\]\n]+))?\]", answer.answer):
            if article_id not in answer.citation_ids or article_id not in ctx.sent_evidence or (heading and heading not in ctx.sent_evidence[article_id]):
                raise HTTPException(502, "模型正文引用了未提供的来源或章节，本次回答未保存")
            if heading:
                ctx.citation_headings = getattr(ctx, "citation_headings", {})
                chosen = ctx.citation_headings.setdefault(article_id, [])
                if heading not in chosen:
                    chosen.append(heading)
        ctx.citation_headings = getattr(ctx, "citation_headings", {})
        for article_id in answer.citation_ids:
            ctx.citation_headings.setdefault(article_id, list(ctx.sent_evidence[article_id])[:3])
        attempt.status = "completed"
        ctx.session.add(attempt)
        if trace := current_execution.get():
            trace.mark('validation_finished')
        return answer
    except HTTPException:
        raise
    except BudgetExceeded as error:
        raise HTTPException(429, "本阶段模型测试预算不足，本次未完成。") from error
    except Exception as error:
        if observer := request_observer.get():
            observer('internal_error', error, None)
        if trace := current_execution.get():
            trace.error_type = trace.error_type or type(error).__name__
        def denied_tool(exc):
            if isinstance(exc, HTTPException) and exc.status_code == 403:
                return True
            return any(denied_tool(child) for child in getattr(exc, "exceptions", ()))
        if denied_tool(error):
            raise HTTPException(403, "本次工具写入未获得明确授权，未保存任何修改。") from error
        if isinstance(error, UsageLimitExceeded):
            limit_text = str(error).lower()
            reason = "工具调用次数" if "tool" in limit_text else "输入资料用量" if "input" in limit_text else "输出用量" if "output" in limit_text else "模型调用次数"
            raise HTTPException(503, f"本轮{reason}达到应用上限，回答未完成且未保存。可手动重试；不会自动重复调用。") from error
        if last_finish_reason == "length":
            raise HTTPException(502, "模型输出达到上限，回答未完成。本次未保存，可以缩小问题或调整服务端输出预算。") from error
        if isinstance(error, (TimeoutError, APITimeoutError)):
            raise HTTPException(504, "模型回答超时，本次未完成且未保存。可手动重试。") from error
        if isinstance(error, (APIStatusError, ModelHTTPError)):
            body = getattr(error, "body", {})
            detail = body.get("error", body) if isinstance(body, dict) else {}
            code = detail.get("code", "") if isinstance(detail, dict) else ""
            if code == "AllocationQuota.FreeTierOnly":
                raise HTTPException(503, "所选模型免费额度已用完或过期，服务商已按用完即停设置停止调用。可在服务端明确选择仍有额度的模型后手动重试。") from error
            if code == "AccessDenied.Unpurchased":
                raise HTTPException(503, "所选模型调用资格或额度不可用，请在百炼核对该模型免费额度、开通状态及业务空间权限。本次未完成。") from error
            if error.status_code in (401, 403):
                raise HTTPException(503, "模型服务鉴权失败，请检查所选服务商密钥、地域和业务空间权限。本次未完成。") from error
            if error.status_code == 404:
                raise HTTPException(503, "所选模型或服务地址不可用，请检查服务端模型名称和地域配置。本次未完成。") from error
            if error.status_code == 429:
                raise HTTPException(503, "模型服务额度不足或请求过于频繁，本次未完成。可稍后手动重试。") from error
        raise HTTPException(503, "模型请求失败、输出未完成或超出限制，本次未完成。可手动重试；不会自动重复调用。") from error
    finally:
        if client is not None and not pooled:
            await client.close()
