from datetime import datetime, UTC, timedelta
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from sqlmodel import Session, select
from app.models import CareLog, CarePlan, Reminder, TaskCompletion, PetNutritionProfile, User, KnowledgeArticle
from app.care_review import build_review
from app.clock import iso
from app.agent import AgentContext, get_care_review
from app.deep_chat import source_cards
from app.core.config import settings
from app.knowledge import sections, search_knowledge
from tests.test_model_adapter import fake_provider

NOW = datetime(2026, 3, 10, 16, tzinfo=UTC)


def add_record(client, headers, pid, kind="diet", **kw):
    return client.post(f"/api/v1/pets/{pid}/logs", headers={**headers, "Idempotency-Key": "record-" + str(kw)},
        json={"kind": kind, "note": "真实执行记录", "occurred_at": iso(NOW - timedelta(hours=1)), **kw})


def test_review_local_calendar_and_weight_sources(client, headers, cat, monkeypatch):
    import app.care_review as module
    monkeypatch.setattr(module, "utc_now", lambda: NOW)
    assert client.patch("/api/v1/users/me", headers=headers, json={"timezone": "America/New_York", "full_name": "复盘测试"}).status_code == 200
    pid = cat["id"]
    # Seven local dates cross the March 8 DST boundary; start is March 4 05:00 UTC.
    assert add_record(client, headers, pid, occurred_at="2026-03-04T04:59:59+00:00").status_code == 200
    first = add_record(client, headers, pid, "weight", value=4, occurred_at="2026-03-04T05:00:00+00:00").json()
    last = add_record(client, headers, pid, "weight", value=4.2, occurred_at="2026-03-10T15:00:00+00:00").json()
    result = client.get(f"/api/v1/pets/{pid}/care-review?days=7", headers=headers)
    assert result.status_code == 200, result.text
    review = result.json()
    assert review["period"] == {"days": 7, "timezone": "America/New_York", "start_date": "2026-03-04", "end_date": "2026-03-10"}
    assert review["summary"]["records"] == 2 and review["summary"]["recorded_days"] == 2
    assert review["summary"]["unrecorded_days"] == 5
    assert review["weight"]["change_kg"] == .2 and review["weight"]["change_percent"] == 5
    assert review["record_ids"] == [first["id"], last["id"]]
    assert "未记录不等于未照护" in review["text"]
    assert client.get(f"/api/v1/pets/{pid}/care-review?days=8", headers=headers).status_code == 422


def test_batch_atomic_retry_and_confirmation(client, headers, cat):
    path = f"/api/v1/pets/{cat['id']}/logs/batch"
    entries = [{"kind": "diet", "note": "主粮实测60克，剩余未测", "occurred_at": iso(NOW)},
        {"kind": "activity", "note": "嗅闻散步，时长未测", "occurred_at": iso(NOW)}]
    for payload in ({"entries": entries}, {"entries": entries, "confirm": False}, {"entries": [], "confirm": True},
        {"entries": [entries[0], entries[0]], "confirm": True},
        {"entries": [entries[0], {**entries[1], "value": 5}], "confirm": True}):
        assert client.post(path, headers=headers, json=payload).status_code == 422
    assert client.get(f"/api/v1/pets/{cat['id']}/logs", headers=headers).json() == []
    auth = {**headers, "Idempotency-Key": "batch-confirmed"}
    first = client.post(path, headers=auth, json={"entries": entries, "confirm": True})
    again = client.post(path, headers=auth, json={"entries": entries, "confirm": True})
    assert first.status_code == 200 and first.json() == again.json()
    assert first.json()["saved"] == 2
    assert len(client.get(f"/api/v1/pets/{cat['id']}/logs", headers=headers).json()) == 2
    assert client.post(path, headers=auth, json={"entries": entries[:1], "confirm": True}).status_code == 409


def test_batch_failure_rolls_back_and_concurrent_retry(client, headers, cat, monkeypatch):
    import app.api.care_routes as routes
    original, calls = routes.add_log, []
    def failed(*args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Injected transaction failure")
        return original(*args)
    monkeypatch.setattr(routes, "add_log", failed)
    path = f"/api/v1/pets/{cat['id']}/logs/batch"
    payload = {"entries": [{"kind": kind, "note": "实际观察", "occurred_at": iso(NOW)} for kind in ("diet", "activity")], "confirm": True}
    auth = {**headers, "Idempotency-Key": "atomic-batch"}
    assert client.post(path, headers=auth, json=payload).status_code == 500
    assert client.get(f"/api/v1/pets/{cat['id']}/logs", headers=headers).json() == []
    monkeypatch.setattr(routes, "add_log", original)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: client.post(path, headers=auth, json=payload), range(3)))
    assert all(r.status_code == 200 for r in results)
    assert all(r.json() == results[0].json() for r in results)
    assert len(client.get(f"/api/v1/pets/{cat['id']}/logs", headers=headers).json()) == 2


def test_review_and_batch_are_private(client, account, headers, cat):
    other = account("review-other@example.com")
    for path in (f"/api/v1/pets/{cat['id']}/care-review",):
        assert client.get(path, headers=other).status_code in (403, 404)
    body = {"entries": [{"kind": "diet", "note": "其他用户注入", "occurred_at": iso(NOW)}], "confirm": True}
    assert client.post(f"/api/v1/pets/{cat['id']}/logs/batch", headers={**other, "Idempotency-Key": "private"}, json=body).status_code in (403, 404)
    assert client.get(f"/api/v1/pets/{cat['id']}/logs", headers=headers).json() == []


def test_review_completed_history_and_nutrition_reassessment(db, cat):
    with Session(db) as session:
        user = session.get(User, cat["user_id"])
        plan = CarePlan(user_id=user.id, pet_id=cat["id"], title="营养方案", basis="用户确认", created_at=iso(NOW - timedelta(days=5)))
        session.add(plan); session.flush()
        profile = PetNutritionProfile(user_id=user.id, pet_id=cat["id"], active_plan_id=plan.id)
        reminder = Reminder(user_id=user.id, pet_id=cat["id"], title="旧任务", timezone=user.timezone, local_time="08:00", due_at=iso(NOW - timedelta(days=2)), paused=True)
        session.add(profile); session.add(reminder); session.flush()
        done = TaskCompletion(user_id=user.id, reminder_id=reminder.id, occurrence_at=reminder.due_at, completed_at=iso(NOW - timedelta(days=1)))
        record = CareLog(user_id=user.id, pet_id=cat["id"], kind="weight", value=4, occurred_at=iso(NOW - timedelta(days=1)))
        session.add(done); session.add(record); session.commit()
        result = build_review(session, user, cat["id"], current=NOW)
        assert result["summary"]["completed_occurrences"] == 1 and result["summary"]["current_due"] == 0
        assert result["weight"]["change_kg"] is None
        assert any(s["title"] == "新记录可用于营养复评" for s in result["suggestions"])
        assert session.get(CarePlan, plan.id).revision == 1 and session.get(Reminder, reminder.id).paused
        assert get_care_review(SimpleNamespace(deps=AgentContext(session, user, cat["id"])), 30)["pet_id"] == cat["id"]


def test_review_fresh_emergency_and_old_observation(db, cat):
    with Session(db) as session:
        user = session.get(User, cat["user_id"])
        for hours, text in [(2, "无法排尿，反复蹲猫砂盆"), (26, "呼吸困难"), (3, "没有呼吸困难")]:
            session.add(CareLog(user_id=user.id, pet_id=cat["id"], kind="observation", note=text, occurred_at=iso(NOW-timedelta(hours=hours))))
        session.commit()
        result = build_review(session, user, cat["id"], current=NOW)
        assert result["alerts"] and all(a["occurred_at"] == iso(NOW-timedelta(hours=2)) for a in result["alerts"])
        assert all(session.get(KnowledgeArticle, a["article_id"]) for a in result["alerts"])
        assert "若仍在发生" in result["alerts"][0]["message"]


def test_chat_review_never_calls_model_or_creates_plan(client, headers, cat, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    async def forbidden(*args):
        raise AssertionError("Review must remain local")
    monkeypatch.setattr("app.model_adapter.run_model", forbidden)
    response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "review-chat"}, json={"pet_id": cat["id"], "text": "请做照护复盘"})
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "local_review" and response.json()["cards"][0]["href"] == "/logs#care-review"
    assert "没有记录" in response.json()["answer"] and response.json()["draft"] is None
    assert client.get(f"/api/v1/pets/{cat['id']}/plans", headers=headers).json() == []


def test_source_evidence_is_actual_excerpt(db, cat):
    with Session(db) as session:
        articles = search_knowledge(session, "cat", "照护复盘", limit=3, personal=True)
        assert any(a["id"] == "care-review-week" for a in articles)
        cards = source_cards(SimpleNamespace(), articles)
        for card in cards:
            for evidence in card["evidence"]:
                original = next(s for s in sections(next(a for a in articles if a["id"] == card["id"])) if s["heading"] == evidence["heading"])
                assert original["text"].startswith(evidence["text"])


def test_review_does_not_use_current_cat_for_another_species(client, headers, cat):
    result = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "other-review"},
        json={"pet_id": cat["id"], "text": "请做狗的照护复盘"})
    assert result.status_code == 200
    assert "切换" in result.json()["answer"] and "宠物不同" in result.json()["answer"]
    assert result.json()["sources"] == [] and result.json()["draft"] is None


@pytest.mark.parametrize("fabricated", [False, True])
def test_model_citation_passage_cannot_be_fabricated(client, headers, cat, monkeypatch, fabricated):
    article = client.get("/api/v1/knowledge/cat-food", headers=headers).json()
    section = sections(article)[0]
    citation = {"article_id": "cat-food", "heading": section["heading"], "evidence_text": "来源没有的固定三分钟保证健康" if fabricated else section["text"][:25]}
    fake_provider(monkeypatch, "核对生命阶段、标签与实际摄入。", source="cat-food", citation_sections=[citation])
    result = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "passage-"+str(fabricated)}, json={"pet_id": cat["id"], "text": "猫日常喂食饮食注意什么"})
    assert result.status_code == (502 if fabricated else 200), result.text
    if fabricated:
        assert "片段" in result.json()["detail"]


def test_six_followup_guides_and_species_scope(db):
    with Session(db) as session:
        ids = {"care-record-quality", "care-review-week", "feeding-followup", "dog-fear-support", "cat-low-stress-care", "care-handoff"}
        for ident in ids:
            a = session.get(KnowledgeArticle, ident)
            assert a and a.review_status == "editorial_summary_unreviewed" and a.references
            assert all(r["url"].startswith("https://") and r["supports"] for r in a.references)
        assert all(a["id"] != "dog-fear-support" for a in search_knowledge(session, "cat", "害怕奖励护理", limit=100))
        assert all(a["id"] != "cat-low-stress-care" for a in search_knowledge(session, "dog", "害怕奖励护理", limit=100))
