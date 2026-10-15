"""Replay saved synthetic streamed answers through the current local validators.

This makes a later stricter guard auditable without spending tokens to generate
different answers. It never changes original measurements or original failures.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from fastapi import HTTPException
from app.answer_sections import SectionAnswer, evidence_map, bind_section, check_text
from app.alibaba_quota import answer_build_hash


def recheck(path):
    report = json.loads(path.read_text(encoding='utf-8'))
    failures, checked = [], 0
    for row in report['results']['optimized']:
        wires = json.loads((Path(report['private_worker_folders']['optimized'])/(row['id']+'-wire.json')).read_text(encoding='utf-8'))
        for index, wire in enumerate(wires):
            if wire.get('finish_reason') != 'stop' or not wire.get('request', {}).get('stream'):
                continue
            payload = json.loads(wire['request']['messages'][-1]['content'])
            sources = {s['id']: s for t in row['turns'] for s in t.get('result', {}).get('sources', [])}
            retrieved = {aid: {'title': sources.get(aid, {}).get('title', aid),
                'source_url': sources.get(aid, {}).get('url', ''),
                'source_organization': sources.get(aid, {}).get('organization', '')} for aid in wire['evidence']}
            ctx = SimpleNamespace(sent_evidence=wire['evidence'], retrieved=retrieved,
                effective_context=payload['supplemental_context'], current_text=payload['user_message'],
                analysis={'tool_results': payload.get('tool_results', {})})
            try:
                answer = SectionAnswer.model_validate_json(wire['content'])
                ev = evidence_map(ctx)
                parts = [bind_section(s, ev, payload['subquestions'], payload['current_profile'], ctx) for s in answer.sections]
                if {q for s in answer.sections for q in s.question_ids} != set(range(1, len(payload['subquestions'])+1)):
                    raise HTTPException(502, '问题覆盖不全')
                check_text('\n\n'.join(p['text'] for p in parts), payload['current_profile'], ctx)
                checked += 1
            except Exception as error:
                failures.append({'case': row['id'], 'wire': index,
                    'reason': error.detail if isinstance(error, HTTPException) else type(error).__name__})
    return {'report': str(path.resolve()), 'report_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'generated_build_sha256': report['answer_build_sha256'], 'validated_build_sha256': answer_build_hash(),
        'case_count': len(report['results']['optimized']), 'checked_complete_streams': checked,
        'current_validation_failures': failures,
        'original_failed_cases': [r['id'] for r in report['results']['optimized'] if not r['passed']],
        'method': 'Replay exact saved output and actual supplied evidence; no new inference; original timings retained'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = recheck(args.report)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
