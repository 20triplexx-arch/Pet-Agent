"""Provider isolation, actual evidence, one-request answers and two spending caps."""
import json
import sqlite3
from datetime import datetime, UTC
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import httpx2
import pytest
from openai import AsyncOpenAI
from sqlmodel import Session
from app.core.config import Settings, settings
from app.chat_models import select_model
from app.evaluation_budget import EvaluationBudget, BudgetExceeded
from app.knowledge import multi_search, sections
from app.models import KnowledgeArticle
from test_model_adapter import fake_provider


def pricing():
    return {"currency": "CNY", "model": "qwen3.7-flash", "checked_at": datetime.now(UTC).isoformat(),
            "tiers": [{"max_input_tokens": n, "input_per_million": i, "output_per_million": o}
                      for n, i, o in [(32768, .2, .8), (262144, .6, 2.4), (1000000, 1.2, 4.8)]]}


def qwen_request():
    return {"model": "qwen3.7-flash", "messages": [{"role": "user", "content": "模拟"}],
            "max_tokens": 4096, "extra_body": {"enable_thinking": False}}


def ask(client, headers, cat, **extra):
    return client.post('/api/v1/chat', headers={**headers, 'Idempotency-Key': 'upgrade'},
                       json={"pet_id": cat["id"], "text": "猫抓沙发怎么办？", **extra})


def test_environment_precedes_dotenv_and_addresses_are_explicit(tmp_path, monkeypatch):
    env = tmp_path / '.env'
    env.write_text('DASHSCOPE_API_KEY=file-key\nDASHSCOPE_WORKSPACE_ID=file-space\n', encoding='utf-8')
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'server-secret')
    monkeypatch.setenv('DASHSCOPE_WORKSPACE_ID', 'server-space')
    cfg = Settings(_env_file=env, MODEL_PROVIDER='alibaba', DEMO_MODE=False)
    assert cfg.model_key == 'server-secret' and cfg.model_name == 'qwen3.7-flash' and cfg.model_mode == 'live'
    assert cfg.dashscope_url == 'https://server-space.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
    assert 'server-secret' not in repr(cfg)
    assert Settings(_env_file=None, DASHSCOPE_BASE_URL='https://explicit.example/v1/', DASHSCOPE_WORKSPACE_ID='space').dashscope_url == 'https://explicit.example/v1'
    assert Settings(_env_file=None, DASHSCOPE_WORKSPACE_ID='', DASHSCOPE_BASE_URL='').dashscope_url == 'https://dashscope.aliyuncs.com/compatible-mode/v1'


def test_alibaba_catalog_and_real_routing_use_own_key(client, headers, cat, monkeypatch):
    seen = fake_provider(monkeypatch, '提供稳定抓板并按反应调整。', source='__first__', model='qwen3.7-plus')
    monkeypatch.setattr(settings, 'MODEL_PROVIDER', 'alibaba')
    monkeypatch.setattr(settings, 'DASHSCOPE_API_KEY', 'ali-only-private')
    monkeypatch.setattr(settings, 'DASHSCOPE_MODEL', 'qwen3.7-plus')
    monkeypatch.setattr(settings, 'DASHSCOPE_WORKSPACE_ID', 'test-space')
    import app.model_adapter as adapter
    real_factory = adapter.AsyncOpenAI
    options = []
    def factory(**kwargs):
        options.append(kwargs)
        return real_factory(**kwargs)
    monkeypatch.setattr(adapter, 'AsyncOpenAI', factory)
    catalog = client.get('/api/v1/chat/models', headers=headers).json()
    ali = next(o for o in catalog['options'] if o['id'] == 'alibaba')
    assert catalog['default_id'] == 'alibaba' and ali['label'] == '阿里千问 · qwen3.7-plus' and ali['available']
    response = ask(client, headers, cat)
    assert response.status_code == 200, response.text
    assert options[0]['api_key'] == 'ali-only-private' and options[0]['base_url'] == settings.dashscope_url
    assert options[0]['max_retries'] == 0 and seen[0]['enable_thinking'] is False and 'thinking' not in seen[0]
    assert response.json()['execution']['answer_path'] == 'direct' and len(seen) == 1
    assert not seen[0].get('tools') and seen[0]['response_format']['type'] == 'json_schema'
    assert seen[0]['response_format']['json_schema']['strict'] is True
    assert all(value not in response.text + json.dumps(catalog) + repr(select_model('alibaba')) for value in ['ali-only-private', 'test-space'])
    replay = ask(client, headers, cat)
    assert replay.json()['message']['id'] == response.json()['message']['id'] and len(seen) == 1


def test_missing_alibaba_never_borrows_other_provider_key(client, headers, cat, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(settings, 'MODEL_PROVIDER', 'alibaba')
    monkeypatch.setattr(settings, 'MODEL_API_KEY', 'other-secret')
    monkeypatch.setattr(settings, 'DEEPSEEK_API_KEY', 'deep-secret')
    response = ask(client, headers, cat)
    assert response.status_code == 503 and '密钥未配置' in response.text
    assert client.get('/api/v1/status', headers=headers).json()['mode'] == 'configuration_error'


@pytest.mark.parametrize('text,term', [('蓝猫是什么规范品种？', '毛色'), ('泰迪具体属于什么？', '贵宾'), ('金渐层能直接确定品种吗？', '毛色')])
def test_breed_identity_uses_existing_clarification_even_with_selected_pet(client, headers, cat, monkeypatch, text, term):
    calls = fake_provider(monkeypatch, '不应调用')
    response = ask(client, headers, cat, text=text)
    assert response.status_code == 200 and term in response.json()['answer'], response.text
    assert not calls and not response.json()['sources']


def test_direct_answer_keeps_pet_profile_and_professional_limits(client, headers, cat, db, monkeypatch):
    from app.models import Pet, CareLog
    with Session(db) as session:
        pet = session.get(Pet, cat['id'])
        pet.medical_history = '既往肾脏问题'
        pet.allergies = '鸡肉'
        pet.vet_advice = '保持兽医原定饮食方案，不增加零食'
        session.add(pet)
        session.add(CareLog(user_id=pet.user_id, pet_id=pet.id, kind='weight', value=3.6, occurred_at=datetime.now(UTC).isoformat()))
        session.commit()
    seen = fake_provider(monkeypatch, '提供稳定抓板。', source='__first__')
    monkeypatch.setattr(settings, 'DASHSCOPE_API_KEY', 'dummy-ali-key')
    monkeypatch.setattr(settings, 'DASHSCOPE_MODEL', 'mock-model')
    response = ask(client, headers, cat, model_id='alibaba')
    assert response.status_code == 200 and len(seen) == 1, response.text
    supplied = json.loads(seen[0]['messages'][-1]['content'])['current_profile']
    assert supplied['id'] == cat['id'] and supplied['age_months'] is not None
    assert supplied['weight'] == 3.6 and supplied['weight_date']
    assert supplied['medical_history'] == '既往肾脏问题' and supplied['allergies'] == '鸡肉'
    assert supplied['vet_advice'] == '保持兽医原定饮食方案，不增加零食'
    assert 'supports_json_object_output' not in supplied


def test_ambiguous_coat_name_does_not_block_general_care(client, headers, cat, monkeypatch):
    calls = fake_provider(monkeypatch, '先选择完整均衡主食。', source='__first__')
    response = ask(client, headers, cat, text='蓝猫喂食有什么基础原则？')
    assert response.status_code == 200 and calls, response.text


@pytest.mark.parametrize('status,phrase', [(401, '鉴权失败'), (403, '鉴权失败'), (404, '不可用'), (429, '额度不足')])
def test_provider_errors_are_distinct_and_secret_free(client, headers, cat, monkeypatch, status, phrase):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx2.Response(status, json={'error': {'message': 'must-not-echo-private-provider-details', 'code': 'rejected'}})
    def factory(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)))
    monkeypatch.setattr('app.model_adapter.AsyncOpenAI', factory)
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(settings, 'DASHSCOPE_API_KEY', 'dummy-ali-key')
    response = ask(client, headers, cat, model_id='alibaba')
    assert response.status_code == 503 and phrase in response.json()['detail'], response.text
    assert 'must-not-echo' not in response.text and len(calls) == 1


@pytest.mark.parametrize('depth,maximum', [('brief', 1024), ('auto', 2048), ('detailed', 4096)])
def test_depth_budget_and_compact_complete_evidence(client, headers, cat, monkeypatch, depth, maximum):
    seen = fake_provider(monkeypatch, '先提供稳定的替代抓挠位置。', source='__first__')
    response = ask(client, headers, cat, answer_depth=depth)
    assert response.status_code == 200, response.text
    assert len(seen) == 1 and (seen[0].get('max_tokens') or seen[0].get('max_completion_tokens')) == maximum
    prompt = json.loads(seen[0]['messages'][-1]['content'])
    assert all('body' not in a and a['matched_sections'] for a in prompt['retrieved_data'])


def test_multiple_questions_merge_different_passages(db, monkeypatch):
    from app import knowledge
    with Session(db) as session:
        article = session.get(KnowledgeArticle, 'cat-food').model_dump()
        all_sections = sections(article)
        assert len(all_sections) >= 2
        monkeypatch.setattr(knowledge, 'search_knowledge', lambda *args, **kwargs: [article])
        monkeypatch.setattr(knowledge, 'evidence_sections', lambda a, q: [all_sections[0 if q == 'first' else 1]])
        found = multi_search(session, 'cat', ['first', 'second'])
        assert len(found) == 1 and found[0]['matched_questions'] == ['first', 'second']
        assert found[0]['matched_sections'] == all_sections[:2]


def test_existing_but_unsent_chapter_is_rejected(client, headers, cat, db, monkeypatch):
    with Session(db) as session:
        article = session.get(KnowledgeArticle, 'cat-food')
        article.body += '\n\n## 未提供的拓展原理\n这段确实存在于数据库，但没有提供给模型。'
        session.add(article); session.commit(); session.refresh(article)
        data = article.model_dump()
    monkeypatch.setattr('app.deep_chat.multi_search', lambda *a, **k: [{**data, 'matched_sections': sections(data)[:1], 'matched_questions': ['猫抓沙发怎么办']}])
    fake_provider(monkeypatch, '引用未提供的章节。', source='cat-food', citation_sections=[{'article_id': 'cat-food', 'heading': '未提供的拓展原理'}])
    response = ask(client, headers, cat)
    assert response.status_code == 502 and '未提供' in response.text


def test_tool_metadata_or_forged_passages_do_not_count_as_provided_evidence():
    from app.model_adapter import remember_tool_evidence
    context = SimpleNamespace(retrieved={'article':{'body':'## 实际章节\n实际原文'}}, sent_evidence={})
    remember_tool_evidence(context, [{'id':'article','title':'仅元数据'},
        {'id':'article','matched_sections':[{'heading':'虚构章节','text':'虚构文字'}]}])
    assert not context.sent_evidence
    remember_tool_evidence(context, {'id':'article','matched_sections':[{'heading':'实际章节','text':'实际原文'}]})
    assert context.sent_evidence == {'article':{'实际章节':'实际原文'}}


def test_inline_unprovided_source_is_rejected(client, headers, cat, monkeypatch):
    fake_provider(monkeypatch, '抓挠建议 [invented-article#凭空章节]', source='__first__')
    response = ask(client, headers, cat)
    assert response.status_code == 502 and '正文引用' in response.text


def test_verified_body_source_omitted_from_metadata_still_gets_source_card(client, headers, cat, monkeypatch):
    seen = fake_provider(monkeypatch, '提供稳定抓板。[cat-scratching]', source=None)
    response = ask(client, headers, cat)
    assert response.status_code == 200, response.text
    assert len(seen) == 1 and [s['id'] for s in response.json()['sources']] == ['cat-scratching']
    assert response.json()['sources'][0]['evidence']


@pytest.mark.parametrize('code,phrase', [('AllocationQuota.FreeTierOnly', '免费额度'), ('AccessDenied.Unpurchased', '调用资格或额度')])
def test_alibaba_quota_and_model_eligibility_errors(client, headers, cat, monkeypatch, code, phrase):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx2.Response(403, json={'error': {'code': code, 'message': 'private-provider-detail'}})
    def factory(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)))
    monkeypatch.setattr('app.model_adapter.AsyncOpenAI', factory)
    monkeypatch.setattr(settings, 'DASHSCOPE_API_KEY', 'dummy-ali-key')
    response = ask(client, headers, cat, model_id='alibaba')
    assert response.status_code == 503 and phrase in response.json()['detail'], response.text
    assert 'private-provider' not in response.text and len(calls) == 1


def test_same_turn_read_is_reused_but_different_query_still_executes(db, cat, monkeypatch):
    from app.agent import AgentContext, search_pet_knowledge
    from app.models import User, Pet
    from app.execution import Execution, current_execution
    from pydantic_ai import RunContext
    import app.agent as module
    real = module.search_knowledge
    calls = []
    def search(*args, **kwargs):
        calls.append(args[2]); return real(*args, **kwargs)
    monkeypatch.setattr(module, 'search_knowledge', search)
    with Session(db) as session:
        pet = session.get(Pet, cat['id'])
        ctx = AgentContext(session, session.get(User, pet.user_id), pet.id)
        run = RunContext(deps=ctx, model=None, usage=None, prompt='synthetic')
        trace = Execution(); token = current_execution.set(trace)
        try:
            first = search_pet_knowledge(run, '猫抓沙发')
            repeated = search_pet_knowledge(run, '猫抓沙发')
            search_pet_knowledge(run, '猫航空箱')
        finally: current_execution.reset(token)
    assert repeated == first and calls == ['猫抓沙发', '猫航空箱']
    assert trace.tools[1]['cached'] and len(trace.tools) == 3


def test_official_pricing_parser_rejects_changed_tariff():
    from evals.alibaba_compare import verify_pricing
    page = '模型价格 华北2（北京） 输入<=32k 输入 0.2 每百万tokens 输出 0.8 每百万tokens 32k<输入<=256k 输入 0.6 每百万tokens 输出 2.4 每百万tokens 256k<输入<=1m 输入 1.2 每百万tokens 输出 4.8 每百万tokens 新加坡'
    assert verify_pricing(page)['tiers'] == pricing()['tiers']
    with pytest.raises(ValueError): verify_pricing(page.replace('0.2', '0.3'))


def test_tiered_accounting_preserves_old_rows_and_both_caps(tmp_path):
    path = tmp_path / 'ledger.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE config (id INTEGER PRIMARY KEY,limit_micro INTEGER NOT NULL)')
        db.execute('INSERT INTO config VALUES (1,10000000)')
        db.execute('CREATE TABLE charges (id TEXT PRIMARY KEY,amount_micro INTEGER NOT NULL,state TEXT NOT NULL,input_tokens INTEGER,output_tokens INTEGER)')
        db.execute("INSERT INTO charges VALUES ('old',3924606,'usage_estimate',1,1)")
    budget = EvaluationBudget(path, pricing(), run_id='this-upgrade', run_limit_cny='.03')
    assert budget.cost(32768, 10) == 6562 and budget.cost(32769, 10) == 19686
    def reserve(_):
        try: return budget.reserve(qwen_request())
        except BudgetExceeded: return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        accepted = [r for r in pool.map(reserve, range(20)) if r]
    state = budget.summary()
    assert state['run_used_cny'] <= .03 and 0 < len(accepted) < 20
    assert state['conservative_used_cny'] == pytest.approx(3.924606 + state['run_used_cny'])
    budget.settle(accepted[0], None)
    assert budget.summary() == state
    budget.settle(accepted[0], SimpleNamespace(prompt_tokens=400, completion_tokens=100))
    assert budget.summary()['run_used_cny'] < state['run_used_cny']
    with pytest.raises(ValueError, match='raised'):
        EvaluationBudget(path, pricing(), run_id='this-upgrade', run_limit_cny='1')
    # The lifetime cap applies even when a new run still has plenty of room.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE charges SET amount_micro=9999999 WHERE id='old'")
    with pytest.raises(BudgetExceeded): budget.reserve(qwen_request())


@pytest.mark.parametrize('change', [{'max_tokens': 4097}, {'extra_body': {}}, {'stream': True}, {'model': 'other'}])
def test_alibaba_budget_rejects_unverified_requests(tmp_path, change):
    budget = EvaluationBudget(tmp_path/'ledger.sqlite', pricing(), run_id='check', run_limit_cny='3')
    with pytest.raises(ValueError): budget.reserve({**qwen_request(), **change})
