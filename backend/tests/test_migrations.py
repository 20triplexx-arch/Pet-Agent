import io
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
import pytest
from app.core.config import settings
from sqlmodel import Session, select
from app.models import User, Pet, CareLog, CarePlan


def test_actual_sqlite_upgrade_downgrade(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "migration.db")
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "user",
        "pet",
        "careplan",
        "caretask",
        "carelog",
        "reminder",
        "message",
        "idempotencyrecord",
        "taskcompletion",
    }.issubset(tables)
    assert {"active", "weekday"}.issubset(
        {c["name"] for c in inspect(engine).get_columns("caretask")}
    )
    engine.dispose()
    command.downgrade(config, "base")
    engine = create_engine(url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()


@pytest.mark.parametrize(
    "url", ["sqlite:///offline.db", "postgresql+psycopg://user:pass@localhost/chongban"]
)
def test_initial_migration_dialects_offline(url, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    output = io.StringIO()
    config = Config("alembic.ini", output_buffer=output)
    command.upgrade(config, "head", sql=True)
    assert "CREATE TABLE careplan" in output.getvalue()
    assert "FOREIGN KEY" in output.getvalue()
    assert "UNIQUE" in output.getvalue()
    assert "CREATE TABLE petnutritionprofile" in output.getvalue()
    assert "ALTER TABLE careplan ADD COLUMN provenance" in output.getvalue()


def test_incremental_upgrade_preserves_existing_data(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "old.db")
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "385c23b07d08")
    engine = create_engine(url)
    # Insert against the old schema, before the new provenance column exists.
    with engine.begin() as c:
        c.exec_driver_sql("INSERT INTO user (id,email,hashed_password,full_name,is_active,timezone,created_at) VALUES ('u','legacy@example.com','hash','保留账户',1,'Asia/Shanghai','2026-01-01')")
        c.exec_driver_sql("INSERT INTO pet (id,user_id,name,species,created_at) VALUES ('p','u','保留猫','cat','2026-01-01')")
        c.exec_driver_sql("INSERT INTO carelog (id,user_id,pet_id,kind,note,occurred_at,created_at) VALUES ('l','u','p','observation','保留记录','2026-01-01','2026-01-01')")
        c.exec_driver_sql("INSERT INTO careplan (id,user_id,pet_id,title,basis,status,revision,created_at) VALUES ('c','u','p','保留计划','用户安排','active',1,'2026-01-01')")
    command.upgrade(config, "head")
    with Session(engine) as s:
        assert s.get(User, "u").email == "legacy@example.com"
        assert s.get(Pet, "p").name == "保留猫"
        assert s.get(CareLog, "l").note == "保留记录"
        assert s.get(CarePlan, "c").provenance is None
    engine.dispose()
