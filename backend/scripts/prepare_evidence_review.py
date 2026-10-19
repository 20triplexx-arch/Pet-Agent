"""Export anonymous source-review inputs without opening the version key.

Claim units are review candidates, not automatic truth judgements. The reviewer
must explicitly classify every unit and retain rejected model output.
"""
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from evals.quality_compare import blind_review


def prepare(folder, partial=False):
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if partial:
        report=copy.deepcopy(report)
        common=set.intersection(*[{r['id'] for r in rows} for rows in report['results'].values()])
        report['results']={v:[r for r in rows if r['id'] in common] for v,rows in report['results'].items()}
    blind_path=folder/'blind-review.json'
    if not blind_path.exists() or partial:
        blind_review(report,folder)
    pairs=json.loads(blind_path.read_text(encoding='utf-8'))
    result=[]
    for pair in pairs:
        output={'id':pair['id'],'answers':{}}
        for label,answer in pair['answers'].items():
            matches=[r for rows in report['results'].values() for r in rows if r['id']==pair['id'] and
                     [(t['status'],t.get('result',{}).get('answer')) for t in r['turns']]==
                     [(t['status'],t.get('answer')) for t in answer['turns']]]
            cards=[[[s for s in t.get('result',{}).get('sources',[])] for t in r['turns']] for r in matches]
            # Identical local guards can match both versions; preserve ambiguity.
            source_cards=cards[0] if cards and all(c==cards[0] for c in cards) else cards
            payloads=[]
            for rows in report['results'].values():
                for row in rows:
                    if row not in matches:continue
                    # Match actual raw requests, not a private version key.
                    variant=next(v for v,rs in report['results'].items() if row in rs)
                    wire=json.loads((Path(report['private_worker_folders'][variant])/(row['id']+'-wire.json')).read_text(encoding='utf-8'))
                    requests=[w for w in wire if 'request' in w]
                    actual=[{'raw_output':w.get('content') or w.get('response'),'evidence':w.get('evidence',{})} for w in requests]
                    if actual!=answer['actual_requests']:continue
                    payloads=[]
                    for w in requests:
                        try:payload=json.loads(w['request']['messages'][-1]['content'])
                        except (ValueError,KeyError,TypeError):payload={}
                        raw=w.get('content') or w.get('response')
                        try:parsed=json.loads(raw) if isinstance(raw,str) else raw
                        except ValueError:parsed=None
                        sections=parsed.get('sections',[]) if isinstance(parsed,dict) else []
                        if not sections and isinstance(parsed,dict) and parsed.get('answer'):
                            sections=[{'text':parsed['answer']}]
                        units=[]
                        for pi,section in enumerate(sections):
                            # Keep the full paragraph for cross-sentence conditions.
                            for ci,text in enumerate(s.strip() for s in re.split(r'(?<=[。！？；;])',section['text']) if s.strip()):
                                units.append({'id':f'p{pi}c{ci}','text':text,'paragraph':section['text'],
                                    'evidence_ids':section.get('evidence_ids',[]),'judgement':None,'reason':None})
                        payloads.append({'input':payload.get('user_message'),'profile':payload.get('current_profile'),
                            'answer_context':payload.get('answer_context'),'evidence':payload.get('evidence',w.get('evidence',{})),
                            'raw_output':raw,'units':units})
                    break
                if payloads:break
            output['answers'][label]={'turns':answer['turns'],'source_cards':source_cards,'requests':payloads}
        result.append(output)
    path=folder/('review-input-progress.json' if partial else 'review-input.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'path':str(path),'pairs':len(result),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--partial',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(args.folder,args.partial)))


if __name__=='__main__':main()
