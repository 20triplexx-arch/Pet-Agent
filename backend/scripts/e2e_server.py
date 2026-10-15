"""Isolated browser-test server; never touches the demo user's local database."""

import os, tempfile
from pathlib import Path

def prepare():
    folder = Path(
    tempfile.mkdtemp(prefix="e2e-", dir=Path(__file__).resolve().parents[1] / "storage")
    )
    os.environ["DATABASE_URL"] = "sqlite:///" + (folder / "e2e.db").as_posix()
    os.environ["EXECUTION_LOG_PATH"] = str(folder / "execution.jsonl")
    os.environ["DEMO_MODE"] = "true"
    os.environ["MODEL_API_KEY"] = ""
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["DASHSCOPE_API_KEY"] = ""
    os.environ["DASHSCOPE_WORKSPACE_ID"] = ""
    os.environ["DASHSCOPE_BASE_URL"] = ""
    os.environ["MODEL_PROVIDER"] = "compatible"
    os.environ["SECRET_KEY"] = "isolated-browser-test-key-not-for-production"
    os.environ["AMAP_ENABLED"] = "false"
    os.environ["AMAP_API_KEY"] = ""
    os.environ["HOSPITAL_MAP_PROVIDER"] = "amap"
    os.environ["TIANDITU_ENABLED"] = "false"
    os.environ["TIANDITU_API_KEY"] = ""
    from scripts.init_db import initialize
    initialize(demo=True)
if __name__ == "__main__":
    prepare()
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("CHONGBAN_E2E_PORT", "8011")))
