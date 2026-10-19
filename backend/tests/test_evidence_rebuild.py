"""Evidence integrity, task isolation and actual observed proposition regressions."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlmodel import Session
from app.evidence_index import build_index, chunks_for, digest
from app.answer_context import current_focus, relevant_history, answer_context
from app.answer_sections import check_text
from app.knowledge import multi_search, model_sections
from app.deep_chat import questions_for

ROOT=Path(__file__).resolve().parents[1]/'data'


def test_generation_tasks_use_the_same_request_ids_as_returned_sections():
    from app.answer_sections import remap_task_snapshot
    snapshot={'questions':[{'id':1,'evidence_ids':['cat:stable','custom#步骤'],'missing_evidence':False},
                           {'id':2,'evidence_ids':['cat:absent'],'missing_evidence':False}]}
    evidence={'e1':{'chunk_id':'cat:stable','article_id':'cat','heading':'前提'},
              'e2':{'chunk_id':None,'article_id':'custom','heading':'步骤'}}
    model=remap_task_snapshot(snapshot,evidence)
    assert model['questions'][0]['evidence_ids']==['e1','e2']
    assert model['questions'][1]['evidence_ids']==[] and model['questions'][1]['missing_evidence']
    assert snapshot['questions'][0]['evidence_ids']==['cat:stable','custom#步骤']


@pytest.mark.parametrize('text,invalid',[
    ('避免刚吃完饭就上手护理。',True),
    ('不建议在饭后梳毛。',True),
    ('不必避免刚吃完饭时护理，先看参与意愿。',False),
    ('不能说不要在饭后护理。',False),
    ('不把刚吃完饭当作通用禁忌。',False),
    ('不是不能避免刚吃完饭就护理。',True),
])
def test_care_time_prohibitions_keep_their_own_negation(text,invalid):
    from app.answer_quality import unsupported_advice
    assert bool(unsupported_advice(text,{'cat-grooming':{'时机':'按当前参与意愿，回避或疼痛时停止。'}}))==invalid


@pytest.mark.parametrize('text',[
    '还需要体况评分（含评估日期和填写者）、肌肉状况、活动水平。',
    '请记录BCS评估时间、评估人和肌肉状况；这不是同一个评分。',
])
def test_scoring_record_fields_are_not_muscle_definitions(text):
    from app.answer_quality import factual_error, unsupported_advice
    assert factual_error(text,None,SimpleNamespace(analysis={},current_text='',sent_evidence={})) is None
    assert unsupported_advice(text,{}) is None


def test_mixed_species_carriers_retrieve_both_scopes(db):
    query='运输前犬箱能站起来但没法转身，另一只猫用可拆顶箱。犬的空间限制与猫的搬运方式怎样分别核对？'
    with Session(db) as session:
        found=multi_search(session,'cat',[query],personal=True)
    chunks=[c for a in found for c in model_sections(a)]
    assert any('dog' in c.get('species',[]) and '转身' in c['text'] for c in chunks)
    assert any('cat' in c.get('species',[]) and '底部' in c['text'] for c in chunks)


def test_product_mentions_do_not_create_animal_subjects():
    from app.question_scope import explicit_species
    assert explicit_species('我家猫吃了给狗准备的狗粮，猫的BCS怎样理解？')=={'cat'}
    assert explicit_species('犬箱与猫的搬运方式分别核对')=={'cat','dog'}


def test_dental_adaptation_does_not_create_an_arrival_task(db):
    text='狗刷牙抗拒同时口气变化，哪些情况先做专业检查？请同时讲渐进适应和停止条件，不要给自行刮牙的办法。'
    questions=questions_for(text)
    assert len(questions)==2
    assert all('新宠' not in q for q in questions)
    assert '口腔护理' in questions[1] and '停止条件' in questions[1]
    from app.deep_chat import evidence_is_ready
    with Session(db) as session:
        found=multi_search(session,'dog',questions,personal=True)
    assert evidence_is_ready(found,questions)
    assert all(any(q in links for a in found for links in a['section_questions'].values()) for q in questions)


@pytest.mark.parametrize('text',[
    '运输资料没有一份全国统一的固定清单。',
    '自驾运输没有一张全国统一的文件清单。',
    '国内不存在通用的证件要求。',
    '全国尚无统一文件规定。',
    '不是不能说全国没有统一清单。',
    '不能说全国没有统一清单，但是全国不存在通用清单。',
])
def test_unverified_nationwide_absence_paraphrases_are_rejected(text):
    from app.answer_quality import unsupported_advice
    ctx=SimpleNamespace(analysis={},current_text='',sent_evidence={'pet-travel':{'证件':'按实际运营方和目的地核实。'}})
    assert unsupported_advice(text,ctx.sent_evidence)=='资料不足以断言全国不存在统一文件或证件规定'


@pytest.mark.parametrize('text',[
    '不能说全国没有统一清单。',
    '现有资料不足以证明全国不存在统一规定。',
    '资料未说明要求，不能据此断言全国没有统一清单。',
    '本次资料没有列出全国统一清单。',
    '国内是否不存在统一清单仍待核实。',
    '并非全国都没有统一的规定。',
])
def test_denials_and_document_scope_are_accepted(text):
    from app.answer_quality import unsupported_advice
    ctx=SimpleNamespace(analysis={},current_text='',sent_evidence={'pet-travel':{'证件':'按实际运营方和目的地核实。'}})
    assert unsupported_advice(text,ctx.sent_evidence) is None


@pytest.mark.parametrize('text,invalid',[
    ('可以每天安排一次可退出的互动。',True),
    ('无需每天安排一次，要按参与意愿调整。',False),
    ('猫每天的互动按愿意参与的程度调整，不规定次数。',False),
])
def test_play_frequency_is_distinct_from_daily_topic(text,invalid):
    from app.answer_quality import unsupported_advice
    reason=unsupported_advice(text,{'cat-play':{'互动':'允许观察与退开，兴趣下降或紧张时结束。'}})
    assert bool(reason)==invalid


@pytest.mark.parametrize('text,invalid',[
    ('每天可以安排一次或多次可退出的互动。',True),
    ('每日建议进行两次互动。',True),
    ('不是不能每天安排一次互动。',True),
    ('不等于可以每天安排一次互动。',False),
    ('不要求每天安排一次互动。',False),
    ('无需每天安排一次，但每日可以互动两次。',True),
])
def test_frequency_modals_and_negation_are_scoped(text,invalid):
    from app.answer_quality import unsupported_advice
    assert bool(unsupported_advice(text,{'cat-play':{'互动':'按参与意愿推进，不设统一次数。'}}))==invalid


def test_frequency_evidence_must_be_affirmative_and_match_bounds():
    from app.answer_quality import unsupported_advice
    claim='每日可以安排一次互动。'
    assert unsupported_advice(claim,{'cat-play':{'互动':'每天安排1次互动。'}}) is None
    assert unsupported_advice(claim,{'cat-play':{'互动':'不要每天安排一次互动。'}})
    assert unsupported_advice(claim,{'cat-play':{'互动':'每天最多安排一次互动。'}})


@pytest.mark.parametrize('text,invalid',[
    ('即使补上标签，也不等于能直接算出这只猫的精确喂食量。',False),
    ('这些资料不能保证能够给出这只猫的精确喂食量。',False),
    ('不能直接算出这只猫的精确喂食量。',False),
    ('补上标签就能够算出这只猫的精确喂食量。',True),
    ('不是不能算出这只猫的精确喂食量。',True),
    ('不能算出狗的食量但能算出这只猫的精确喂食量。',True),
    ('不能计算旧方案却能算出这只猫的精确喂食量。',True),
    ('无法仅凭这些信息给出这只猫的精确喂食量。',False),
    ('不能保证旧方案却能给出精确喂食量。',True),
])
def test_precision_denial_scopes_the_result_verb(text,invalid):
    from app.answer_quality import factual_error
    ctx=SimpleNamespace(analysis={'tool_results':{'nutrition':{'status':'missing'}}},current_text='',sent_evidence={})
    assert bool(factual_error(text,None,ctx))==invalid


def test_ripped_food_bag_retrieves_storage_stop_condition(db):
    query='猫粮袋破了但没有异味，怎样决定是否继续喂和保留哪些信息？'
    with Session(db) as session:
        found=multi_search(session,'cat',[query],personal=True)
    storage=[s['text'] for a in found if a['id']=='food-storage' for s in model_sections(a)]
    assert any('包装破损' in s for s in storage)
    assert any('气味' in s or '闻起来' in s for s in storage)


@pytest.mark.parametrize('text',[
    'BCS（体况评分）是看脂肪储备的评分。',
    '体况评分(BCS)评估脂肪储备。',
    'MCS（肌肉状况评分）是用来评估肌肉的。',
])
def test_parenthesized_score_alias_needs_a_real_definition(text):
    from app.answer_quality import unsupported_advice
    evidence={'nutrition-cat-bcs':{'记录':'记录评分日期与体重；旧评分不能代替今天的状态。'}}
    assert unsupported_advice(text,evidence)=='评分定义未绑定实际提供的评分章节'


def test_body_condition_concept_retrieves_its_actual_definition(db):
    from app.answer_quality import unsupported_advice
    with Session(db) as session:
        found=multi_search(session,'cat',['猫BCS体况和体重有什么区别与实际意义？'],personal=True)
    evidence={a['id']:{c['heading']:c['text'] for c in model_sections(a)} for a in found}
    assert any('脂肪' in text for text in evidence.get('nutrition-cat-bcs',{}).values())
    assert unsupported_advice('BCS（体况评分）是看脂肪储备的评分。',evidence) is None


@pytest.mark.parametrize('text,invalid',[
    ('后腿躲开本身不等于确诊疼痛或皮肤病。',False),
    ('后腿躲开就可以确诊皮肤病。',True),
    ('回避并不意味着一定是皮肤病。',False),
    ('不能因此确诊皮肤病。',False),
    ('不是不能直接确诊皮肤病。',True),
    ('不能不说一定是肾病。',True),
    ('不是不等于确诊皮肤病。',True),
    ('不等于确诊皮肤病，但它肯定是感染。',True),
])
def test_diagnosis_negation_qualifies_the_actual_verb(text,invalid):
    from app.answer_quality import has_disallowed_health_claim
    assert has_disallowed_health_claim(text)==invalid


def corpus():
    return [a for path in sorted(ROOT.glob('knowledge*.json')) for a in json.loads(path.read_text(encoding='utf-8'))]


def test_all_classified_and_build_is_reproducible():
    articles=corpus()
    annotations=json.loads((ROOT/'evidence/annotations.json').read_text(encoding='utf-8'))
    index=json.loads((ROOT/'evidence/index.json').read_text(encoding='utf-8'))
    assert len(articles)==95 and all(a['content_kind'] in {'care','breed','food','supplies'} for a in articles)
    assert len(annotations['topics'])==11
    assert build_index(articles,annotations,index)==index
    assert len({c['chunk_id'] for c in index['chunks']})==len(index['chunks'])
    for chunk in index['chunks']:
        article=next(a for a in articles if a['id']==chunk['article_id'])
        assert chunk['text'] in article['body']
        assert chunk['text_sha256']==digest(chunk['text'])
        assert chunk['review_status']=='editorial_summary_unreviewed'
        assert chunk['source_ids']


@pytest.mark.parametrize('fault',['missing_source','missing_section','dangling_dependency','cycle','species'])
def test_invalid_annotation_refuses_build(fault):
    articles=corpus()
    meta=json.loads((ROOT/'evidence/annotations.json').read_text(encoding='utf-8'))
    article=meta['articles']['cat-carrier']
    heading=next(iter(article['sections']))
    spec=article['sections'][heading]
    if fault=='missing_source': spec['source_ids']=['invented']
    elif fault=='missing_section': del article['sections'][heading]
    elif fault=='dangling_dependency': spec['depends_on']=['invented']
    elif fault=='cycle': spec['depends_on']=[spec['key']]
    else: spec['species']=['dog']
    with pytest.raises(ValueError): build_index(articles,meta)


def test_stale_database_body_is_never_bound_to_old_index():
    article=next(a for a in corpus() if a['id']=='cat-carrier')
    with pytest.raises(ValueError,match='stale'):
        chunks_for({**article,'body':article['body']+'\nChanged'})


def test_changed_source_locator_requires_new_claim_review():
    meta=json.loads((ROOT/'evidence/annotations.json').read_text(encoding='utf-8'))
    spec=next(iter(meta['articles']['cat-carrier']['sections'].values()))
    meta['sources'][spec['source_ids'][0]]['locator']+=' changed'
    with pytest.raises(ValueError,match='Source changed since claim review'):
        build_index(corpus(),meta)


def test_partial_claim_coverage_cannot_certify_a_whole_paragraph():
    meta=json.loads((ROOT/'evidence/annotations.json').read_text(encoding='utf-8'))
    spec=next(iter(meta['articles']['cat-carrier']['sections'].values()))
    spec['claim_annotations'][0]['text']=spec['claim_annotations'][0]['text'][:8]
    with pytest.raises(ValueError,match='Incomplete reviewed claim coverage'):
        build_index(corpus(),meta)


def test_breed_selected_citation_uses_actual_care_source():
    from app.knowledge import grounded_sections
    from app.evidence_index import public_citation_source
    article=next(a for a in corpus() if a['id']=='breed-dog-shiba')
    article['matched_sections']=grounded_sections(article,'柴犬梳毛护理怎样进行？')
    assert article['matched_sections'] and all(p.get('chunk_id') for p in article['matched_sections'])
    headings=['被毛与日常检查']
    card=public_citation_source(article,headings)
    assert card['url']==card['references'][0]['url']
    assert all('原文定位：' in r['supports'] for r in card['references'])
    assert not any('winter' in r['url'] for r in card['references'])


def test_review_overlay_refuses_changed_body():
    from scripts.apply_section_reviews import apply
    articles=corpus()
    meta=json.loads((ROOT/'evidence/annotations.json').read_text(encoding='utf-8'))
    reviewed=json.loads((ROOT/'evidence/section_reviews.json').read_text(encoding='utf-8'))
    pages=json.loads((ROOT/'evidence/source_reviews.json').read_text(encoding='utf-8'))
    articles[0]['body']+='\nUnreviewed material'
    with pytest.raises(ValueError,match='Body changed since editorial review'):
        apply(meta,articles,reviewed,pages)


def test_chunk_revision_and_identity_survive_reordering():
    articles=corpus()
    meta=json.loads((ROOT/'evidence/annotations.json').read_text(encoding='utf-8'))
    old=build_index(articles,meta)
    assert build_index(list(reversed(articles)),meta,old)==old
    updated=copy.deepcopy(articles)
    item=next(a for a in updated if a['id']=='cat-carrier')
    item['body']=item['body'].replace('猫可能因装箱','这只猫可能因装箱',1)
    # Editing a reviewed paragraph does not silently renew its support review.
    reviewed=next(iter(meta['articles']['cat-carrier']['sections'].values()))
    reviewed['claim_review_status']='pending_granular_review'
    rebuilt=build_index(updated,meta,old)
    assert {c['chunk_id'] for c in old['chunks']}=={c['chunk_id'] for c in rebuilt['chunks']}
    prior={c['chunk_id']:c for c in old['chunks']}
    changed=[c for c in rebuilt['chunks'] if c['text_sha256']!=prior[c['chunk_id']]['text_sha256']]
    assert len(changed)==1 and changed[0]['revision']==prior[changed[0]['chunk_id']]['revision']+1


@pytest.mark.parametrize('switch',['现在想问','现在想了解','这次只想了解'])
def test_topic_switch_keeps_health_restrictions_and_removes_old_goals(switch):
    text='兽医要求不能换粮，对鸡肉过敏。上周问航空箱、路线和用品价格。'+switch+'梳毛时怎样判断应停止？'
    questions=questions_for(text)
    assert len(questions)==1 and '航空箱' not in questions[0] and '梳毛' in questions[0]
    history=[{'role':'user','content':'航空箱怎么选？','id':'u0','created_at':'2026-10-01'},
             {'role':'assistant','content':'此前的航空箱回答','id':'a0','created_at':'2026-10-01'}]
    assert relevant_history(history,current_focus(text))==[]
    facts=answer_context(None,{},history,text,{})
    assert any('鸡肉过敏' in report.get('text','') for report in facts['reported_restrictions_and_conflicts'])


def test_real_long_history_preserves_early_allergy_without_old_tasks():
    history=[{'role':'user','content':'我家猫对鸡肉过敏，兽医要求不能自行换粮。','id':'u0','created_at':'2026-01-01'}]
    history += [{'role':'user' if i%2==0 else 'assistant','content':'旧话题：航空箱与用品价格。','id':f'h{i}','created_at':'2026-02-01'} for i in range(60)]
    text='猫梳毛时抗拒，怎么停止？'
    facts=answer_context(None,{},history,text,{})
    assert any(report.get('message_id')=='u0' and '鸡肉过敏' in report['text'] for report in facts['reported_restrictions_and_conflicts'])
    assert not relevant_history(history,text)


def test_dependencies_are_included_once_and_questions_covered(db):
    questions=['猫剪指甲怎么适应？','航空箱怎么练习？','猫粮如何储存？','多猫怎样相处？','食品标签怎样核对？']
    with Session(db) as session:
        found=multi_search(session,'cat',questions,personal=True)
    chunks=[p for a in found for p in model_sections(a)]
    ids=[c['chunk_id'] for c in chunks]
    assert len(ids)==len(set(ids))
    assert all(dep in ids for c in chunks for dep in c['depends_on'])
    assert all(any(q in linked for a in found for linked in a['section_questions'].values()) for q in questions)
    assert all('cat' in c['species'] for c in chunks)


@pytest.mark.parametrize('text',[
 '健康文件不等于一律必须另开健康证明。',
 '并不是必须携带健康证明，应该核实目的地要求。',
 '不能说自驾一律需要健康证明。',
 '请核实运营方是否需要健康证明。',
])
def test_correct_travel_negations_are_accepted(text):
    check_text(text,None,SimpleNamespace(effective_context={},analysis={},current_text='',
        sent_evidence={'pet-travel':{'文件':'按实际运营方与目的地核实证件要求。'}}))


@pytest.mark.parametrize('text',[
 '自驾必须携带健康证明。',
 '健康证明必须携带。',
 '不是不能要求必须携带健康证明。',
 '不必核对包装，但是自驾必须携带健康证明。',
])
def test_positive_travel_claim_is_not_excused_by_unrelated_denial(text):
    with pytest.raises(HTTPException):
        check_text(text,None,SimpleNamespace(effective_context={},analysis={},current_text='',
            sent_evidence={'pet-travel':{'文件':'健康文件不等于必须另开健康证明。'}}))


@pytest.mark.parametrize('text',[
 '运输资料没有全国统一的固定清单。',
 '全国不存在统一证件要求。',
])
def test_unknown_travel_law_cannot_be_rewritten_as_absence(text):
    with pytest.raises(HTTPException):
        check_text(text,None,SimpleNamespace(effective_context={},analysis={},current_text='',
            sent_evidence={'pet-travel':{'文件':'按实际运营方与目的地核实证件要求。'}}))


def test_unknown_travel_law_can_remain_unknown():
    check_text('资料不足，不能据此断言没有全国统一的固定清单。',None,
        SimpleNamespace(effective_context={},analysis={},current_text='',
            sent_evidence={'pet-travel':{'文件':'按实际运营方与目的地核实证件要求。'}}))


@pytest.mark.parametrize('query,article,words',[
 ('猫的喂食和饮水有哪些基础原则？','cat-food','清洁饮水'),
 ('猫吐了之后，怎样记录呕吐过程和变化？','cat-vomiting','呕吐'),
])
def test_live_review_wrong_topic_regressions(db,query,article,words):
    with Session(db) as session:
        found=multi_search(session,'cat',[query],personal=True)
    passages=[p for a in found if a['id']==article for p in model_sections(a)]
    assert passages and any(words in p['text'] for p in passages)


@pytest.mark.parametrize('text',[
 '肌肉流失并不会导致BCS升高。',
 '不能认为肌肉流失导致BCS升高。',
 'BCS并非评估肌肉状况，MCS才是肌肉观察。',
 'BCS不包括肌肉，脂肪和肌肉分别记录。',
 'BCS评估脂肪，MCS不是评估脂肪而是评估肌肉状况。',
 '补齐这些数据后营养评估才可能给出食量。补一项标签并不等于就能精确算出该猫食量。',
])
def test_scoped_bcs_and_precision_denials(text):
    check_text(text,None,SimpleNamespace(effective_context={},current_text='',
        analysis={'tool_results':{'nutrition':{'status':'needs_information'}}},
        sent_evidence={'nutrition-muscle':{'区分':'BCS评估脂肪，MCS评估肌肉。'}}))


@pytest.mark.parametrize('text',[
 '肌肉流失会导致BCS升高。',
 '肌肉流失不是不会导致BCS升高。',
 '不能不说肌肉流失导致BCS升高。',
 'BCS不能不评估肌肉状况。',
 'BCS并非脂肪评分，而是评估肌肉状况。',
 '不能精确确定食量。不过提供标签后就能精确算出个体食量。',
])
def test_scoped_positive_or_double_negative_assertions(text):
    with pytest.raises(HTTPException):
        check_text(text,None,SimpleNamespace(effective_context={},current_text='',
            analysis={'tool_results':{'nutrition':{'status':'needs_information'}}},
            sent_evidence={'nutrition-muscle':{'区分':'BCS评估脂肪，MCS评估肌肉。'}}))


def test_explicit_run_authorization_preserves_the_shared_ledger(tmp_path):
    from datetime import datetime,UTC
    from app.evaluation_budget import EvaluationBudget
    pricing={'currency':'CNY','model':'deepseek-flash','checked_at':datetime.now(UTC).isoformat(),
             'peak_input_cache_miss_per_million':2,'peak_output_per_million':8}
    path=tmp_path/'shared.sqlite'
    original=EvaluationBudget(path,pricing,run_id='same',run_limit_cny='3')
    original.reserve({'model':'deepseek-flash','max_tokens':100,'extra_body':{'thinking':{'type':'disabled'}}})
    before=original.summary()
    with pytest.raises(ValueError):
        EvaluationBudget(path,pricing,run_id='same',run_limit_cny='10')
    authorized=EvaluationBudget(path,pricing,run_id='same',run_limit_cny='10',authorized_run_ceiling_cny='10')
    after=authorized.summary()
    assert after['limit_cny']==10 and after['run_limit_cny']==10
    assert after['conservative_used_cny']==before['conservative_used_cny']
    assert after['unresolved_reservations']==before['unresolved_reservations']==1
    with authorized.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM run_authorizations').fetchone()[0]==1
