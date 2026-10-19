"""Apply independently recorded page reviews without touching business data.

Page availability and claim support are separate states. This overlay never
marks a whole article or a paragraph as supported merely because a URL opens.
"""
import json
from pathlib import Path
from app.evidence_index import digest

DATA = Path(__file__).resolve().parents[1] / 'data'


def apply(annotations, articles, review):
    pages = {p['url']: p for p in review['pages']}
    replacements = {p['url']: p['replacement'] for p in review['replacements']}
    sources = annotations['sources']
    for url, page in pages.items():
        sid = 'src-' + digest(url)[:16]
        old = sources.get(sid, {})
        sources[sid] = {
            **old, 'url': url, 'title': page['title'],
            'organization': old.get('organization', page.get('organization', url.split('/')[2])),
            'published_at': page.get('published_at'), 'version': page['version'],
            'checked_at': review['review_date'], 'verification_status': 'page_rechecked',
            'locator': page['locator'], 'supports': page['supports'],
            'species': page['species'],
            'life_stages': page.get('life_stages', []),
            'coverage': page.get('coverage', 'specified_locator_only'),
            'claim_review_status': 'separate_section_review_required',
            'reuse': '独立中文摘要；仅保留必要原文定位，不复制整篇',
        }
    replaced_ids = {}
    for url, target in replacements.items():
        if target not in pages:
            raise ValueError('Replacement page was not reviewed: ' + target)
        replaced_ids['src-' + digest(url)[:16]] = 'src-' + digest(target)[:16]
    for article in articles:
        meta = annotations['articles'][article['id']]
        for spec in meta['sections'].values():
            spec['source_ids'] = list(dict.fromkeys(replaced_ids.get(s, s) for s in spec['source_ids']))
        if article['source_url'] in replacements:
            target = replacements[article['source_url']]
            article['source_url'] = target
            article['source_version'] = pages[target]['version']
            article['source_organization'] = sources['src-' + digest(target)[:16]]['organization']
        refs = {}
        for ref in article['references']:
            url = replacements.get(ref['url'], ref['url'])
            if url in pages:
                p = pages[url]
                ref = {**ref, 'url': url, 'version': p['version'], 'supports': p['supports'],
                       'checked_at': review['review_date'],
                       'organization': sources['src-' + digest(url)[:16]]['organization']}
            refs[url] = ref
        article['references'] = list(refs.values())
    # Inactive links stay in the audit file, not in the active source registry.
    used = {sid for a in annotations['articles'].values() for s in a['sections'].values() for sid in s['source_ids']}
    annotations['sources'] = {sid: source for sid, source in sources.items() if sid in used}
    annotations['page_review_overlay_sha256'] = digest(review)
    for meta in annotations['articles'].values():
        meta['source_mapping_checked_at'] = review['review_date']
        # Do not convert a page check into a per-claim accuracy certificate.
        for section in meta['sections'].values():
            section.setdefault('claim_review_status', 'pending_granular_review')
    return annotations


def main():
    path = DATA / 'evidence/annotations.json'
    annotations = json.loads(path.read_text(encoding='utf-8'))
    review = json.loads((DATA/'evidence/source_reviews.json').read_text(encoding='utf-8'))
    files = {p: json.loads(p.read_text(encoding='utf-8')) for p in sorted(DATA.glob('knowledge*.json'))}
    apply(annotations, [a for group in files.values() for a in group], review)
    for p, articles in files.items():
        p.write_text(json.dumps(articles, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    path.write_text(json.dumps(annotations, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    batch_path=DATA/'evidence/batch.json'
    batch=json.loads(batch_path.read_text(encoding='utf-8'))
    batch['rechecked_source_count']=sum(s['verification_status']=='page_rechecked' for s in annotations['sources'].values())
    batch['pending_source_count']=len(annotations['sources'])-batch['rechecked_source_count']
    batch['source_mapping_checked_articles']=len(annotations['articles'])
    batch['limitations']=['分类和网页定位核对不等于兽医审核','逐结论支持与依赖审阅尚需单独验收，不能以页面可读代替','切分、检索和真实回答另行验收']
    batch_path.write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'reviewed_active_pages': sum(s['verification_status']=='page_rechecked' for s in annotations['sources'].values()),
                      'active_pages': len(annotations['sources'])}))


if __name__ == '__main__':
    main()
