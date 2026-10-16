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
    ("航空箱", "运输箱", "笼箱"), ("热量", "能量", "卡路里"),
    ("保暖", "冬季"), ("玩具", "啃咬", "互动"),
)


def expanded_query(query):
    additions = [w for group in SYNONYMS if any(w in query for w in group) for w in group]
    return query + " " + " ".join(dict.fromkeys(additions))


def tokenize(text, vocabulary=()):
    """Deterministic dictionary maximum matching plus CJK bigrams; no remote service."""
    return list(_tokenize(text, tuple(sorted(set(vocabulary)))))


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
        generic = {"宠物", "动物", "怎么", "如何", "什么", "怎样", "需要", "注意", "是否", "可以", "照护", "我的", "你的"}
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


def evidence_sections(article, query, count=3):
    terms = set(tokenize(expanded_query(query), article["keywords"])) - {'如何', '怎么', '什么', '是否', '可以', '需要', '建议', '宠物', '照护', '安排'}
    scored = sorted(enumerate(sections(article)), key=lambda item: (
        -len(terms & set(tokenize(item[1]["heading"] + " " + item[1]["text"], article["keywords"]))), item[0]))
    relevant = [(i, s) for i, s in scored if terms & set(tokenize(s['heading'] + ' ' + s['text'], article['keywords']))]
    return [section for _, section in sorted(relevant[:count])]


def model_sections(article):
    """Complete matched passages plus their scope and safety boundaries, once."""
    complete = sections(article)
    chosen = {s["heading"] for s in article.get("matched_sections", complete)}
    if complete:
        chosen.add(complete[0]["heading"])
    chosen.update(s["heading"] for s in complete if re.search(r"适用|边界|限制|风险|安全|就医|求助|停止", s["heading"]))
    return [s for s in complete if s["heading"] in chosen]


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
    groups = [search_knowledge(session, species, question, limit=3, **filters) for question in questions]
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
