"""Back up the configured local SQLite database and verify business rows survive upgrades."""
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import settings, STORAGE


def rows(connection, table, columns):
    names = ",".join('"' + col.replace('"', '""') + '"' for col in columns)
    data = connection.execute(f'SELECT {names} FROM "{table}"').fetchall()
    return sorted(data, key=repr)


def main():
    url = make_url(settings.DATABASE_URL)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("This backup helper is for an existing local SQLite file")
    path = Path(url.database).resolve()
    if not path.is_file():
        raise RuntimeError("Database missing; initialize it first")
    folder = STORAGE / "backups" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-products")
    folder.mkdir(parents=True, exist_ok=False)
    secret = STORAGE / ".secret"
    secret_hash = hashlib.sha256(secret.read_bytes()).hexdigest() if secret.exists() else None
    if secret.exists():
        shutil.copy2(secret, folder / ".secret")
    with sqlite3.connect(path) as before, sqlite3.connect(folder / "chongban.db") as backup:
        before.backup(backup)
        tables = [r[0] for r in before.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        preserved = {}
        for table in tables:
            if table in ("knowledgearticle", "alembic_version", "breed"):
                continue
            columns = [r[1] for r in before.execute(f'PRAGMA table_info("{table}")')]
            preserved[table] = (columns, rows(before, table, columns))
    from scripts.init_db import initialize
    initialize(demo=False)
    with sqlite3.connect(path) as after:
        counts = {}
        for table, (columns, expected) in preserved.items():
            assert rows(after, table, columns) == expected, f"Business data changed: {table}; backup at {folder}"
            counts[table] = len(expected)
        assert not after.execute("PRAGMA foreign_key_check").fetchall()
        knowledge = after.execute("SELECT COUNT(*) FROM knowledgearticle").fetchone()[0]
        breeds = after.execute("SELECT COUNT(*) FROM breed").fetchone()[0]
        revision = after.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    if secret_hash:
        assert hashlib.sha256(secret.read_bytes()).hexdigest() == secret_hash
    report = {"backup": str(folder), "preserved_tables": counts, "knowledge": knowledge, "breeds": breeds, "revision": revision, "secret_preserved": bool(secret_hash)}
    (folder / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
