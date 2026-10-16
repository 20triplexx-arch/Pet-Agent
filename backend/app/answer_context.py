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
    # Preserve exact user wording instead of extracting guessed health facts.
    for message in history:
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
    for message in [*history, {'role': 'user', 'id': 'current', 'created_at': None, 'content': text}]:
        if message['role'] != 'user':
            continue
        for clause in re.split(r'[。！？?；;\n]', message['content']):
            if re.search(r'如果|假如|是否|几岁|多大|另一|朋友|别人', clause):
                continue
            match = re.search(r'(?:我家(?:的)?(?:猫|狗|犬)|它|年龄)(?:现在|今年|是|为|已|大约|约|\s)*([0-9]+(?:\.[0-9]+)?)\s*(岁|个月)', clause)
            if match:
                value = float(match[1]) * (12 if match[2] == '岁' else 1)
                report = {'value': value, 'source': 'user_report', 'message_id': message['id'],
                          'date': message['created_at'], 'text': clause.strip()}
                if 'age_months' not in known:
                    known['age_months'] = report
                elif known['age_months']['value'] != value:
                    if known['age_months']['source'] == 'current_profile':
                        reports.append({'field': 'age_months', **report, 'conflicts_with_profile': True})
                    else:
                        reports.append({'field': 'age_months', **known['age_months'], 'source': 'earlier_user_report'})
                        known['age_months'] = report
    nutrition = tools.get('nutrition') or {}
    gaps = list(dict.fromkeys(nutrition.get('questions', [])))
    return {'known_fields': known, 'reported_restrictions_and_conflicts': reports,
            'reported_nutrition_fields': {key: value for key, value in nutrition.get('input_parameters', {}).items()
                                          if value not in (None, '', 'unknown', [])},
            'nutrition_status': nutrition.get('status'), 'necessary_gaps': gaps,
            'rule': '已知字段不重新索取；冲突核对时间和对象，不覆盖档案。体重更新须说明原记录日期与本次确认目的。空病史不等于健康。'}


def response_focus(text, history, questions, depth):
    followup = bool(history and len(text.strip()) <= 60 and len(questions) == 1
                    and re.match(r'那|它|这个|这样|这种|继续|还|不配合|抗拒|练习时|每次|多久', text.strip()))
    if depth == 'detailed':
        return {'style': 'explain', 'plan': '先回答结论，再解释依据与取舍、必要条件、行动及观察方式；按问题组织，不套统一标题。'}
    if len(questions) == 1 and re.search(r'区别|区分|是什么|什么意思', text):
        return {'style': 'concept', 'plan': '通常1—2段，先解释概念差别与实际意义。不要自动延伸为喂食量计算、整套表单、用品选购或记录计划。'}
    if followup:
        return {'style': 'followup', 'plan': '只回答本次新增疑问，通常1—2个自然段。不重述上答步骤、档案、通用记录要求或免责声明；无需补资料时直接结束。'}
    return {'style': 'direct', 'plan': '首段回答，后文只保留决定行动的依据、条件和步骤。通常2—3段；一句能讲清的概念无需展开成照护方案。'}


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
