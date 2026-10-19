"""Completion, focus and claim-vs-field regressions from the reviewed outputs."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlmodel import Session
from app.answer_context import answer_context
from app.answer_sections import check_text
from app.knowledge import multi_search, model_sections


def context(evidence):
    return SimpleNamespace(effective_context={}, analysis={}, current_text='', sent_evidence=evidence)


@pytest.mark.parametrize('text', [
    '还缺BCS体况评分记录和食物标签。', '请提供已有的肌肉状况评分记录。',
    'BCS记录尚未提供，需要核对已有结果；不能据此确定克数。',
    'BCS是未知项，请提供已有记录。',
])
def test_scoring_field_requests_are_not_definitions(text):
    check_text(text, None, context({'nutrition-feeding': {'缺口': '需核对体况与食物标签。'}}))


@pytest.mark.parametrize('text', [
    '还缺BCS记录；BCS评估脂肪储备。', '请提供肌肉状况评分，MCS用于评估肌肉。',
    '评估脂肪储备的评分就是BCS。', 'BCS不是整体健康评分，只关注脂肪。',
])
def test_definition_still_requires_actual_scoring_chapter(text):
    with pytest.raises(HTTPException):
        check_text(text, None, context({'nutrition-feeding': {'缺口': '需核对体况与食物标签。'}}))


@pytest.mark.parametrize('article,bad,good,source', [
    ('cat-body-language', '咬手时保持静止不动。', '发现紧张或回避时停止接触，给猫空间。',
     '发现紧张或回避时停止接触，给猫空间。'),
    ('pet-travel', '自驾必须携带健康证明。', '整理健康文件，核实实际运营方是否要求健康证明。',
     '整理健康文件，向实际运营方及目的地核对证件要求。'),
])
def test_unprovided_actions_and_mandatory_documents(article, bad, good, source):
    ctx = context({article: {'说明': source}})
    with pytest.raises(HTTPException):
        check_text(bad, None, ctx)
    check_text(good, None, ctx)


@pytest.mark.parametrize('species,question,article,required,excluded', [
    ('cat', '猫梳毛和剪指甲时很紧张，怎么逐步适应？', 'cat-grooming', '血管区域', 'cat-home'),
    ('cat', '养猫前应该评估哪些时间和空间条件？', 'cat-prepare', '工作日、周末和出差', 'care-review-week'),
    ('dog', '狗独处时在家叫喊和拆家，如何先记录再安排练习？', 'dog-alone', '舒适的难度', 'visit-preparation'),
    ('dog', '养狗前怎样评估时间与家庭空间？', 'dog-prepare', '替代照护人', 'nutrition-muscle'),
    ('cat', '猫每天的互动与探索怎样安排？', 'cat-play', '计入零食', 'cat-home'),
    ('dog', '夏天高温时遛狗如何安排，怎样避免车内滞留？', 'heat-safety', '受热路面', 'pet-travel'),
    ('cat', '猫粮开封后怎样储存，湿粮和食盆如何清洁？', 'food-storage', '需要冷藏时', 'cat-food'),
    ('dog', '狗日常运动和嗅闻互动怎么安排？', 'dog-play', '恢复', 'supply-toys'),
    ('dog', '狗粮喂食和体重记录有哪些原则？', 'dog-food', '体重', 'visit-preparation'),
    ('dog', '狗的笼箱适应，怎样建立安全休息空间？', 'dog-crate', '自然站立、转身', 'dog-home'),
    ('cat', '猫砂盆日常清洁和排泄观察要注意什么？', 'cat-clean', '排不出尿', 'supply-litter'),
    ('dog', '狗刷牙怎么练习？', 'dog-dental', '嘴边轻触', 'supply-dental'),
])
def test_prefetch_keeps_actions_and_removes_unasked_topics(db, species, question, article, required, excluded):
    with Session(db) as session:
        found = multi_search(session, species, [question], personal=True)
    assert excluded not in {item['id'] for item in found}
    item = next(item for item in found if item['id'] == article)
    assert required in '\n'.join(p['text'] for p in model_sections(item))
    assert any(question in linked for linked in item['section_questions'].values())


def test_parallel_questions_still_keep_their_own_actions(db):
    questions = ['猫剪指甲怎么适应？', '航空箱怎么练习？', '猫粮如何储存？', '多猫怎样相处？']
    with Session(db) as session:
        found = multi_search(session, 'cat', questions, personal=True)
    assert {'cat-grooming', 'cat-carrier', 'food-storage', 'cat-multi'} <= {a['id'] for a in found}
    assert all(any(q in linked for a in found for linked in a['section_questions'].values()) for q in questions)


def test_handling_distress_keeps_complementary_retreat_steps(db):
    with Session(db) as session:
        found = multi_search(session, 'cat', ['猫梳毛和剪指甲时很紧张，怎么逐步适应？'], personal=True)
    item = next(a for a in found if a['id'] == 'cat-low-stress-care')
    text = '\n'.join(p['text'] for p in model_sections(item))
    assert '分开练习' in text and '安静不动不一定代表舒服' in text


def test_practice_question_does_not_expand_into_dental_product_comparison(db):
    with Session(db) as session:
        found = multi_search(session, 'dog', ['狗刷牙怎么练习？'], personal=True)
    dental = next(a for a in found if a['id'] == 'dog-dental')
    assert not any('辅助用品' in p['heading'] or '比较口腔用品' in p['heading'] for p in model_sections(dental))


def test_food_labels_do_not_hide_eligibility_gaps():
    questions = ['请填写体况评分。', '请确认肌肉状况。', '请确认健康状态。', '请填写主粮及包装热量。']
    facts = answer_context({'weight':4.5}, {}, [], '吃多少克？', {'nutrition': {'status':'needs_info','questions':questions}})
    assert facts['decision_gaps']['eligibility'] == questions[:3]
    assert facts['decision_gaps']['food'] == questions[3:]
    assert facts['known_fields']['weight']['value'] == 4.5


@pytest.mark.parametrize('question', ['不愿进去时怎么办？', '抗拒时怎么办？', '练习时怎么奖励？'])
def test_obstacle_followup_focuses_on_new_information(question):
    from app.answer_context import response_focus
    assert response_focus(question, [{'role':'user','content':'此前的问题'}], [question], 'standard')['style'] == 'followup'


def test_reported_facts_keep_provenance_and_conflicts_without_profile_updates():
    profile = {'weight': 4.5, 'weight_date': '2026-09-01', 'neutered': False}
    history = [{'role':'user','id':'u1','created_at':'2026-10-01','content':'我家猫体重4.8公斤。它已经绝育。'}]
    facts = answer_context(profile, {}, history, '兽医限制暂时不能换粮。', {})
    assert facts['known_fields']['weight']['value'] == 4.5
    conflicts = facts['reported_restrictions_and_conflicts']
    assert any(r.get('field') == 'weight' and r['value'] == 4.8 and r['date'] == '2026-10-01' for r in conflicts)
    assert any(r.get('field') == 'neutered' and r['conflicts_with_profile'] for r in conflicts)
    assert any(r.get('message_id') == 'current' and '不能换粮' in r.get('text', '') for r in conflicts)
    assert profile == {'weight': 4.5, 'weight_date': '2026-09-01', 'neutered': False}


@pytest.mark.parametrize('text', ['如果我家猫体重8公斤。', '朋友的猫体重8公斤。', '它体重8公斤吗？', '它吃了8公斤粮。', '它目标体重8公斤。'])
def test_hypotheses_other_pets_and_food_are_not_weight_facts(text):
    assert 'weight' not in answer_context(None, {}, [], text, {})['known_fields']


def test_current_supplement_is_a_dated_user_report():
    facts = answer_context(None, {'values': {'observations':'我家猫体重8斤。它未绝育。'},
        'provenance': {'observations': {'message_id':'u2','date':'2026-10-02'}}}, [], '吃多少？', {})
    assert facts['known_fields']['weight']['value'] == 4
    assert facts['known_fields']['weight']['source'] == 'supplemental_context'
    assert facts['known_fields']['weight']['date'] == '2026-10-02'
    assert facts['known_fields']['neutered']['value'] is False


def test_preflight_reserves_room_for_the_whole_batch_and_a_request():
    from evals.quality_compare import preflight
    cases = [{'turns': ['question']}] * 30
    pricing = {'tiers': [{'max_input_tokens':262144,'input_per_million':1.2,'output_per_million':7.2}]}
    result = preflight(cases, 1000000, {'run_used_cny':2.9,'conservative_used_cny':9.1}, variants=3, pricing=pricing)
    assert 'insufficient_existing_budget_for_batch' in result['reasons']
    assert result['forecast_cny'] > .1


def test_isolation_is_checked_before_any_database_initialization(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    from evals.runner import setup_database
    import scripts.init_db as init
    monkeypatch.setattr(init, 'initialize', lambda **kwargs: pytest.fail('Must refuse before initializing the cached database'))
    with pytest.raises(RuntimeError, match='isolation'):
        setup_database(tmp_path)


def test_worker_refuses_to_start_a_new_spending_ledger(tmp_path, monkeypatch):
    from evals.streaming_compare import worker
    monkeypatch.setenv('CHONGBAN_EVAL_STATE_DIR', str(tmp_path))
    with pytest.raises(ValueError, match='existing shared evaluation ledger'):
        worker(SimpleNamespace())


def test_reported_neuter_state_survives_a_followup_without_silently_overriding_conflict():
    history = [{'role':'user','id':'u1','created_at':'2026-10-01','content':'它已经绝育。'}]
    profile = {'neutered': None}
    ctx = context({})
    ctx.analysis = {'answer_context': answer_context(profile, {}, history, '还需要什么资料？', {})}
    check_text('你此前报告已绝育，无需再次填写。', profile, ctx)
    profile = {'neutered': False}
    ctx.analysis = {'answer_context': answer_context(profile, {}, history, '还需要什么资料？', {})}
    check_text('你此前报告已绝育，与档案存在冲突，需要核对记录日期。', profile, ctx)
    with pytest.raises(HTTPException):
        check_text('这只已绝育的猫可以继续。', profile, ctx)


@pytest.mark.parametrize('bad,good', [
    ('因肌肉流失导致实际体况不佳。', '不是因肌肉流失导致实际体况不佳。'),
    ('肌肉减少造成当前体况下降。', '肌肉减少不一定造成当前体况下降。'),
    ('不是不能说因肌肉流失导致实际体况不佳。', '肌肉和脂肪分别记录，肌肉损失不等于脂肪减少。'),
])
def test_bcs_causal_paraphrases_and_negations(bad, good):
    ctx = context({'nutrition-muscle': {'区别':'体况评分关注脂肪，肌肉状况关注肌肉减少；两者不能互相替代。'}})
    ctx.current_text = 'BCS体况与体重有什么区别？'
    with pytest.raises(HTTPException):
        check_text(bad, None, ctx)
    check_text(good, None, ctx)
    with pytest.raises(HTTPException):
        check_text(good + bad, None, ctx)
