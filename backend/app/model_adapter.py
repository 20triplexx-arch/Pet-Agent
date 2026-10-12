"""Configurable compatible model, evidence budgets and durable attempt accounting."""
import asyncio
import json
import re
from datetime import datetime, UTC
from zoneinfo import ZoneInfo
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits
from fastapi import HTTPException
from sqlmodel import select
from app.core.config import settings
from app.models import ModelUsage, ModelAttempt
from app.knowledge import sections


def day_start():
    current = datetime.now(ZoneInfo("Asia/Shanghai"))
    return current.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat()


def quota_status(session, user_id):
    attempts = session.exec(select(ModelAttempt).where(ModelAttempt.user_id == user_id, ModelAttempt.created_at >= day_start())).all()
    return {"daily_limit": settings.MODEL_TURNS_PER_DAY, "attempted_turns": len(attempts),
        "failed_turns": sum(a.status == "failed" for a in attempts),
        "remaining_turns": max(0, settings.MODEL_TURNS_PER_DAY - len(attempts)), "timezone": "Asia/Shanghai",
        "output_token_limit": settings.MODEL_MAX_OUTPUT_TOKENS,
        "note": "应用真实问答尝试数，含失败；token为成功取得的供应商用量，不是账单或余额。"}


def assemble_prompt(ctx, text, history, profile, articles):
    tools = dict(ctx.analysis.get("tool_results", {}))
    tools["recent_care"] = tools.get("recent_care", [])[:10]
    payload = {
        "current_profile": profile,
        "user_message": text,
        "supplemental_context": ctx.effective_context,
        "answer_depth": ctx.resolved_depth,
        "subquestions": ctx.analysis.get("questions", [text]),
        "context_conflicts": ctx.analysis.get("conflicts", []),
        "missing_health_information": ctx.analysis.get("health_questions"),
        "tool_results": tools,
        "history_summary": ctx.memory,
        "history": [{"id": m["id"], "role": m["role"], "content": m["content"], "date": m["created_at"]} for m in history[-24:]],
        "retrieved_data": [{k: a[k] for k in ("id", "title", "body", "species", "life_stages", "topic", "review_status")} | {"matched_sections": a.get("matched_sections", sections(a))} for a in articles],
    }
    notes = []
    def length():
        return len(json.dumps(payload, ensure_ascii=False))
    budget = max(16000, settings.MODEL_CONTEXT_CHARS)
    while length() > budget and payload["history"]:
        payload["history"].pop(0)
        if "较早完整消息已由带来源摘要替代" not in notes:
            notes.append("较早完整消息已由带来源摘要替代")
    if length() > budget:
        for a in payload["retrieved_data"]:
            a["body"] = "\n\n".join(s["heading"] + "\n" + s["text"] for s in a["matched_sections"])
        notes.append("知识正文仅提供与子问题匹配的完整章节")
    while length() > budget and len(payload["tool_results"].get("recent_care", [])) > 1:
        payload["tool_results"]["recent_care"].pop()
        if "近期记录按时间选取，完整记录仍可由工具读取" not in notes:
            notes.append("近期记录按时间选取，完整记录仍可由工具读取")
    if length() > budget:
        raise HTTPException(422, "当前资料超过服务端上下文预算；请分次提供补充资料。本次未截断问题或保存回答。")
    ctx.context_budget_notes = notes
    return json.dumps(payload, ensure_ascii=False)


async def run_model(ctx, text, history, profile, articles):
    from app.agent import agent
    prompt = assemble_prompt(ctx, text, history, profile, articles)
    attempt = ModelAttempt(user_id=ctx.user.id)
    ctx.session.add(attempt)
    ctx.session.flush()
    if quota_status(ctx.session, ctx.user.id)["attempted_turns"] > settings.MODEL_TURNS_PER_DAY:
        raise HTTPException(429, "今日真实问答次数已达上限，尚未调用模型。可以查看知识或明日重试。")
    ctx.model_attempt = attempt
    client = None
    try:
        client = AsyncOpenAI(api_key=settings.MODEL_API_KEY, base_url=settings.MODEL_BASE_URL,
            max_retries=0, timeout=settings.MODEL_TIMEOUT_SECONDS)
        model = OpenAIChatModel(settings.MODEL_NAME, provider=OpenAIProvider(openai_client=client))
        result = await asyncio.wait_for(agent.run(prompt, model=model, deps=ctx,
            model_settings={"max_tokens": settings.MODEL_MAX_OUTPUT_TOKENS, "temperature": .2},
            usage_limits=UsageLimits(request_limit=settings.MODEL_MAX_REQUESTS, tool_calls_limit=8,
                input_tokens_limit=settings.MODEL_MAX_INPUT_TOKENS,
                output_tokens_limit=settings.MODEL_MAX_OUTPUT_TOKENS * settings.MODEL_MAX_REQUESTS)),
            timeout=settings.MODEL_TIMEOUT_SECONDS)
        usage = result.usage
        row = ModelUsage(user_id=ctx.user.id, model=settings.MODEL_NAME,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, requests=usage.requests)
        ctx.known_model_usage = row
        ctx.session.add(row)
        if any(getattr(m, "finish_reason", None) == "length" for m in result.all_messages()):
            raise HTTPException(502, "模型输出达到上限，回答未完成。本次未保存，可以缩小问题或调整服务端输出预算。")
        answer = result.output
        if not answer.answer.strip() or any(i not in ctx.retrieved for i in answer.citation_ids):
            raise HTTPException(502, "模型未返回完整回答或返回了未检索来源，本次回答未保存")
        screened = answer.answer
        for reported in [(profile or {}).get("medical_history"), (profile or {}).get("vet_advice"), ctx.effective_context.get("values", {}).get("professional_advice")]:
            if reported:
                screened = screened.replace(reported, "[用户原始资料]")
        if re.search(r"(?:确诊|肯定是|一定是|诊断为).{0,16}(?:疾病|肾病|肝病|糖尿病|感染|中毒|炎|病)", screened) or re.search(r"(?:服用|用药|注射|给药).{0,40}\d+(?:\.\d+)?\s*(?:mg|毫克|毫升|ml|片)", screened, re.I):
            raise HTTPException(502, "模型回答包含不允许的确定诊断或药物剂量，本次未保存。可以继续询问观察和就医准备。")
        for cite in answer.citation_sections:
            article = ctx.retrieved.get(cite.article_id)
            if not article or cite.article_id not in answer.citation_ids or cite.heading not in {s["heading"] for s in sections(article)}:
                raise HTTPException(502, "模型引用了不存在的知识章节，本次回答未保存")
            headings = getattr(ctx, "citation_headings", {})
            headings.setdefault(cite.article_id, []).append(cite.heading)
            ctx.citation_headings = headings
        attempt.status = "completed"
        return answer
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(503, "模型请求失败、输出未完成或超出限制，本次未完成。可手动重试；不会自动重复调用。") from error
    finally:
        if client is not None:
            await client.close()
