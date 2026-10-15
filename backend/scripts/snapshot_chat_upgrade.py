"""Preserve the exact pre-upgrade source and consistent local data, without logging secrets."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import argparse

ROOT = Path(__file__).resolve().parents[2]


def snapshot(runtime_only=False):
    baseline = ROOT / 'artifacts/chat-streaming-baseline'
    if baseline.exists() and not runtime_only:
        raise RuntimeError('Baseline already exists; use --runtime-only for rollout backup')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = ROOT / 'backend/storage/backups' / (stamp + '-chat-streaming')
    target.mkdir(parents=True)
    for name in ('.env', 'backend/storage/.secret', 'backend/storage/alibaba-quota.json', 'backend/storage/alibaba-qualified.json'):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / source.name)
    hashes = {}
    for name in ('chongban.db', 'evals/stage-one-budget.sqlite', 'chat-requests.sqlite', 'alibaba-free-reservations.sqlite'):
        source = ROOT / 'backend/storage' / name
        if source.exists():
            with sqlite3.connect(source) as original, sqlite3.connect(target / source.name) as copy:
                original.backup(copy)
                if name == 'chongban.db':
                    for (table,) in original.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
                        rows = original.execute('SELECT * FROM "' + table.replace('"', '""') + '"').fetchall()
                        hashes[table] = hashlib.sha256(json.dumps(sorted(map(repr, rows))).encode()).hexdigest()
    (target / 'row-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    if not runtime_only:
        baseline.mkdir(parents=True)
        shutil.copytree(ROOT / 'backend/app', baseline / 'app', ignore=shutil.ignore_patterns('__pycache__'))
        (baseline / 'snapshot.json').write_text(json.dumps({'backup': str(target), 'source_files': {
            str(p.relative_to(baseline)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (baseline / 'app').rglob('*') if p.is_file()}}, indent=2), encoding='utf-8')
    print(json.dumps({'backup': str(target), 'baseline': str(baseline), 'tables': len(hashes), 'runtime_only': runtime_only}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-only', action='store_true')
    snapshot(parser.parse_args().runtime_only)
