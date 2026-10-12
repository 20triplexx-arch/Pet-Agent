"""Knowledge coverage, retrieval usefulness, retained bookmarks and safe demo reading."""
import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.models import KnowledgeArticle
from scripts.import_knowledge import import_file


def chat(client, headers, pet_id, text):
    from uuid import uuid4
    return client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"pet_id": pet_id, "text": text})


def test_curated_corpus_has_readable_coverage(client, headers):
    articles = client.get("/api/v1/knowledge", headers=headers).json()
    corpus = [a for path in Path("data").glob("knowledge*.json") for a in json.loads(path.read_text(encoding="utf-8"))]
    assert {a["id"] for a in articles} == {a["id"] for a in corpus}
    assert len({a["id"] for a in articles}) == len(articles)
    topics = {"养宠前准备", "新宠到家", "饮食与体重", "居住与清洁", "互动与训练", "生命阶段", "误区与危险", "健康与就医"}
    assert topics.issubset({a["topic"] for a in articles})
    for species in ("cat", "dog"):
        for topic in topics:
            selected = client.get("/api/v1/knowledge", headers=headers, params={"species": species, "topic": topic}).json()
            assert selected, (species, topic)
    for article in articles:
        assert len(article["body"]) >= 300
        assert article["body"].count("## ") >= 4
        assert article["source_url"].startswith("https://")
        assert article["source_version"]
        assert article["review_status"] == "editorial_summary_unreviewed"


@pytest.mark.parametrize("species,query,expected", [
    ("cat", "猫抓沙发怎么办", "cat-scratching"),
    ("cat", "多猫相处怎样介绍新猫", "cat-multi"),
    ("cat", "猫不吃东西", "cat-appetite"),
    ("cat", "猫航空箱适应", "cat-carrier"),
    ("dog", "幼犬乱尿怎么教如厕", "dog-toilet"),
    ("dog", "狗独自在家叫", "dog-alone"),
    ("dog", "狗刷牙用品", "dog-dental"),
    ("dog", "冬季狗保暖", "dog-winter"),
])
def test_specific_questions_find_species_appropriate_articles(client, headers, species, query, expected):
    articles = client.get("/api/v1/knowledge", headers=headers, params={"species": species, "q": query}).json()
    assert articles[0]["id"] == expected
    assert all(species in a["species"] for a in articles)
    assert client.get("/api/v1/knowledge", headers=headers, params={"species": "rabbit", "q": query}).json() == []


def test_content_upsert_preserves_personal_bookmark(client, headers, db, tmp_path):
    assert client.put("/api/v1/knowledge/cat-food/bookmark", headers=headers).status_code == 200
    data = next(a for a in json.loads(Path("data/knowledge.json").read_text(encoding="utf-8")) if a["id"] == "cat-food")
    data["body"] += "\n\n## 内容更新测试\n新的编辑说明。"
    path = tmp_path / "update.json"
    path.write_text(json.dumps([data], ensure_ascii=False), encoding="utf-8")
    with Session(db) as session:
        before = len(session.exec(select(KnowledgeArticle)).all())
        assert import_file(path, session) == 1
        assert import_file(path, session) == 1
        assert len(session.exec(select(KnowledgeArticle)).all()) == before
    article = client.get("/api/v1/knowledge/cat-food", headers=headers).json()
    assert article["bookmarked"] is True and article["body"].endswith("新的编辑说明。")


def test_demo_excerpts_and_citations_are_real_and_bounded(client, headers, cat):
    reply = chat(client, headers, cat["id"], "猫抓沙发怎么办").json()
    assert reply["mode"] == "demo"
    assert "步骤" in reply["answer"] or "怎样" in reply["answer"]
    assert "替代" in reply["answer"] and "1." in reply["answer"]
    assert reply["sources"][0]["id"] == "cat-scratching"
    assert "## " in reply["answer"] and reply["sources"][0]["sections"]
    for source in reply["sources"]:
        article = client.get("/api/v1/knowledge/" + source["id"], headers=headers).json()
        assert source["url"] == article["source_url"]
    health = chat(client, headers, cat["id"], "猫不吃东西").json()
    assert "不能" in health["answer"] or "不足以确定病因" in health["answer"]
    assert "不先按“挑食”处理" in health["answer"]
    assert any(s["id"] == "cat-appetite" for s in health["sources"])
    urgent = chat(client, headers, cat["id"], "猫呼吸困难").json()
    assert urgent["urgent"] is True
    assert urgent["answer"].startswith("请立即联系兽医")
