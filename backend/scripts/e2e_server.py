"""Isolated browser-test server; never touches the demo user's local database."""

import os, tempfile
from pathlib import Path

folder = Path(
    tempfile.mkdtemp(prefix="e2e-", dir=Path(__file__).resolve().parents[1] / "storage")
)
os.environ["DATABASE_URL"] = "sqlite:///" + (folder / "e2e.db").as_posix()
os.environ["DEMO_MODE"] = "true"
os.environ["MODEL_API_KEY"] = ""
from scripts.init_db import initialize

initialize(demo=True)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8011)
