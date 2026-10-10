import re
from abc import ABC, abstractmethod
from sqlmodel import Session, select
from app.models import KnowledgeArticle, Bookmark


class Retriever(ABC):
    @abstractmethod
    def search(
        self,
        session: Session,
        species: str | None,
        query: str,
        topic: str | None = None,
        life_stage: str | None = None,
    ): ...


class KeywordRetriever(Retriever):
    def search(self, session, species, query, topic=None, life_stage=None):
        if species and species not in ("cat", "dog"):
            return []
        articles = session.exec(select(KnowledgeArticle)).all()
        terms = [t for t in re.split(r"[\s，。？！、]+", query.lower()) if t]
        ranked = []
        for a in articles:
            if species and species not in a.species:
                continue
            if topic and a.topic != topic:
                continue
            if (
                life_stage
                and "all" not in a.life_stages
                and life_stage not in a.life_stages
            ):
                continue
            hay = (a.title + " " + a.body + " " + " ".join(a.keywords)).lower()
            score = sum(3 for k in a.keywords if k in query.lower()) + sum(
                1 for t in terms if t in hay
            )
            if not query or score > 0:
                ranked.append((score, a))
        return [a for _, a in sorted(ranked, key=lambda x: (-x[0], x[1].id))]


retriever: Retriever = KeywordRetriever()


def serialize_article(a, bookmarked=False):
    return {**a.model_dump(), "bookmarked": bookmarked}


def search_knowledge(session, species, query, topic=None, limit=5, life_stage=None):
    return [
        a.model_dump()
        for a in retriever.search(session, species, query, topic, life_stage)[:limit]
    ]
