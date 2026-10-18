"""Explicit facts and answer intent; user reports never update the pet profile."""
import re


PROFILE_FIELDS = ('age_months', 'weight', 'neutered', 'allergies', 'medical_history', 'vet_advice')


def answer_context(profile, context, history, text, tools):
    dates = {'weight': (profile or {}).get('weight_date'),
             'age_months': (profile or {}).get('birthday') or (profile or {}).get('age_estimated_on')}
    known = {key: {'value': profile[key], 'source': 'current_profile',
                   'date': dates.get(key)}
             for key in PROFILE_FIELDS if profile and profile.get(key) not in (None, '')}
    reports = []
    current = {'role': 'user', 'id': 'current', 'created_at': None, 'content': text}
    # Preserve exact user wording instead of extracting guessed health facts.
    for message in [*history, current]:
        if message['role'] == 'user' and re.search(r'过敏|病史|兽医|处方|限制|确诊', message['content']):
            restrictions = [part for part in re.split(r'(?<=[。！？\n])', message['content'])
                            if re.search(r'过敏|病史|兽医|处方|限制|确诊', part)]
            reports.append({'text': ''.join(restrictions), 'message_id': message['id'], 'date': message['created_at']})
    for field in ('professional_advice', 'observations', 'timeline'):
        value = context.get('values', {}).get(field)
        if value:
            reports.append({'field': field, 'value': value,
                            **context.get('provenance', {}).get(field, {}), 'source': 'supplemental_context'})
    # Only explicit first-person statements of stable fields are recognized.
    # Questions, hypotheses, another animal and assistant prose are not facts.
    def retain(field, value, message, clause):
        report = {'value': value, 'source': message.get('source', 'user_report'), 'message_id': message['id'],
                  'date': message['created_at'], 'text': clause.strip()}
        if field not in known:
            known[field] = report
        elif known[field]['value'] != value:
            if known[field]['source'] == 'current_profile':
                reports.append({'field': field, **report, 'conflicts_with_profile': True})
            else:
                reports.append({'field': field, **known[field], 'source': 'earlier_user_report'})
                known[field] = report

    supplements = [{'role': 'user', 'id': context.get('provenance', {}).get(field, {}).get('message_id', 'current'),
                    'created_at': context.get('provenance', {}).get(field, {}).get('date'),
                    'content': value, 'source': 'supplemental_context'}
                   for field, value in context.get('values', {}).items() if isinstance(value, str)]
    for message in [*history, *supplements, current]:
        if message['role'] != 'user':
            continue
        for clause in re.split(r'[。！？?；;\n]', message['content']):
            if re.search(r'如果|假如|是否|几岁|多大|另一|朋友|别人|吗|会不会|能不能|应该', clause):
                continue
            match = re.search(r'(?:我家(?:的)?(?:猫|狗|犬)|它|年龄)(?:现在|今年|是|为|已|大约|约|\s)*([0-9]+(?:\.[0-9]+)?)\s*(岁|个月)', clause)
            if match:
                value = float(match[1]) * (12 if match[2] == '岁' else 1)
                retain('age_months', value, message, clause)
            subject = r'(?:(?:我家(?:的)?(?:猫|狗|犬)|它)(?:现在|目前|今天|刚)?(?:体重|重|称重|称了)(?:是|为)?|体重(?:是|为)?)'
            weight = re.search(subject + r'\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|公斤|千克|斤)', clause, re.I)
            if weight and not re.search(r'目标|理想|减到|增到|应该|估计', clause):
                value = float(weight[1]) * (.5 if weight[2] == '斤' else 1)
                if 0 < value <= 150:
                    retain('weight', value, message, clause)
            neutered = re.search(r'(?:我家(?:的)?(?:猫|狗|犬)|它)[^，,]{0,12}?(未绝育|没有绝育|还没绝育|已经绝育|已绝育)', clause)
            if neutered:
                retain('neutered', neutered[1] in ('已经绝育', '已绝育'), message, clause)
    nutrition = tools.get('nutrition') or {}
    gaps = list(dict.fromkeys(nutrition.get('questions', [])))
    eligibility = [gap for gap in gaps if re.search(r'健康|异常|孕|哺|体况|肌肉|生命阶段', gap)]
    food = [gap for gap in gaps if re.search(r'主粮|零食|包装|热量', gap)]
    return {'known_fields': known, 'reported_restrictions_and_conflicts': reports,
            'reported_nutrition_fields': {key: value for key, value in nutrition.get('input_parameters', {}).items()
                                          if value not in (None, '', 'unknown', [])},
            'nutrition_status': nutrition.get('status'), 'necessary_gaps': gaps,
            'decision_gaps': {'eligibility': eligibility, 'food': food},
            'rule': '已知字段不重新索取；冲突核对时间和对象，不覆盖档案。体重更新须说明原记录日期与本次确认目的。空病史不等于健康。'}


def response_focus(text, history, questions, depth):
    followup = bool(history and len(text.strip()) <= 60 and len(questions) == 1
                    and re.match(r'那|它|这个|这样|这种|继续|还|不配合|不愿|抗拒|躲开|后退|练习时|每次|多久', text.strip()))
    if depth == 'detailed':
        return {'style': 'explain', 'plan': '先回答结论，再解释依据与取舍、必要条件、行动及观察方式；按问题组织，不套统一标题。'}
    if len(questions) == 1 and re.search(r'区别|区分|是什么|什么意思', text):
        return {'style': 'concept', 'plan': '先解释各概念的对象、差别与实际意义。不要自动延伸为喂食量计算、整套表单、用品选购或记录计划。'}
    if followup:
        return {'style': 'followup', 'plan': '只回答本次新增疑问。不重述上答步骤、档案、通用记录要求或免责声明；无需补资料时直接结束。'}
    return {'style': 'direct', 'plan': '先回答当前问题，再给决定行动的条件和具体步骤。覆盖并列任务，保留关键操作与停止条件；不以概括的“按情况调整”替代原文已有的做法。'}


def repeated_known_question(text, known):
    """Bounded guard for re-asking stable fields, not a semantic fact checker."""
    patterns = {'age_months': r'年龄|月龄|几岁|多大', 'neutered': r'绝育(?:情况|状态)?|是否绝育',
                'allergies': r'过敏史', 'medical_history': r'既往病史', 'vet_advice': r'已有兽医建议'}
    for clause in re.split(r'[。！？?；;\n]', text):
        if re.search(r'不必|不用|无需|无需再|已经|已知|已提供|已记录|沿用|档案中|档案已', clause):
            continue
        asking = re.search(r'(?:请|还需|需要|需|能否|可以).{0,8}(?:补充|提供|告诉|填写)|还缺|尚缺|未知|不清楚|几岁|多大', clause)
        if not asking:
            continue
        for field, pattern in patterns.items():
            if field in known and re.search(pattern, clause):
                if field != 'age_months' and re.search(r'新增|变化|近期|更新|冲突|核对', clause):
                    continue
                return field
    return None
