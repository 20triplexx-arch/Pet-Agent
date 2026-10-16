"""Behavioral regressions from the live source review, with no external traffic."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.answer_context import answer_context, repeated_known_question, response_focus
from app.answer_sections import check_text, bind_section, AnswerSection
from app.deep_chat import evidence_is_ready
from app.knowledge import multi_search, evidence_sections
from sqlmodel import Session

FIXTURES = json.loads((Path(__file__).parents[1] / 'evals/answer_quality_regressions.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', FIXTURES['cases'], ids=lambda c: c['id'])
def test_live_defect_and_supported_alternative(case):
    ctx = SimpleNamespace(effective_context={}, analysis={}, current_text='',
                          sent_evidence={case['article']: {'原文': case['good']}})
    with pytest.raises(HTTPException):
        check_text(case['bad'], None, ctx)
    check_text(case['good'], None, ctx)


@pytest.mark.parametrize('case', FIXTURES['captured_raw'], ids=lambda c: c['id'])
def test_actual_historical_raw_errors_are_not_deliverable(case):
    ctx = SimpleNamespace(effective_context={}, analysis={}, current_text='',
                          sent_evidence={case['article']: {'原文': '仅采用本节所述对象与步骤。'}})
    with pytest.raises(HTTPException):
        check_text(case['text'], None, ctx)


def test_known_fields_keep_dates_false_values_and_conflicting_reports():
    history = [{'id': 'u1', 'role': 'user', 'created_at': '2026-10-01', 'content': '兽医限制：不要自行换粮。'}]
    facts = answer_context({'age_months': 24, 'weight': 4.5, 'weight_date': '2026-10-01', 'neutered': False},
                           {}, history, '我家猫3岁。', {})
    assert facts['known_fields']['weight']['date'] == '2026-10-01'
    assert facts['known_fields']['neutered']['value'] is False
    assert facts['known_fields']['age_months']['value'] == 24
    assert facts['reported_restrictions_and_conflicts'][0]['message_id'] == 'u1'
    assert facts['reported_restrictions_and_conflicts'][1]['conflicts_with_profile']
    assert 'medical_history' not in facts['known_fields']  # Empty is not healthy.


def test_user_report_is_not_a_profile_write_or_an_assistant_fact():
    history = [{'role':'assistant', 'id':'a', 'created_at':'today', 'content':'我家猫9岁。'}]
    assert not answer_context(None, {}, history, '如果我家猫3岁该怎么养？', {})['known_fields']
    assert answer_context(None, {}, history, '我家猫3岁。', {})['known_fields']['age_months']['value'] == 36


def test_known_age_is_not_confused_with_an_invented_care_interval():
    ctx = SimpleNamespace(effective_context={}, analysis={}, current_text='', sent_evidence={})
    check_text('已知猫24个月，年龄无需再填。', {'age_months':24}, ctx)
    with pytest.raises(HTTPException, match='固定安排'):
        check_text('建议猫每24个月重新检查一次。', {'age_months':24}, ctx)


def test_actual_cb043_reask_is_detected_even_in_a_long_list():
    case = next(case for case in FIXTURES['context_cases'] if case['id'] == 'CB-043')
    assert repeated_known_question(case['bad'], case['known'])
    assert not repeated_known_question(case['good'], case['known'])


def test_recent_restriction_survives_history_compaction():
    history = [{'id':'old', 'role':'user', 'created_at':'2026-10-01',
                'content':'旧话题。兽医限制：不要自行换粮。无关话题。'}]
    context = {'values':{'professional_advice':'本次仍不能自行换粮'},
               'provenance':{'professional_advice':{'message_id':'current', 'date':'2026-10-16'}}}
    facts = answer_context({}, context, history, '猫抓沙发怎么处理？', {})
    restrictions = facts['reported_restrictions_and_conflicts']
    assert restrictions[0]['text'] == '兽医限制：不要自行换粮。'
    assert restrictions[0]['message_id'] == 'old'
    assert restrictions[1]['date'] == '2026-10-16'


@pytest.mark.parametrize('text', ['请补充年龄和食物标签。', '还缺年龄资料。', '它现在多大？'])
def test_known_age_not_reasked(text):
    assert repeated_known_question(text, {'age_months': {'value': 24}}) == 'age_months'


@pytest.mark.parametrize('text', ['年龄已知，请提供主粮标签。', '无需再填写年龄。',
                                '档案体重来自上月，请确认最新体重用于本次评估。', '请补充近期过敏史变化。'])
def test_genuine_gaps_and_updates_are_not_blocked(text):
    assert not repeated_known_question(text, {'age_months': {}, 'weight': {}, 'allergies': {}})


def test_wrong_chapter_cannot_support_scoring_definition():
    ctx = SimpleNamespace(effective_context={}, analysis={}, retrieved={}, current_text='')
    with pytest.raises(HTTPException, match='适用条件'):
        bind_section(AnswerSection(text='BCS评估脂肪储备。', evidence_ids=['e1'], question_ids=[1]),
                     {'e1': {'article_id':'nutrition-feeding', 'heading':'零食', 'text':'保持适合个体的食物。'}},
                     ['BCS是什么？'], None, ctx)


def test_passages_match_each_question_and_zero_overlap_is_not_ready(db):
    with Session(db) as session:
        questions = ['猫抓沙发怎么处理？', '猫航空箱如何适应？']
        articles = multi_search(session, 'cat', questions, personal=True)
    assert evidence_is_ready(articles, questions)
    for article in articles:
        assert len({s['heading'] for s in article['matched_sections']}) == len(article['matched_sections'])
        assert all(q in questions for linked in article['section_questions'].values() for q in linked)
    assert not evidence_is_ready([{'id':'cat-carrier', 'matched_questions':['怎么修卫星？'],
                                   'matched_sections':[{'heading':'适应', 'text':'自主接近'}]}], ['怎么修卫星？'])
    assert not evidence_sections({'keywords':['运输箱'], 'body':'## 练习\n自主接近运输箱。'}, '卫星轨道')


def test_followup_focus_does_not_expand_from_old_supplements():
    assert response_focus('练习时怎么奖励？', [{'role':'user'}], ['练习时怎么奖励'], 'standard')['style'] == 'followup'
    assert response_focus('练习时怎么奖励？', [{'role':'user'}], ['练习时怎么奖励'], 'detailed')['style'] == 'explain'


def test_source_question_mapping_is_checked_before_emitting():
    ctx = SimpleNamespace(retrieved={'cat-carrier': {'section_questions': {'练习': ['如何练习航空箱']}}})
    with pytest.raises(HTTPException, match='对应问题不匹配'):
        bind_section(AnswerSection(text='包装热量需要核对单位。', evidence_ids=['e1'], question_ids=[2]),
                     {'e1': {'article_id':'cat-carrier', 'heading':'练习', 'text':'自主接近运输箱。'}},
                     ['如何练习航空箱', '食品标签怎么看'], None, ctx)


@pytest.mark.parametrize('text,concept', [('猫的BCS体况与体重有什么区别？', True),
                                       ('狗的MCS肌肉与脂肪体况记录有什么区别？', True),
                                       ('我家猫吃多少克？', False)])
def test_one_request_uses_known_facts_and_only_relevant_business_data(client, headers, cat, monkeypatch, text, concept):
    from test_model_adapter import fake_provider
    seen = fake_provider(monkeypatch, '结合当前问题与已提供资料说明适用条件。', source='__first__')
    pet = cat
    if text.startswith('狗'):
        pet = client.post('/api/v1/pets', headers={**headers, 'Idempotency-Key':'quality-dog'},
                          json={'name':'测试犬', 'species':'dog', 'estimated_age_months':36}).json()
    response = client.post('/api/v1/chat', headers={**headers, 'Idempotency-Key':'quality-facts'},
                           json={'pet_id':pet['id'], 'text':text})
    assert response.status_code == 200, response.text
    assert len(seen) == 1
    payload = json.loads(seen[0]['messages'][-1]['content'])
    assert payload['answer_context']['known_fields']['age_months']['value'] is not None
    if concept:
        assert 'nutrition' not in payload['tool_results']
        assert 'recent_care' not in payload['tool_results']
    else:
        assert payload['answer_context']['necessary_gaps']
    assert 'section_questions' in payload['retrieved_data'][0]


def test_comparison_gate_keeps_free_quota_and_existing_budget():
    from evals.quality_compare import preflight
    cases = [{'turns':['question']} for _ in range(30)]
    budget = {'conservative_used_cny':6.828585, 'run_used_cny':1.053174}
    assert preflight(cases, 8600, budget)['reasons'] == ['insufficient_verified_free_tokens']
    assert preflight(cases, 1000000, budget)['allowed']
    assert not preflight(cases, 1000000, {**budget, 'run_used_cny':3})['allowed']
