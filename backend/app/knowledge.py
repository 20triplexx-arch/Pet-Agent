import re
import math
from collections import Counter
from functools import lru_cache
from abc import ABC, abstractmethod
from sqlmodel import Session, select
from app.models import KnowledgeArticle, Bookmark
from app.species import supports
from app.execution import current_execution


class Retriever(ABC):
    @abstractmethod
    def search(
        self,
        session: Session,
        species: str | None,
        query: str,
        topic: str | None = None,
        life_stage: str | None = None,
        breed_id: str | None = None,
        content_kind: str | None = None,
    ): ...


SYNONYMS = (
    ("拉稀", "腹泻"), ("不吃", "拒食", "食欲下降", "食欲不振"),
    ("乱尿", "如厕", "排泄"), ("抓沙发", "抓挠", "猫抓板"),
    ("独自在家", "独处", "分离", "叫"), ("刷牙", "口腔", "牙齿"),
    ("新猫", "新宠", "适应", "到家"), ("粮", "主粮", "食物"),
    ("胖", "肥胖", "体重", "体况"), ("多猫", "多宠", "相处"),
    ("航空箱", "运输箱", "笼箱", "犬箱", "猫箱", "可拆顶箱"), ("热量", "能量", "卡路里"),
    ("剪指甲", "剪甲", "指甲护理", "指甲"),
    ("食盆", "食碗", "狗碗", "猫碗", "食水器具"),
    ("保暖", "冬季"), ("玩具", "啃咬", "互动"),
    ("袋开了", "开袋", "开封"), ("收好", "储存", "存放"),
    ("粮袋破", "破粮袋", "破袋", "包装破损"), ("没有异味", "闻起来正常"),
)


def expanded_query(query):
    additions = [w for group in SYNONYMS if any(w in query for w in group) for w in group]
    return query + " " + " ".join(dict.fromkeys(additions))


def tokenize(text, vocabulary=()):
    """Deterministic dictionary maximum matching plus CJK bigrams; no remote service."""
    return list(_tokenize(text, vocabulary if isinstance(vocabulary, tuple) else tuple(sorted(set(vocabulary)))))


@lru_cache(maxsize=32)
def lexicon(vocabulary):
    buckets = {}
    for word in sorted({w.lower() for w in vocabulary if len(w) >= 2}, key=len, reverse=True):
        buckets.setdefault(word[0], []).append(word)
    return buckets


@lru_cache(maxsize=8192)
def _tokenize(text, vocabulary):
    words = lexicon(vocabulary)
    tokens = []
    for chunk in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.lower()):
        if not re.search(r"[\u3400-\u9fff]", chunk):
            tokens.append(chunk)
            continue
        position = 0
        while position < len(chunk):
            match = next((w for w in words.get(chunk[position], []) if chunk.startswith(w, position)), None)
            if match:
                tokens.append(match)
                position += len(match)
            else:
                if position + 1 < len(chunk):
                    tokens.append(chunk[position:position + 2])
                position += 1
    return tuple(tokens)


class BM25Retriever(Retriever):
    def search(self, session, species, query, topic=None, life_stage=None, breed_id=None, content_kind=None):
        if species and not supports(species, "knowledge"):
            return []
        articles = session.exec(select(KnowledgeArticle)).all()
        filtered = []
        for a in articles:
            if species and species not in a.species:
                continue
            if topic and a.topic != topic:
                continue
            if content_kind and a.content_kind != content_kind:
                continue
            if breed_id and a.breed_ids and breed_id not in a.breed_ids:
                continue
            if (
                life_stage
                and "all" not in a.life_stages
                and life_stage not in a.life_stages
            ):
                continue
            filtered.append(a)
        if not query.strip():
            return sorted(filtered, key=lambda a: a.id)
        if not filtered:
            return []
        vocabulary = [k for a in filtered for k in a.keywords] + [w for g in SYNONYMS for w in g]
        generic = {"宠物", "动物", "怎么", "如何", "什么", "怎样", "需要", "注意", "是否", "可以", "照护", "我的", "你的",
                   "适应", "记录", "观察", "练习", "安全", "准备", "资料"}
        query_tokens = set(tokenize(expanded_query(query), vocabulary)) - generic
        docs, average, frequencies = corpus_index(tuple((a.id, a.title, a.body, tuple(a.keywords)) for a in filtered), tuple(vocabulary))
        ranked = []
        for a, doc in zip(filtered, docs):
            length = sum(doc.values())
            score = sum(math.log(1 + (len(docs) - frequencies[t] + .5) / (frequencies[t] + .5))
                * doc[t] * 2.2 / (doc[t] + 1.2 * (.25 + .75 * length / average))
                for t in query_tokens if doc[t])
            # Original intent wins over expanded generic words; keep precise topic ordering.
            exact_keywords = [k for k in a.keywords if len(k) > 1 and k.lower() in query.lower() and k not in generic]
            score += sum(12 + len(k) for k in exact_keywords)
            score += sum(6 for k in a.keywords if len(k) > 1 and k in a.title and k in query)
            if a.content_kind == 'supplies' and not re.search(r'买|选购|挑选|用品|规格|材质|比较|多少钱|尺寸', query):
                score *= .45
            if score > 0 and (exact_keywords or len(query_tokens & doc.keys()) >= 2):
                ranked.append((score, a))
        return [a for _, a in sorted(ranked, key=lambda x: (-x[0], x[1].id))]


KeywordRetriever = BM25Retriever  # compatibility for existing integrations
retriever: Retriever = BM25Retriever()


@lru_cache(maxsize=8)
def corpus_index(articles, vocabulary):
    docs = tuple(Counter(tokenize(title + ' ' + body + ' ' + ' '.join(keywords), vocabulary))
                 for _, title, body, keywords in articles)
    return docs, sum(sum(doc.values()) for doc in docs) / len(docs) or 1, Counter(term for doc in docs for term in doc)


@lru_cache(maxsize=512)
def _sections(body):
    chunks = re.split(r"(?m)^##\s+", body)
    result = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        heading, _, body = chunk.partition("\n")
        result.append((heading.strip(), body.strip() or heading.strip()))
    return tuple(result)


def sections(article):
    return [{'heading': heading, 'text': text} for heading, text in _sections(article['body'])]


def passage_role(passage):
    if passage.get('roles'):
        return next((role for role in ('action', 'boundary', 'observation', 'prerequisites', 'explanation', 'scope')
                     if role in passage['roles']), 'explanation')
    heading, text = passage['heading'], passage['text']
    if re.search(r'深入分析前|需要哪些资料|填写|资料缺口', heading):
        return 'prerequisites'
    if re.search(r'(?m)^\d+\. ', text) or re.search(r'分步|清单|顺序|责任|练习|怎样.*(?:安排|执行|调整)|检查家庭', heading):
        return 'action'
    if re.search(r'边界|限制|风险|安全|就医|求助|停止|专业处理|改变安排', heading):
        return 'boundary'
    if re.search(r'观察|记录|衡量|进展', heading):
        return 'observation'
    return 'explanation'


def evidence_sections(article, query, count=3):
    from app.evidence_index import chunks_for, select_chunks
    indexed = chunks_for(article)
    if indexed is not None:
        return select_chunks(indexed, query, count)
    def passage_terms(text):
        # Preserve compound substrings: 剪指甲 must still match 指甲护理.
        grams = {chunk[i:i+2] for chunk in re.findall(r'[\u3400-\u9fff]+', text) for i in range(len(chunk)-1)}
        return set(tokenize(text, article['keywords'])) | grams
    terms = passage_terms(expanded_query(query)) - {'如何', '怎么', '什么', '是否', '可以', '需要', '建议', '宠物', '照护', '安排'}
    shopping = re.search(r'买|选购|挑选|比较|辅助用品|什么用品|哪些用品|规格|材质|多少钱', query)
    candidates = [(i, s) for i, s in enumerate(sections(article))
                  if shopping or not re.search(r'购买|选购|辅助用品|(?:选择|比较).*用品', s['heading'])]
    scored = sorted(candidates, key=lambda item: (
        -len(terms & passage_terms(item[1]["heading"] + " " + item[1]["text"])), item[0]))
    relevant = [(i, s) for i, s in scored if terms & passage_terms(s['heading'] + ' ' + s['text'])]
    chosen = {i for i, _ in relevant[:count]}
    concept = re.search(r'区别|区分|是什么|什么意思|怎么理解', query)
    if relevant and not concept and re.search(r'怎么|如何|怎样|安排|准备|练习|适应|条件|注意', query):
        # Lexical overlap alone can select three "what to record" sections and
        # omit the actual action. Keep an action and its numbered procedure.
        actions = [(i, s) for i, s in scored if passage_role(s) == 'action']
        if actions:
            chosen.add(actions[0][0])
        numbered = [(i, s) for i, s in actions if re.search(r'(?m)^\d+\. ', s['text'])]
        if numbered:
            chosen.add(numbered[0][0])
        if re.search(r'练习|训练|适应', query):
            practice = [(i, s) for i, s in enumerate(sections(article))
                        if re.search(r'练习|分步|可承受', s['heading']) and passage_role(s) == 'action']
            if practice:
                chosen.add(practice[0][0])
    return [section for i, section in enumerate(sections(article)) if i in chosen]


def model_sections(article):
    """Only selected evidence and its explicit dependencies; never expand by title."""
    passages = article.get('matched_sections', sections(article))
    return list({s.get('chunk_id', s['heading']): s for s in passages}.values())


def passage_questions(article, heading):
    """A scope passage supplements the questions its primary passages support.

    It never makes an unmatched article sufficient or links an unrelated chapter.
    """
    mapping = article.get('section_questions', {})
    if heading in mapping:
        return mapping[heading]
    complete = sections(article) if article.get('body') else []
    is_scope = any(s['heading'] == heading and (index == 0 or re.search(
        r'适用|边界|限制|风险|安全|就医|求助|停止', heading)) for index, s in enumerate(complete))
    if is_scope:
        primary = {q for linked in mapping.values() for q in linked}
        return [q for q in article.get('matched_questions', []) if q in primary]
    return []


def reading_excerpt(article, query, max_chars=420):
    """Select a scope, a relevant/action section and a boundary, without copying the article."""
    blocks = [b.strip() for b in article["body"].split("\n\n") if b.strip()]
    if not blocks:
        return ""
    terms = [k.lower() for k in article["keywords"] if k.lower() in query.lower()]
    terms += [t for t in re.split(r"[\s，。？！、]+", query.lower()) if t]
    middle = blocks[1:-1] or blocks[1:]
    ranked = sorted(
        middle,
        key=lambda b: sum(t in b.lower() for t in terms)
        + (2 if re.search(r"(?m)^\d+\. ", b) else 0),
        reverse=True,
    )
    selected = [blocks[0]]
    if ranked:
        selected.append(ranked[0])
    if len(blocks) > 2 and blocks[-1] not in selected:
        selected.append(blocks[-1])
    result = "\n\n".join(re.sub(r"(?m)^## ", "", b) for b in selected)
    if len(result) > max_chars:
        # Prefer a complete sentence/step over cutting into a clinical condition.
        cut = max(result.rfind(c, 0, max_chars) for c in ("。", "；", "\n"))
        result = result[: cut + 1 if cut > max_chars // 2 else max_chars] + "…"
    return result


def serialize_article(a, bookmarked=False):
    return {**a.model_dump(), "bookmarked": bookmarked}


def search_knowledge(session, species, query, topic=None, limit=5, life_stage=None, breed_id=None, content_kind=None, personal=False):
    items = [
        a.model_dump()
        for a in [a for a in retriever.search(session, species, query, topic, life_stage, breed_id, content_kind)
                  if not personal or breed_id or not a.breed_ids][:limit]
    ]
    if trace := current_execution.get():
        trace.retrieved({article["id"]: article for article in items})
    return items


def multi_search(session, species, questions, **filters):
    """Reserve coverage per subquestion before filling remaining evidence slots."""
    from app.evidence_index import manifest
    if manifest() is not None:
        return evidence_search(session, species, questions, **filters)
    return legacy_multi_search(session, species, questions, **filters)


def grounded_sections(article, query, count=3):
    """Explicit tool/breed selections use the same managed units and dependencies."""
    from app.evidence_index import chunks_for, select_chunks
    available = chunks_for(article)
    return select_chunks(available, query, count) if available is not None else evidence_sections(article, query, count)


def legacy_multi_search(session, species, questions, **filters):
    """Frozen article-first comparator and compatibility for installations without an index."""
    groups = [focused_articles(search_knowledge(session, species, question, limit=3, **filters), question)
              for question in questions]
    selected = {}
    for rank in range(3):
        for question, articles in zip(questions, groups):
            if rank < len(articles):
                article = articles[rank]
                if article["id"] not in selected and len(selected) < max(6, len(questions)):
                    selected[article["id"]] = {**article, "matched_sections": [], "matched_questions": [], "section_questions": {}}
                if article["id"] in selected:
                    current = selected[article["id"]]
                    if question not in current["matched_questions"]:
                        current["matched_questions"].append(question)
                    headings = {s["heading"] for s in current["matched_sections"]}
                    for passage in evidence_sections(article, question):
                        headings.add(passage['heading'])
                        linked = current['section_questions'].setdefault(passage['heading'], [])
                        if question not in linked:
                            linked.append(question)
                    current["matched_sections"] = [s for s in sections(article) if s["heading"] in headings]
    return list(selected.values())


def evidence_search(session, species, questions, **filters):
    from app.evidence_index import chunks_for, rank_chunks, dependency_closure, direct_chunks, manifest
    from app.question_scope import explicit_species
    index = manifest()
    personal = filters.pop('personal', False)
    detected = [explicit_species(q) for q in questions]
    mixed = len(set().union(*detected)) > 1
    scopes = [scope or ({species} if species else set()) for scope in detected] if mixed else [({species} if species else scope) for scope in detected]
    requested = set().union(*scopes)
    if mixed:
        filters = {**filters, 'breed_id': None, 'life_stage': None}
    eligible = {a.id: a.model_dump() for a in retriever.search(session, None if mixed else species, '', **filters)
                if not personal or filters.get('breed_id') or not a.breed_ids}
    available = []
    legacy = []
    for article in eligible.values():
        chunks = chunks_for(article,index)
        if chunks is None:
            legacy.append(article)
        else:
            available.extend(c for c in chunks if not requested or requested.intersection(c['species']))
    selected = {}
    for question, scope in zip(questions, scopes):
        applicable = [c for c in available if not scope or scope.intersection(c['species'])]
        shopping = re.search(r'买|选购|挑选|用品|规格|材质|比较|多少钱|尺寸', question)
        def relevant(ranked):
            if shopping:
                return ranked
            return [c for c in ranked if (c['content_kind'] != 'supplies' or any(alias in question for alias in c.get('object_aliases',[])))
                    and not re.search(r'购买|选购|辅助用品|(?:选择|比较).*用品', c['heading'])]
        ranked = relevant(rank_chunks(applicable, question))
        # A combined question still needs direct evidence for each animal.
        # Shared introductory passages must not crowd out either species.
        if len(scope) > 1:
            direct_by_id = {}
            for animal in sorted(scope):
                animal_ranked = relevant(rank_chunks([c for c in applicable if animal in c['species']], question))
                for c in direct_chunks(animal_ranked, question):
                    direct_by_id[c['chunk_id']] = c
            direct = list(direct_by_id.values())
        else:
            direct = direct_chunks(ranked, question)
        if re.search(r'梳毛|剪甲|剪指甲', question) and re.search(r'紧张|害怕|抗拒|强迫', question):
            support = next((c for c in ranked if c['article_id'] == 'cat-low-stress-care' and 'action' in c['roles']), None)
            if support and support not in direct:
                direct.append(support)
        complete = dependency_closure(direct, applicable)
        for chunk in complete:
            aid = chunk['article_id']
            current = selected.setdefault(aid, {**eligible[aid], 'matched_sections': [],
                          'matched_questions': [], 'section_questions': {}, 'direct_chunk_ids': []})
            if question not in current['matched_questions']:
                current['matched_questions'].append(question)
            mapping = current['section_questions'].setdefault(chunk['heading'], [])
            if question not in mapping:
                mapping.append(question)
            if chunk['chunk_id'] not in {c['chunk_id'] for c in current['matched_sections']}:
                current['matched_sections'].append(chunk)
            if chunk in direct and chunk['chunk_id'] not in current['direct_chunk_ids']:
                current['direct_chunk_ids'].append(chunk['chunk_id'])
    # Extension articles have no managed index; retain the existing interface.
    if legacy and not selected:
        return legacy_multi_search(session, species, questions, personal=personal, **filters)
    if trace := current_execution.get():
        trace.retrieved(selected)
    return list(selected.values())


def focused_articles(articles, query):
    """Secondary articles must add an explicitly requested topic, not a synonym detour.

    The full search tool remains available for genuinely uncovered questions.
    This only narrows the automatically prefetched context.
    """
    if not articles:
        return []
    primary = articles[0]
    generic = {'猫', '狗', '犬', '宠物', '照护', '记录', '观察', '准备', '资料', '原则',
               '日常', '条件', '安排', '适应', '互动', '安全', '选择', '如何', '怎样', '需要'}
    def anchors(article):
        words = set(article['keywords']) | set(tokenize(article['title']))
        return {word for word in words if len(word) >= 2 and word not in generic and word.lower() in query.lower()}
    covered = anchors(primary)
    result = [primary]
    for article in articles[1:]:
        if article.get('content_kind') == 'supplies' and not re.search(r'买|选购|挑选|用品|规格|材质|比较|多少钱|尺寸', query):
            continue
        additions = {word for word in anchors(article) - covered if word not in primary['body']
                     and not (word in ('猫粮', '狗粮') and '粮' in primary['body'])}
        species_detail = (article.get('topic') == primary.get('topic') and anchors(article)
                          and article.get('content_kind') == primary.get('content_kind')
                          and len(article.get('species', [])) < len(primary.get('species', [])))
        handling_support = (article.get('topic') == primary.get('topic') and anchors(article)
                            and '低压力' in article['title'] and re.search(r'紧张|害怕|抗拒|强迫', query))
        if (additions or species_detail or handling_support) and evidence_sections(article, query):
            result.append(article)
            covered.update(additions)
    return result
