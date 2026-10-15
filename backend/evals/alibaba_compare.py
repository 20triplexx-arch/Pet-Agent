"""Paired, interleaved, synthetic Alibaba evaluation with a shared durable cap.

The baseline is a source snapshot taken immediately after minimal Alibaba wiring.
Workers have independent databases and processes; only the spending ledger is shared.
"""
import argparse
from datetime import datetime, UTC
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
RUN_ID = 'alibaba-quality-speed-20261015'
PRICING_URL = 'https://help.aliyun.com/zh/model-studio/qwen3-7-flash'


def verify_pricing(page=None):
    if page is None:
        page = urllib.request.urlopen(PRICING_URL, timeout=25).read().decode('utf-8')
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', page)).replace('\\n', ' '))
    start = text.index('模型价格')
    block = text[start:]
    block = block[block.index('华北') : block.index('新加坡')]
    prices = re.findall(r'输入\s+([\d.]+)\s+每百万\s*tokens\s+输出\s+([\d.]+)\s+每百万\s*tokens', block)
    if prices != [('0.2', '0.8'), ('0.6', '2.4'), ('1.2', '4.8')] or not all(t in block.lower() for t in ('32k', '256k', '1m')):
        raise ValueError('Official Beijing Qwen tariff changed; do not make paid requests')
    return {'currency': 'CNY', 'model': 'qwen3.7-flash', 'region': 'cn-beijing',
            'checked_at': datetime.now(UTC).isoformat(), 'source': PRICING_URL,
            'table_sha256': hashlib.sha256(block.encode()).hexdigest(),
            'tiers': [{'max_input_tokens': n, 'input_per_million': float(i), 'output_per_million': float(o)}
                      for n, (i, o) in zip((32768, 262144, 1000000), prices)]}


def worker(args):
    from evals.runner import setup_database, run_case
    # Clear every external service other than the explicitly selected provider.
    os.environ.update({'DEMO_MODE': 'false', 'MODEL_PROVIDER': 'alibaba', 'MODEL_API_KEY': '',
                       'DEEPSEEK_API_KEY': '', 'MODEL_LIMITS_ENABLED': 'false', 'MODEL_MAX_REQUESTS': '4',
                       'MODEL_MAX_INPUT_TOKENS': '64000', 'MODEL_MAX_OUTPUT_TOKENS': '4096',
                       'MODEL_TIMEOUT_SECONDS': '60', 'TIANDITU_ENABLED': 'false', 'TIANDITU_API_KEY': ''})
    folder = Path(args.folder)
    pets = setup_database(folder)
    from app.evaluation_budget import EvaluationBudget, current_budget
    pricing = json.loads(Path(args.pricing).read_text(encoding='utf-8'))
    budget = EvaluationBudget(BACKEND/'storage/evals/stage-one-budget.sqlite', pricing,
                              run_id=RUN_ID, run_limit_cny='3')
    from app.core.config import settings
    if not settings.DASHSCOPE_API_KEY or settings.DASHSCOPE_MODEL != 'qwen3.7-flash':
        raise ValueError('Verified Qwen model and environment key required')
    if 'cn-beijing.maas.aliyuncs.com' not in settings.dashscope_url and settings.dashscope_url != 'https://dashscope.aliyuncs.com/compatible-mode/v1':
        raise ValueError('Only the verified Beijing endpoint is budgeted')
    from fastapi.testclient import TestClient
    from app.main import app
    # Only this synthetic evaluation saves wire responses, in ignored private
    # artifacts. Production execution logs continue to contain metadata only.
    import app.model_adapter as adapter
    factory = adapter.AsyncOpenAI
    wire = []
    def capture_client(**kwargs):
        client = factory(**kwargs)
        create = client.chat.completions.create
        async def capture(**request):
            try:
                response = await create(**request)
            except Exception as error:
                body = getattr(error, 'body', {})
                detail = body.get('error', body) if isinstance(body, dict) else {}
                message = str(detail.get('message', '')) if isinstance(detail, dict) else ''
                for name in ('DASHSCOPE_API_KEY', 'DASHSCOPE_WORKSPACE_ID', 'DEEPSEEK_API_KEY'):
                    secret = os.environ.get(name)
                    if secret: message = message.replace(secret, '[redacted]')
                wire.append({'provider_error': {'status': getattr(error, 'status_code', None),
                             'code': detail.get('code') if isinstance(detail, dict) else None,
                             'message': message[:800]}})
                raise
            wire.append({'response': response.model_dump(mode='json'),
                         'messages': request.get('messages'), 'response_format': request.get('response_format'),
                         'model': request.get('model'), 'max_tokens': request.get('max_tokens') or request.get('max_completion_tokens'),
                         'enable_thinking': request.get('extra_body', {}).get('enable_thinking'), 'has_tools':bool(request.get('tools'))})
            return response
        client.chat.completions.create = capture
        return client
    adapter.AsyncOpenAI = capture_client
    token = current_budget.set(budget)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            login = client.post('/api/v1/login/access-token', data={'username': 'synthetic-eval@example.com', 'password': 'SyntheticEval2026!'})
            headers = {'Authorization': 'Bearer '+login.json()['access_token']}
            print(json.dumps({'worker_event': 'ready', 'variant': args.worker}), flush=True)
            for line in sys.stdin:
                case = json.loads(line)
                # Separate repetitions never replay a prior idempotency key.
                started = time.perf_counter()
                wire.clear()
                result = run_case(client, headers, pets, case)
                (folder/(case['id']+'-wire.json')).write_text(json.dumps(wire, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
                row = {'id': case['id'], 'category': case['category'], **result,
                       'passed': all(result['checks'].values()), 'elapsed_ms': round((time.perf_counter()-started)*1000, 2),
                       'provider_error_codes': [x['provider_error']['code'] for x in wire if 'provider_error' in x]}
                print(json.dumps({'worker_event': 'result', 'variant': args.worker, 'row': row,
                                  'budget': budget.summary()}, ensure_ascii=True), flush=True)
    finally:
        current_budget.reset(token)


def read_event(process, expected):
    while True:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(f'Evaluation worker exited ({process.poll()}); see private stderr')
        try: value = json.loads(line)
        except ValueError: continue
        if value.get('worker_event') == expected:
            return value


def metrics(rows):
    times = sorted(r['elapsed_ms'] for r in rows)
    turns = [t for r in rows for t in r['turns']]
    return {'completed': len(rows), 'passed': sum(r['passed'] for r in rows),
            'failed_cases': sum(not r['passed'] for r in rows),
            'p50_case_ms': times[len(times)//2] if times else None,
            'p95_case_ms': times[min(len(times)-1, math.ceil(.95*len(times))-1)] if times else None,
            'model_requests': sum((t.get('execution') or {}).get('model_requests', 0) for t in turns),
            'input_tokens': sum((t.get('execution') or {}).get('input_tokens', 0) for t in turns),
            'output_tokens': sum((t.get('execution') or {}).get('output_tokens', 0) for t in turns),
            'model_turns': sum((t.get('execution') or {}).get('model_requests', 0)>0 for t in turns),
            'direct_turns': sum((t.get('execution') or {}).get('answer_path') == 'direct' for t in turns)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=['baseline', 'optimized'])
    parser.add_argument('--folder')
    parser.add_argument('--pricing')
    parser.add_argument('--only', help='Comma separated IDs from the fixed first 60 cases')
    parser.add_argument('--variant', choices=['paired', 'optimized'], default='paired')
    parser.add_argument('--depth', choices=['auto', 'brief', 'detailed'], default='auto')
    parser.add_argument('--sequential', action='store_true', help='Dispatch one variant at a time instead of paired concurrent requests')
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if not os.environ.get('DASHSCOPE_API_KEY'):
        parser.error('DASHSCOPE_API_KEY must be present in the server environment')
    snapshot = ROOT/'artifacts/alibaba-baseline'
    if args.variant == 'paired' and not (snapshot/'manifest.json').is_file():
        parser.error('Minimum-wiring baseline snapshot is required')
    from evals.runner import load_cases
    dataset, checksum = load_cases()
    cases = dataset['cases'][:60]
    if args.only:
        wanted = set(args.only.split(',')); cases = [c for c in cases if c['id'] in wanted]
        if {c['id'] for c in cases} != wanted: parser.error('Unknown paired case IDs')
    cases = [{**case, 'answer_depth': args.depth} for case in cases]
    pricing = verify_pricing()
    run_name = datetime.now(UTC).strftime('%Y%m%dT%H%M%S')+'-alibaba-'+args.variant
    output = ROOT/'artifacts/evaluations'/run_name; output.mkdir(parents=True)
    price_path = output/'pricing.json'; price_path.write_text(json.dumps(pricing, indent=2), encoding='utf-8')
    report = {'run_id': RUN_ID, 'created_at': datetime.now(UTC).isoformat(), 'synthetic_data_only': True,
              'dataset_sha256': checksum, 'dataset_version': dataset['version'], 'selected_count': len(cases),
              'model': 'qwen3.7-flash', 'results': {'baseline': [], 'optimized': []},
              'answer_depth_override': args.depth,
              'implementation_sha256': hashlib.sha256(b''.join(p.read_bytes() for p in sorted((BACKEND/'app').rglob('*.py'))) + (BACKEND/'app/agent_system.txt').read_bytes()).hexdigest(),
              'baseline_manifest_sha256': hashlib.sha256((snapshot/'manifest.json').read_bytes()).hexdigest() if snapshot.exists() else None,
              'benchmark_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'dispatch': 'sequential' if args.sequential else 'paired_concurrent',
              'method': 'Separate processes/databases; alternating A/B dispatch order per case. Concurrent pair by default (max two workers), then wait for both. Same endpoint/model/configuration. Shared atomic spending ledger; baseline inference preserved.'}
    processes, streams = {}, []
    variants = ['baseline', 'optimized'] if args.variant == 'paired' else ['optimized']
    def save():
        report['metrics'] = {v: metrics(report['results'][v]) for v in variants}
        if all(report['metrics'].get(v, {}).get('p50_case_ms') for v in ('baseline', 'optimized')):
            report['p50_reduction'] = 1-report['metrics']['optimized']['p50_case_ms']/report['metrics']['baseline']['p50_case_ms']
            report['p95_not_worse'] = report['metrics']['optimized']['p95_case_ms'] <= report['metrics']['baseline']['p95_case_ms']
            pairs = {r['id'] for r in report['results']['baseline'] if r['passed']} & {r['id'] for r in report['results']['optimized'] if r['passed']}
            report['successful_pairs'] = {v: metrics([r for r in report['results'][v] if r['id'] in pairs]) for v in variants}
            report['successful_pair_count'] = len(pairs)
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        for variant in variants:
            folder = Path(tempfile.mkdtemp(prefix=variant+'-', dir=BACKEND/'storage/evals'))
            env = os.environ.copy(); env['PYTHONUTF8'] = '1'
            env['PYTHONPATH'] = str(snapshot if variant == 'baseline' else BACKEND)+os.pathsep+str(BACKEND)
            # A script's sys.path[0] is evals/, so PYTHONPATH selects the intended app package.
            stderr = (output/(variant+'-stderr.log')).open('w', encoding='utf-8'); streams.append(stderr)
            process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker', variant,
                                        '--folder', str(folder), '--pricing', str(price_path)], cwd=BACKEND, env=env,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True, encoding='utf-8',
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            processes[variant] = process; read_event(process, 'ready')
            report.setdefault('private_worker_folders', {})[variant] = str(folder)
        for index, case in enumerate(cases):
            order = variants if index % 2 == 0 else list(reversed(variants))
            if not args.sequential:
                for variant in order:
                    process = processes[variant]
                    process.stdin.write(json.dumps(case, ensure_ascii=True)+'\n'); process.stdin.flush()
            for variant in order:
                process = processes[variant]
                if args.sequential:
                    process.stdin.write(json.dumps(case, ensure_ascii=True)+'\n'); process.stdin.flush()
                event = read_event(process, 'result')
                report['results'][variant].append(event['row']); report['budget'] = event['budget']; save()
                print(json.dumps({'case': case['id'], 'variant': variant, 'passed': event['row']['passed'],
                                  'elapsed_ms': event['row']['elapsed_ms'], 'run_used_cny': event['budget']['run_used_cny']}), flush=True)
                if any(t['status'] == 429 for t in event['row']['turns']):
                    report['stopped_reason'] = 'budget_exhausted'; return 1
                if any(code in ('AccessDenied.Unpurchased', 'AllocationQuota.FreeTierOnly') for code in event['row'].get('provider_error_codes', [])):
                    report['stopped_reason'] = 'provider_model_or_free_quota_unavailable'; return 1
                if event['row'].get('provider_error_codes'):
                    report['stopped_reason'] = 'provider_request_failed'; return 1
    finally:
        for process in processes.values():
            process.stdin.close()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=10)
        for stream in streams: stream.close()
        save()
        print(json.dumps({'report': str(output), 'metrics': report['metrics'], 'stopped_reason': report.get('stopped_reason')}), flush=True)
    return int(any(not r['passed'] for v in variants for r in report['results'][v]))


if __name__ == '__main__':
    raise SystemExit(main())
