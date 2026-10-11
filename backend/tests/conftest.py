from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from app.main import app
from app.api.deps import get_db
from scripts.import_knowledge import import_file
from app.core.config import settings
from app.breeds import seed_breeds


@pytest.fixture(autouse=True)
def no_live_services(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "MODEL_API_KEY", "")
    monkeypatch.setattr(settings, "AMAP_ENABLED", False)
    monkeypatch.setattr(settings, "AMAP_API_KEY", "")


@pytest.fixture
def db(tmp_path):
    e = create_engine(
        "sqlite:///" + str(tmp_path / "test.db"),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(e, "connect")
    def fk(c, _):
        c.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        seed_breeds(s)
        import_file(Path("data/knowledge.json"), s)
        import_file(Path("data/knowledge_nutrition.json"), s)
        import_file(Path("data/knowledge_care.json"), s)
        import_file(Path("data/knowledge_breeds.json"), s)
        import_file(Path("data/knowledge_products.json"), s)
    yield e
    e.dispose()


@pytest.fixture
def client(db):
    def override():
        with Session(db) as s:
            yield s

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def account(client):
    def create(email="one@example.com"):
        assert (
            client.post(
                "/api/v1/users/signup",
                json={
                    "email": email,
                    "password": "StrongPassword2026!",
                    "full_name": "测试者",
                },
            ).status_code
            == 200
        )
        r = client.post(
            "/api/v1/login/access-token",
            data={"username": email, "password": "StrongPassword2026!"},
        )
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    return create


@pytest.fixture
def headers(account):
    return account()


@pytest.fixture
def cat(client, headers):
    r = client.post(
        "/api/v1/pets",
        headers={**headers, "Idempotency-Key": "cat"},
        json={
            "name": "测试猫",
            "species": "cat",
            "estimated_age_months": 8,
            "diet": "幼猫粮",
        },
    )
    assert r.status_code == 200
    return r.json()
