"""Publish compact audit facts from immutable local runs; never call a model."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path
from evals.streaming_compare import metrics
from app.alibaba_quota import answer_build_hash

ROOT=Path(__file__).resolve().parents[2]


def paired_latency(results):
    samples=[]
    for before,after in zip(results.get('baseline',[]),results.get('optimized',[]),strict=True):
        assert before['id']==after['id']
        for left,right in zip(before['turns'],after['turns'],strict=True):
            if any(t['status']!=200 or not (t.get('execution') or {}).get('model_requests') for t in (left,right)):
                continue
            timing=[t['result'].get('delivery_timing',{}).get('browser_complete_visible_ms') for t in (left,right)]
            if all(v is not None for v in timing):
                samples.append(timing)
    if not samples:
        return None
    before,after=[statistics.median([s[i] for s in samples]) for i in (0,1)]
    return {'matched_successful_turns':len(samples),'baseline_median_ms':round(before,2),
            'candidate_median_ms':round(after,2),'median_speedup_percent':round(100*(before-after)/before,2),
            'failed_outputs_excluded_but_retained':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',action='append',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/evidence-acceptance-20261019.json')
    args=parser.parse_args()
    normalized=[]
    registry=json.loads((ROOT/'backend/evals/evidence_dataset_registry.json').read_text(encoding='utf-8'))
    dataset_names={d['sha256']:d['file'] for d in registry['datasets']}
    for path in args.report:
        path=path.resolve()
        raw=path.read_bytes()
        report=json.loads(raw)
        executed=next((rows for rows in report['results'].values() if rows),None)
        if not executed:
            continue  # Preflight-only reports are preserved, not quality samples.
        ident=executed[0]['id']
        name='quality_holdout_v7.json' if ident.startswith('EQ-') else 'quality_holdout_v6.json' if ident.startswith('EX-') else 'quality_holdout_v5.json' if ident.startswith('EV-') else 'quality_holdout_v4.json' if ident.startswith('EG-') else 'quality_holdout_v3.json' if ident.startswith('EF-') else 'quality_holdout_v2.json' if ident.startswith('EH-') else 'cases.v1.json'
        name=dataset_names.get(report['dataset_sha256'],name)
        cases=json.loads((ROOT/'backend/evals'/name).read_text(encoding='utf-8'))['cases']
        depths={c['id']:c.get('answer_depth','auto') for c in cases}
        row={'report':path.relative_to(ROOT).as_posix(),'report_sha256':hashlib.sha256(raw).hexdigest(),
             'answer_build_sha256':report['answer_build_sha256'],'model':report['model'],
             'dataset':name,'dataset_sha256':report['dataset_sha256'],
             'actual_model_pair_count':report.get('actual_model_pair_count',29 if name=='cases.v1.json' else None),
             'local_guard_case_ids':report.get('local_guard_case_ids',['CB-049'] if name=='cases.v1.json' else []),
             'pair_selection_sha256':report.get('pair_selection_sha256'),
             'metrics':{v:metrics(rows,depths) for v,rows in report['results'].items()},
             'failures':{v:[r['id'] for r in rows if not r['passed']] for v,rows in report['results'].items()},
             'paired_browser_complete':paired_latency(report['results']) if 'baseline' in report['results'] else None,
             'source_review_status':'pending',
             'budget_after':report['budget']}
        reviewed=path.parent/'source-review-summary.json'
        if reviewed.exists():
            row['source_review']=json.loads(reviewed.read_text(encoding='utf-8'))
            if 'major_claim_support' in row['source_review'] and (
                row['source_review'].get('answer_build_sha256')!=report['answer_build_sha256']
                or row['source_review'].get('report_sha256')!=hashlib.sha256(raw).hexdigest()):
                raise ValueError('Stale major-claim review: '+str(reviewed))
            row['source_review_status']='assistant_anonymous_review_not_independent_or_veterinary'
        normalized.append(row)
    annotation=json.loads((ROOT/'backend/data/evidence/annotations.json').read_text(encoding='utf-8'))
    build=answer_build_hash()
    index=json.loads((ROOT/'backend/data/evidence/index.json').read_text(encoding='utf-8'))
    pending_sources=[sid for sid,s in annotation['sources'].items() if s['verification_status']!='page_rechecked']
    gates={key:False for key in ('all_articles_source_checked','quality_30_pairs','zero_regression',
            'major_claim_support_95','fresh_holdout','first_visible_latency','ordinary_complete_latency','median_speedup_30')}
    gates['all_articles_source_checked']=len(annotation['articles'])==95 and not pending_sources and all(c.get('claim_review_status')=='checked' for c in index['chunks'])
    matching=[r for r in normalized if r['answer_build_sha256']==build]
    paired=next((r for r in reversed(matching) if r['dataset']=='cases.v1.json'
                 and r.get('actual_model_pair_count',0)>=30
                 and r['metrics'].get('baseline',{}).get('cases')==r['metrics'].get('optimized',{}).get('cases')),None)
    if paired:
        review=paired.get('source_review',{})
        preferences=review.get('preference',{})
        complete_review=review.get('reviewed_model_pairs')==paired['actual_model_pair_count'] and sum(preferences.values())==paired['actual_model_pair_count']
        gates['quality_30_pairs']=complete_review and preferences.get('optimized',0)>=20
        gates['zero_regression']=complete_review and preferences.get('baseline',1)==0 and preferences.get('not_comparable',1)==0 and review.get('severe_candidate_issues',1)==0 and review.get('reasked_known_fields',{}).get('optimized',1)==0
        claims=review.get('major_claim_support',{}).get('optimized',{})
        gates['major_claim_support_95']=claims.get('total',0)>0 and claims.get('supported',0)/claims['total']>=.95
        gates['median_speedup_30']=(paired.get('paired_browser_complete') or {}).get('median_speedup_percent',-100)>=30
        observed=paired['metrics']['optimized']
        def meets(group,key,p50,p95):
            values=observed[group].get(key) or {}
            return values.get('count',0)>=20 and values.get('p50_ms',float('inf'))<=p50 and values.get('p95_ms',float('inf'))<=p95
        gates['first_visible_latency']=all(meets(group,'browser_first_visible',1500,3000) for group in ('ordinary','detailed','cached','uncached'))
        gates['ordinary_complete_latency']=meets('ordinary','browser_complete_visible',3000,6000)
    holdout=next((r for r in reversed(matching) if r['dataset'].startswith('quality_holdout')
                 and paired and r['model']==paired['model']),None)
    gates['fresh_holdout']=bool(holdout and holdout['metrics']['optimized']['cases']==10 and holdout['metrics']['optimized']['passed']==10 and holdout.get('source_review',{}).get('all_delivered_main_claims_supported') is True)
    output={'date':'2026-10-20','answer_build_sha256':build,
        'releasable':all(gates.values()),'activated':False,
        'gates':gates,
        'article_count':len(annotation['articles']),
        'source_count':len(annotation['sources']),
        'pending_source_ids':pending_sources,
        'runs':normalized,'budget':normalized[-1]['budget_after'],
        'limitations':[
            'Automatic pass is application validation, not expert factual quality.',
            'Anonymous assistant editorial source review is not independent or veterinary review. Paragraph and explicit major-claim metrics are separate.',
            'Previous 30-pair results retain their original build identities. Do not transfer their scores or timings to the final build.',
            'Latency includes only successful complete model answers; failed attempts remain in failures and original reports.',
            'Cached means provider reported some input cache tokens; not whole-prompt or application answer-cache hit.',
            'Cold/provider-uncached and detailed samples are insufficient to claim percentile targets.',
            'Full-corpus source and claim provenance is an assistant editorial review; unreviewed veterinary status retained.',
            'Verified free Alibaba calls have zero cash cost and no cash cap; paid/unknown liability remains in the original capped ledger. Historical reference amounts are not a provider invoice.'
        ]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'build':output['answer_build_sha256'],'budget':output['budget']['conservative_used_cny'],
                      'runs':len(normalized),'releasable':output['releasable']}))


if __name__=='__main__':
    main()
