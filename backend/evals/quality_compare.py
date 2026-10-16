"""Same-model, streaming-vs-streaming quality comparison against a Git revision.

Both workers use identical evaluation transport and the existing shared budget.
Only synthetic accounts are used. Wire captures and blind decoding keys stay local.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, UTC
import zipfile

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
BASELINE = '8d8bfe7ca4905aee73f5fd99163ffd8d99974b80'
MODEL = 'qwen3.8-flash'


def preflight(cases, safe_tokens, budget):
    turns = sum(len(case.get('turns', [])) for case in cases) * 2
    # The prior same-model review used ~2,800 tokens/turn. Reserve a forecast
    # of 4,000 plus room for the largest single wire reservation. Actual calls
    # still undergo the authoritative atomic token/price checks individually.
    forecast = turns * 4000 + 32000
    reasons = []
    if safe_tokens < forecast:
        reasons.append('insufficient_verified_free_tokens')
    if budget['conservative_used_cny'] >= 10 or budget['run_used_cny'] >= 3:
        reasons.append('existing_budget_exhausted')
    return {'allowed': not reasons, 'reasons': reasons, 'case_count': len(cases),
            'planned_model_turns': turns, 'forecast_tokens': forecast,
            'safe_remaining_tokens': safe_tokens, 'budget': budget}


def budget_snapshot():
    path = BACKEND / 'storage/evals/stage-one-budget.sqlite'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        used, pending = db.execute("SELECT SUM(amount_micro),SUM(state='reserved') FROM charges").fetchone()
        run_used = db.execute('SELECT COALESCE(SUM(amount_micro),0) FROM charges WHERE run_id=?',
                             ('alibaba-chat-streaming-20261015',)).fetchone()[0]
    return {'conservative_used_cny': (used or 0) / 1e6, 'run_used_cny': run_used / 1e6,
            'unresolved_reservations': pending or 0, 'cumulative_limit_cny': 10, 'run_limit_cny': 3,
            'run_id': 'alibaba-chat-streaming-20261015'}


def freeze_baseline(folder):
    archive = subprocess.run(['git', 'archive', '--format=zip', BASELINE, 'backend/app', 'backend/data'],
                             cwd=ROOT, capture_output=True, check=True).stdout
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(folder)
    return folder / 'backend', hashlib.sha256(archive).hexdigest()


def blind_review(report, folder):
    """No scores are invented: this creates inputs for an explicit source review."""
    rng = random.Random(report['answer_build_sha256'])
    pairs, key = [], {}
    for before, after in zip(report['results']['baseline'], report['results']['optimized']):
        if before['id'] != after['id']:
            raise ValueError('Paired case IDs differ')
        variants = ['baseline', 'optimized']
        rng.shuffle(variants)
        rows = {'baseline': before, 'optimized': after}
        key[before['id']] = dict(zip(('A', 'B'), variants))
        answers = {}
        for label, variant in key[before['id']].items():
            wire_file = Path(report['private_worker_folders'][variant]) / (before['id'] + '-wire.json')
            wire = json.loads(wire_file.read_text(encoding='utf-8'))
            answers[label] = {'turns': [{'status': turn['status'], 'answer': turn.get('result', {}).get('answer'),
                                        'error': turn.get('result', {}).get('detail')} for turn in rows[variant]['turns']],
                             'actual_requests': [{'raw_output': entry.get('content') or entry.get('response'), 'evidence': entry.get('evidence', {})}
                                                  for entry in wire if 'request' in entry]}
        pairs.append({'id': before['id'], 'answers': answers,
                      'review': {dimension: None for dimension in ('facts', 'support', 'coverage', 'usefulness', 'conciseness')},
                      'major_claims': None, 'supported_major_claims': None, 'severe_raw_issues': None,
                      'reasked_known_fields': None, 'preference': None, 'reason': None})
    (folder / 'blind-review.json').write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'private-review-key.json').write_text(json.dumps(key, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--folder')
    parser.add_argument('--pricing')
    args = parser.parse_args()
    from evals import streaming_compare as shared
    if args.worker:
        # Both revisions already implement streaming; do not use the older
        # shared comparator's non-streaming baseline or its compatibility overlay.
        args.worker, args.model = 'optimized', MODEL
        shared.worker(args)
        return 0
    from evals.runner import load_cases
    from app import alibaba_quota as quota
    dataset, dataset_hash = load_cases()
    cases = [case for case in dataset['cases'] if case['id'] in {'CB-' + i for i in shared.REVIEW_IDS}]
    if len(cases) != 30:
        raise ValueError('The fixed thirty-case review set changed')
    folder = ROOT / 'artifacts/evaluations' / (datetime.now(UTC).strftime('%Y%m%dT%H%M%S') + '-quality-step2')
    folder.mkdir(parents=True)
    report = {'created_at': datetime.now(UTC).isoformat(), 'model': MODEL, 'baseline_commit': BASELINE, 'dataset_sha256': dataset_hash,
              'benchmark_sha256': hashlib.sha256(Path(__file__).read_bytes() + Path(shared.__file__).read_bytes()).hexdigest(),
              'answer_build_sha256': quota.answer_build_hash(), 'results': {'baseline': [], 'optimized': []},
              'measurement': 'Both revisions use /chat/stream; first checked section and committed final, browser network excluded',
              'review_method': 'Assistant blind paired source review: facts, support, coverage, usefulness, conciseness; not veterinary accuracy',
              'quality_targets': {'improved_cases': 20, 'regressed_cases': 0, 'major_source_support_rate': .95,
                                  'known_severe_raw_issues': 0, 'reasked_known_fields': 0}}
    try:
        quota.refresh_quotas()
        data = quota.snapshot()
        with quota.ledger() as db:
            safe = next((quota.remaining(row, data['checked_at'], db) for row in data.get('models', []) if row['model'] == MODEL), 0)
        report['preflight'] = preflight(cases, safe, budget_snapshot())
    except (OSError, RuntimeError, ValueError, sqlite3.Error, subprocess.SubprocessError):
        report['preflight'] = {'allowed': False, 'reasons': ['preflight_state_unverifiable']}
    def save():
        report['metrics'] = {variant: shared.metrics(rows) for variant, rows in report['results'].items()}
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    if not report['preflight']['allowed'] or args.preflight_only:
        report['status'] = 'blocked' if not report['preflight']['allowed'] else 'preflight_only'
        report['real_model_requests'] = 0
        save()
        print(json.dumps({'report': str(folder / 'report.json'), 'status': report['status'], 'preflight': report['preflight']}))
        return 2 if report['status'] == 'blocked' else 0
    prices = shared.verified_price(MODEL)
    price_file = folder / 'pricing.json'
    price_file.write_text(json.dumps(prices), encoding='utf-8')
    baseline, checksum = freeze_baseline(folder / 'frozen')
    report['baseline_archive_sha256'] = checksum
    workers, logs = {}, []
    try:
        for variant, source in (('baseline', baseline), ('optimized', BACKEND)):
            work = Path(tempfile.mkdtemp(prefix='quality-' + variant + '-', dir=BACKEND / 'storage/evals'))
            log = (folder / (variant + '-stderr.log')).open('w', encoding='utf-8')
            logs.append(log)
            env = dict(os.environ, PYTHONUTF8='1', PYTHONPATH=str(source) + os.pathsep + str(BACKEND))
            process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker',
                '--folder', str(work), '--pricing', str(price_file)], cwd=BACKEND, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            workers[variant] = process
            shared.read_event(process, 'ready')
            report.setdefault('private_worker_folders', {})[variant] = str(work)
        for index, case in enumerate(cases):
            # Interleave sequentially, avoiding self-induced parallel latency.
            for variant in (('baseline', 'optimized') if index % 2 == 0 else ('optimized', 'baseline')):
                process = workers[variant]
                process.stdin.write(json.dumps(case) + '\n')
                process.stdin.flush()
                event = shared.read_event(process, 'result')
                report['results'][variant].append(event['row'])
                report['budget'] = event['budget']
                save()
                if any(turn['status'] in (429, 503, 504) for turn in event['row']['turns']):
                    report['status'] = 'stopped_without_retry'
                    return 2
        report['status'] = 'awaiting_source_review'
        blind_review(report, folder)
    finally:
        for process in workers.values():
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        for log in logs:
            log.close()
        save()
    print(json.dumps({'report': str(folder / 'report.json'), 'status': report['status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
