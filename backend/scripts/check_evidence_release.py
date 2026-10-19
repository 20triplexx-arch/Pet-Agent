"""Read-only release gate. Never changes the database or model eligibility.

The reproducible index check is separate from source and live-quality gates.
Unreviewed/insufficient evidence must stay visible even when unit tests pass.
"""
import argparse
import json
from pathlib import Path
from app.evidence_index import build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acceptance-report', type=Path)
    args = parser.parse_args()
    data = Path(__file__).resolve().parents[1] / 'data'
    annotations = json.loads((data/'evidence/annotations.json').read_text(encoding='utf-8'))
    articles = [a for p in sorted(data.glob('knowledge*.json')) for a in json.loads(p.read_text(encoding='utf-8'))]
    stored = json.loads((data/'evidence/index.json').read_text(encoding='utf-8'))
    rebuilt = build_index(articles, annotations, stored)
    errors = []
    if rebuilt != stored:
        errors.append('stale_evidence_index')
    pending = [sid for sid, source in annotations['sources'].items()
               if source['verification_status'] != 'page_rechecked'
               or '待复核' in source['locator']]
    if pending:
        errors.append('source_locators_or_support_pending')
    pending_claims = [c['chunk_id'] for c in stored['chunks'] if c.get('claim_review_status')!='checked']
    if pending_claims:
        errors.append('granular_claim_support_review_pending')
    acceptance = json.loads(args.acceptance_report.read_text(encoding='utf-8')) if args.acceptance_report else {}
    if acceptance.get('answer_build_sha256') != __import__('app.alibaba_quota',fromlist=['answer_build_hash']).answer_build_hash():
        errors.append('missing_or_stale_acceptance_report')
    for gate in ('all_articles_source_checked','quality_30_pairs','zero_regression',
                 'major_claim_support_95','fresh_holdout','first_visible_latency',
                 'ordinary_complete_latency','median_speedup_30'):
        if acceptance.get('gates',{}).get(gate) is not True:
            errors.append(gate)
    print(json.dumps({'releasable':not errors,'errors':errors,'pending_source_ids':pending,
                      'pending_claim_review_count':len(pending_claims),
                      'article_count':len(articles),'chunk_count':len(stored['chunks'])},ensure_ascii=False,indent=2))
    return int(bool(errors))


if __name__=='__main__':
    raise SystemExit(main())
