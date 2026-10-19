"""Apply frozen editorial reviews; never silently renew them after body changes."""
import json
from pathlib import Path
from app.evidence_index import article_sections, digest

DATA=Path(__file__).resolve().parents[1]/'data'


def apply(annotations, articles, reviews, pages):
    if set(reviews['articles']) != {a['id'] for a in articles}:
        raise ValueError('Full-corpus editorial review identity mismatch')
    page_lookup={p['url']:p for p in pages['pages']}
    source_lookup={s['url']:s for s in annotations['sources'].values()}
    for article in articles:
        aid=article['id']; reviewed=reviews['articles'][aid]
        if reviewed['body_sha256'] != digest(article['body']):
            raise ValueError('Body changed since editorial review: '+aid)
        sections={s['heading']:s for s in article_sections(article['body'])}
        meta=annotations['articles'][aid]
        if set(reviewed['sections']) != set(sections):
            raise ValueError('Section review locator is stale: '+aid)
        for heading,review in reviewed['sections'].items():
            spec=meta['sections'][heading]
            if review['text_sha256'] != digest(sections[heading]['text']):
                raise ValueError('Section changed since editorial review: '+aid+':'+heading)
            refs=[]
            for url in review['source_urls']:
                sid='src-'+digest(url)[:16]
                if url not in source_lookup:
                    page=page_lookup[url]
                    source_lookup[url]={**page,'organization':page.get('organization',url.split('/')[2]),
                        'published_at':page.get('published_at'),'checked_at':pages['review_date'],
                        'verification_status':'page_rechecked','coverage':page.get('coverage','specified_locator_only'),
                        'reuse':'独立中文摘要与定位，不复制整篇'}
                annotations['sources'][sid]=source_lookup[url]
                expected=review['source_fingerprints'].get(url)
                actual=digest({k:source_lookup[url].get(k) for k in ('version','locator','supports','species')})
                if expected!=actual:
                    raise ValueError('Source changed since section review: '+aid+':'+heading)
                refs.append(sid)
            claims=review['claims']
            if not claims or any(c['text'] not in sections[heading]['text'] for c in claims):
                raise ValueError('Claim text locator is stale: '+aid+':'+heading)
            dependencies=[meta['sections'][h]['key'] for h in review['dependency_headings']]
            spec.update(source_ids=refs,depends_on=dependencies,evidence_nature=review['evidence_nature'],
                        claim_annotations=claims,claim_review_status=review['status'],
                        review_source_hashes={sid:review['source_fingerprints'][u] for sid,u in zip(refs,review['source_urls'])},
                        conditions=review['conditions'],reviewed_at=reviews['review_date'])
        urls=list(dict.fromkeys(u for s in reviewed['sections'].values() for u in s['source_urls']))
        article['references']=[{'url':u,'organization':source_lookup[u]['organization'],
            'version':source_lookup[u]['version'],'checked_at':source_lookup[u]['checked_at'],
            'supports':source_lookup[u]['supports']} for u in urls]
    used={sid for a in annotations['articles'].values() for s in a['sections'].values() for sid in s['source_ids']}
    annotations['sources']={sid:s for sid,s in annotations['sources'].items() if sid in used}
    annotations['section_reviews_sha256']=digest(reviews)


def main():
    path=DATA/'evidence/annotations.json'
    annotations=json.loads(path.read_text(encoding='utf-8'))
    reviews=json.loads((DATA/'evidence/section_reviews.json').read_text(encoding='utf-8'))
    pages=json.loads((DATA/'evidence/source_reviews.json').read_text(encoding='utf-8'))
    files={p:json.loads(p.read_text(encoding='utf-8')) for p in sorted(DATA.glob('knowledge*.json'))}
    apply(annotations,[a for rows in files.values() for a in rows],reviews,pages)
    for p,rows in files.items():p.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    path.write_text(json.dumps(annotations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    batch_path=DATA/'evidence/batch.json';batch=json.loads(batch_path.read_text(encoding='utf-8'))
    checked=sum(s['verification_status']=='page_rechecked' for s in annotations['sources'].values())
    batch.update(rechecked_source_count=checked,pending_source_count=len(annotations['sources'])-checked,
                 section_review_count=sum(s['status']=='checked' for a in reviews['articles'].values() for s in a['sections'].values()))
    batch['limitations']=['全文与来源支持检查为编辑审阅，未经兽医审核','原创清单、应用行为和专业结论分别标记，不代表机构为操作流程背书','外部真实质量与速度另行验收']
    batch_path.write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'articles_reviewed':len(reviews['articles']),'sections':batch['section_review_count']}))


if __name__=='__main__':main()
