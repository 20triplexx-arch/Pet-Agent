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
