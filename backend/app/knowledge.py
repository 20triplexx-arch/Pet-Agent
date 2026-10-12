import re
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


class KeywordRetriever(Retriever):
    def search(self, session, species, query, topic=None, life_stage=None, breed_id=None, content_kind=None):
        if species and not supports(species, "knowledge"):
            return []
        articles = session.exec(select(KnowledgeArticle)).all()
        terms = [t for t in re.split(r"[\s，。？！、]+", query.lower()) if t]
        ranked = []
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
            hay = (a.title + " " + a.body + " " + " ".join(a.keywords)).lower()
            score = sum(3 for k in a.keywords if k.lower() in query.lower()) + sum(
                1 for t in terms if t in hay
            )
            if not query or score > 0:
                ranked.append((score, a))
        return [a for _, a in sorted(ranked, key=lambda x: (-x[0], x[1].id))]


retriever: Retriever = KeywordRetriever()


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
