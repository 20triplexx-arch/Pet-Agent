import json
import time
from datetime import datetime, UTC, timedelta
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app import alibaba_quota as quota
from app.chat_models import select_model, catalog
from app.core.config import settings


@pytest.fixture
def free_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'DASHSCOPE_API_KEY', 'fake-backend-only-key')
    monkeypatch.setattr(settings, 'DASHSCOPE_WORKSPACE_ID', 'test-workspace')
    monkeypatch.setattr(settings, 'DASHSCOPE_FREE_ONLY', True)
    monkeypatch.setattr(settings, 'DASHSCOPE_AUTO_SELECT', True)
    monkeypatch.setattr(settings, 'DASHSCOPE_QUOTA_FILE', str(tmp_path / 'quota.json'))
    monkeypatch.setattr(settings, 'DASHSCOPE_QUALIFIED_FILE', str(tmp_path / 'qualified.json'))
    models = ['qwen3.7-flash-2026-07-15', 'qwen3.8-flash']
    data = {'credential_scope': quota.credential_scope(), 'workspace_verified': True, 'checked_at': time.time(),
        'models': [{'model': model, 'remaining': 1000000, 'expires': (datetime.now(UTC)+timedelta(days=10)).date().isoformat(), 'autoStop': True} for model in models]}
    Path(settings.DASHSCOPE_QUOTA_FILE).write_text(json.dumps(data), encoding='utf-8')
    Path(settings.DASHSCOPE_QUALIFIED_FILE).write_text(json.dumps({'order': models, 'models': {model: {
        'approved': True, 'case_count': 30, 'answer_build_sha256': quota.answer_build_hash()} for model in models}}), encoding='utf-8')
    return data


def write(data):
    Path(settings.DASHSCOPE_QUOTA_FILE).write_text(json.dumps(data), encoding='utf-8')


def test_only_verified_qualified_models_are_candidates(free_pool):
    assert quota.available_models() == ['qwen3.7-flash-2026-07-15', 'qwen3.8-flash']
    assert select_model('alibaba-auto').name == 'qwen3.7-flash-2026-07-15'
    Path(settings.DASHSCOPE_QUALIFIED_FILE).write_text('{}', encoding='utf-8')
    assert quota.available_models() == []
    assert len(quota.available_models(qualified=False)) == 2


@pytest.mark.parametrize('change', ['expired_snapshot', 'wrong_workspace', 'wrong_key', 'stop_off', 'no_remaining', 'expired_quota'])
def test_unknown_or_paid_eligibility_never_becomes_available(free_pool, monkeypatch, change):
    if change == 'expired_snapshot': free_pool['checked_at'] -= 1000
    if change == 'wrong_workspace': free_pool['workspace_verified'] = False
    if change == 'wrong_key': monkeypatch.setattr(settings, 'DASHSCOPE_API_KEY', 'changed-key')
    for row in free_pool['models']:
        if change == 'stop_off': row['autoStop'] = False
        if change == 'no_remaining': row['remaining'] = None
        if change == 'expired_quota': row['expires'] = '2020-01-01'
    write(free_pool)
    assert not quota.available_models()


def test_pending_usage_is_reserved_and_exhaustion_selects_next(free_pool):
    request = {'model': 'qwen3.7-flash-2026-07-15', 'messages': [{'role': 'user', 'content': '测试'}], 'max_tokens': 4096}
    receipt = quota.reserve(request, automatic=True)
    with quota.ledger() as db:
        held = db.execute("SELECT tokens,state FROM reservations WHERE id=?", (receipt,)).fetchone()
    assert held[0] > 4096 and held[1] == 'reserved'
    quota.settle(receipt, None)
    with quota.ledger() as db:
        assert db.execute('SELECT state FROM reservations WHERE id=?', (receipt,)).fetchone()[0] == 'reserved'
    quota.mark_exhausted(request['model'])
    assert quota.choose_model() == 'qwen3.8-flash'
    quota.mark_exhausted('qwen3.8-flash')
    with pytest.raises(HTTPException, match='免费模型'):
        quota.choose_model()


def test_catalog_has_no_key_workspace_or_exact_balance(free_pool, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(settings, 'MODEL_PROVIDER', 'alibaba')
    data = catalog()
    assert data['default_id'] == 'alibaba-auto'
    rendered = json.dumps(data)
    assert 'fake-backend-only-key' not in rendered and 'test-workspace' not in rendered and '1000000' not in rendered


def test_cli_adapter_uses_exact_fields_and_keeps_inference_key(free_pool, monkeypatch):
    calls = []
    def cli(args):
        calls.append(args)
        if args[0] == 'workspace': return [{'id': 'test-workspace'}]
        return [{'model': 'qwen3.8-flash', 'remaining': 123456, 'expires': '2099-01-01', 'autoStop': True}]
    monkeypatch.setattr(quota, 'cli_call', cli)
    rows = quota.refresh_quotas(enable_stop=True)
    assert rows[0]['remaining'] == 123456 and settings.DASHSCOPE_API_KEY == 'fake-backend-only-key'
    assert not any('freetier' in command for command in calls)


def test_free_only_guard_prevents_any_wire_request(client, headers, cat, monkeypatch, tmp_path):
    from test_chat_stream import fake_stream, ask, events
    captured = fake_stream(monkeypatch)
    monkeypatch.setattr(settings, 'DASHSCOPE_FREE_ONLY', True)
    monkeypatch.setattr(settings, 'DASHSCOPE_QUOTA_FILE', str(tmp_path/'missing.json'))
    response = events(ask(client, headers, cat))
    assert response[-1][0] == 'error' and '免费额度' in response[-1][1]['detail']
    assert captured == []


@pytest.mark.parametrize('code,expected_calls', [('AllocationQuota.FreeTierOnly', 2), ('AccessDenied.Unpurchased', 1), ('invalid_api_key', 1)])
def test_only_explicit_free_exhaustion_switches_before_body(client, headers, cat, free_pool, monkeypatch, code, expected_calls):
    import httpx2
    from openai import PermissionDeniedError
    import app.model_adapter as adapter
    from test_chat_stream import fake_stream, ask, events
    fake_stream(monkeypatch)
    free_pool['credential_scope'] = quota.credential_scope()
    write(free_pool)
    factory = adapter.AsyncOpenAI
    seen = []
    def intercepted(**kwargs):
        client = factory(**kwargs)
        original = client.chat.completions.create
        async def create(**request):
            seen.append(request['model'])
            if len(seen) == 1:
                response = httpx2.Response(403, request=httpx2.Request('POST', 'https://test.invalid/chat'))
                raise PermissionDeniedError('private provider failure', response=response, body={'error': {'code': code}})
            return await original(**request)
        client.chat.completions.create = create
        return client
    monkeypatch.setattr(adapter, 'AsyncOpenAI', intercepted)
    result = events(ask(client, headers, cat, model_id='alibaba-auto'))
    assert len(seen) == expected_calls
    if expected_calls == 2:
        assert result[-1][0] == 'final'
        assert result[-1][1]['model_used'] == 'qwen3.8-flash'
        assert result[-1][1]['execution']['model_requests'] == 2
    else:
        assert result[-1][0] == 'error'
        assert 'private provider' not in str(result)
