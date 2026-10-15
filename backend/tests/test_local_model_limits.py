import json
import httpx2
from openai import AsyncOpenAI as RealClient
from sqlmodel import Session, select
from app.core.config import settings
from app.models import ModelAttempt, ModelUsage
from test_model_adapter import fake_provider
from test_model_loop import loop_provider


def ask(client, headers, cat, key='local-unlimited'):
    return client.post('/api/v1/chat', headers={**headers,'Idempotency-Key':key}, json={'pet_id':cat['id'],'text':'猫喂食建议','model_id':'compatible'})


def test_unlimited_daily_allows_more_than_twenty_attempts(client, headers, cat, db, monkeypatch):
    seen = fake_provider(monkeypatch, '按个体档案和食物标签核对饮食。')
    monkeypatch.setattr(settings,'MODEL_LIMITS_ENABLED',False)
    monkeypatch.setattr(settings,'MODEL_TURNS_PER_DAY',0)
    with Session(db) as session:
        session.add_all([ModelAttempt(user_id=cat['user_id'],status='completed') for _ in range(25)])
        session.commit()
    response=ask(client,headers,cat)
    assert response.status_code==200 and len(seen)==1
    quota=client.get('/api/v1/usage/quota',headers=headers).json()
    assert quota['limits_enabled'] is False and quota['daily_limit'] is None and quota['remaining_turns'] is None
    assert quota['request_limit'] is None and quota['tool_calls_limit'] is None and quota['attempted_turns']==26


def test_unlimited_flow_exceeds_old_model_and_tool_limits(client, headers, cat, db, monkeypatch):
    monkeypatch.setattr('app.deep_chat.evidence_is_ready', lambda *args: False)
    seen=[]
    source=None
    def handler(request):
        nonlocal source
        body=json.loads(request.content);seen.append(body)
        tools={t['function']['name']:t['function'] for t in body.get('tools',[])}
        if source is None:
            prompt=next(json.loads(m['content']) for m in body['messages'] if m['role']=='user' and 'retrieved_data' in m.get('content',''))
            source=prompt['retrieved_data'][0]['id']
        if len(seen)<=9:
            assert 'search_pet_knowledge' in tools
            name='search_pet_knowledge';args={'query':f'猫喂食 第{len(seen)}项','topic':None}
        else:
            name=next(n for n,t in tools.items() if 'answer' in t['parameters'].get('properties',{}))
            args={'answer':'根据真实检索资料说明饮食的适用条件。','citation_ids':[source],'draft':None,'citation_sections':[]}
        return httpx2.Response(200,json={'id':'local-fixture','object':'chat.completion','created':1,'model':'local-test',
            'choices':[{'index':0,'message':{'role':'assistant','content':None,'tool_calls':[{'id':f'call-{len(seen)}','type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]},'finish_reason':'tool_calls'}],
            'usage':{'prompt_tokens':320,'completion_tokens':70,'total_tokens':390}})
    def factory(**kwargs):
        return RealClient(**kwargs,http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr('app.model_adapter.AsyncOpenAI',factory)
    monkeypatch.setattr(settings,'MODEL_LIMITS_ENABLED',False)
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    monkeypatch.setattr(settings,'MODEL_API_KEY','local-private-fixture')
    response=ask(client,headers,cat)
    assert response.status_code==200,response.text
    assert len(seen)==10 and response.json()['execution']['model_requests']==10
    assert len([t for t in response.json()['execution']['tools'] if t['name']=='search_pet_knowledge'])==9
    assert not response.json()['execution']['model_finalization_forced']
    replay=ask(client,headers,cat)
    assert replay.json()['message']['id']==response.json()['message']['id'] and len(seen)==10
    with Session(db) as session:
        assert session.exec(select(ModelUsage)).one().requests==10


def test_unlimited_still_finishes_repeated_reads_without_cap(client, headers, cat, monkeypatch):
    seen=loop_provider(monkeypatch)
    monkeypatch.setattr(settings,'MODEL_LIMITS_ENABLED',False)
    response=ask(client,headers,cat)
    assert response.status_code==200,response.text
    assert len(seen)==2 and not seen[-1].get('tools')
    assert response.json()['execution']['model_finalization_forced']


def test_unlimited_cannot_bypass_identity_or_citations(client, headers, cat, account, monkeypatch):
    seen=fake_provider(monkeypatch,'未经检索的引用必须拒绝。','unknown-article')
    monkeypatch.setattr(settings,'MODEL_LIMITS_ENABLED',False)
    foreign=ask(client,account('other@example.com'),cat)
    assert foreign.status_code==404 and not seen
    invalid=ask(client,headers,cat)
    assert invalid.status_code==502 and len(seen)==1
