"""Free-only synthetic evaluation with frozen baseline and shared durable ceilings."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, UTC

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
RUN_ID = 'alibaba-chat-streaming-20261015'
MODELS = ('qwen3.7-flash-2026-07-15', 'qwen3.8-flash', 'qwen-flash',
          'qwen3.7-plus', 'qwen3.6-flash', 'qwen3.5-flash', 'qwen3.7-max', 'qwen-flash-2025-07-28')
REVIEW_IDS = '001 003 004 008 009 012 017 018 021 022 024 025 028 033 037 040 043 049 053 057 002 005 006 010 011 013 015 026 034 059'.split()


def verified_price(model):
    from app.alibaba_models import family
    from evals.alibaba_prices import TARIFFS, verified_price as reviewed_price
    if family(model) in TARIFFS:
        return reviewed_price(model)
    if model == MODELS[0]:
        from evals.alibaba_compare import verify_pricing
        result = verify_pricing()
        return {**result, 'model': model}
    import re
    import html
    import urllib.request
    url = 'https://help.aliyun.com/zh/model-studio/' + ('qwen-flash' if family(model) == 'qwen-flash' else 'qwen3-8-flash')
    raw = urllib.request.urlopen(url, timeout=25).read().decode()
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', raw)).replace('\\n', ' '))
    block = text[text.index('模型价格'):]
    block = block[block.index('华北'):block.index('新加坡')]
    if family(model) == 'qwen-flash':
        prices = re.findall(r'输入\s+([\d.]+)\s+每百万\s*tokens\s+输出\s+([\d.]+)\s+每百万\s*tokens', block)
        if prices != [('0.15', '1.5'), ('0.6', '6'), ('1.2', '12')]:
            raise ValueError('Official Qwen Flash tariff could not be verified')
        return {'currency': 'CNY', 'model': model, 'checked_at': datetime.now(UTC).isoformat(), 'source': url,
                'table_sha256': hashlib.sha256(block.encode()).hexdigest(),
                'tiers': [{'max_input_tokens': n, 'input_per_million': float(i), 'output_per_million': float(o)}
                          for n, (i, o) in zip((131072, 262144, 1000000), prices)]}
    if not (re.search(r'输入\s+0\.8\s+每百万', block) and re.search(r'输出\s+2\.7\s+每百万', block)):
        raise ValueError('Official Qwen 3.8 Beijing tariff could not be verified')
    return {'currency': 'CNY', 'model': model, 'checked_at': datetime.now(UTC).isoformat(), 'source': url,
            'table_sha256': hashlib.sha256(block.encode()).hexdigest(),
            'tiers': [{'max_input_tokens': 1000000, 'input_per_million': .8, 'output_per_million': 2.7}]}


class StreamingClient:
    def __init__(self, client, streaming=True):
        self.client, self.streaming = client, streaming

    def __getattr__(self, name):
        return getattr(self.client, name)

    def post(self, path, **kwargs):
        if path != '/api/v1/chat':
            return self.client.post(path, **kwargs)
        started = time.perf_counter()
        response = self.client.post('/api/v1/chat/stream' if self.streaming else path, **kwargs)
        if response.status_code != 200:
            return response
        import httpx2
        if not self.streaming:
            data = response.json()
            data['delivery_timing'] = {'complete_ms': round((time.perf_counter()-started)*1000, 2)}
            return httpx2.Response(200, json=data, headers=response.headers)
        for frame in reversed(response.text.split('\n\n')):
            lines = frame.splitlines()
            kind = next((line[7:] for line in lines if line.startswith('event: ')), None)
            data = next((json.loads(line[6:]) for line in lines if line.startswith('data: ')), None)
            if kind == 'final':
                data['delivery_timing'] = {'complete_ms': round((time.perf_counter()-started)*1000, 2)}
                return httpx2.Response(200, json=data, headers=response.headers)
            if kind == 'error':
                return httpx2.Response(data.get('status', 503), json={'detail': data['detail']}, headers=response.headers)
        return httpx2.Response(502, json={'detail': 'Stream ended without final event'}, headers=response.headers)


def worker(args):
    os.environ.update({'DEMO_MODE': 'false', 'MODEL_PROVIDER': 'alibaba', 'DASHSCOPE_MODEL': args.model,
        'DASHSCOPE_AUTO_SELECT': 'false', 'DASHSCOPE_FREE_ONLY': 'true', 'MODEL_API_KEY': '', 'DEEPSEEK_API_KEY': '',
        'MODEL_LIMITS_ENABLED': 'false', 'MODEL_MAX_REQUESTS': '4', 'MODEL_MAX_INPUT_TOKENS': '64000',
        'MODEL_MAX_OUTPUT_TOKENS': '4096', 'MODEL_TIMEOUT_SECONDS': '60',
        'DASHSCOPE_QUOTA_FILE': str(BACKEND/'storage/alibaba-quota.json'),
        'DASHSCOPE_QUALIFIED_FILE': str(BACKEND/'storage/alibaba-qualified.json'),
        'DASHSCOPE_CLI': str(ROOT/'.tools/bailian/2.3.0/bl.exe'),
        'DASHSCOPE_CLI_CONFIG_DIR': str(BACKEND/'storage/bailian-cli')})
    from evals.runner import setup_database, run_case
    folder = Path(args.folder)
    pets = setup_database(folder)
    from app.core.config import settings
    if getattr(args, 'capability_overlay', False):
        # Import after isolated worker environment initialization, otherwise a
        # developer's .env can silently select the serving auto pool in evals.
        import app.model_adapter as adapter
        from app.alibaba_models import supports_schema
        adapter.native_schema = lambda selection: selection.provider == 'alibaba' and supports_schema(selection.name)
    from app import alibaba_quota as free
    from app.evaluation_budget import EvaluationBudget, current_budget
    prices = json.loads(Path(args.pricing).read_text(encoding='utf-8'))
    budget = EvaluationBudget(BACKEND/'storage/evals/stage-one-budget.sqlite', prices, run_id=RUN_ID, run_limit_cny='3')
    if not settings.DASHSCOPE_API_KEY or args.model not in free.available_models(qualified=False):
        free.refresh_quotas()
    if args.model not in free.available_models(qualified=False):
        raise ValueError('The selected model has no verified free-only quota')
    wire = []
    current = None
    def observe(kind, value, evidence):
        nonlocal current
        if kind == 'request':
            current = {'request': json.loads(json.dumps({k: v for k, v in value.items() if k in (
                'model', 'messages', 'tools', 'response_format', 'max_tokens', 'max_completion_tokens',
                'extra_body', 'stream', 'stream_options')}, ensure_ascii=False, default=str)),
                'evidence': json.loads(json.dumps(evidence or {}, ensure_ascii=False)), 'content': '', 'started': time.perf_counter()}
            wire.append(current)
        elif kind == 'chunk':
            for choice in value.choices:
                if choice.delta.content:
                    current.setdefault('first_token_ms', (time.perf_counter()-current['started'])*1000)
                    current['content'] += choice.delta.content
                if choice.finish_reason:
                    current['finish_reason'] = choice.finish_reason
            if value.usage:
                current['usage'] = value.usage.model_dump(mode='json')
        elif kind == 'response':
            current['response'] = value.model_dump(mode='json')
            current['usage'] = value.usage.model_dump(mode='json') if value.usage else None
        elif kind == 'error':
            body = getattr(value, 'body', {})
            detail = body.get('error', body) if isinstance(body, dict) else {}
            current['error'] = {'status': getattr(value, 'status_code', None), 'code': detail.get('code') if isinstance(detail, dict) else None}
        elif kind == 'internal_error':
            import traceback
            wire.append({'internal_error': type(value).__name__,
                'attribute': str(value) if isinstance(value, AttributeError) else None,
                'frames': [{'file': Path(f.filename).name, 'function': f.name, 'line': f.lineno} for f in traceback.extract_tb(value.__traceback__)]})
    observer_token = None
    if args.worker == 'optimized':
        from app.model_runtime import request_observer
        observer_token = request_observer.set(observe)
    else:
        # Frozen inference code is unchanged. Only the external transport gains
        # the same free-only preflight and synthetic wire recording.
        import app.model_adapter as adapter
        factory = adapter.AsyncOpenAI
        def guarded_factory(**options):
            client = factory(**options)
            original = client.chat.completions.create
            async def create(**request):
                receipt = free.reserve(request)
                observe('request', request, {})
                try:
                    response = await original(**request)
                except Exception as error:
                    observe('error', error, None)
                    raise
                free.settle(receipt, response.usage)
                observe('response', response, None)
                return response
            client.chat.completions.create = create
            return client
        adapter.AsyncOpenAI = guarded_factory
    from fastapi.testclient import TestClient
    from app.main import app
    token = current_budget.set(budget)
    try:
        with TestClient(app, raise_server_exceptions=False) as actual:
            client = StreamingClient(actual, streaming=args.worker == 'optimized')
            response = client.post('/api/v1/login/access-token', data={'username': 'synthetic-eval@example.com', 'password': 'SyntheticEval2026!'})
            headers = {'Authorization': 'Bearer '+response.json()['access_token']}
            print(json.dumps({'event': 'ready'}), flush=True)
            last_refresh = time.time()
            for line in sys.stdin:
                case = json.loads(line)
                if time.time()-last_refresh > 45:
                    free.refresh_quotas()
                    last_refresh = time.time()
                wire.clear()
                started = time.perf_counter()
                result = run_case(client, headers, pets, case)
                for entry in wire:
                    entry.pop('started', None)
                (folder/(case['id']+'-wire.json')).write_text(json.dumps(wire, ensure_ascii=False, indent=2), encoding='utf-8')
                row = {'id': case['id'], 'category': case['category'], **result,
                       'passed': all(result['checks'].values()), 'elapsed_ms': round((time.perf_counter()-started)*1000, 2)}
                print(json.dumps({'event': 'result', 'row': row, 'budget': budget.summary()}, ensure_ascii=True), flush=True)
    finally:
        current_budget.reset(token)
        if observer_token is not None:
            request_observer.reset(observer_token)


def read_event(process, kind):
    while True:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError('Isolated worker exited; inspect its private stderr')
        try:
            value = json.loads(line)
        except ValueError:
            continue  # Database initialization may print a non-protocol status line.
        if value.get('event') == kind:
            return value


def metrics(rows):
    turns = [turn for row in rows for turn in row['turns']]
    model_turns = [turn for turn in turns if (turn.get('execution') or {}).get('model_requests')]
    def distribution(values):
        values = sorted(values)
        if not values:
            return None
        import statistics
        return {'count': len(values), 'p50_ms': round(statistics.median(values), 2), 'p95_ms': round(values[max(0, math.ceil(.95*len(values))-1)], 2)}
    complete = [turn['result'].get('delivery_timing', {}).get('complete_ms', turn['execution']['elapsed_ms']) for turn in model_turns if turn['status'] == 200]
    first = [turn['execution'].get('stages_ms', {}).get('first_section', turn['result'].get('delivery_timing', {}).get('complete_ms', turn['execution']['elapsed_ms']))
             for turn in model_turns if turn['status'] == 200]
    def group(items):
        success = [t for t in items if t['status'] == 200]
        return {'turns': len(items), 'failures': len(items)-len(success),
            'complete': distribution([t['result'].get('delivery_timing', {}).get('complete_ms', t['execution']['elapsed_ms']) for t in success]),
            'first_section': distribution([t['execution'].get('stages_ms', {}).get('first_section', t['result'].get('delivery_timing', {}).get('complete_ms', t['execution']['elapsed_ms'])) for t in success]),
            'request_counts': [t['execution']['model_requests'] for t in items]}
    return {'cases': len(rows), 'passed': sum(row['passed'] for row in rows), 'failed': sum(not row['passed'] for row in rows),
            'complete_successful_model_answers': distribution(complete), 'first_visible_successful_model_answers': distribution(first),
            'ordinary': group([t for t in model_turns if t['result'].get('answer_depth') != 'detailed']),
            'detailed': group([t for t in model_turns if t['result'].get('answer_depth') == 'detailed']),
            'cached': group([t for t in model_turns if t['execution'].get('cached_input_tokens')]),
            'uncached': group([t for t in model_turns if not t['execution'].get('cached_input_tokens')]),
            'model_requests': sum((turn.get('execution') or {}).get('model_requests', 0) for turn in turns),
            'input_tokens': sum((turn.get('execution') or {}).get('input_tokens', 0) for turn in turns),
            'output_tokens': sum((turn.get('execution') or {}).get('output_tokens', 0) for turn in turns)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=('baseline', 'optimized'))
    parser.add_argument('--folder')
    parser.add_argument('--pricing')
    parser.add_argument('--model', choices=MODELS, default=MODELS[0])
    parser.add_argument('--variant', choices=('paired', 'optimized'), default='optimized')
    parser.add_argument('--count', type=int, default=30)
    parser.add_argument('--case-ids')
    parser.add_argument('--depth', choices=('auto', 'brief', 'detailed'))
    parser.add_argument('--sequential', action='store_true')
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return 0
    from evals.runner import load_cases
    dataset, dataset_hash = load_cases()
    ids = args.case_ids.split(',') if args.case_ids else ['CB-'+ident for ident in REVIEW_IDS]
    cases = [case for case in dataset['cases'] if case['id'] in ids][:args.count]
    if args.variant == 'paired' and not args.case_ids:
        cases = dataset['cases'][:args.count]
    if args.depth:
        cases = [{**case, 'answer_depth': args.depth} for case in cases]
    output = ROOT/'artifacts/evaluations'/(datetime.now(UTC).strftime('%Y%m%dT%H%M%S')+'-streaming-'+args.variant)
    output.mkdir(parents=True)
    prices = json.loads(Path(args.pricing).read_text(encoding='utf-8')) if args.pricing else verified_price(args.model)
    if prices['model'] != args.model:
        raise ValueError('Verified price snapshot does not match the selected model')
    price_file = output/'pricing.json'
    price_file.write_text(json.dumps(prices, indent=2), encoding='utf-8')
    variants = ['baseline', 'optimized'] if args.variant == 'paired' else ['optimized']
    report = {'created_at': datetime.now(UTC).isoformat(), 'model': args.model, 'run_id': RUN_ID,
              'dataset_sha256': dataset_hash, 'results': {name: [] for name in variants}, 'private_worker_folders': {},
              'benchmark_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'measurement': 'Server first checked section and complete validated response; browser network excluded'}
    from app.alibaba_quota import answer_build_hash
    report['answer_build_sha256'] = answer_build_hash()
    report['baseline_snapshot_sha256'] = hashlib.sha256((ROOT/'artifacts/chat-streaming-baseline/snapshot.json').read_bytes()).hexdigest()
    processes, logs = {}, []
    def save():
        report['metrics'] = {name: metrics(rows) for name, rows in report['results'].items()}
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        for variant in variants:
            folder = Path(tempfile.mkdtemp(prefix='stream-'+variant+'-', dir=BACKEND/'storage/evals'))
            source = BACKEND
            if variant == 'baseline':
                source = folder/'source'
                shutil.copytree(ROOT/'artifacts/chat-streaming-baseline/app', source/'app')
                shutil.copytree(BACKEND/'data', source/'data')
                # Measurement/config additions only; all frozen inference code and prompts remain intact.
                for relative in ('core/config.py', 'evaluation_budget.py', 'alibaba_quota.py'):
                    shutil.copy2(BACKEND/'app'/relative, source/'app'/relative)
                if args.model == 'qwen-flash':
                    # Minimal model hookup for a fair same-model baseline:
                    # qwen-flash supports JSON Object, not native JSON Schema.
                    adapter = source/'app/model_adapter.py'
                    original = adapter.read_text(encoding='utf-8')
                    compatible = original.replace('"supports_json_schema_output": True', '"supports_json_schema_output": False').replace(
                        'if selection.provider == "alibaba" else PromptedOutput(AgentAnswer)',
                        'if False else PromptedOutput(AgentAnswer)')
                    if compatible == original:
                        raise RuntimeError('Baseline capability overlay did not apply')
                    adapter.write_text(compatible, encoding='utf-8')
                    report['baseline_compatibility_overlay'] = {'reason': 'Qwen Flash JSON Object capability; frozen prompt/retrieval/agent logic unchanged',
                        'sha256': hashlib.sha256(compatible.encode()).hexdigest()}
            env = dict(os.environ, PYTHONUTF8='1', PYTHONPATH=str(source)+os.pathsep+str(BACKEND))
            log = (output/(variant+'-stderr.log')).open('w', encoding='utf-8')
            logs.append(log)
            process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker', variant,
                '--folder', str(folder), '--pricing', str(price_file), '--model', args.model], cwd=BACKEND, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            processes[variant] = process
            read_event(process, 'ready')
            report['private_worker_folders'][variant] = str(folder)
        for index, case in enumerate(cases):
            order = variants if index % 2 == 0 else list(reversed(variants))
            for variant in order:
                if args.sequential:
                    continue
                processes[variant].stdin.write(json.dumps(case)+'\n')
                processes[variant].stdin.flush()
            for variant in order:
                if args.sequential:
                    processes[variant].stdin.write(json.dumps(case)+'\n')
                    processes[variant].stdin.flush()
                result = read_event(processes[variant], 'result')
                report['results'][variant].append(result['row'])
                report['budget'] = result['budget']
                save()
                print(json.dumps({'case': case['id'], 'variant': variant, 'passed': result['row']['passed'],
                                  'elapsed_ms': result['row']['elapsed_ms'], 'run_used_cny': result['budget']['run_used_cny']}), flush=True)
                if any(turn['status'] in (429, 503, 504) for turn in result['row']['turns']):
                    report['stopped_reason'] = 'Budget, quota, provider, timeout or completeness failure; no automatic retry'
                    return 1
    finally:
        for process in processes.values():
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        for log in logs:
            log.close()
        save()
        print(json.dumps({'report': str(output), 'metrics': report['metrics']}), flush=True)
    return int(any(not row['passed'] for rows in report['results'].values() for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
