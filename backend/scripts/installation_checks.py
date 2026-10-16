"""Synthetic installation checks shared by native and Docker verification."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import urllib.request
import urllib.parse
from uuid import uuid4

ISOLATED_ENV = {
    'DEMO_MODE': 'true', 'MODEL_PROVIDER': 'compatible', 'MODEL_API_KEY': '',
    'DEEPSEEK_API_KEY': '', 'DASHSCOPE_API_KEY': '', 'DASHSCOPE_WORKSPACE_ID': '',
    'DASHSCOPE_BASE_URL': '', 'DASHSCOPE_AUTO_SELECT': 'false', 'DASHSCOPE_CLI': '',
    'AMAP_ENABLED': 'false', 'AMAP_API_KEY': '', 'TIANDITU_ENABLED': 'false',
    'TIANDITU_API_KEY': '', 'SECRET_KEY': '',
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def valid_health(value):
    model = value.get('model') if isinstance(value, dict) else None
    return (isinstance(value, dict) and value.get('status') == 'ok'
            and value.get('mode') == 'demo' and isinstance(model, dict)
            and model.get('id') == 'demo' and model.get('available') is True)


def wait_health(base, timeout=60):
    deadline, last = time.monotonic() + timeout, 'no response'
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + '/health', timeout=2) as response:
                value = json.load(response)
            last = json.dumps(value, ensure_ascii=False)
            if valid_health(value):
                return value
        except (OSError, ValueError) as exc:
            last = f'{type(exc).__name__}: {exc}'
        time.sleep(0.25)
    raise RuntimeError('Service did not become ready; last health: ' + last)


def request(base, path, *, data=None, form=None, token=None, key=None):
    headers, body = {}, None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode()
        headers['Content-Type'] = 'application/json'
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if key:
        headers['Idempotency-Key'] = key
    with urllib.request.urlopen(urllib.request.Request(base + path, body, headers), timeout=15) as response:
        return json.load(response)


def check_public(base):
    for route in ['/', '/chat', '/knowledge']:
        with urllib.request.urlopen(base + route, timeout=5) as response:
            html = response.read()
            require(response.status == 200 and b'<html' in html, 'SPA route missing: ' + route)
    assets = re.findall(r'(?:src|href)="(/assets/[^"?#]+)', html.decode())
    require(any(p.endswith('.js') for p in assets), 'Built JavaScript missing')
    require(any(p.endswith('.css') for p in assets), 'Built stylesheet missing')
    for path in set(assets):
        with urllib.request.urlopen(base + path, timeout=5) as response:
            require(response.status == 200 and response.read(), 'Empty static asset: ' + path)


def exercise(base):
    email, password = 'install-' + uuid4().hex + '@example.com', secrets.token_urlsafe(24)
    request(base, '/api/v1/users/signup', data={'email': email, 'password': password, 'full_name': '安装验收'})
    token = request(base, '/api/v1/login/access-token', form={'username': email, 'password': password})['access_token']
    user = request(base, '/api/v1/users/me', token=token)
    pet = request(base, '/api/v1/pets', token=token, key=str(uuid4()),
                  data={'name': '安装验收猫', 'species': 'cat', 'estimated_age_months': 24})
    path, key = '/api/v1/pets/' + pet['id'] + '/logs', str(uuid4())
    payload = {'kind': 'weight', 'value': 4, 'occurred_at': datetime.now(timezone.utc).isoformat()}
    record = request(base, path, token=token, key=key, data=payload)
    repeated = request(base, path, token=token, key=key, data=payload)
    require(record['id'] == repeated['id'], 'Repeated record was not idempotent')
    chat, key = {'pet_id': pet['id'], 'text': '猫抓沙发怎么办？', 'model_id': 'demo'}, str(uuid4())
    answer = request(base, '/api/v1/chat', data=chat, token=token, key=key)
    require(answer['mode'] == 'demo' and answer['message']['content'], 'Demo answer missing')
    require(answer.get('sources'), 'Demo knowledge sources missing')
    repeated = request(base, '/api/v1/chat', data=chat, token=token, key=key)
    require(answer['message']['id'] == repeated['message']['id'], 'Repeated chat generated twice')
    ocr = request(base, '/api/v1/products/ocr/status', token=token)
    require(ocr.get('available') is False, 'Default install unexpectedly depends on OCR')
    return {'token': token, 'user': user['id'], 'pet': pet['id'], 'log': record['id'],
            'conversation': answer['conversation_id'], 'message': answer['message']['id']}


def check_persisted(base, state):
    require(request(base, '/api/v1/users/me', token=state['token'])['id'] == state['user'], 'Login did not survive restart')
    pets = request(base, '/api/v1/pets', token=state['token'])
    require(any(p['id'] == state['pet'] for p in pets), 'Pet did not survive restart')
    logs = request(base, '/api/v1/pets/' + state['pet'] + '/logs', token=state['token'])
    require([x['id'] for x in logs] == [state['log']], 'Record missing or duplicated')
    messages = request(base, '/api/v1/conversations/' + state['conversation'] + '/messages', token=state['token'])
    require(len(messages) == 2 and messages[-1]['id'] == state['message'], 'Conversation missing or duplicated')


def validate_catalog(actual_ids, revisions, expected_ids, heads):
    require(set(actual_ids) == set(expected_ids), 'Imported knowledge IDs differ from source files')
    require(len(actual_ids) == len(set(actual_ids)), 'Duplicate imported knowledge IDs')
    require(len(heads) == 1 and set(revisions) == set(heads), 'Database is not at the unique Alembic head')


def read_state(root=None):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    expected = set()
    for path in sorted((root / 'data').glob('knowledge*.json')):
        expected.update(row['id'] for row in json.loads(path.read_text(encoding='utf-8')))
    require(expected, 'No source knowledge found')
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    heads = ScriptDirectory.from_config(config).get_heads()
    with sqlite3.connect((root / 'storage/chongban.db').as_uri() + '?mode=ro', uri=True) as db:
        ids = [row[0] for row in db.execute('SELECT id FROM knowledgearticle')]
        revisions = [row[0] for row in db.execute('SELECT version_num FROM alembic_version')]
        validate_catalog(ids, revisions, expected, heads)
        counts, business = {}, {}
        for table in ['user', 'pet', 'carelog', 'conversation', 'message']:
            rows = sorted(db.execute('SELECT * FROM ' + table).fetchall(), key=str)
            counts[table], business[table] = len(rows), rows
    return {'knowledge': len(ids), 'revision': revisions[0], 'counts': counts,
            'business_hash': hashlib.sha256(json.dumps(business, sort_keys=True).encode()).hexdigest(),
            'key_hash': hashlib.sha256((root / 'storage/.secret').read_bytes()).hexdigest()}


if __name__ == '__main__':
    print(json.dumps(read_state(), ensure_ascii=False))
