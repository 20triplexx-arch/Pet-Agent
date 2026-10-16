import json
from io import BytesIO
import pytest
from scripts import installation_checks as checks


def test_health_allows_additional_fields_but_requires_available_demo():
    healthy = {'status': 'ok', 'mode': 'demo', 'model': {'id': 'demo', 'available': True, 'label': '本地'}, 'new_field': 1}
    assert checks.valid_health(healthy)
    for bad in [None, [], {}, {**healthy, 'mode': 'live'}, {**healthy, 'status': 'error'},
                {**healthy, 'model': None}, {**healthy, 'model': {'id': 'demo', 'available': False}}]:
        assert not checks.valid_health(bad)


@pytest.mark.parametrize('ids,revisions,heads', [
    (['one'], ['current'], ['current']),
    (['one', 'two', 'two'], ['current'], ['current']),
    (['one', 'two'], ['old'], ['current']),
    (['one', 'two'], ['current'], ['current', 'other']),
])
def test_missing_knowledge_or_stale_migration_is_rejected(ids, revisions, heads):
    with pytest.raises(AssertionError):
        checks.validate_catalog(ids, revisions, {'one', 'two'}, heads)


def test_catalog_tracks_source_changes_instead_of_a_fixed_article_count():
    checks.validate_catalog(['two', 'one', 'new'], ['new-head'], {'one', 'two', 'new'}, ['new-head'])


def test_health_timeout_reports_last_response_without_waiting(monkeypatch):
    times = iter([0, 0, 2])
    monkeypatch.setattr(checks.time, 'monotonic', lambda: next(times))
    monkeypatch.setattr(checks.time, 'sleep', lambda _: None)
    monkeypatch.setattr(checks.urllib.request, 'urlopen', lambda *a, **kw: BytesIO(json.dumps({'status': 'error', 'mode': 'demo'}).encode()))
    with pytest.raises(RuntimeError, match='last health:.*error'):
        checks.wait_health('http://example.invalid', timeout=1)


def test_container_rediscovers_ephemeral_port_after_restart(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    path = Path(__file__).resolve().parents[2] / 'scripts/verify_container.py'
    spec = importlib.util.spec_from_file_location('container_verification', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    restarted, snapshots, health_urls = False, 0, []

    def command(*args):
        nonlocal restarted, snapshots
        if args[1] == 'port':
            return '127.0.0.1:' + ('49153' if restarted else '49152')
        if args[1] == 'restart':
            restarted = True
        if args[-1] == 'scripts.installation_checks':
            snapshots += 1
            return json.dumps({'counts': {'user': 0 if snapshots == 1 else 1},
                               'knowledge': 95, 'revision': 'current', 'key_hash': 'same', 'business_hash': 'same'})
        return ''

    monkeypatch.setattr(module, 'command', command)
    monkeypatch.setattr(module, 'wait_health', lambda url: health_urls.append(url))
    monkeypatch.setattr(module, 'check_public', lambda url: None)
    monkeypatch.setattr(module, 'exercise', lambda url: {})
    monkeypatch.setattr(module, 'check_persisted', lambda url, state: None)
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    module.main()
    assert health_urls == ['http://127.0.0.1:49152', 'http://127.0.0.1:49153']
