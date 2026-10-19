"""Versioned public evidence. No user data, network calls or database writes.

Articles remain canonical. An annotation selects a complete heading and names
its indispensable dependencies; the build artifact is disposable and verified
against the actual database article before it can be used.
"""
import hashlib
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'evidence'
RULE_VERSION = 'semantic-heading-v1'
RETRIEVAL_VERSION = 'question-evidence-v1'

TOPIC_SIGNALS = {
    'grooming': r'梳毛|剪甲|剪指甲|指甲护理',
    'dental': r'刷牙|口腔|牙齿',
    'alone': r'独处|独自在家|在家叫|分离|拆家',
    'carrier': r'航空箱|运输箱|笼箱|进箱|犬箱|猫箱|可拆顶箱',
    'food-transition': r'换粮|转粮|混粮|更换.{0,4}粮',
    'food-label': r'食品标签|食物标签|包装|保证分析|营养适用声明|代谢能|配料',
    'cleaning': r'清洁|清洗|消毒|储存|存放|开封|开袋|粮袋.{0,3}(?:开|破)|破.{0,2}粮袋|包装破损|食品.{0,8}保存|保存.{0,4}(?:天|时长)|罐头剩余|砂盆|猫砂盆',
    'preparation': r'养猫前|养狗前|养宠前|准备养|领养前|时间.{0,6}空间',
    'body-muscle': r'BCS|MCS|体况评分|肌肉状况|脂肪.{0,4}肌肉',
    'travel': r'出行|自驾|承运|健康证明|就医材料|就医前|就诊前|联系人|交接',
    'arrival': r'新猫|新宠|刚到家|多猫|多宠|相处',
    'interaction-training': r'玩耍|互动|探索|嗅闻|运动',
    'feeding': r'日常喂食|喂食饮食|饮食注意|喂食原则|喂食和体重|喂食与体重|喂食.{0,4}饮水|食水.{0,6}原则',
    'appetite': r'不吃|拒食|食欲下降|食欲不振',
    'vomiting': r'呕吐|吐了|吐过|吐后',
}


def query_topics(query):
    return {topic for topic, pattern in TOPIC_SIGNALS.items() if re.search(pattern, query, re.I)}


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def article_sections(body):
    result = []
    for part in re.split(r'(?m)^##\s+', body):
        if not part.strip():
            continue
        heading, _, text = part.strip().partition('\n')
        result.append({'heading': heading.strip(), 'text': text.strip() or heading.strip()})
    return result


def build_index(articles, annotations, previous=None):
    """Strict build: stale annotations, dangling sources and cycles fail closed."""
    by_id = {a['id']: a for a in articles}
    if len(by_id) != len(articles) or set(by_id) != set(annotations['articles']):
        raise ValueError('Article/annotation identity mismatch')
    old = {c['chunk_id']: c for c in (previous or {}).get('chunks', [])}
    chunks, identities = [], set()
    for aid, article in sorted(by_id.items()):
        meta = annotations['articles'][aid]
        if meta['content_kind'] != article.get('content_kind', 'care') or meta['species'] != article['species']:
            raise ValueError('Classification mismatch: ' + aid)
        passages = article_sections(article['body'])
        if len({p['heading'] for p in passages}) != len(passages):
            raise ValueError('Ambiguous duplicate heading: ' + aid)
        if set(meta['sections']) != {p['heading'] for p in passages}:
            raise ValueError('Stale section annotations: ' + aid)
        for passage in passages:
            spec = meta['sections'][passage['heading']]
            cid = aid + ':' + spec['key']
            if cid in identities:
                raise ValueError('Duplicate stable chunk identity: ' + cid)
            identities.add(cid)
            refs = spec['source_ids']
            if not refs or any(ref not in annotations['sources'] for ref in refs):
                raise ValueError('Missing source mapping: ' + cid)
            for ref in refs:
                source = annotations['sources'][ref]
                if not source['locator'] or not source['supports']:
                    raise ValueError('Missing source locator/support: ' + ref)
            if spec.get('claim_review_status')=='checked':
                if any(spec.get('review_source_hashes',{}).get(ref)!=digest({k:annotations['sources'][ref].get(k)
                       for k in ('version','locator','supports','species')}) for ref in refs):
                    raise ValueError('Source changed since claim review: '+cid)
                claims=spec.get('claim_annotations',[])
                if not claims or re.sub(r'\s+','',''.join(c['text'] for c in claims))!=re.sub(r'\s+','',passage['text']):
                    raise ValueError('Incomplete reviewed claim coverage: '+cid)
                if any(c['nature'] not in {'professional_summary','editorial_application','application_behavior','manufacturer_statement','arithmetic'}
                       or not c['source_ids'] or not set(c['source_ids'])<=set(refs) for c in claims):
                    raise ValueError('Invalid reviewed claim provenance: '+cid)
            if not set(spec.get('species', article['species'])) <= set(article['species']):
                raise ValueError('Chunk broadens article species: ' + cid)
            content_hash = digest(passage['text'])
            evidence_hash = digest({'passage':passage, 'annotation':spec,
                'classification':{k:v for k,v in meta.items() if k!='sections'},
                'sources':{ref:annotations['sources'][ref] for ref in refs}})
            prior = old.get(cid)
            revision = (prior['revision'] + (prior.get('evidence_sha256') != evidence_hash)) if prior else 1
            chunks.append({
                'chunk_id': cid, 'article_id': aid, 'revision': revision,
                'article_sha256': digest(article['body']), 'text_sha256': content_hash,
                'evidence_sha256':evidence_hash,
                **passage, 'heading_path': [article['title'], passage['heading']],
                'species': spec.get('species', article['species']),
                'life_stages': spec.get('life_stages', article['life_stages']),
                'breed_ids': article.get('breed_ids', []), 'content_kind': meta['content_kind'],
                'topic_id': meta['topic_id'], 'subtopics': meta['subtopics'],
                'roles': spec['roles'], 'source_ids': refs,
                'depends_on': [aid + ':' + dep for dep in spec['depends_on']],
                'conditions': spec.get('conditions', []), 'region': meta['region'],
                'questions': spec.get('questions', []),
                'object_aliases':spec.get('object_aliases',[]),
                'keywords': list(dict.fromkeys(article['keywords'] + meta['aliases'])),
                'evidence_nature': spec['evidence_nature'],
                'claim_review_status':spec.get('claim_review_status','pending_granular_review'),
                'claim_annotations':spec.get('claim_annotations',[]),
                'review_status': article['review_status'],
            })
    lookup = {c['chunk_id']: c for c in chunks}
    def visit(cid, active, visited):
        if cid not in lookup:
            raise ValueError('Dangling dependency: ' + cid)
        if cid in active:
            raise ValueError('Dependency cycle: ' + cid)
        if cid in visited:
            return
        for dep in lookup[cid]['depends_on']:
            visit(dep, active | {cid}, visited)
        visited.add(cid)
    visited = set()
    for cid in lookup:
        visit(cid, set(), visited)
    from app.knowledge import tokenize
    vocabulary = tuple(sorted({word for chunk in chunks for word in chunk['keywords']}))
    token_index = {'vocabulary':list(vocabulary),'documents':{}}
    for chunk in chunks:
        local=' '.join([chunk['heading'],chunk['text'],*chunk['questions']])
        token_index['documents'][chunk['chunk_id']] = {
            'counts':dict(Counter(tokenize(chunk['heading_path'][0]+' '+local,vocabulary))),
            'local_terms':sorted(set(tokenize(local,vocabulary)))}
    result = {'rule_version': RULE_VERSION, 'retrieval_version': RETRIEVAL_VERSION,
              'articles_sha256': digest(sorted(articles, key=lambda a: a['id'])),
              'annotations_sha256': digest(annotations), 'chunks': chunks, 'token_index':token_index}
    result['manifest_sha256'] = digest(result)
    return result


@lru_cache(maxsize=2)
def _source_annotations(path, mtime, size, expected):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    if digest(raw) != expected:
        raise ValueError('Evidence source annotations are stale')
    return raw['sources']


def citation_references(article, headings):
    """Resolve the selected internal block references to the existing public shape."""
    chunks = [c for c in article.get('matched_sections',[]) if c['heading'] in headings]
    ids = list(dict.fromkeys(sid for c in chunks for sid in c.get('source_ids',[])))
    data = manifest()
    if not ids or data is None:
        return article.get('references',[])
    # The manifest includes source metadata in the independently hashed annotation;
    # load it by matching that hash so stale locators cannot attach to new prose.
    path = ROOT/'annotations.json'
    stat = path.stat()
    sources = _source_annotations(str(path),stat.st_mtime_ns,stat.st_size,data['annotations_sha256'])
    return [{'organization':s['organization'],'url':s['url'],'version':s['version'],
             'checked_at':s['checked_at'],'supports':s['supports']+'；原文定位：'+s['locator']}
            for sid in ids for s in [sources[sid]]]


def public_citation_source(article, headings):
    refs=citation_references(article,headings)
    managed=any(p.get('source_ids') for p in article.get('matched_sections',[]) if p['heading'] in headings)
    primary=refs[0] if managed and refs else {'url':article['source_url'],'organization':article['source_organization']}
    return {'id':article['id'],'title':article['title'],'url':primary['url'],
            'organization':primary['organization'],'sections':headings,
            'references':refs,'review_status':article.get('review_status','editorial_summary_unreviewed')}


@lru_cache(maxsize=2)
def _load(path, mtime, size):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('manifest_sha256') != digest({k: v for k, v in data.items() if k != 'manifest_sha256'}):
        raise ValueError('Evidence manifest checksum mismatch')
    if data['rule_version'] != RULE_VERSION:
        raise ValueError('Unsupported evidence version')
    data['_by_article'] = {}
    data['_by_id'] = {c['chunk_id']:c for c in data['chunks']}
    for chunk in data['chunks']:
        data['_by_article'].setdefault(chunk['article_id'], []).append(chunk)
    return data


def manifest():
    path = ROOT / 'index.json'
    if not path.exists():
        return None
    stat = path.stat()
    return _load(str(path), stat.st_mtime_ns, stat.st_size)


def chunks_for(article, index=None):
    if not article.get('id'):
        return None
    data = index or manifest()
    if data is None:
        return None
    selected = data['_by_article'].get(article['id'])
    if selected is None:
        return None  # Third-party/custom articles continue to use the public interface.
    if selected[0]['article_sha256'] != digest(article['body']):
        raise ValueError('Evidence is stale; rebuild before answering: ' + article['id'])
    return selected


def dependency_closure(selected, available):
    lookup = {c['chunk_id']: c for c in available}
    result, active = {}, set()
    def visit(chunk):
        cid = chunk['chunk_id']
        if cid in active:
            raise ValueError('Evidence dependency cycle')
        if cid in result:
            return
        active.add(cid)
        for dep in chunk['depends_on']:
            if dep not in lookup:
                raise ValueError('Missing applicable evidence dependency: ' + dep)
            visit(lookup[dep])
        active.remove(cid)
        result[cid] = chunk
    for chunk in selected:
        visit(chunk)
    return list(result.values())


GENERIC = {'猫', '狗', '犬', '宠物', '照护', '如何', '怎么', '什么', '是否', '可以', '需要',
           '建议', '我的', '你的', '资料', '记录', '观察', '准备', '安全', '安排', '适应'}


@lru_cache(maxsize=8)
def _corpus(serialized):
    return _build_corpus(json.loads(serialized))


@lru_cache(maxsize=8)
def _managed_corpus(version, identities):
    lookup = manifest()['_by_id']
    return _build_corpus([lookup[cid] for cid in identities])


def _build_corpus(chunks):
    from app.knowledge import tokenize
    data=manifest()
    indexed=data.get('token_index') if data and all(data['_by_id'].get(c['chunk_id']) is c for c in chunks) else None
    vocabulary = tuple(indexed['vocabulary']) if indexed else tuple(sorted({k for c in chunks for k in c['keywords']}))
    docs = [Counter(indexed['documents'][c['chunk_id']]['counts']) if indexed else
            Counter(tokenize(' '.join([c['heading_path'][0],c['heading'],c['text'],*c['questions']]),vocabulary)) for c in chunks]
    local_terms=[set(indexed['documents'][c['chunk_id']]['local_terms']) if indexed else
                 set(tokenize(' '.join([c['heading'],c['text'],*c['questions']]),vocabulary)) for c in chunks]
    df = Counter(t for doc in docs for t in doc)
    average = sum(sum(d.values()) for d in docs) / max(1, len(docs)) or 1
    return chunks, vocabulary, docs, df, average,local_terms


def rank_chunks(chunks, query, candidates=16):
    from app.knowledge import tokenize, expanded_query
    if not chunks or not query.strip():
        return []
    data = manifest()
    if data and all(data['_by_id'].get(c['chunk_id']) is c for c in chunks):
        corpus, vocabulary, docs, df, average, local_sets = _managed_corpus(data['manifest_sha256'],tuple(c['chunk_id'] for c in chunks))
    else:
        corpus, vocabulary, docs, df, average, local_sets = _corpus(json.dumps(chunks, ensure_ascii=False, sort_keys=True))
    terms = set(tokenize(expanded_query(query), vocabulary)) - GENERIC
    ranked = []
    shopping = bool(re.search(r'买|选购|挑选|用品|规格|材质|比较|多少钱|尺寸', query))
    topics = query_topics(query)
    for chunk, doc, local_terms in zip(corpus, docs, local_sets):
        if topics and chunk['content_kind']!='breed' and not topics.intersection(chunk['subtopics']):
            continue
        matched = terms & doc.keys()
        anchors = [k for k in chunk['keywords'] if k not in GENERIC and len(k) > 1 and k.lower() in query.lower()]
        # Article keywords qualify the topic, but only passage text qualifies a hit.
        local = chunk['heading'] + ' ' + chunk['text'] + ' ' + ' '.join(chunk['questions'])
        direct = [k for k in anchors if k.lower() in local.lower()]
        if len(matched) < 2 and not direct:
            continue
        score = sum(math.log(1 + (len(docs) - df[t] + .5)/(df[t] + .5)) * doc[t]*2.2 /
                    (doc[t] + 1.2*(.25 + .75*sum(doc.values())/average)) for t in matched)
        score += sum(min(30,10*math.log(1+len(docs)/df[t])) for t in terms & local_terms)
        if re.search(r'(?m)^\d+\. ', chunk['text']) and re.search(r'怎么|如何|怎样|安排|练习|步骤', query) and not is_concept(query):
            score += 12
        if re.search(r'没有|缺少|缺失|未知|不全|不足',query) and re.search(r'不足|缺口|需要哪些资料|资料缺失',chunk['heading']):
            score += 15
        if chunk['content_kind'] == 'supplies' and not shopping:
            score *= .45
        if chunk['roles'] == ['scope'] and not is_concept(query):
            score *= .25
        ranked.append((score, chunk))
    return [c for _, c in sorted(ranked, key=lambda row: (-row[0], row[1]['chunk_id']))[:candidates]]


def select_chunks(chunks, query, count=3):
    ranked = rank_chunks(chunks, query)
    return dependency_closure(direct_chunks(ranked, query, count), chunks)


def direct_chunks(ranked, query, count=3):
    if not ranked:
        return []
    # Identical editorial templates across articles add no independent evidence.
    unique = {}
    for chunk in ranked:
        unique.setdefault(chunk['text_sha256'], chunk)
    ranked = list(unique.values())
    chosen = ranked[:count]
    concept = is_concept(query)
    required = []
    # A general food/water question directly asks for the scope/adequacy
    # principle. This is query-specific evidence, not a blanket first chapter.
    if 'feeding' in query_topics(query) and re.search(r'原则|基础|日常',query):
        scope = next((c for c in ranked if c['article_id'] in {'cat-food','dog-food'} and c['roles']==['scope']),None)
        if scope:
            required.append(scope)
    if not concept and re.search(r'怎么|如何|怎样|练习|适应|安排|护理|清洁|评估|核对|准备', query):
        action = next((c for c in ranked if 'action' in c['roles'] and re.search(r'(?m)^\d+\. ',c['text'])), None)
        action = action or next((c for c in ranked if 'action' in c['roles']), None)
        if action:
            required.append(action)
        if re.search(r'练习|训练|适应',query):
            practice = next((c for c in ranked if 'action' in c['roles'] and re.search(r'练习|分步|可承受',c['heading'])),None)
            if practice and practice not in required:
                required.append(practice)
    for chunk in required:
        if chunk not in chosen:
            remove = next((c for c in reversed(chosen) if c not in required),None)
            if remove:
                chosen.remove(remove)
            chosen.append(chunk)
    return chosen


def is_concept(query):
    return bool(re.search(r'区别|区分|是什么|什么意思|怎么理解|等于|是不是|认证|证明|能先|实测值|准确|一定|必须',query))
