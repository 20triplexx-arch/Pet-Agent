"""Exercise the real Agent loop against a deterministic compatible HTTP fixture."""
import json
import pytest
import httpx2
from openai import AsyncOpenAI as RealClient
from sqlmodel import Session, select
from app.core.config import settings
from app.models import Message, ModelUsage, ModelAttempt


def loop_provider(monkeypatch, *, stubborn=False, finish_reason=None, input_tokens=320):
    # Exercise the collection path explicitly; ordinary covered questions use JSON directly.
    monkeypatch.setattr('app.deep_chat.evidence_is_ready', lambda *args: False)
    seen = []
    source = None
    def handler(request):
        nonlocal source
        body = json.loads(request.content)
        seen.append(body)
        tools = {t['function']['name']: t['function'] for t in body.get('tools', [])}
        final = next((name for name, tool in tools.items() if 'answer' in tool['parameters'].get('properties', {})), 'json-answer')
        if source is None:
            prompt = next(json.loads(message['content']) for message in body['messages'] if message['role']=='user' and 'retrieved_data' in message.get('content', ''))
            source = prompt['retrieved_data'][0]['id'] if prompt['retrieved_data'] else None
        answer = {'answer': '根据当前年龄、实际档案及检索资料说明照护条件；未知信息保持未知。', 'citation_ids': [source] if source else [], 'draft': None, 'citation_sections': []}
        if not tools and not stubborn:
            return httpx2.Response(200, json={'id':'fixture-json','object':'chat.completion','created':1,'model':'fixture-model',
                'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(answer,ensure_ascii=False)},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':input_tokens,'completion_tokens':70,'total_tokens':input_tokens+70}})
        if finish_reason:
            calls = [{'id': 'incomplete', 'type': 'function', 'function': {'name': final, 'arguments': '{"answer":"unfinished'}}]
        elif stubborn or 'search_pet_knowledge' in tools:
            calls = [{'id': f'search-{len(seen)}-{i}', 'type': 'function', 'function': {'name': 'search_pet_knowledge', 'arguments': json.dumps({'query': '猫喂食', 'topic': None})}} for i in range(2)]
        elif 'get_care_review' in tools:
            calls = [{'id': 'review', 'type': 'function', 'function': {'name': 'get_care_review', 'arguments': '{}'}}]
        else:
            calls = [{'id': 'answer', 'type': 'function', 'function': {'name': final, 'arguments': json.dumps({'answer': '根据当前年龄、实际档案及检索资料说明照护条件；未知信息保持未知。', 'citation_ids': [source] if source else [], 'draft': None, 'citation_sections': []}, ensure_ascii=False)}}]
        return httpx2.Response(200, json={'id':'fixture-loop','object':'chat.completion','created':1,'model':'fixture-model',
            'choices':[{'index':0,'message':{'role':'assistant','content':None,'tool_calls':calls},'finish_reason':finish_reason or 'tool_calls'}],
            'usage':{'prompt_tokens':input_tokens,'completion_tokens':70,'total_tokens':input_tokens+70}})
    def factory(**kwargs):
        return RealClient(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr('app.model_adapter.AsyncOpenAI', factory)
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    monkeypatch.setattr(settings,'MODEL_API_KEY','fixture-only-private-key')
    monkeypatch.setattr(settings,'MODEL_NAME','fixture-model')
    return seen


def ask(client, headers, cat, key='loop-test'):
    return client.post('/api/v1/chat', headers={**headers,'Idempotency-Key':key}, json={'pet_id':cat['id'],'text':'母猫一般多久绝育合适','model_id':'compatible'})


def test_repeated_retrieval_stops_and_reserves_final_answer(client, headers, cat, db, monkeypatch):
    seen=loop_provider(monkeypatch)
    response=ask(client,headers,cat)
    assert response.status_code==200, response.text
    assert len(seen)==3 and response.json()['complete'] and response.json()['mode']=='live'
    names=[{t['function']['name'] for t in body.get('tools', [])} for body in seen]
    assert 'search_pet_knowledge' in names[0] and 'search_pet_knowledge' not in names[1]
    assert not names[2] and seen[2]['response_format']['type']=='json_object'
    assert response.json()['execution']['model_finalization_forced']
    assert len([t for t in response.json()['execution']['tools'] if t['name']=='search_pet_knowledge'])==2
    # Repeated tool returns cannot put a full article beside the initial excerpts.
    outgoing = seen[1]['messages']
    prompt = next(json.loads(m['content']) for m in outgoing if m['role']=='user')
    provided = {(a['id'], s['heading']) for a in prompt['retrieved_data'] for s in a['matched_sections']}
    def check(value):
        if isinstance(value, list):
            for child in value: check(child)
        elif isinstance(value, dict):
            if 'matched_sections' in value and 'id' in value:
                assert 'body' not in value
                for passage in value['matched_sections']:
                    pair = (value['id'], passage['heading'])
                    assert pair not in provided
                    provided.add(pair)
            else:
                for child in value.values(): check(child)
    for message in outgoing:
        if message['role']=='tool': check(json.loads(message['content']))
    replay=ask(client,headers,cat)
    assert replay.json()['message']['id']==response.json()['message']['id'] and len(seen)==3
    with Session(db) as session:
        assert len(session.exec(select(Message)).all())==2
        usage=session.exec(select(ModelUsage)).one()
        assert usage.requests==3 and usage.input_tokens==960 and usage.output_tokens==210


@pytest.mark.parametrize('limit',[1,2])
def test_small_request_budget_still_reserves_answer(client,headers,cat,monkeypatch,limit):
    seen=loop_provider(monkeypatch)
    monkeypatch.setattr(settings,'MODEL_MAX_REQUESTS',limit)
    response=ask(client,headers,cat)
    assert response.status_code==200, response.text
    assert len(seen)==limit
    assert not seen[-1].get('tools') and seen[-1]['response_format']['type']=='json_object'


def test_model_ignoring_finalization_cannot_create_success_or_retry(client,headers,cat,db,monkeypatch):
    seen=loop_provider(monkeypatch,stubborn=True)
    response=ask(client,headers,cat)
    assert response.status_code in (502,503) and len(seen)<=4
    assert 'fixture-only-private-key' not in response.text
    with Session(db) as session:
        assert not session.exec(select(Message)).all()
        assert session.exec(select(ModelAttempt)).one().status=='failed'


def test_input_usage_limit_is_explicit_and_preserves_consumed_tokens(client,headers,cat,db,monkeypatch):
    seen=loop_provider(monkeypatch,input_tokens=100000)
    response=ask(client,headers,cat)
    assert response.status_code==503 and '输入资料用量' in response.json()['detail'] and len(seen)==1
    with Session(db) as session:
        assert not session.exec(select(Message)).all()
        assert session.exec(select(ModelUsage)).one().input_tokens==100000


def test_truncated_result_has_specific_message_not_generic_failure(client,headers,cat,db,monkeypatch):
    seen=loop_provider(monkeypatch,finish_reason='length')
    response=ask(client,headers,cat)
    assert response.status_code==502 and '模型输出达到上限' in response.json()['detail'] and len(seen)==1
    with Session(db) as session:
        assert not session.exec(select(Message)).all()
        assert session.exec(select(ModelUsage)).one().output_tokens==70
