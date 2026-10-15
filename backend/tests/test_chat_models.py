import json
import pytest
from sqlmodel import Session, select
from app.core.config import settings
from app.chat_models import select_model
from app.models import ModelUsage, Message
from test_model_adapter import fake_provider


def test_catalog_authentication_and_secret_free_options(client, headers, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "private-deepseek-key")
    assert client.get("/api/v1/chat/models").status_code == 401
    response = client.get("/api/v1/chat/models", headers=headers)
    data = response.json()
    assert data["default_id"] == "deepseek"
    options = {o["id"]: o for o in data["options"]}
    assert options["demo"]["available"] and options["deepseek"]["available"]
    assert not options["compatible"]["available"]
    assert "private-deepseek-key" not in response.text and "base_url" not in response.text
    assert "private-deepseek-key" not in repr(select_model("deepseek"))


def test_explicit_demo_does_not_call_model_or_change_global_mode(client, headers, cat, monkeypatch, db):
    fake_provider(monkeypatch, "不会调用此回答")
    monkeypatch.setattr(settings, "MODEL_TURNS_PER_DAY", 0)
    response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "demo-override"},
        json={"pet_id": cat["id"], "text": "猫喂食要注意什么", "model_id": "demo"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mode"] == "demo" and data["model_selection"]["id"] == "demo"
    assert data["model_used"] is None and data["execution"]["model_requests"] == 0
    assert settings.DEMO_MODE is False
    with Session(db) as session:
        assert session.exec(select(ModelUsage)).all() == []
        user = session.exec(select(Message).where(Message.role == "user")).one()
        assert user.metadata_json["model_id"] == "demo"


def test_explicit_real_uses_selected_model_and_idempotency_in_demo_default(client, headers, cat, monkeypatch, db):
    seen = fake_provider(monkeypatch, "根据检索资料核对猫的饮食。", model="selected-model")
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    payload = {"pet_id": cat["id"], "text": "猫喂食建议", "model_id": "compatible"}
    key = {**headers, "Idempotency-Key": "real-override"}
    first = client.post("/api/v1/chat", headers=key, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["mode"] == "live" and first.json()["model_used"] == "selected-model"
    assert first.json()["model_selection"]["id"] == "compatible"
    assert client.post("/api/v1/chat", headers=key, json=payload).json()["message"]["id"] == first.json()["message"]["id"]
    assert len(seen) == 1 and settings.DEMO_MODE is True
    assert client.post("/api/v1/chat", headers=key, json={**payload, "model_id": "demo"}).status_code == 409
    with Session(db) as session:
        assert session.exec(select(ModelUsage)).one().model == "selected-model"


def test_provider_selection_does_not_borrow_keys_and_safety_precedes_configuration(client, headers, cat, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_API_KEY", "compatible-only-private-key")
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    payload = {"pet_id": cat["id"], "model_id": "deepseek"}
    failed = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "missing-selected-key"}, json={**payload, "text": "猫喂食建议"})
    assert failed.status_code == 503 and "compatible-only-private-key" not in failed.text
    emergency = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "selected-safety"}, json={**payload, "text": "猫无法排尿"})
    assert emergency.status_code == 200 and emergency.json()["urgent"]
    assert emergency.json()["model_used"] is None and emergency.json()["mode"] == "safety"


def test_explicit_deepseek_uses_own_key_url_and_thinking_setting(client, headers, cat, monkeypatch):
    seen = fake_provider(monkeypatch, "根据真实检索内容回答。", model="deep-model")
    from app import model_adapter
    client_factory = model_adapter.AsyncOpenAI
    captured = []
    def factory(**kwargs):
        captured.append(kwargs)
        return client_factory(**kwargs)
    monkeypatch.setattr(model_adapter, "AsyncOpenAI", factory)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "deepseek-own-private-key")
    monkeypatch.setattr(settings, "DEEPSEEK_MODEL", "deep-model")
    monkeypatch.setattr(settings, "MODEL_NAME", "other-model")
    response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "choose-deepseek"},
        json={"pet_id": cat["id"], "text": "猫喂食建议", "model_id": "deepseek"})
    assert response.status_code == 200, response.text
    assert captured[0]["api_key"] == "deepseek-own-private-key" and captured[0]["base_url"] == "https://api.deepseek.com"
    assert seen[0]["model"] == "deep-model" and seen[0]["thinking"] == {"type": "disabled"}
    assert settings.MODEL_PROVIDER == "compatible" and "deepseek-own-private-key" not in response.text


@pytest.mark.parametrize("extra", [{"model_id": "unlisted-model"}, {"model_id": "demo", "base_url": "https://example.com"}, {"model_id": "demo", "api_key": "browser-key"}])
def test_client_cannot_choose_arbitrary_model_or_credentials(client, headers, extra):
    response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": "invalid-model"}, json={"text": "猫照护", **extra})
    assert response.status_code == 422
