"""Do not make a failed detailed answer disappear from its timing group."""
from evals.streaming_compare import metrics


def test_failed_detailed_response_remains_in_detailed_group():
    rows=[{'id':'x','passed':False,'requested_answer_depth':'detailed','turns':[
        {'status':502,'result':{'detail':'withdrawn'},'execution':{'model_requests':1,'elapsed_ms':90}}]}]
    result=metrics(rows)
    assert result['detailed']['turns']==result['detailed']['failures']==1
    assert result['ordinary']['turns']==0
    assert result['detailed']['complete'] is None


def test_historical_report_depth_is_restored_without_editing_raw_rows():
    row={'id':'x','passed':False,'turns':[{'status':502,'result':{},'execution':{'model_requests':1,'elapsed_ms':90}}]}
    assert metrics([row],{'x':'detailed'})['detailed']['failures']==1
    assert 'requested_answer_depth' not in row and '_depth' not in row['turns'][0]
