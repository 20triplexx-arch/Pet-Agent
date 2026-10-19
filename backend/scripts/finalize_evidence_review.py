"""Seal explicit editorial decisions, then decode anonymous version labels.

No language model or automatic truth scoring is used. Each reviewed case must
name the exact unit inventory hash and record all unsupported units explicitly.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha(value):
    return hashlib.sha256(value).hexdigest()


def inventory(pair):
    return [(label,ri,u['id'],u['text']) for label,a in pair['answers'].items()
            for ri,r in enumerate(a['requests']) for u in r['units']]


def inventory_hash(pair):
    return sha(json.dumps(inventory(pair),ensure_ascii=False,separators=(',',':')).encode())


def finalize(folder):
    input_path=folder/'review-input.json';notes_path=folder/'editorial-notes.json'
    pairs=json.loads(input_path.read_text(encoding='utf-8'))
    notes=json.loads(notes_path.read_text(encoding='utf-8'))
    if {p['id'] for p in pairs}!=set(notes):
        raise ValueError('Every anonymous pair needs an explicit review')
    for pair in pairs:
        note=notes[pair['id']]
        if note.get('reviewed_unit_inventory_sha256')!=inventory_hash(pair):
            raise ValueError('Review missing or stale: '+pair['id'])
        units={(label,ri,uid) for label,ri,uid,text in inventory(pair)}
        issues={(i['label'],i['request'],i['unit']) for i in note['issues'] if i.get('unsupported',True)}
        if not issues<=units:
            raise ValueError('Issue locator does not exist: '+pair['id'])
    seal_path=folder/'editorial-final-seal.json'
    seal={'review_input_sha256':sha(input_path.read_bytes()),'notes_sha256':sha(notes_path.read_bytes()),
          'method':'Explicit assistant editorial source review; not independent or veterinary. Source traceability included in overall preference; text separately judged.',
          'major_claim_unit':'Full sentences or semicolon-separated action/condition groups, whole paragraph retained as context; any unsupported component fails the group.',
          'version_key_opened_before_seal':False}
    if seal_path.exists():
        if json.loads(seal_path.read_text(encoding='utf-8'))!=seal:
            raise ValueError('Do not overwrite a sealed review')
    else:seal_path.write_text(json.dumps(seal,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # This is intentionally after sealing. No decisions depend on the key.
    key=json.loads((folder/'private-review-key.json').read_text(encoding='utf-8'))
    report_path=folder/'report.json';report=json.loads(report_path.read_text(encoding='utf-8'))
    guards=set(report.get('local_guard_case_ids',['CB-049']))
    preferences=Counter({k:0 for k in ('baseline','optimized','tie','not_comparable')})
    text_preferences=preferences.copy();claims={v:Counter(total=0,supported=0,delivered_total=0,delivered_supported=0) for v in ('baseline','optimized')}
    detailed=[];severe=Counter();format_failures=Counter();reasked=Counter()
    for pair in pairs:
        cid=pair['id'];note=notes[cid]
        if cid not in guards:
            preferences[key[cid].get(note['preference'],note['preference'])]+=1
            text_preferences[key[cid].get(note['text_preference'],note['text_preference'])]+=1
        for label,a in pair['answers'].items():
            variant=key[cid][label]
            issues={(i['request'],i['unit']):i for i in note['issues'] if i['label']==label}
            reasked[variant]+=sum(bool(i.get('reasked_known_field')) for i in issues.values())
            delivered=all(t['status']==200 for t in a['turns'])
            if not delivered:format_failures[variant]+=1
            for ri,request in enumerate(a['requests']):
                for u in request['units']:
                    issue=issues.get((ri,u['id']))
                    supported=not issue or not issue.get('unsupported',True)
                    claims[variant]['total']+=1;claims[variant]['supported']+=int(supported)
                    if delivered:
                        claims[variant]['delivered_total']+=1;claims[variant]['delivered_supported']+=int(supported)
                    severe[variant]+=int(bool(issue and issue.get('severe')))
                    detailed.append({'case_id':cid,'variant':variant,'request':ri,**u,
                        'judgement':'supported' if supported else 'unsupported',
                        'reason':issue['reason'] if issue else note['support_basis'],
                        'bound_evidence':{ref:request['evidence'].get(ref) for ref in u['evidence_ids']},
                        'all_supplied_evidence':request['evidence'],
                        'user_facts':request.get('answer_context'), 'delivered':delivered})
    (folder/'major-claim-review.json').write_text(json.dumps(detailed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    output={'report_sha256':sha(report_path.read_bytes()),'answer_build_sha256':report['answer_build_sha256'],
        'reviewed_pairs':len(pairs),'reviewed_model_pairs':len(pairs)-len(guards),'local_guard_pairs':len(guards),
        'preference':dict(preferences),'text_preference':dict(text_preferences),
        'major_claim_support':{v:dict(c) for v,c in claims.items()},
        'severe_candidate_issues':severe['optimized'],'severe_raw_issues':dict(severe),
        'reasked_known_fields':dict(reasked),
        'delivery_failure_cases':dict(format_failures),**seal}
    (folder/'source-review-summary.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    print(json.dumps(finalize(p.parse_args().folder),ensure_ascii=False))


if __name__=='__main__':main()
