import io
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
import pytest
from app.core.config import settings


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
