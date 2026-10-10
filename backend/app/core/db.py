from sqlalchemy import event
from sqlmodel import create_engine
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30}
    if settings.DATABASE_URL.startswith("sqlite")
    else {},
    pool_pre_ping=True,
)
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_config(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
