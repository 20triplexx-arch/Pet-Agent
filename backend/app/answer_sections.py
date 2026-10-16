"""Incremental, closed-object parsing and shared paragraph evidence checks."""
import json
import re
from types import SimpleNamespace
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from fastapi import HTTPException
from pydantic_ai.usage import RunUsage
from app.answer_quality import has_disallowed_health_claim, unsupported_advice, factual_error
from app.answer_context import repeated_known_question
from app.model_runtime import section_sink
from app.execution import current_execution
from app.knowledge import passage_questions


class AnswerSection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=3500)
    evidence_ids: list[str] = Field(max_length=16)
    question_ids: list[int] = Field(min_length=1, max_length=40)


class SectionAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    sections: list[AnswerSection] = Field(min_length=1, max_length=40)


class ClosedSections:
    """Only raw_decode-complete objects are visible; partial validation is insufficient."""
    def __init__(self):
        self.text, self.position, self.ended = '', None, False

    def feed(self, delta):
        self.text += delta
        if len(self.text) > 120000:
            raise HTTPException(502, '模型输出超过完整性检查范围，本次未保存。')
        if self.position is None:
            match = re.match(r'^\s*\{\s*"sections"\s*:\s*\[', self.text)
            if not match:
                return []
            self.position = match.end()
        found = []
        while not self.ended:
            while self.position < len(self.text) and self.text[self.position] in ' \r\n\t,':
                self.position += 1
            if self.position >= len(self.text):
                break
            if self.text[self.position] == ']':
                self.ended = True
                break
            try:
                value, end = json.JSONDecoder().raw_decode(self.text, self.position)
            except ValueError:
                break
            if not isinstance(value, dict):
                raise HTTPException(502, '模型回答段落格式无效，本次未保存。')
            found.append(AnswerSection.model_validate(value))
            self.position = end
        return found


def screen_health(text, profile, context):
    for reported in [(profile or {}).get('medical_history'), (profile or {}).get('vet_advice'),
                     context.get('values', {}).get('professional_advice')]:
        if reported:
            text = text.replace(reported, '[用户原始资料]')
    return text


def check_text(text, profile, ctx):
    screened = screen_health(text, profile, ctx.effective_context)
    if has_disallowed_health_claim(screened):
        raise HTTPException(502, '模型回答包含不允许的确定诊断或药物剂量，本次未保存。可以继续询问观察和就医准备。')
    if unsupported_advice(screened, ctx.sent_evidence):
        raise HTTPException(502, '模型建议与实际资料的适用条件不一致，本次回答未保存。可补充条件后手动重试。')
    if reason := factual_error(screened, profile, ctx):
        raise HTTPException(502, '模型回答未通过事实核对：' + reason + '。本次未保存，可手动重试。')
    known = getattr(ctx, 'analysis', {}).get('answer_context', {}).get('known_fields', {})
    if repeated_known_question(text, known):
        raise HTTPException(502, '模型重复索取已明确提供的资料，本次未保存，可手动重试。')


def evidence_map(ctx):
    return {f'e{index}': {'article_id': aid, 'heading': heading, 'text': text}
            for index, (aid, heading, text) in enumerate(
                ((aid, heading, text) for aid, passages in ctx.sent_evidence.items()
                 for heading, text in passages.items()), 1)}


def bind_section(section, evidence, questions, profile, ctx):
    canonical_refs = [ref.lower() if ref.lower() in evidence else ref for ref in section.evidence_ids]
    if any(ref not in evidence for ref in canonical_refs):
        raise HTTPException(502, '模型引用了未提供的知识章节，本次回答未保存。')
    refs = list(dict.fromkeys(canonical_refs))
    aids = list(dict.fromkeys(evidence[ref]['article_id'] for ref in refs))
    # A redundant marker is reconciled only when it names the exact same
    # supplied evidence already bound to this paragraph. Unknown markers fail.
    def remove_verified_marker(match):
        marker = match.group(1)
        if marker.lower() in refs or marker in aids:
            return ''
        return match.group(0)
    prose = re.sub(r'\[([^\]\n]+)\]', remove_verified_marker, section.text)
    prose = re.sub(r'[（(](e\d+)[）)]', remove_verified_marker, prose, flags=re.I)
    if re.search(r'(?<![a-zA-Z0-9])e\d+(?![a-zA-Z0-9])', prose, re.I):
        raise HTTPException(502, '模型正文包含未处理的内部证据编号，本次未保存。')
    if not prose.strip() or re.search(r'https?://|\[[^\]]*\]', prose):
        raise HTTPException(502, '模型正文格式或来源标记无效，本次未保存。')
    if any(q < 1 or q > len(questions) for q in section.question_ids):
        raise HTTPException(502, '模型回答的问题对应关系无效，本次未保存。')
    mappings = [ctx.retrieved.get(evidence[ref]['article_id'], {}).get('section_questions') for ref in refs]
    if refs and all(mapping is not None for mapping in mappings):
        linked = {question for ref in refs for question in passage_questions(
            ctx.retrieved[evidence[ref]['article_id']], evidence[ref]['heading'])}
        if any(questions[q - 1] not in linked for q in section.question_ids):
            raise HTTPException(502, '模型段落所引章节与对应问题不匹配，本次未保存。')
    if evidence and not refs:
        # Facts and instructions need a bound source. A question about missing
        # user data can stand alone, but uncited care advice cannot.
        if not re.fullmatch(r'[^。！？!?]*[？?]', prose.strip()):
            raise HTTPException(502, '模型照护段落未绑定实际依据，本次未保存。')
    bound_evidence = {}
    for ref in refs:
        passage = evidence[ref]
        bound_evidence.setdefault(passage['article_id'], {})[passage['heading']] = passage['text']
    check_text(prose, profile, SimpleNamespace(effective_context=ctx.effective_context,
        sent_evidence=bound_evidence, analysis=getattr(ctx, 'analysis', {}),
        current_text=getattr(ctx, 'current_text', '')))
    text = prose.strip() + ''.join(f'[{aid}]' for aid in aids)
    sources = []
    for aid in aids:
        article = ctx.retrieved[aid]
        passages = [evidence[ref] for ref in refs if evidence[ref]['article_id'] == aid]
        sources.append({'id': aid, 'title': article['title'], 'url': article['source_url'],
                        'organization': article['source_organization'],
                        'sections': [p['heading'] for p in passages],
                        'evidence': [{'heading': p['heading'], 'text': p['text'][:400]} for p in passages]})
    return {'text': text, 'question_ids': section.question_ids, 'sources': sources}


async def generate_sections(ctx, prompt, profile, create, model_settings, system, initial_usage=None):
    from app.schemas import AgentAnswer, CitationSection
    evidence = evidence_map(ctx)
    payload = json.loads(prompt)
    # Send only selected passages, with their meaning and question association.
    questions = payload['subquestions']
    payload['evidence'] = {ref: {'source': ctx.retrieved[passage['article_id']]['title'],
        'section': passage['heading'], 'text': passage['text'],
        'questions': [i for i, question in enumerate(questions, 1)
                      if question in passage_questions(ctx.retrieved[passage['article_id']], passage['heading'])]}
        for ref, passage in evidence.items()}
    payload.pop('retrieved_data', None)
    payload['subquestions'] = {str(i): q for i, q in enumerate(questions, 1)}
    source_rules = payload.pop('source_specific_rules', [])
    if not re.search(r'零食|奖励|比例|百分|10\s*[%％]', getattr(ctx, 'current_text', '')):
        source_rules.append('当前问题未询问零食配额，不主动引入10%等比例；直接回答当前喂食、饮水或记录原则。')
    instructions = ('只输出JSON对象sections数组，每段含text、evidence_ids、question_ids三个字段。'
        '首段通常用25—45字直接回答当前问题，必要条件必须说全，可以适当更长；不先复述问题。'
        'text为完整自然段或完整列表项，不含引用标记、链接或内部编号；evidence_ids只取本轮evidence的编号。'
        '每段事实和操作必须由绑定原文支持；引用数值时，同段写全适用条件。纯追问可无证据。'
        '只说原文明示的步骤和文件；定性要求不换成具体频率、小时数或强制证件，不补充医学机理。'
        '证据短编号每轮重新分配，只用本轮evidence的键；不沿用历史回答的来源编号。'
        'question_ids使用subquestions的数字编号，整篇覆盖全部问题；不要为凑段落重复结论。'
        '输出紧凑JSON，不缩进。每段优先绑定最直接的1—2个证据，不必把每个证据都讲一遍。'
        '每段text不换行，不在一个text里放多个段落，不追加“依据：”或内部编号；来源由服务端展示。'
        '段数取决于实际信息量：普通问题通常2—3段，简单追问1—2段且只讲新增点；深入回答按需展开。'
        '没有新增依据就结束，不为凑段数扩写选购、机制、医疗或复盘话题，不重讲上一答。'
        '缺资料说明已知原则及真正影响判断的缺口，不追问已知字段。不声称保存，不返回草稿。'
        '\n证据约束示例（示例不属于本轮证据，不可引用）：'
        '原文“观察接受程度，逐步调整，不要求统一频率”只能改述接受度与调整；不能增加每天几次、分钟数或奖励种类。'
        '原文“需同时核对A、B、C；未知不推算”应明确缺口，不得说“补A就能准确确定”，也不生成假设数值示例。'
        '概念解释只能沿用资料的评估对象，生活观察不能改称正式评分指标。')
    instructions += ('\n先按response_focus组织答案，answer_context.known_fields是已知信息，不列入补充清单。'
        'necessary_gaps可能很多，只选阻碍当前判断的关键项，不复述整套表单；专业评估前提不可省略。'
        'evidence.questions是章节直接关联的问题；空列表表示补充边界，不能单靠它回答不相干的问题。'
        '回答“怎么奖励”就说明绑定原文支持的奖励时机与目标，不推论诱导、服从、动机或学习机理。'
        '概念题先给清楚的区分，不展开无关喂食、记录或用品方案。已解释的风险没有新变化不反复铺陈。')
    if source_rules:
        # These rules are static server code, not instructions from documents.
        # Put their scope at system priority once, outside the evidence payload.
        instructions += '\n本轮适用边界：\n' + '\n'.join(source_rules)
    request = dict(model_settings, model=ctx.selected_model.name,
                   messages=[{'role': 'system', 'content': system + '\n' + instructions},
                             {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}],
                   stream=True, stream_options={'include_usage': True})
    schema = SectionAnswer.model_json_schema()
    fields = schema['$defs']['AnswerSection']['properties']
    fields['text']['pattern'] = r'^[^\[\]]+$'
    fields['evidence_ids']['items'] = {'type': 'string', 'enum': list(evidence)} if evidence else {'type': 'string'}
    if not evidence:
        fields['evidence_ids']['maxItems'] = 0
    fields['question_ids']['items'] = {'type': 'integer', 'enum': list(range(1, len(questions)+1))}
    ctx.segment_schema = schema
    # SDK schema requires all declared properties, which these models already provide.
    from app.alibaba_models import supports_schema
    if ctx.selected_model.provider == 'alibaba' and supports_schema(ctx.selected_model.name):
        request['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': 'CareAnswerSections', 'strict': True, 'schema': schema}}
    else:
        request['response_format'] = {'type': 'json_object'}
        request['messages'][0]['content'] += ('\n输出正文对象，不输出JSON Schema或字段定义。格式：'
            '{"sections":[{"text":"完整正文","evidence_ids":["本轮证据编号"],"question_ids":[1]}]}')
    parser, emitted, sections = ClosedSections(), [], []
    usage = None
    finish = None
    invalid = None
    stream = await create(**request)
    try:
        async for chunk in stream:
            if chunk.usage:
                usage = chunk.usage
            for choice in chunk.choices:
                finish = choice.finish_reason or finish
                delta = choice.delta.content or ''
                if delta and (trace := current_execution.get()):
                    trace.mark('model_first_token', once=True)
                if invalid is not None:
                    continue
                try:
                    for section in parser.feed(delta):
                        if len(sections) >= 40:
                            raise HTTPException(502, '模型回答段落过多，本次未保存。')
                        bound = bind_section(section, evidence, questions, profile, ctx)
                        sections.append(section)
                        emitted.append(bound)
                        if sink := section_sink.get():
                            ctx.sections_emitted = len(emitted)
                            if trace := current_execution.get():
                                trace.mark('first_section', once=True)
                            await sink({**bound, 'index': len(emitted) - 1,
                                        'model_used': ctx.selected_model.name, 'complete': False})
                except (HTTPException, ValidationError) as error:
                    # Finish this one response solely to receive its final usage;
                    # never emit further paragraphs, repair, or issue a retry.
                    # Explicit user cancellation still closes the upstream now.
                    invalid = error
    finally:
        await stream.close()
    if trace := current_execution.get():
        trace.mark('generation_finished')
    if invalid is not None:
        if isinstance(invalid, HTTPException):
            raise invalid
        raise HTTPException(502, '模型段落结构未通过检查，本次未保存。') from invalid
    # Require syntactically complete JSON, every question, and an explicit clean stop.
    try:
        final = SectionAnswer.model_validate_json(parser.text)
    except ValidationError as error:
        raise HTTPException(502, '模型回答结构未通过检查，本次未保存。') from error
    if finish != 'stop' or not parser.ended or final.sections != sections:
        raise HTTPException(502, '模型输出未完整结束，本次回答未保存。')
    covered = {q for section in sections for q in section.question_ids}
    if covered != set(range(1, len(questions) + 1)):
        raise HTTPException(502, '模型未覆盖全部问题，本次回答未保存。')
    citations = []
    for section in sections:
        for ref in section.evidence_ids:
            item = evidence[ref.lower() if ref.lower() in evidence else ref]
            pair = (item['article_id'], item['heading'])
            if pair not in citations:
                citations.append(pair)
    answer = AgentAnswer(answer='\n\n'.join(part['text'] for part in emitted),
        citation_ids=list(dict.fromkeys(aid for aid, _ in citations)),
        citation_sections=[CitationSection(article_id=aid, heading=heading) for aid, heading in citations])
    combined = RunUsage()
    if initial_usage:
        combined.incr(initial_usage)
    combined.incr(RunUsage(requests=1, input_tokens=usage.prompt_tokens if usage else 0,
                          output_tokens=usage.completion_tokens if usage else 0))
    return SimpleNamespace(output=answer, usage=combined, all_messages=lambda: [])
