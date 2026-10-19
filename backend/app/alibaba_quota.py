"""Verified free-tier routing. No inference probing, paid fallback, or public secrets."""
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, UTC, timedelta
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from app.core.config import settings, ROOT
from app.alibaba_models import DEFAULT_MODELS, family, ordered_candidates

KNOWN_MODELS = DEFAULT_MODELS  # Retained for integrations importing the old constant.


def credential_scope():
    return hashlib.sha256(json.dumps([settings.DASHSCOPE_API_KEY, settings.dashscope_url,
        settings.DASHSCOPE_WORKSPACE_ID], separators=(',', ':')).encode()).hexdigest()


def answer_build_hash():
    digest = hashlib.sha256()
    for name in ('agent_system.txt', 'answer_sections.py', 'answer_quality.py', 'answer_context.py', 'alibaba_models.py', 'model_adapter.py', 'deep_chat.py', 'knowledge.py', 'question_scope.py', 'answer_contract.py', 'propositions.py', 'evidence_index.py'):
        digest.update(name.encode())
        path = Path(__file__).with_name(name)
        digest.update(path.read_bytes() if path.exists() else b'absent-in-frozen-baseline')
    data = Path(__file__).resolve().parents[1] / 'data'
    for path in sorted([*data.glob('knowledge*.json'), *data.glob('evidence/*.json')]):
        digest.update(path.relative_to(data).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def configured_models():
    if settings.DASHSCOPE_FREE_MODELS.strip() == 'auto':
        return ordered_candidates(read_json(settings.DASHSCOPE_QUOTA_FILE).get('models', [])) or list(DEFAULT_MODELS)
    return list(dict.fromkeys(name.strip() for name in settings.DASHSCOPE_FREE_MODELS.split(',') if family(name.strip())))


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def snapshot():
    data = read_json(settings.DASHSCOPE_QUOTA_FILE)
    if type(data.get('checked_at')) not in (int, float):
        return {}
    age = time.time() - data.get('checked_at', 0)
    if data.get('credential_scope') != credential_scope() or data.get('workspace_verified') is not True or not 0 <= age <= settings.DASHSCOPE_QUOTA_MAX_AGE_SECONDS:
        return {}
    return data


@contextmanager
def ledger():
    path = Path(settings.DASHSCOPE_QUOTA_FILE).with_name('alibaba-free-reservations.sqlite')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY,scope TEXT,model TEXT,tokens INTEGER,state TEXT,created REAL)')
        db.execute('CREATE TABLE IF NOT EXISTS blocks (scope TEXT,model TEXT,until REAL,PRIMARY KEY(scope,model))')
        db.execute('CREATE TABLE IF NOT EXISTS active (scope TEXT PRIMARY KEY,model TEXT)')
        db.commit()
        with db:
            yield db
    finally:
        db.close()


def quota_unexpired(row):
    try:
        # CLI dates have day precision. Midnight UTC+8 is conservative.
        expires = datetime.fromisoformat(row['expires']).replace(tzinfo=UTC) - timedelta(hours=8)
    except (KeyError, TypeError, ValueError):
        return False
    return expires.timestamp() > time.time()


def remaining(row, checked_at, db):
    value = row.get('remaining')
    if type(value) is not int or value < 0 or row.get('autoStop') is not True or not quota_unexpired(row):
        return 0
    blocked = db.execute('SELECT until FROM blocks WHERE scope=? AND model=?', (credential_scope(), row['model'])).fetchone()
    if blocked and (time.time() < blocked[0] or checked_at < blocked[0]):
        return 0
    # Console usage is minute-delayed. Deduct a two-minute overlap conservatively,
    # plus every unresolved reservation, including across processes/restarts.
    held = db.execute("SELECT COALESCE(SUM(tokens),0) FROM reservations WHERE scope=? AND model=? AND state!='not_sent' AND (state='reserved' OR created>=?)",
                      (credential_scope(), row['model'], checked_at - 120)).fetchone()[0]
    return max(0, value - held)


def available_models(*, qualified=True, exclude=()):
    data = snapshot()
    if not data:
        return []
    approval = read_json(settings.DASHSCOPE_QUALIFIED_FILE)
    order = [name for name in approval.get('order', []) if name in configured_models()]
    order += [name for name in configured_models() if name not in order]
    approved = approval.get('models', {})
    build = answer_build_hash() if qualified else None
    rows = {row.get('model'): row for row in data.get('models', []) if isinstance(row, dict)}
    with ledger() as db:
        active = db.execute('SELECT model FROM active WHERE scope=?', (credential_scope(),)).fetchone()
        if active and active[0] in order:
            order = [active[0]] + [name for name in order if name != active[0]]
        return [name for name in order if name not in exclude and name in rows
                and (not qualified or (approved.get(name, {}).get('approved') is True
                     and approved[name].get('case_count', 0) >= 30
                     and approved[name].get('answer_build_sha256') == build))
                and remaining(rows[name], data['checked_at'], db) > 0]


def choose_model(exclude=()):
    options = available_models(exclude=exclude)
    if not options:
        raise HTTPException(503, '没有已核实且通过质量验证的阿里免费模型。请核对免费额度及网页登录状态；不会自动转为付费调用。')
    return options[0]


def reserve(request, *, automatic=False):
    data = snapshot()
    model = request['model']
    if not data:
        raise HTTPException(503, '阿里免费额度尚未核实或状态已过期，请刷新免费额度授权；本次未调用模型。')
    if automatic and model not in available_models():
        raise HTTPException(503, '当前免费模型未通过质量验证或额度不可用，本次未调用。')
    row = next((row for row in data.get('models', []) if row.get('model') == model), None)
    payload = {key: value for key, value in request.items() if key in ('messages', 'tools', 'response_format')}
    tokens = len(json.dumps(payload, ensure_ascii=False, default=str).encode()) + 8192 + (request.get('max_tokens') or request.get('max_completion_tokens') or 0)
    with ledger() as db:
        db.execute('BEGIN IMMEDIATE')
        if not row or remaining(row, data['checked_at'], db) < tokens:
            raise HTTPException(503, '所选阿里模型剩余免费额度不足以安全完成本次回答，或未开启用完即停。本次未调用模型。')
        ident = str(uuid4())
        db.execute("INSERT INTO reservations VALUES (?,?,?,?,'reserved',?)", (ident, credential_scope(), model, tokens, time.time()))
        if automatic:
            db.execute('INSERT INTO active VALUES (?,?) ON CONFLICT(scope) DO UPDATE SET model=excluded.model', (credential_scope(), model))
    return ident


def settle(ident, usage=None, *, not_sent=False):
    if not ident or (usage is None and not not_sent):
        return
    if not_sent:
        tokens, state = 0, 'not_sent'
    else:
        if type(usage.prompt_tokens) is not int or type(usage.completion_tokens) is not int:
            return
        tokens, state = usage.prompt_tokens + usage.completion_tokens, 'known'
    with ledger() as db:
        db.execute('UPDATE reservations SET tokens=?,state=? WHERE id=? AND scope=?', (tokens, state, ident, credential_scope()))


def mark_exhausted(model):
    with ledger() as db:
        db.execute('INSERT INTO blocks VALUES (?,?,?) ON CONFLICT(scope,model) DO UPDATE SET until=excluded.until',
                   (credential_scope(), model, time.time() + 120))


def cli_path():
    if settings.DASHSCOPE_CLI:
        return settings.DASHSCOPE_CLI
    installed = read_json(ROOT / 'artifacts/tools/bailian-install.json')
    path = installed.get('binary') or shutil.which('bl')
    if not path or not Path(path).is_file():
        raise RuntimeError('Official Bailian CLI is not configured')
    return path


def cli_call(args):
    env = dict(os.environ, BAILIAN_CONFIG_DIR=settings.DASHSCOPE_CLI_CONFIG_DIR,
               BAILIAN_WORKSPACE_ID=settings.DASHSCOPE_WORKSPACE_ID)
    command = [cli_path(), *args, '--config', settings.DASHSCOPE_CLI_PROFILE,
               '--output', 'json', '--timeout', '15']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env,
        timeout=22, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    # Official CLI sends errors to stderr, with empty stdout. Preserve the
    # actionable category without exposing provider bodies or credentials.
    if result.returncode:
        try:
            failure = json.loads(result.stderr or result.stdout)
            message = str(failure.get('error',{}).get('message','')).lower()
        except (ValueError, AttributeError):
            message = ''
        if 'not logged in' in message or 'expired' in message:
            raise RuntimeError('Quota console login is required: session expired')
        raise RuntimeError('Quota console request failed; verify console login and connectivity')
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('Quota console response is unavailable') from None
    if result.returncode or (isinstance(data, dict) and 'error' in data):
        raise RuntimeError('Quota console login is required')
    return data


def contains_workspace(value, ident):
    if isinstance(value, dict):
        return any(contains_workspace(child, ident) for child in value.values())
    if isinstance(value, list):
        return any(contains_workspace(child, ident) for child in value)
    return isinstance(value, str) and value == ident


def refresh_quotas(*, enable_stop=False):
    if not settings.DASHSCOPE_WORKSPACE_ID or not settings.DASHSCOPE_API_KEY:
        raise RuntimeError('A matching workspace and backend inference key are required')
    workspaces = cli_call(['workspace', 'list'])
    if not contains_workspace(workspaces, settings.DASHSCOPE_WORKSPACE_ID):
        raise RuntimeError('Console login does not match the configured workspace')
    rows = cli_call(['usage', 'free', '--all', '--console-region', 'cn-beijing'])
    if not isinstance(rows, list):
        raise RuntimeError('Unknown free quota response format')
    models = ordered_candidates(rows) if settings.DASHSCOPE_FREE_MODELS.strip() == 'auto' else configured_models()
    pending = [row['model'] for row in rows if row.get('model') in models
               and type(row.get('remaining')) is int and row['remaining'] > 0 and row.get('autoStop') is False]
    if enable_stop and pending:
        cli_call(['usage', 'freetier', '--model', ','.join(pending), '--on', '--console-region', 'cn-beijing'])
        rows = cli_call(['usage', 'free', '--all', '--console-region', 'cn-beijing'])
    cleaned = [{key: row.get(key) for key in ('model', 'type', 'remaining', 'expires', 'autoStop')}
               for row in rows if isinstance(row, dict) and isinstance(row.get('model'), str)]
    result = {'schema_version': 1, 'credential_scope': credential_scope(), 'workspace_verified': True,
              'checked_at': time.time(), 'models': cleaned}
    target = Path(settings.DASHSCOPE_QUOTA_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.' + str(uuid4()) + '.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, target)
    return cleaned


async def refresh_loop():
    while True:
        try:
            await asyncio.to_thread(refresh_quotas)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            # The previous snapshot expires normally; never infer eligibility from errors.
            pass
        await asyncio.sleep(60)
