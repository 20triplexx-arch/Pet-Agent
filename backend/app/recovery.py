"""Verified SQLite snapshots and restore into a new directory only."""
import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime, UTC
from contextlib import closing


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_database(path):
    with closing(sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key check failed")


def create_backup(database, secret, destination):
    database, secret, destination = Path(database), Path(secret), Path(destination)
    if not database.is_file() or destination.exists():
        raise ValueError("Existing source database and a new destination are required")
    verify_database(database)
    destination.mkdir(parents=True, exist_ok=False)
    target = destination / "chongban.db"
    before = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    after = sqlite3.connect(target)
    try:
        before.backup(after)
    finally:
        before.close()
        after.close()
    verify_database(target)
    files = {"chongban.db": digest(target)}
    if secret.is_file():
        (destination / ".secret").write_bytes(secret.read_bytes())
        files[".secret"] = digest(destination / ".secret")
    manifest = {"version": 1, "created_at": datetime.now(UTC).isoformat(), "files": files}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def restore_backup(source, destination):
    source, destination = Path(source), Path(destination)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    names = set(manifest["files"])
    if manifest["version"] != 1 or not {"chongban.db"} <= names <= {"chongban.db", ".secret"}:
        raise ValueError("Invalid backup manifest")
    if destination.exists():
        raise ValueError("Restore destination must not exist; running data is never overwritten")
    for name, expected in manifest["files"].items():
        if digest(source / name) != expected:
            raise ValueError("Backup checksum mismatch")
    verify_database(source / "chongban.db")
    destination.mkdir(parents=True, exist_ok=False)
    for name in names:
        (destination / name).write_bytes((source / name).read_bytes())
    verify_database(destination / "chongban.db")
    return {"restored_files": sorted(names), "integrity": "ok"}
