import pytest
from app.answer_quality import has_disallowed_health_claim, unsupported_advice, evidence_rules, factual_error
from types import SimpleNamespace


@pytest.mark.parametrize('text', ['建议每天90—110克干粮。', '每日总需能约135千卡。', '已绝育的猫每天需要30克。'])
def test_invented_nutrition_quantities_and_profile_are_blocked(text):
    ctx = SimpleNamespace(analysis={'tool_results': {'nutrition': {'status': 'needs_info'}}}, current_text='我家猫吃多少克？')
    assert factual_error(text, {'neutered': None}, ctx)


def test_label_unit_and_actual_calculated_numbers_are_distinct():
    ctx = SimpleNamespace(analysis={'tool_results': {'nutrition': {'status': 'needs_info'}}}, current_text='食量多少？')
    assert not factual_error('请提供包装上每100克的热量值，当前体重4.5公斤。', {'neutered': None}, ctx)
    ctx.analysis['tool_results']['nutrition'] = {'status': 'ready', 'calculation': {'daily_kcal_range': [180.2, 220.4]},
                                               'foods': [{'reference_grams_range': [45.1, 55.1]}]}
    assert not factual_error('本地起始范围180—220千卡，对应45—55克。', {'neutered': True}, ctx)
    assert factual_error('建议每天300克。', {'neutered': True}, ctx)


def test_unknown_neutering_is_not_invented_but_current_report_is_used():
    ctx = SimpleNamespace(analysis={}, current_text='猫如何选食物？')
    assert factual_error('根据档案，它已绝育。', {'neutered': None}, ctx)
    assert not factual_error('如果已绝育，需要核对适用条件。', {'neutered': None}, ctx)
    ctx.current_text = '它刚做完绝育手术后如何照护？'
    assert not factual_error('按你刚提供的情况，它已绝育，档案尚未更新。', {'neutered': None}, ctx)


@pytest.mark.parametrize('text', [
    '猫一定是肾病。', '现在可以确诊为感染。', '不能判断，但它一定是肾病。',
    '不能不诊断为肾病。', '建议服用阿莫西林20mg。', '请给药2毫升。',
])
def test_actual_diagnosis_or_new_dose_remains_blocked(text):
    assert has_disallowed_health_claim(text)


@pytest.mark.parametrize('text', [
    '乱尿行为不一定是报复，少量排尿也不能排除疾病可能。',
    '不能据此诊断为肾病。', '目前无法确诊为感染。', '不一定是肾病。',
    '并不能肯定是感染。', '不能直接判断一定是糖尿病。',
    '整理既往确诊疾病、正在使用的药物及原有剂量。',
    '不可自行诊断为肌肉疾病。',
])
def test_negation_and_unrelated_clauses_do_not_become_diagnosis(text):
    assert not has_disallowed_health_claim(text)


@pytest.mark.parametrize('text,ids', [
    ('避免在刚睡醒或饭后立即护理。', ['cat-low-stress-care']),
    ('不要饭后护理。', ['cat-grooming']),
    ('仅在放松时给予零食奖励。', ['cat-low-stress-care']),
    ('使用猫薄荷引导它抓板。', ['cat-scratching']),
    ('使用安全喷雾保护家具。', ['supply-scratch']),
    ('零食热量不能超过总量10%。', ['nutrition-feeding']),
    ('零食不超过总热量10%（仅限健康成年猫）。', ['nutrition-feeding']),
    ('背部触感、起身能力等肌肉指标。', ['nutrition-muscle']),
    ('起身费力应视为肌肉损失信号。', ['nutrition-muscle']),
    ('不要用喷剂而要用猫薄荷。', ['cat-scratching']),
    ('零食10%。先记录运动。此限制仅适用健康成年猫狗。', ['nutrition-feeding']),
])
def test_observed_source_contradictions_are_not_accepted(text, ids):
    assert unsupported_advice(text, ids)


@pytest.mark.parametrize('text,ids', [
    ('不把刚睡醒或饭后作为通用护理时机，按反应调整。', ['cat-grooming']),
    ('不要使用喷剂，先提供稳定抓板。', ['cat-scratching']),
    ('仅对健康、体况合适的成年猫狗，零食热量边界为10%。', ['nutrition-feeding']),
    ('不要把10%作为所有个体的通用规则。', ['nutrition-energy']),
    ('只在放松时练习，害怕时停止，不笼统限制奖励。', ['cat-low-stress-care']),
    ('记录起身费力等观察事实，不能把它作为肌肉指标。', ['nutrition-muscle']),
    ('请避免使用资料未支持的喷剂或猫薄荷产品。', ['cat-scratching']),
    ('零食热量不超过10%。此限制仅适用于健康、体况合适的成年猫狗。', ['nutrition-feeding']),
    ('零食不超过总热量10%。此前提仅适用于健康、体况合适的成年猫狗。', ['nutrition-feeding']),
    ('零食不超过10%。注意：该比例通常适用于健康、体况合适的成年猫狗。', ['nutrition-feeding']),
    ('零食不超过10%。需注意，此边界仅适用于健康、体况合适的成年猫狗。', ['nutrition-feeding']),
])
def test_supported_conditions_and_refusals_still_pass(text, ids):
    assert not unsupported_advice(text, ids)


def test_rules_are_selected_from_actual_evidence():
    assert evidence_rules(['cat-grooming']) and not evidence_rules(['food-storage'])


def test_qualitative_guidance_cannot_become_invented_schedule():
    ctx = SimpleNamespace(analysis={}, current_text='自驾出行需要准备什么？',
                          sent_evidence={'travel': {'途中': '安排符合个体需要的休息。'}})
    assert factual_error('每2-3小时停车休息一次。', None, ctx)
    assert not factual_error('途中按个体需要安排休息。', None, ctx)
    assert not factual_error('档案中24个月大、体重4.5kg的猫。', {'age_months': 24}, ctx)


def test_incomplete_nutrition_cannot_promise_precise_amount_after_few_answers():
    ctx = SimpleNamespace(analysis={'tool_results': {'nutrition': {'status': 'needs_info'}}}, current_text='吃多少？')
    assert factual_error('获取这些信息后，可依据标签进行准确的克数换算。', {'neutered': None}, ctx)


def test_bcs_definition_must_not_include_muscle():
    ctx = SimpleNamespace(analysis={}, current_text='BCS和体重有何区别？')
    assert factual_error('BCS（体况评分）则专门评估脂肪分布与肌肉状况。', None, ctx)
    assert not factual_error('BCS关注脂肪，MCS评估肌肉，两个记录不能替代。', None, ctx)
