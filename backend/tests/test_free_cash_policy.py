"""Explicit free-only calls do not consume the user's paid DeepSeek ceiling."""
import json
import time
from datetime import datetime,UTC
from pathlib import Path
from types import SimpleNamespace
import pytest
from app import alibaba_quota as free
from app.alibaba_models import ordered_candidates,family,supports_schema
from app.core.config import settings
from app.evaluation_budget import EvaluationBudget,BudgetExceeded


@pytest.fixture
def verified(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'DASHSCOPE_QUOTA_FILE',str(tmp_path/'quota.json'))
    monkeypatch.setattr(settings,'DASHSCOPE_QUALIFIED_FILE',str(tmp_path/'qualified.json'))
    monkeypatch.setattr(settings,'DASHSCOPE_API_KEY','synthetic-free-key')
    monkeypatch.setattr(settings,'DASHSCOPE_WORKSPACE_ID','synthetic-workspace')
    monkeypatch.setattr(settings,'DASHSCOPE_FREE_MODELS','auto')
    monkeypatch.setattr(settings,'DASHSCOPE_FREE_ONLY',True)
    data={'checked_at':time.time(),'credential_scope':free.credential_scope(),'workspace_verified':True,
          'models':[{'model':'deepseek-v4-pro-0813','type':'Text','remaining':1000000,'expires':'2099-01-01','autoStop':True}]}
    Path(settings.DASHSCOPE_QUOTA_FILE).write_text(json.dumps(data),encoding='utf-8')
    return data


def price(model='deepseek-v4-pro-0813'):
    return {'currency':'CNY','provider':'alibaba','model':model,'billing_mode':'verified_free',
            'checked_at':datetime.now(UTC).isoformat()}


def request():
    return {'model':'deepseek-v4-pro-0813','messages':[{'role':'user','content':'synthetic'}],
            'max_tokens':100,'stream':True,'stream_options':{'include_usage':True},
            'extra_body':{'enable_thinking':False}}


def test_all_named_strong_models_are_discoverable_without_aliasing_paid_endpoint():
    names=['deepseek-v4-pro-0813','deepseek-v4-flash-0731','deepseek-v4.1-flash-1017','qwen3.8-27b','glm-5.1']
    rows=[{'model':n,'type':'Text'} for n in names+['qwen-vl-ocr','text-embedding-v3','unknown-future']]
    assert set(ordered_candidates(rows))==set(names)
    assert ordered_candidates(rows)[0]=='deepseek-v4-pro-0813'
    assert all(family(n) for n in names)
    assert not supports_schema('deepseek-v4.1-flash-1017')


def test_free_accounting_requires_explicit_policy_authorization(verified,tmp_path):
    with pytest.raises(ValueError,match='explicit authorization'):
        EvaluationBudget(tmp_path/'ledger.db',price())


def test_free_calls_work_when_paid_ceiling_is_exhausted_and_preserve_unknowns(verified,tmp_path):
    budget=EvaluationBudget(tmp_path/'ledger.db',price(),authorized_budget_scope='paid_only')
    with budget.connect() as db:
        db.execute("INSERT INTO charges(id,amount_micro,state,provider) VALUES ('old',10000000,'usage_estimate','deepseek')")
        db.execute("INSERT INTO charges(id,amount_micro,state,provider) VALUES ('unknown',200000,'reserved','alibaba')")
    for _ in range(5):
        receipt=free.reserve(request())
        ident=budget.reserve(request())
        budget.settle(ident,SimpleNamespace(prompt_tokens=12,completion_tokens=5))
        free.settle(receipt,SimpleNamespace(prompt_tokens=12,completion_tokens=5))
    summary=budget.summary()
    assert summary['conservative_used_cny']==summary['cash_budget_used_cny']==10.2
    assert summary['unresolved_reservations']==1
    with budget.connect() as db:
        assert db.execute("SELECT amount_micro FROM charges WHERE id='unknown'").fetchone()[0]==200000
        assert db.execute("SELECT COUNT(*) FROM charges WHERE amount_micro=0 AND provider='alibaba'").fetchone()[0]==5
    paid={'currency':'CNY','model':'deepseek-flash','checked_at':datetime.now(UTC).isoformat(),
          'peak_input_cache_miss_per_million':2,'peak_output_per_million':8}
    paid_budget=EvaluationBudget(tmp_path/'ledger.db',paid)
    with pytest.raises(BudgetExceeded):
        paid_budget.reserve({**request(),'model':'deepseek-flash','extra_body':{'thinking':{'type':'disabled'}}})


def test_cash_scope_keeps_historical_reference_amounts_and_all_unresolved_liabilities(verified,tmp_path):
    budget=EvaluationBudget(tmp_path/'ledger.db',price(),authorized_budget_scope='paid_only')
    with budget.connect() as db:
        db.executemany('INSERT INTO charges(id,amount_micro,state,provider) VALUES (?,?,?,?)',[
            ('free-old',3000000,'usage_estimate','alibaba'),('paid-old',1200000,'usage_estimate','deepseek'),
            ('unidentified',700000,'usage_estimate',None),('unresolved',100000,'reserved','alibaba')])
    summary=budget.summary()
    assert summary['conservative_used_cny']==5
    assert summary['cash_budget_used_cny']==2
    assert summary['unresolved_reservations']==1


@pytest.mark.parametrize('fault',['stop_off','expired','quota_expired','wrong_key','missing_snapshot'])
def test_zero_cash_mode_never_bypasses_free_eligibility(verified,tmp_path,monkeypatch,fault):
    budget=EvaluationBudget(tmp_path/'ledger.db',price(),authorized_budget_scope='paid_only')
    if fault=='stop_off': verified['models'][0]['autoStop']=False
    if fault=='expired': verified['checked_at']-=1000
    if fault=='quota_expired': verified['models'][0]['expires']='2000-01-01'
    if fault=='wrong_key': monkeypatch.setattr(settings,'DASHSCOPE_API_KEY','changed')
    if fault=='missing_snapshot': verified={}
    Path(settings.DASHSCOPE_QUOTA_FILE).write_text(json.dumps(verified),encoding='utf-8')
    with pytest.raises(ValueError,match='free-only quota'):
        budget.reserve(request())


def test_free_preflight_ignores_cash_and_checks_tokens():
    from evals.quality_compare import preflight
    budget={'conservative_used_cny':99,'run_used_cny':99,'run_limit_cny':10}
    cases=[{'turns':['synthetic']}]
    assert preflight(cases,1000000,budget,pricing=price())['allowed']
    assert preflight(cases,0,budget,pricing=price())['reasons']==['insufficient_verified_free_tokens']


def test_exhausted_strong_model_rotates_to_next_reviewed_family(verified,monkeypatch):
    names=['deepseek-v4-pro-0813','deepseek-v4.1-flash-1017','qwen3.8-27b']
    verified['models']=[{**verified['models'][0],'model':name} for name in names]
    Path(settings.DASHSCOPE_QUOTA_FILE).write_text(json.dumps(verified),encoding='utf-8')
    approval={'order':names,'models':{name:{'approved':True,'case_count':30,'answer_build_sha256':'synthetic-build'} for name in names}}
    Path(settings.DASHSCOPE_QUALIFIED_FILE).write_text(json.dumps(approval),encoding='utf-8')
    monkeypatch.setattr(free,'answer_build_hash',lambda:'synthetic-build')
    assert free.choose_model()==names[0]
    free.mark_exhausted(names[0])
    assert free.choose_model()==names[1]
    free.mark_exhausted(names[1])
    assert free.choose_model()==names[2]


def test_console_expired_error_is_read_from_stderr_without_exposing_provider_body(monkeypatch):
    monkeypatch.setattr(free,'cli_path',lambda:'official-cli')
    monkeypatch.setattr(free.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=3,stdout='',
        stderr=json.dumps({'error':{'code':3,'message':'Console session is not logged in or has expired.','secret':'do-not-print'}})))
    with pytest.raises(RuntimeError,match='session expired') as error:
        free.cli_call(['workspace','list'])
    assert 'do-not-print' not in str(error.value)
