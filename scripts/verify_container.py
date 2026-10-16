"""Linux CI: fresh Docker volume and persistent synthetic workflow, without live APIs."""
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from scripts.installation_checks import ISOLATED_ENV, check_persisted, check_public, exercise, require, wait_health


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'{args[0]} {args[1]} failed: {result.stderr[-4000:]}')
    return result.stdout.strip()


def main():
    ident = 'chongban-ci-' + uuid4().hex[:12]
    volume, container = ident + '-data', ident + '-app'
    created_volume = created_container = False
    report = ROOT / 'artifacts/installation'
    report.mkdir(parents=True, exist_ok=True)
    try:
        command('docker', 'volume', 'create', volume)
        created_volume = True
        env = [arg for k, v in ISOLATED_ENV.items() for arg in ['-e', f'{k}={v}']]
        command('docker', 'run', '-d', '--name', container, '-p', '127.0.0.1::8000',
                '-v', volume + ':/app/backend/storage', *env, 'chongban-ci')
        created_container = True
        port = command('docker', 'port', container, '8000/tcp').splitlines()[0].rsplit(':', 1)[1]
        base = 'http://127.0.0.1:' + port
        wait_health(base)
        check_public(base)
        initial = json.loads(command('docker', 'exec', container, 'python', '-m', 'scripts.installation_checks'))
        require(initial['counts']['user'] == 0, 'Fresh image unexpectedly contains accounts')
        state = exercise(base)
        before = json.loads(command('docker', 'exec', container, 'python', '-m', 'scripts.installation_checks'))
        command('docker', 'exec', container, 'python', '-m', 'scripts.init_db')
        command('docker', 'restart', container)
        wait_health(base)
        check_public(base)
        check_persisted(base, state)
        after = json.loads(command('docker', 'exec', container, 'python', '-m', 'scripts.installation_checks'))
        require(before == after, 'Data or signing key changed after initialization/restart')
        result = {'fresh_install': 'passed', 'persistent_restart': 'passed',
                  'knowledge': initial['knowledge'], 'revision': initial['revision'], 'private_data_used': False}
        (report / 'container.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))
    except Exception:
        if created_container:
            logs = subprocess.run(['docker', 'logs', '--tail', '200', container], capture_output=True, text=True)
            (report / 'container.log').write_text(logs.stdout + logs.stderr, encoding='utf-8')
            status = subprocess.run(['docker', 'inspect', '--format', '{{json .State}}', container], capture_output=True, text=True)
            print('Container state: ' + status.stdout, file=sys.stderr)
            print((logs.stdout + logs.stderr)[-6000:], file=sys.stderr)
        raise
    finally:
        if created_container:
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        if created_volume:
            subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    main()
