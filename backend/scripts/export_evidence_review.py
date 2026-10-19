"""Export reviewable synthetic QA and source decisions without credentials or wire logs."""
import argparse
import hashlib
import json
from pathlib import Path
from app.evidence_index import digest


def export(paired,holdout,target):
    packages={};runs=[]
    for folder in (paired,holdout):
        report_path=folder/'report.json';raw=report_path.read_bytes();report=json.loads(raw)
        summary=json.loads((folder/'source-review-summary.json').read_text(encoding='utf-8'))
        if summary['report_sha256']!=hashlib.sha256(raw).hexdigest():
            raise ValueError('Stale review summary')
        item={'report':folder.name,'report_sha256':summary['report_sha256'],
              'model':report['model'],'answer_build_sha256':report['answer_build_sha256'],
              'summary':summary,'cases':[]}
        if folder==paired:
            pairs=json.loads((folder/'review-input.json').read_text(encoding='utf-8'))
            notes=json.loads((folder/'editorial-notes.json').read_text(encoding='utf-8'))
            key=json.loads((folder/'private-review-key.json').read_text(encoding='utf-8'))
            claims=json.loads((folder/'major-claim-review.json').read_text(encoding='utf-8'))
            for pair in pairs:
                case={'id':pair['id'],'review':notes[pair['id']],'answers':{}}
                for label,answer in pair['answers'].items():
                    variant=key[pair['id']][label];requests=[]
                    for ri,req in enumerate(answer['requests']):
                        pid=digest(req['evidence']);packages[pid]=req['evidence']
                        units=[{k:v for k,v in c.items() if k not in ('all_supplied_evidence','user_facts','bound_evidence')}
                               for c in claims if c['case_id']==pair['id'] and c['variant']==variant and c['request']==ri]
                        requests.append({'input':req['input'],'evidence_package_sha256':pid,'units':units})
                    case['answers'][variant]={'anonymous_label':label,'turns':answer['turns'],
                        'actual_source_cards':answer['source_cards'],'requests':requests}
                item['cases'].append(case)
        else:
            rows=json.loads((folder/'holdout-review-input.json').read_text(encoding='utf-8'))
            claims=json.loads((folder/'major-claim-review.json').read_text(encoding='utf-8'))
            for row in rows:
                case={'id':row['id'],'status':row['status'],'requests':[]}
                for ri,req in enumerate(row['requests']):
                    pid=digest(req['evidence']);packages[pid]=req['evidence']
                    units=[{k:v for k,v in c.items() if k!='bound_evidence'} for c in claims
                           if c['case_id']==row['id'] and c['request']==ri]
                    case['requests'].append({'input':req['input'],'subquestions':req['subquestions'],
                        'evidence_package_sha256':pid,'units':units})
                item['cases'].append(case)
        runs.append(item)
    output={'date':'2026-10-20','synthetic_accounts_only':True,'activated':False,
        'method':'Assistant editorial source review, not independent or veterinary. Anonymous paired decisions sealed before version decoding. Sentence/action groups retain full paragraph context; any unsupported component fails the group. Repeated assertions remain visible and counted as occurrences, not unique medical facts.',
        'runs':runs,'actual_evidence_packages':packages}
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                      'reviewed_system_cases':sum(len(r['cases']) for r in runs),'evidence_packages':len(packages)}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--paired',type=Path,required=True);p.add_argument('--holdout',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    export(a.paired,a.holdout,a.output)


if __name__=='__main__':main()
