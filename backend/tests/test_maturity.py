import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace
import pytest
from app.core.config import settings
from app.evaluation_budget import EvaluationBudget, BudgetExceeded, current_budget
from app.recovery import create_backup, restore_backup
from test_model_adapter import fake_provider
from app.execution import Execution, current_execution


def price():
    return {"currency": "CNY", "model": "deepseek-flash", "checked_at": datetime.now(UTC).isoformat(),
            "peak_input_cache_miss_per_million": 2, "peak_output_per_million": 8}


def request():
    return {"model": "deepseek-flash", "messages": [{"role": "user", "content": "模拟"}], "max_tokens": 100,
            "extra_body": {"thinking": {"type": "disabled"}}}


def test_deepseek_key_and_thinking_disabled(client, headers, cat, monkeypatch, caplog):
    seen = fake_provider(monkeypatch, "根据资料逐步进行喂食管理。")
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "deepseek-test-secret")
    monkeypatch.setattr(settings, "DEEPSEEK_MODEL", "mock-model")
    caplog.set_level(logging.INFO, logger="chongban.execution")
    response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "deepseek-trace"}, json={"pet_id": cat["id"], "text": "喂食建议"})
    assert response.status_code == 200, response.text
    assert seen[0]["thinking"] == {"type": "disabled"}
    data = response.json()
    assert data["mode"] == "live"
    assert data["execution"]["request_id"] == response.headers["x-request-id"]
    assert data["execution"]["model_requests"] == 1
    assert data["execution"]["input_tokens"] == 320
    assert all(a["source_version"] for a in data["execution"]["retrieval"])
    entries = [json.loads(r.message) for r in caplog.records if r.name == "chongban.execution"]
    assert entries[-1]["http_status"] == 200
    assert not any(word in json.dumps(entries, ensure_ascii=False) for word in ("喂食建议", "deepseek-test-secret", "测试猫", "根据资料逐步"))


def test_deepseek_does_not_borrow_compatible_key(client, headers, cat, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "MODEL_API_KEY", "other-service-key")
    assert client.get("/api/v1/status", headers=headers).json()["mode"] == "configuration_error"
    response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "missing-deepseek"}, json={"pet_id": cat["id"], "text": "喂食建议"})
    assert response.status_code == 503
    assert "other-service-key" not in response.text


def test_budget_persists_failure_reservation_and_caps_concurrent_requests(tmp_path):
    path = tmp_path / "budget.db"
    budget = EvaluationBudget(path, price(), "0.1")
    def reserve(_):
        try:
            return budget.reserve(request())
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = [r for r in pool.map(reserve, range(20)) if r]
    state = budget.summary()
    assert 0 < state["conservative_used_cny"] <= 0.1
    assert state["reserved_or_billed_requests"] == len(accepted) < 20
    reopened = EvaluationBudget(path, price(), "0.1")
    assert reopened.summary()["conservative_used_cny"] == state["conservative_used_cny"]
    reopened.settle(accepted[0], None)
    assert reopened.summary()["conservative_used_cny"] == state["conservative_used_cny"]
    reopened.settle(accepted[0], SimpleNamespace(prompt_tokens=100, completion_tokens=10))
    assert reopened.summary()["conservative_used_cny"] < state["conservative_used_cny"]
    with pytest.raises(ValueError, match="raised"):
        EvaluationBudget(path, price(), "1")


def test_budget_rejects_unbounded_or_stale_requests(tmp_path):
    pricing = price()
    budget = EvaluationBudget(tmp_path / "budget.db", pricing)
    for change in ({"model": "deepseek-v4-pro"}, {"max_tokens": 100000}, {"stream": True}):
        with pytest.raises(ValueError):
            budget.reserve({**request(), **change})
    pricing["checked_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    with pytest.raises(ValueError, match="24 hours"):
        EvaluationBudget(tmp_path / "stale.db", pricing)


def test_provider_charge_survives_invalid_citation_rollback(client, headers, cat, monkeypatch, tmp_path):
    captured = fake_provider(monkeypatch, "伪造的来源", source="invented-article", model="deepseek-flash")
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "mock-key")
    budget = EvaluationBudget(tmp_path / "charges.db", price())
    token = current_budget.set(budget)
    try:
        response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "billed-failure"}, json={"pet_id": cat["id"], "text": "喂食建议"})
    finally:
        current_budget.reset(token)
    assert response.status_code == 502
    assert (captured[0].get("max_tokens") or captured[0].get("max_completion_tokens")) <= 1800
    assert budget.summary()["reserved_or_billed_requests"] == 1
    assert budget.summary()["conservative_used_cny"] == pytest.approx(.0012)
    assert client.get("/api/v1/usage", headers=headers).json() == {"requests": 1, "input_tokens": 320, "output_tokens": 70}


def test_budget_denial_returns_429_before_provider_call(client, headers, cat, monkeypatch, tmp_path):
    captured = fake_provider(monkeypatch, "不会执行", model="deepseek-flash")
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "mock-key")
    budget = EvaluationBudget(tmp_path / "small.db", price(), "0.01")
    token = current_budget.set(budget)
    try:
        response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "budget-denied"}, json={"pet_id": cat["id"], "text": "喂食建议"})
    finally:
        current_budget.reset(token)
    assert response.status_code == 429
    assert captured == []
    assert budget.summary()["reserved_or_billed_requests"] == 0


@pytest.mark.parametrize("name", ["get_pet_profile", "search_pet_knowledge", "get_breed_knowledge", "assess_pet_products",
                                "get_care_history", "get_current_care_plans", "assess_nutrition", "search_nearby_hospitals", "build_vet_visit_summary"])
def test_all_read_tools_execute_and_trace_current_pet(name, db, cat):
    import app.agent as agent_module
    from app.agent import AgentContext
    from app.models import User, Pet
    from pydantic_ai import RunContext
    from sqlmodel import Session
    with Session(db) as session:
        pet = session.get(Pet, cat["id"])
        context = AgentContext(session, session.get(User, pet.user_id), pet.id)
        run = RunContext(deps=context, model=None, usage=None, prompt="模拟只读工具检查")
        trace = Execution()
        token = current_execution.set(trace)
        try:
            value = getattr(agent_module, name)(run, "猫砂") if name == "search_pet_knowledge" else getattr(agent_module, name)(run)
        finally:
            current_execution.reset(token)
        assert value is not None
        assert trace.tools == [{"name": name, "status": "succeeded", "elapsed_ms": trace.tools[0]["elapsed_ms"]}]
        assert trace.model_requests == 0


@pytest.mark.parametrize("name,model_name", [("save_care_plan", "CarePlan"), ("create_reminder", "Reminder"), ("record_care_log", "CareLog")])
def test_all_write_tools_require_exact_authorization_and_trace(name, model_name, db, cat):
    import app.agent as agent_module
    import app.models as models
    from app.agent import AgentContext
    from app.schemas import PlanDraft, ReminderInput, LogInput
    from pydantic_ai import RunContext
    from fastapi import HTTPException
    from sqlmodel import Session, select
    payloads = {
        "save_care_plan": PlanDraft(title="明确授权模拟计划", basis="模拟依据", tasks=[{"title": "观察", "instructions": "记录真实观察", "basis": "模拟依据"}]),
        "create_reminder": ReminderInput(title="明确授权模拟提醒", due_local="2030-01-01T08:00:00", timezone="Asia/Shanghai"),
        "record_care_log": LogInput(kind="observation", note="明确授权模拟记录", occurred_at=datetime.now(UTC)),
    }
    with Session(db) as session:
        pet = session.get(models.Pet, cat["id"])
        context = AgentContext(session, session.get(models.User, pet.user_id), pet.id)
        run = RunContext(deps=context, model=None, usage=None, prompt="明确授权的模拟工具测试")
        trace = Execution()
        token = current_execution.set(trace)
        model = getattr(models, model_name)
        before = len(session.exec(select(model)).all())
        try:
            with pytest.raises(HTTPException) as error:
                getattr(agent_module, name)(run, payloads[name])
            assert error.value.status_code == 403
            assert len(session.exec(select(model)).all()) == before
            context.authorization = name
            context.authorized_payload = payloads[name].model_dump(mode="json")
            value = getattr(agent_module, name)(run, payloads[name])
        finally:
            current_execution.reset(token)
        assert value["id"]
        assert context.authorization is None
        assert len(session.exec(select(model)).all()) == before + 1
        assert [(t["name"], t["status"]) for t in trace.tools] == [(name, "failed"), (name, "succeeded")]


def test_verified_backup_restore_keeps_data_and_key(tmp_path):
    database = tmp_path / "original.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE example (id INTEGER PRIMARY KEY, note TEXT)")
        db.execute("INSERT INTO example VALUES (1, 'private-record')")
    secret = tmp_path / "original.secret"
    secret.write_bytes(b"private-signing-key")
    original = database.read_bytes()
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    manifest = create_backup(database, secret, backup)
    assert "private" not in json.dumps(manifest)
    restore_backup(backup, restored)
    with sqlite3.connect(restored / "chongban.db") as db:
        assert db.execute("SELECT note FROM example").fetchone() == ("private-record",)
    assert (restored / ".secret").read_bytes() == secret.read_bytes()
    assert database.read_bytes() == original
    with pytest.raises(ValueError, match="must not exist"):
        restore_backup(backup, restored)
    (backup / ".secret").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        restore_backup(backup, tmp_path / "invalid")
