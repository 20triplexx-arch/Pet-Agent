"""Durable in-flight claims, without business migrations or prompt storage."""
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager
from fastapi import HTTPException
from app.services import fingerprint, lookup_idempotent
from app.core.config import STORAGE, settings


def chat_fingerprint(data):
    payload = data.model_dump()
    if data.model_id == 'default':
        payload.pop('model_id')
    return fingerprint('chat', payload)


class ChatRequests:
    def __init__(self, session, user_id, key):
        if not key or len(key) > 200:
            raise HTTPException(400, '写入请求需要有效 Idempotency-Key')
        bind = session.get_bind()
        url = getattr(bind, 'url', getattr(getattr(bind, 'engine', None), 'url', None))
        database = getattr(url, 'database', None)
        self.path = (Path(database).resolve().parent if database and database != ':memory:' else STORAGE) / 'chat-requests.sqlite'
        self.scope = hashlib.sha256((str(url) + '|' + user_id).encode()).hexdigest()
        self.key = hashlib.sha256(key.encode()).hexdigest()
        self.owner = None
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (scope TEXT,key TEXT,fingerprint TEXT,owner TEXT,state TEXT,started REAL,finished REAL,error TEXT,PRIMARY KEY(scope,key))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA busy_timeout=10000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def begin(self, fp):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT fingerprint,state,started FROM requests WHERE scope=? AND key=?', (self.scope, self.key)).fetchone()
            if row:
                if row[0] != fp:
                    raise HTTPException(409, '同一个幂等键不能用于不同请求')
                if row[1] in ('pending', 'complete'):
                    message = '该请求仍在处理，请先查询状态；不会重复调用模型。' if time.time() - row[2] <= settings.MODEL_TIMEOUT_SECONDS * 2 else '该请求最终状态尚不明确，请查询会话；不会自动再次调用模型。'
                    raise HTTPException(409, message)
            self.owner = str(uuid4())
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,NULL,NULL) ON CONFLICT(scope,key) DO UPDATE SET owner=excluded.owner,state=excluded.state,started=excluded.started,finished=NULL,error=NULL',
                       (self.scope, self.key, fp, self.owner, 'pending', time.time()))

    def finish(self, state, error=None):
        with self.connect() as db:
            db.execute('UPDATE requests SET state=?,finished=?,error=? WHERE scope=? AND key=? AND owner=?',
                       (state, time.time(), json.dumps(error, ensure_ascii=False) if error else None, self.scope, self.key, self.owner))

    def status(self):
        with self.connect() as db:
            row = db.execute('SELECT state,started,error FROM requests WHERE scope=? AND key=?', (self.scope, self.key)).fetchone()
        if not row:
            return {'state': 'not_found'}
        state = row[0]
        if state == 'pending' and time.time() - row[1] > settings.MODEL_TIMEOUT_SECONDS * 2:
            state = 'unknown'
        return {'state': state, 'error': json.loads(row[2]) if row[2] else None}


def begin_chat(data, session, user, key):
    fp = chat_fingerprint(data)
    old = lookup_idempotent(session, user.id, key, fp)
    if old is not None:
        return None, old
    registry = ChatRequests(session, user.id, key)
    registry.begin(fp)
    return registry, None


async def run_registered(data, session, user, key, registry):
    import asyncio
    from app.api.routes import perform_chat
    try:
        result = await perform_chat(data, session, user, key)
        registry.finish('complete')
        return result
    except asyncio.CancelledError:
        registry.finish('canceled', {'detail': '生成已停止，未保存未完成回答。'})
        raise
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else '回答未完成，请手动重试。'
        registry.finish('failed', {'detail': detail, 'status': getattr(exc, 'status_code', 503)})
        raise
