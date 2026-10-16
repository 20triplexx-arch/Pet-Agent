"""Complete quota discovery and per-family transport; never calls a real model."""
import json
from types import SimpleNamespace
from datetime import datetime, UTC
import pytest
from app import alibaba_quota as quota
from app.alibaba_models import family, supports_schema, ordered_candidates
from app.core.config import settings
from app.evaluation_budget import EvaluationBudget


@pytest.mark.parametrize('name,native', [('qwen3.7-plus',True),('qwen3.7-plus-2026-05-26',True),
                                      ('qwen3.6-flash',False),('qwen3.5-flash',False),
                                      ('qwen-flash-2025-07-28',False),('qwen3.7-max',True)])
def test_general_chat_capabilities_are_not_inferred_from_provider_alone(name,native):
    from app.model_adapter import native_schema
    assert family(name) and supports_schema(name) is native
    assert native_schema(SimpleNamespace(provider='alibaba',name=name)) is native


def test_specialized_or_unknown_models_are_not_auto_promoted():
    rows=[{'model':name,'type':kind} for name,kind in [('qwen3.7-plus','Text'),('qwen-vl-ocr','Text'),
        ('qwen3-coder-flash','Text'),('qwen3.8-omni-flash','Multimodal'),('wan3.0-video','Vision'),('future-unknown','Text')]]
    assert ordered_candidates(rows)==['qwen3.7-plus']


def test_complete_console_catalog_is_stored_but_unreviewed_models_stay_unavailable(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'DASHSCOPE_QUOTA_FILE',str(tmp_path/'quota.json'))
    monkeypatch.setattr(settings,'DASHSCOPE_QUALIFIED_FILE',str(tmp_path/'approved.json'))
    monkeypatch.setattr(settings,'DASHSCOPE_FREE_MODELS','auto')
    monkeypatch.setattr(settings,'DASHSCOPE_API_KEY','synthetic-key')
    monkeypatch.setattr(settings,'DASHSCOPE_WORKSPACE_ID','synthetic-workspace')
    calls=[]
    def cli(args):
        calls.append(args)
        if args[0]=='workspace': return [{'id':'synthetic-workspace'}]
        return [{'model':name,'type':kind,'remaining':1000000,'expires':'2099-01-01','autoStop':True}
                for name,kind in [('qwen3.7-plus','Text'),('qwen3.6-flash','Text'),('wan3.0-video','Vision')]]
    monkeypatch.setattr(quota,'cli_call',cli)
    assert len(quota.refresh_quotas())==3
    assert any('--all' in args for args in calls)
    assert quota.configured_models()==['qwen3.7-plus','qwen3.6-flash']
    assert quota.available_models(qualified=False)==['qwen3.7-plus','qwen3.6-flash']
    assert quota.available_models()==[]


@pytest.mark.parametrize('name', ['qwen3.7-plus','qwen3.6-flash','qwen3.5-flash'])
def test_new_tariffs_are_verified_and_share_the_existing_ceiling(tmp_path,name):
    from evals.alibaba_prices import verified_price,TARIFFS
    values=TARIFFS[name]
    page=name+' 模型价格 华北2（北京） '+ ' '.join(f'输入 {i} 每百万tokens 输出 {o} 每百万tokens' for _,i,o in values)+' 新加坡'
    pricing=verified_price(name,page)
    budget=EvaluationBudget(tmp_path/'budget.sqlite',pricing,run_id='same-run',run_limit_cny='3')
    assert budget.provider=='alibaba' and budget.output_token_limit==4096
    assert budget.cost(1000,100)>0
    with pytest.raises(ValueError): verified_price(name,page.replace('输出 ','输出 999 ',1))


def test_evaluation_worker_sets_environment_before_importing_runtime():
    import os
    import subprocess
    import sys
    code = '''import sys,types
stub=types.ModuleType('evals.streaming_compare')
def worker(args):
    assert 'app.core.config' not in sys.modules
    assert args.model=='qwen3.7-plus' and args.capability_overlay
    print('isolated-bootstrap-ok')
stub.worker=worker
sys.modules['evals.streaming_compare']=stub
sys.argv=['quality_compare','--worker','--model','qwen3.7-plus']
from evals.quality_compare import main
main()
'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,env={**os.environ,'PYTHONUTF8':'1'})
    assert result.returncode==0, result.stderr
    assert 'isolated-bootstrap-ok' in result.stdout


def test_comparator_keeps_old_local_json_rejections_without_retrying_or_hiding_failure():
    from evals.quality_compare import stop_for_failure
    row = {'turns': [{'status': 503}]}
    wire = [{'internal_error': 'ValidationError', 'frames': [{'file': 'answer_sections.py'}]}]
    assert not stop_for_failure(row, wire)
    assert row['turns'][0]['status'] == 503
    assert stop_for_failure(row, [])
    assert stop_for_failure({'turns': [{'status': 429}]}, wire)
    assert stop_for_failure({'turns': [{'status': 504}]}, wire)


def test_resume_refuses_changed_answer_build_before_quota_or_inference(tmp_path, monkeypatch):
    import sys
    from evals import quality_compare
    from evals.runner import load_cases
    _, dataset_hash = load_cases()
    prior = {'model':'qwen3.6-flash', 'variant':'paired', 'baseline_commit':quality_compare.BASELINE,
             'dataset_sha256':dataset_hash, 'answer_build_sha256':'a-different-build'}
    (tmp_path/'report.json').write_text(json.dumps(prior), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['quality_compare', '--model', 'qwen3.6-flash', '--resume', str(tmp_path)])
    monkeypatch.setattr(quota, 'refresh_quotas', lambda: pytest.fail('Changed build must not reach quota or inference'))
    with pytest.raises(ValueError, match='answer_build_sha256'):
        quality_compare.main()
