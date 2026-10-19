"""Offline, same-content retrieval ablation against the frozen pre-change code."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import zipfile

BACKEND=Path(__file__).resolve().parents[1]
ROOT=BACKEND.parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-zip',type=Path,default=ROOT/'artifacts/evidence-rebuild/baseline.zip')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/evidence-rebuild/offline.json')
    args=parser.parse_args()
    folder=Path(tempfile.mkdtemp(prefix='evidence-offline-',dir=BACKEND/'storage/evals'))
    os.environ.update(DEMO_MODE='true',DASHSCOPE_AUTO_SELECT='false',DASHSCOPE_API_KEY='',
                      DEEPSEEK_API_KEY='',MODEL_API_KEY='',AMAP_ENABLED='false',TIANDITU_ENABLED='false')
    from evals.runner import setup_database
    setup_database(folder)
    with zipfile.ZipFile(args.baseline_zip) as archive:
        old=archive.read('backend/app/knowledge.py')
    path=folder/'baseline_knowledge.py'
    path.write_bytes(old)
    spec=importlib.util.spec_from_file_location('baseline_knowledge',path)
    baseline=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    from sqlmodel import Session
    from app.core.db import engine
    from app.knowledge import multi_search,model_sections
    from app.evidence_index import chunks_for,dependency_closure,manifest
    from app.answer_context import current_focus
    raw=(BACKEND/'evals/evidence_cases.json').read_bytes()
    cases=json.loads(raw)['cases']
    rows=[]
    with Session(engine) as session:
        for case in cases:
            query=current_focus(case['query'])
            variants={}
            for variant in ('article_chapters','scoped_chapters','evidence_blocks'):
                start=time.perf_counter()
                articles=(multi_search if variant=='evidence_blocks' else baseline.multi_search)(
                    session,case['species'],[query],personal=True)
                passages=[]
                for article in articles:
                    if variant=='article_chapters':
                        selected=baseline.model_sections(article)
                    elif variant=='scoped_chapters':
                        available=chunks_for(article)
                        headings={p['heading'] for p in article['matched_sections']}
                        selected=dependency_closure([p for p in available if p['heading'] in headings],available)
                    else:
                        selected=model_sections(article)
                    passages.extend(selected)
                elapsed=(time.perf_counter()-start)*1000
                text='\n'.join(p['text'] for p in passages)
                actual={a['id'] for a in articles}
                hit=bool(actual.intersection(case['expected']))
                required=all(any(option in text for option in value.get('any_of',[])) if isinstance(value,dict)
                             else value in text for value in case['required'])
                ids={p['chunk_id'] for p in passages if p.get('chunk_id')}
                dependencies=all(dep in ids for p in passages for dep in p.get('depends_on',[]))
                variants[variant]={'articles':sorted(actual),'hit':hit,'required_content':required,
                    'dependencies_complete':dependencies,'complete_package':hit and required and dependencies,
                    'characters':len(text),'chunks':len(passages),'retrieval_ms':round(elapsed,3)}
            rows.append({'id':case['id'],'theme':case['theme'],'query':case['query'],'variants':variants})
    metrics={}
    for variant in ('article_chapters','scoped_chapters','evidence_blocks'):
        values=[row['variants'][variant] for row in rows]
        def distribution(key):
            ordered=sorted(row[key] for row in values)
            return {'p50':ordered[len(ordered)//2],'p95':ordered[min(len(ordered)-1,__import__('math').ceil(len(ordered)*.95)-1)]}
        metrics[variant]={'cases':len(values),'article_hits':sum(v['hit'] for v in values),
            'complete_packages':sum(v['complete_package'] for v in values),
            'dependency_complete':sum(v['dependencies_complete'] for v in values),
            'characters':distribution('characters'),'retrieval_ms':distribution('retrieval_ms')}
    article_cases=json.loads((BACKEND/'evals/evidence_article_cases.json').read_text(encoding='utf-8'))
    article_lookup={a['id']:a for path in (BACKEND/'data').glob('knowledge*.json') for a in json.loads(path.read_text(encoding='utf-8'))}
    edit_rows=[]
    case_types=['direct','paraphrase','conditions','insufficient','interference','negation']
    with Session(engine) as session:
        for aid,queries in article_cases['articles'].items():
            if len(queries)!=6:
                raise ValueError('Edited article lacks six question types: '+aid)
            for kind,query in zip(case_types,queries):
                species=article_lookup[aid]['species'][0]
                found=multi_search(session,species,[current_focus(query)],personal=True)
                edit_rows.append({'article_id':aid,'type':kind,'query':query,
                                  'hit':aid in {a['id'] for a in found}})
    report={'method':'same updated content; frozen article-first vs explicit dependencies vs block BM25',
        'dataset_sha256':hashlib.sha256(raw).hexdigest(),'manifest_sha256':manifest()['manifest_sha256'],
        'baseline_knowledge_sha256':hashlib.sha256(old).hexdigest(),'real_model_requests':0,
        'source_support_note':'Gold checks retrieval and required content, not semantic or veterinary accuracy.',
        'metrics':metrics,'results':rows,'edited_article_cases':edit_rows,
        'edited_article_metrics':{'cases':len(edit_rows),'hits':sum(row['hit'] for row in edit_rows)}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'metrics':metrics},ensure_ascii=True))


if __name__=='__main__':
    main()
