"""Transport, source binding, replay and rollback. All model traffic is mocked."""
import asyncio
import json
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import httpx2
import pytest
from openai import AsyncOpenAI
from sqlmodel import Session, select
from fastapi import HTTPException
from app.answer_sections import ClosedSections, AnswerSection, bind_section
from app.chat_requests import ChatRequests
from app.core.config import settings
from app.models import Message


def fake_stream(monkeypatch, *, bad_ref=False, missing_question=False, finish='stop', truncated=False):
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        payload = json.loads(body['messages'][-1]['content'])
        refs = list(payload['evidence'])
        questions = list(map(int, payload['subquestions']))
        output = {'sections': [
            {'text': '先提供稳定的替代抓挠位置，再观察实际使用情况。',
             'evidence_ids': ['invented'] if bad_ref else refs[:1], 'question_ids': questions[:1] if missing_question else questions},
            {'text': '根据实际反应调整位置，不强迫靠近。', 'evidence_ids': refs[:1], 'question_ids': questions[:1]}]}
        content = json.dumps(output, ensure_ascii=False)
        if truncated:
            content = content[:-2]
        events = []
        for i in range(0, len(content), 5):
            events.append({'id': 'stream-test', 'object': 'chat.completion.chunk', 'created': 1, 'model': body['model'],
                'choices': [{'index': 0, 'delta': {'content': content[i:i+5]}, 'finish_reason': None}]})
        events.append({'id': 'stream-test', 'object': 'chat.completion.chunk', 'created': 1, 'model': body['model'],
                       'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})
        events.append({'id': 'stream-test', 'object': 'chat.completion.chunk', 'created': 1, 'model': body['model'], 'choices': [],
                       'usage': {'prompt_tokens': 400, 'completion_tokens': 100, 'total_tokens': 500, 'prompt_tokens_details': {'cached_tokens': 120}}})
        data = ''.join('data: ' + json.dumps(e, ensure_ascii=False) + '\n\n' for e in events) + 'data: [DONE]\n\n'
        return httpx2.Response(200, content=data.encode(), headers={'content-type': 'text/event-stream'})
    monkeypatch.setattr('app.model_adapter.AsyncOpenAI', lambda **kwargs: AsyncOpenAI(**kwargs,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler))))
    monkeypatch.setattr(settings, 'DASHSCOPE_API_KEY', 'test-only-key')
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    return requests


def events(response):
    parsed = []
    for frame in response.text.split('\n\n'):
        lines = frame.splitlines()
        kind = next((line[7:] for line in lines if line.startswith('event: ')), None)
        value = next((json.loads(line[6:]) for line in lines if line.startswith('data: ')), None)
        if kind:
            parsed.append((kind, value))
    return parsed


def ask(client, headers, cat, key='stream', **extra):
    return client.post('/api/v1/chat/stream', headers={**headers, 'Idempotency-Key': key},
        json={'pet_id': cat['id'], 'text': '猫抓沙发怎么办？', 'model_id': 'alibaba', **extra})


def test_stream_checks_sections_then_commits_and_replays(client, headers, cat, monkeypatch):
    calls = fake_stream(monkeypatch)
    result = ask(client, headers, cat)
    assert result.status_code == 200
    items = events(result)
    assert [kind for kind, _ in items] == ['accepted', 'section', 'section', 'final']
    first, final = items[1][1], items[-1][1]
    assert first['sources'] and first['sources'][0]['evidence']
    assert first['text'] in final['answer'] and len(calls) == 1
    assert calls[0]['stream'] and calls[0]['stream_options']['include_usage']
    assert calls[0]['enable_thinking'] is False and not calls[0].get('tools')
    assert final['execution']['cached_input_tokens'] == 120
    assert 'first_section' in final['execution']['stages_ms']
    status = client.get('/api/v1/chat/status', headers={**headers, 'Idempotency-Key': 'stream'}).json()
    assert status['state'] == 'complete' and status['response'] == final
    replay = ask(client, headers, cat)
    assert [kind for kind, _ in events(replay)] == ['accepted', 'final'] and len(calls) == 1
    legacy = client.post('/api/v1/chat', headers={**headers, 'Idempotency-Key': 'stream'},
        json={'pet_id': cat['id'], 'text': '猫抓沙发怎么办？', 'model_id': 'alibaba'})
    assert legacy.json() == final and len(calls) == 1


@pytest.mark.parametrize('options,early', [({'bad_ref': True}, False), ({'missing_question': True}, True),
    ({'finish': 'length'}, True), ({'truncated': True}, True)])
def test_invalid_final_retracts_and_never_saves_half_reply(client, headers, cat, db, monkeypatch, options, early):
    fake_stream(monkeypatch, **options)
    extra = {'text': '猫抓沙发怎么办？猫独处如何互动？'} if options.get('missing_question') else {}
    result = events(ask(client, headers, cat, **extra))
    assert result[-1][0] == 'error' and result[-1][1]['retract']
    assert ('section' in [kind for kind, _ in result]) is early
    with Session(db) as session:
        assert not session.exec(select(Message)).all()
    assert client.get('/api/v1/chat/status', headers={**headers, 'Idempotency-Key': 'stream'}).json()['state'] == 'failed'
    usage = client.get('/api/v1/usage', headers=headers).json()
    assert usage['input_tokens'] == 400  # Local rejection still consumes the final usage chunk.


def test_parser_never_emits_unclosed_object_and_handles_escaped_braces():
    value = {'sections': [{'text': '中文：括号 } 和引号 " 都在字符串中。', 'evidence_ids': ['e1'], 'question_ids': [1]}]}
    content = json.dumps(value, ensure_ascii=False)
    parser, parts = ClosedSections(), []
    for index, char in enumerate(content):
        found = parser.feed(char)
        if found:
            assert content[index] == '}'
        parts.extend(found)
    assert [part.model_dump() for part in parts] == value['sections']
    assert parser.ended


def test_proportion_condition_cannot_arrive_in_later_section():
    ctx = SimpleNamespace(effective_context={}, sent_evidence={'nutrition-feeding': {'范围': '健康、体况合适的成年个体。'}}, retrieved={})
    with pytest.raises(HTTPException, match='适用条件'):
        bind_section(AnswerSection(text='零食不超过10%。', evidence_ids=['e1'], question_ids=[1]),
            {'e1': {'article_id': 'nutrition-feeding', 'heading': '范围', 'text': '健康、体况合适的成年个体。'}}, ['问题'], None, ctx)


def test_atomic_inflight_claims_and_user_isolation(db):
    def claim():
        with Session(db) as session:
            registry = ChatRequests(session, 'user-one', 'same-key')
            try:
                registry.begin('same-payload')
                return 'started'
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: claim(), range(2)))
    assert sorted(map(str, results)) == ['409', 'started']
    with Session(db) as session:
        assert ChatRequests(session, 'other-user', 'same-key').status()['state'] == 'not_found'


def test_more_than_three_questions_and_simple_followup_depth(client, headers, cat):
    from app.deep_chat import questions_for
    questions = questions_for('猫怎么梳毛？怎么刷牙？怎么选猫砂？如何练航空箱？怎样换粮？')
    assert len(questions) == 5
    response = client.post('/api/v1/chat', headers={**headers, 'Idempotency-Key': 'context-depth'},
        json={'pet_id': cat['id'], 'text': '猫抓沙发怎么办？', 'context': {'goal': '长期照护'}})
    assert response.json()['answer_depth'] == 'standard'


def test_closing_stream_cancels_generation_and_marks_no_half_reply(db, cat, monkeypatch):
    from app.api.chat_stream import chat_stream
    from app.model_runtime import section_sink
    from app.models import User
    from app.schemas import ChatInput
    canceled = []
    async def pending(*args):
        try:
            await section_sink.get()({'index': 0, 'text': '已检查的临时段落。', 'sources': [], 'question_ids': [1]})
            await asyncio.Event().wait()
        finally:
            canceled.append(True)
    monkeypatch.setattr('app.api.routes.perform_chat', pending)
    async def exercise():
        with Session(db) as session:
            user = session.get(User, cat['user_id'])
            response = await chat_stream(ChatInput(pet_id=cat['id'], text='猫抓沙发怎么办？'), None, session, user, 'cancel-stream')
            iterator = response.body_iterator
            assert 'event: accepted' in await anext(iterator)
            assert 'event: section' in await anext(iterator)
            await iterator.aclose()
            assert canceled == [True]
            assert ChatRequests(session, user.id, 'cancel-stream').status()['state'] == 'canceled'
            assert not session.exec(select(Message)).all()
    asyncio.run(exercise())
