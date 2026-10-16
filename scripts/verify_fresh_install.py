"""Run the documented native installer twice in a pristine, isolated source copy."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from scripts.installation_checks import ISOLATED_ENV, check_persisted, check_public, exercise, require, wait_health


def stop(process):
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=15)


def main():
    report = ROOT / 'artifacts/installation'
    report.mkdir(parents=True, exist_ok=True)
    source = Path(tempfile.mkdtemp(prefix='Pet Agent 安装验证 ', dir=report))
    files = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    for name in set(x.decode('utf-8') for x in files.split(b'\0') if x):
        origin = ROOT / name
        require(not name.startswith(('backend/storage/', 'artifacts/', '.tools/')), 'Private runtime file is tracked')
        require(Path(name).name != '.env', 'Local configuration is tracked')
        if origin.is_file():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
    require(all(not (source / name).exists() for name in
                ['.env', '.venv', 'backend/storage', 'frontend/node_modules', 'frontend/dist']), 'Source copy is not pristine')
    env = {**os.environ, **ISOLATED_ENV, 'PYTHONUTF8': '1'}
    for key in ['DATABASE_URL', 'EXECUTION_LOG_PATH', 'CHONGBAN_TEST_PYTHON']:
        env.pop(key, None)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env['CHONGBAN_PORT'] = str(port)
    base = 'http://127.0.0.1:' + str(port)
    python = source / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    setup = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/setup.ps1'] if os.name == 'nt' else ['sh', 'scripts/setup.sh']
    start = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/start.ps1', '-Port', str(port)] if os.name == 'nt' else ['sh', 'scripts/start.sh']
    process = None

    def state():
        return json.loads(subprocess.check_output([str(python), '-m', 'scripts.installation_checks'], cwd=source / 'backend', env=env, text=True, encoding='utf-8'))

    def launch(log):
        return subprocess.Popen(start, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=os.name != 'nt')

    try:
        with (report / 'setup.log').open('w', encoding='utf-8') as log:
            subprocess.run(setup, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        initial = state()
        require(initial['counts']['user'] == 1, 'Installer did not create exactly one demo account')
        config_hash = hashlib.sha256((source / '.env').read_bytes()).hexdigest()
        with (report / 'server.log').open('w', encoding='utf-8') as log:
            process = launch(log)
            wait_health(base)
            check_public(base)
            synthetic = exercise(base)
            stop(process)
            process = None
        before = state()
        with (report / 'setup-repeat.log').open('w', encoding='utf-8') as log:
            subprocess.run(setup, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        require(state() == before, 'Repeated installation changed business data or signing key')
        require(hashlib.sha256((source / '.env').read_bytes()).hexdigest() == config_hash, 'Installer overwrote configuration')
        with (report / 'server-restart.log').open('w', encoding='utf-8') as log:
            process = launch(log)
            wait_health(base)
            check_public(base)
            check_persisted(base, synthetic)
            stop(process)
            process = None
        require(state() == before, 'Restart changed persisted data or signing key')
        result = {'platform': sys.platform, 'fresh_install': 'passed', 'repeat_install': 'passed',
                  'persistent_restart': 'passed', 'ocr_required': False, 'private_data_used': False,
                  'knowledge': initial['knowledge'], 'revision': initial['revision']}
        (report / 'fresh-install.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))
    except Exception:
        for name in ['setup.log', 'server.log', 'setup-repeat.log', 'server-restart.log']:
            path = report / name
            if path.exists():
                print(name + ':\n' + path.read_text(encoding='utf-8', errors='replace')[-5000:], file=sys.stderr)
        raise
    finally:
        stop(process)
        # Keep this exact isolated copy for diagnosis; CI artifact uploads whitelist logs only.


if __name__ == '__main__':
    main()
