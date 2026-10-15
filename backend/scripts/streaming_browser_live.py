"""Opt-in synthetic browser timing server, guarded by the shared live-test ledger."""
import json
import os
from pathlib import Path
import tempfile

BACKEND = Path(__file__).resolve().parents[1]


def prepare():
    from evals.streaming_compare import RUN_ID, verified_price
    os.environ.update({'DEMO_MODE': 'false', 'MODEL_PROVIDER': 'alibaba',
        'DASHSCOPE_MODEL': os.environ.get('STREAMING_BROWSER_MODEL', 'qwen3.8-flash'), 'DASHSCOPE_AUTO_SELECT': 'false',
        'DASHSCOPE_FREE_ONLY': 'true', 'MODEL_MAX_OUTPUT_TOKENS': '4096',
        'MODEL_LIMITS_ENABLED': 'false', 'MODEL_API_KEY': '', 'DEEPSEEK_API_KEY': '',
        'DASHSCOPE_QUOTA_FILE': str(BACKEND/'storage/alibaba-quota.json'),
        'DASHSCOPE_CLI_CONFIG_DIR': str(BACKEND/'storage/bailian-cli')})
    folder = Path(tempfile.mkdtemp(prefix='stream-browser-live-', dir=BACKEND/'storage/evals'))
    from evals.runner import setup_database
    pets = setup_database(folder)
    from app.evaluation_budget import EvaluationBudget, current_budget
    from app.main import app
    budget = EvaluationBudget(BACKEND/'storage/evals/stage-one-budget.sqlite',
        verified_price(os.environ['DASHSCOPE_MODEL']), run_id=RUN_ID, run_limit_cny='3')
    class BudgetApplication:
        async def __call__(self, scope, receive, send):
            token = current_budget.set(budget)
            try:
                await app(scope, receive, send)
            finally:
                current_budget.reset(token)
    (BACKEND.parent/'artifacts/streaming-browser-live-session.json').write_text(json.dumps(
        {'folder': str(folder), 'pets': pets, 'model': os.environ['DASHSCOPE_MODEL']}, indent=2), encoding='utf-8')
    return BudgetApplication()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(prepare(), host='127.0.0.1', port=8013, log_level='warning')
