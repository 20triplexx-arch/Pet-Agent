import json, argparse
from pathlib import Path
from urllib.parse import urlparse
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlmodel import Session
from app.core.db import engine
from app.models import KnowledgeArticle, Breed


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str = Field(min_length=1)
    url: HttpUrl
    supports: str = Field(min_length=1)
    version: str = Field(min_length=1)
    checked_at: str


class ArticleImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    species: list[str] = Field(min_length=1)
    life_stages: list[str] = Field(min_length=1)
    topic: str
    keywords: list[str]
    source_organization: str
    source_url: HttpUrl
    source_version: str
    published_at: str | None = None
    ingested_at: str
    updated_at: str
    review_status: str = "editorial_summary_unreviewed"
    content_kind: Literal["care", "breed", "food", "supplies"] = "care"
    breed_ids: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)


def import_file(path, session):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validated = [ArticleImport.model_validate(a).model_dump(mode="json") for a in data]
    for a in validated:
        if a["review_status"] != "editorial_summary_unreviewed":
            raise ValueError("首版导入仅接受未经兽医审核的编辑摘要")
        if urlparse(a["source_url"]).scheme != "https":
            raise ValueError("来源需要 HTTPS")
        if any(s in ("bird", "turtle", "fish", "hamster") for s in a["species"]):
            raise ValueError("这些大类必须细分到具体物种")
        for bid in a["breed_ids"]:
            b = session.get(Breed, bid)
            if not b or b.species not in a["species"]:
                raise ValueError("知识品种必须与已登记物种匹配")
        if any(urlparse(r["url"]).scheme != "https" for r in a["references"]):
            raise ValueError("多来源也需要 HTTPS")
    for a in validated:
        existing = session.get(KnowledgeArticle, a["id"])
        if existing:
            for k, v in a.items():
                setattr(existing, k, v)
            session.add(existing)
        else:
            session.add(KnowledgeArticle(**a))
    session.commit()
    return len(validated)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path")
    args = p.parse_args()
    with Session(engine) as s:
        print(f"Imported {import_file(args.path, s)} articles")
