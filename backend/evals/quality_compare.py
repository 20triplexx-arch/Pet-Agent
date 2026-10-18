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
CURRENT = 'd630845d9eef826e14d53c72c363bdc775b0ce86'
MODEL = 'qwen3.8-flash'


def preflight(cases, safe_tokens, budget, *, variants=2, pricing=None):
    turns = sum(len(case.get('turns', [])) for case in cases) * variants
    # The prior same-model review used ~2,800 tokens/turn. Reserve a forecast
    # of 4,000 plus room for the largest single wire reservation. Actual calls
    # still undergo the authoritative atomic token/price checks individually.
    forecast = turns * 4000 + 32000
    reasons = []
    if safe_tokens < forecast:
        reasons.append('insufficient_verified_free_tokens')
    if budget['conservative_used_cny'] >= 10 or budget['run_used_cny'] >= 3:
        reasons.append('existing_budget_exhausted')
    forecast_cny = None
    if pricing:
        from decimal import Decimal
        tier = next(t for t in pricing['tiers'] if t['max_input_tokens'] >= 32000)
        # Forecast is deliberately above the last measured input/output mix.
        # Add a full request reservation; authoritative per-call checks remain.
        inp, out = Decimal(str(tier['input_per_million'])), Decimal(str(tier['output_per_million']))
        output_forecast = variants * sum(len(case.get('turns', [])) * (1500 if case.get('answer_depth') == 'detailed' else 500)
                                        for case in cases)
        forecast_cny = float((turns * 3500 * inp + output_forecast * out + 32000 * inp + 4096 * out) / 1000000)
        if forecast_cny > min(10 - budget['conservative_used_cny'], 3 - budget['run_used_cny']):
            reasons.append('insufficient_existing_budget_for_batch')
    return {'allowed': not reasons, 'reasons': reasons, 'case_count': len(cases),
            'planned_model_turns': turns, 'forecast_tokens': forecast,
            'safe_remaining_tokens': safe_tokens, 'forecast_cny': forecast_cny, 'budget': budget}


def budget_snapshot():
    path = Path(os.environ.get('CHONGBAN_EVAL_STATE_DIR', BACKEND/'storage')).resolve() / 'evals/stage-one-budget.sqlite'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        used, pending = db.execute("SELECT SUM(amount_micro),SUM(state='reserved') FROM charges").fetchone()
        run_used = db.execute('SELECT COALESCE(SUM(amount_micro),0) FROM charges WHERE run_id=?',
                             ('alibaba-chat-streaming-20261015',)).fetchone()[0]
    return {'conservative_used_cny': (used or 0) / 1e6, 'run_used_cny': run_used / 1e6,
            'unresolved_reservations': pending or 0, 'cumulative_limit_cny': 10, 'run_limit_cny': 3,
            'run_id': 'alibaba-chat-streaming-20261015'}


def stop_for_failure(row, wire):
    """An old revision's locally rejected JSON is a result, not an outage.

    Keep its original failure status and move to the next distinct case, without
    retrying the failed input. Unknown service/budget failures still stop.
    """
    local_json_rejection = any(entry.get('internal_error') == 'ValidationError' and any(
        frame.get('file') == 'answer_sections.py' for frame in entry.get('frames', [])) for entry in wire)
    return any(turn['status'] in (429, 504) or (turn['status'] == 503 and not local_json_rejection)
               for turn in row['turns'])


def freeze_baseline(folder, revision=BASELINE):
    archive = subprocess.run(['git', 'archive', '--format=zip', revision, 'backend/app', 'backend/data'],
                             cwd=ROOT, capture_output=True, check=True).stdout
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(folder)
    return folder / 'backend', hashlib.sha256(archive).hexdigest()


def blind_review(report, folder, reference='baseline'):
    """No scores are invented: this creates inputs for an explicit source review."""
    rng = random.Random(report['answer_build_sha256'])
    pairs, key = [], {}
    for before, after in zip(report['results'][reference], report['results']['optimized']):
        if before['id'] != after['id']:
            raise ValueError('Paired case IDs differ')
        variants = [reference, 'optimized']
        rng.shuffle(variants)
        rows = {reference: before, 'optimized': after}
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
                      'claim_review': [], 'major_claims': None, 'supported_major_claims': None, 'severe_raw_issues': None,
                      'reasked_known_fields': None, 'preference': None, 'reason': None})
    suffix = '' if reference == 'baseline' else '-current'
    (folder / ('blind-review' + suffix + '.json')).write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / ('private-review-key' + suffix + '.json')).write_text(json.dumps(key, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--folder')
    parser.add_argument('--pricing')
    parser.add_argument('--resume', type=Path, help='Complete only unexecuted cases from a compatible report folder')
    parser.add_argument('--model', choices=('qwen3.8-flash', 'qwen3.7-plus', 'qwen3.6-flash', 'qwen3.5-flash', 'qwen-flash-2025-07-28'), default=MODEL)
    parser.add_argument('--variant', choices=('paired', 'triple', 'optimized'), default='paired')
    parser.add_argument('--holdout', action='store_true', help='Run the frozen ten-case generalization set separately')
    args = parser.parse_args()
    from evals import streaming_compare as shared
    if args.worker:
        # Both revisions already implement streaming; do not use the older
        # shared comparator's non-streaming baseline or its compatibility overlay.
        args.worker = 'optimized'
        # Only model capability/accounting glue is shared with the frozen
        # baseline; its answer prompt, retrieval and validation stay unchanged.
        args.capability_overlay = True
        shared.worker(args)
        return 0
    from evals.runner import load_cases
    from app import alibaba_quota as quota
    dataset, dataset_hash = load_cases()
    cases = [case for case in dataset['cases'] if case['id'] in {'CB-' + i for i in shared.REVIEW_IDS}]
    if len(cases) != 30:
        raise ValueError('The fixed thirty-case review set changed')
    if args.holdout:
        if args.variant != 'optimized':
            raise ValueError('Holdout is reported separately from the fixed comparison')
        raw = (BACKEND/'evals/quality_holdout.json').read_bytes()
        dataset_hash = hashlib.sha256(raw).hexdigest()
        cases = json.loads(raw)['cases']
        if len(cases) != 10 or len({case['id'] for case in cases}) != 10:
            raise ValueError('The frozen ten-case holdout changed')
    folder = args.resume or ROOT / 'artifacts/evaluations' / (datetime.now(UTC).strftime('%Y%m%dT%H%M%S') + '-quality-step2')
    folder.mkdir(parents=True, exist_ok=bool(args.resume))
    variants = {'paired': ('baseline', 'optimized'), 'triple': ('baseline', 'current', 'optimized'), 'optimized': ('optimized',)}[args.variant]
    report = {'created_at': datetime.now(UTC).isoformat(), 'model': args.model, 'variant':args.variant, 'baseline_commit': BASELINE, 'dataset_sha256': dataset_hash,
              'benchmark_sha256': hashlib.sha256(Path(__file__).read_bytes() + Path(shared.__file__).read_bytes()).hexdigest(),
              'answer_build_sha256': quota.answer_build_hash(), 'results': {variant:[] for variant in variants},
              'measurement': 'Both revisions use /chat/stream; first checked section and committed final, browser network excluded',
              'review_method': 'Assistant blind paired source review: facts, support, coverage, usefulness, conciseness; not veterinary accuracy',
              'quality_targets': {'improved_cases': 20, 'regressed_cases': 0, 'major_source_support_rate': .95,
                                  'known_severe_raw_issues': 0, 'reasked_known_fields': 0}}
    report.update(current_commit=CURRENT, holdout=args.holdout)
    if args.resume:
        prior = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
        for key in ('model', 'variant', 'baseline_commit', 'dataset_sha256', 'answer_build_sha256'):
            if prior[key] != report[key]:
                raise ValueError('Resume identity changed: ' + key)
        if args.variant == 'triple' and prior.get('current_commit') != CURRENT:
            raise ValueError('Resume identity changed: current_commit')
        allowed = {case['id'] for case in cases}
        for rows in prior['results'].values():
            if len({row['id'] for row in rows}) != len(rows) or any(row['id'] not in allowed for row in rows):
                raise ValueError('Resume contains duplicate or foreign cases')
        report = prior
    segment = {'started_at': datetime.now(UTC).isoformat(), 'resumed': bool(args.resume),
               'benchmark_sha256': hashlib.sha256(Path(__file__).read_bytes() + Path(shared.__file__).read_bytes()).hexdigest()}
    report.setdefault('segments', []).append(segment)
    try:
        quota.refresh_quotas()
        data = quota.snapshot()
        with quota.ledger() as db:
            safe = next((quota.remaining(row, data['checked_at'], db) for row in data.get('models', []) if row['model'] == args.model), 0)
        prices = shared.verified_price(args.model)
        pending_cases = [case for variant in variants for case in cases
                         if not any(row['id'] == case['id'] for row in report['results'][variant])]
        report['preflight'] = preflight(pending_cases, safe, budget_snapshot(), variants=1, pricing=prices)
    except (OSError, RuntimeError, ValueError, sqlite3.Error, subprocess.SubprocessError):
        report['preflight'] = {'allowed': False, 'reasons': ['preflight_state_unverifiable']}
    def save():
        report['metrics'] = {variant: shared.metrics(rows) for variant, rows in report['results'].items()}
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    if not report['preflight']['allowed'] or args.preflight_only:
        report['status'] = 'blocked' if not report['preflight']['allowed'] else 'preflight_only'
        segment['new_real_model_requests'] = 0
        save()
        print(json.dumps({'report': str(folder / 'report.json'), 'status': report['status'], 'preflight': report['preflight']}))
        return 2 if report['status'] == 'blocked' else 0
    price_file = folder / 'pricing.json'
    price_file.write_text(json.dumps(prices), encoding='utf-8')
    sources = {'optimized': BACKEND}
    for variant, revision in (('baseline', BASELINE), ('current', CURRENT)):
        if variant not in variants:
            continue
        source, checksum = freeze_baseline(folder / ('frozen-' + variant), revision)
        if report.get(variant + '_archive_sha256', checksum) != checksum:
            raise ValueError('Frozen reference changed')
        report[variant + '_archive_sha256'] = checksum
        import shutil
        overlays = ('alibaba_models.py', 'alibaba_quota.py', 'evaluation_budget.py', 'core/config.py')
        for relative in overlays:
            shutil.copy2(BACKEND / 'app' / relative, source / 'app' / relative)
        report[variant + '_transport_overlays'] = {relative:hashlib.sha256((source/'app'/relative).read_bytes()).hexdigest() for relative in overlays}
        sources[variant] = source
    workers, logs = {}, []
    try:
        for variant in variants:
            source = sources[variant]
            work = Path(tempfile.mkdtemp(prefix='quality-' + variant + '-', dir=BACKEND / 'storage/evals'))
            if args.resume:
                import shutil
                previous = Path(report['private_worker_folders'][variant])
                for row in report['results'][variant]:
                    shutil.copy2(previous / (row['id'] + '-wire.json'), work)
            log = (folder / (variant + '-stderr-' + str(len(report['segments'])) + '.log')).open('w', encoding='utf-8')
            logs.append(log)
            env = dict(os.environ, PYTHONUTF8='1', PYTHONPATH=str(source) + os.pathsep + str(BACKEND))
            process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker',
                '--folder', str(work), '--pricing', str(price_file), '--model', args.model], cwd=BACKEND, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            workers[variant] = process
            shared.read_event(process, 'ready')
            report.setdefault('private_worker_folders', {})[variant] = str(work)
            segment.setdefault('worker_folders', {})[variant] = str(work)
        for index, case in enumerate(cases):
            # Interleave sequentially, avoiding self-induced parallel latency.
            order = variants[index % len(variants):] + variants[:index % len(variants)]
            for variant in order:
                if any(row['id'] == case['id'] for row in report['results'][variant]):
                    continue
                process = workers[variant]
                process.stdin.write(json.dumps(case) + '\n')
                process.stdin.flush()
                event = shared.read_event(process, 'result')
                report['results'][variant].append(event['row'])
                report['budget'] = event['budget']
                save()
                print(json.dumps({'case':case['id'], 'variant':variant, 'model':args.model,
                    'passed':event['row']['passed'], 'run_used_cny':event['budget']['run_used_cny']}), flush=True)
                wire = json.loads((Path(report['private_worker_folders'][variant]) / (case['id'] + '-wire.json')).read_text(encoding='utf-8'))
                if stop_for_failure(event['row'], wire):
                    report['status'] = 'stopped_without_retry'
                    return 2
        report['status'] = 'awaiting_source_review'
        if args.variant in ('paired', 'triple'):
            blind_review(report, folder)
        if args.variant == 'triple':
            blind_review(report, folder, 'current')
    except (OSError, RuntimeError, ValueError) as error:
        report['status'] = 'worker_failed_without_retry'
        segment['failure'] = type(error).__name__
        return 2
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
