"""Linux CI: fresh volume, health/UI checks and persistent restart. No external models."""
import json
import subprocess
import time
import urllib.request
from uuid import uuid4


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def wait_health():
    for _ in range(90):
        try:
            with urllib.request.urlopen("http://127.0.0.1:18014/health", timeout=2) as response:
                health = json.load(response)
                assert health == {"status": "ok", "mode": "demo"}
                return
        except (OSError, AssertionError):
            time.sleep(1)
    raise RuntimeError("Container did not become ready")


def main():
    ident = "chongban-ci-" + uuid4().hex[:12]
    volume, container = ident + "-data", ident + "-app"
    created_volume = created_container = False
    try:
        command("docker", "volume", "create", volume)
        created_volume = True
        command("docker", "run", "-d", "--name", container, "-p", "127.0.0.1:18014:8000", "-v", volume + ":/app/backend/storage",
                "-e", "DEMO_MODE=true", "-e", "MODEL_API_KEY=", "-e", "DEEPSEEK_API_KEY=", "chongban-ci")
        created_container = True
        wait_health()
        with urllib.request.urlopen("http://127.0.0.1:18014/", timeout=5) as response:
            assert response.status == 200 and b"<html" in response.read()
        # A new install has migrated schema and real knowledge, without demo users.
        check = "import sqlite3,json,hashlib; from pathlib import Path; c=sqlite3.connect('storage/chongban.db'); print(json.dumps({'knowledge':c.execute('SELECT COUNT(*) FROM knowledgearticle').fetchone()[0],'users':c.execute('SELECT COUNT(*) FROM user').fetchone()[0],'revision':c.execute('SELECT version_num FROM alembic_version').fetchone()[0],'key_hash':hashlib.sha256(Path('storage/.secret').read_bytes()).hexdigest()}))"
        before = json.loads(command("docker", "exec", container, "python", "-c", check))
        assert before["knowledge"] == 89 and before["users"] == 0 and before["revision"] == "20261011_products"
        command("docker", "restart", container)
        wait_health()
        after = json.loads(command("docker", "exec", container, "python", "-c", check))
        assert before == after
        print(json.dumps({"fresh_install": "passed", "persistent_restart": "passed", "private_data_used": False}))
    finally:
        # Exact random resources created by this script; no workspace deletion.
        if created_container:
            subprocess.run(["docker", "rm", "-f", container], check=False, capture_output=True)
        if created_volume:
            subprocess.run(["docker", "volume", "rm", volume], check=False, capture_output=True)


if __name__ == "__main__":
    main()
