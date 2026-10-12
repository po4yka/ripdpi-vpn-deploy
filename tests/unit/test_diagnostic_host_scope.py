"""Host overrides reach operator scripts without selecting the primary host."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def executable(path, text):
    path.write_text(text)
    path.chmod(0o700)


def test_explicit_host_scripts_do_not_read_primary_address(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    for name in ['burn-check.sh', 'probing-summary.sh', 'asn-drift.sh']:
        shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
    executable(scripts / 'terraform-env.sh', '''#!/bin/sh
case "$*" in
  'output -raw admin_user') echo admin ;;
  *) echo unexpected-primary-address >> "$CALLS"; exit 1 ;;
esac
''')
    executable(binaries / 'curl', '''#!/bin/sh
printf '%s\n' "$*" >> "$CALLS"
exit 22
''')
    executable(binaries / 'ssh', '''#!/bin/sh
printf '%s\n' "$*" >> "$CALLS"
cat >/dev/null
''')
    (scripts / 'probing-summary-remote.py').write_text('# synthetic aggregator\n')
    executable(scripts / 'probe-asn.sh', '''#!/bin/sh
printf '%s\t64500\t203.0.113.0/24\tTEST\tTEST\n' "$1"
''')
    env = dict(os.environ, PATH=f'{binaries}:{os.environ["PATH"]}', HOME=str(tmp_path),
               IP='203.0.113.77', PROVIDER='upcloud', ENV='test', CALLS=str(tmp_path/'calls'),
               ENABLE_HYSTERIA='false')
    for key in ['NTFY_URL', 'NTFY_TOPIC', 'NODE_EXPORTER_TEXTFILE_DIR']:
        env.pop(key, None)
    result = subprocess.run(['bash', str(scripts/'burn-check.sh')], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2, result.stderr
    assert 'host=203.0.113.77:443' in (tmp_path/'calls').read_text()
    result = subprocess.run(['bash', str(scripts/'probing-summary.sh')], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    calls = (tmp_path/'calls').read_text()
    assert 'admin@203.0.113.77' in calls and 'unexpected-primary-address' not in calls
    state = tmp_path/'.cache/vpn-deploy'
    state.mkdir(parents=True)
    primary = state/'asn-upcloud-test.state'
    primary.write_text('retained primary baseline\n')
    result = subprocess.run(['bash', str(scripts/'asn-drift.sh')], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert primary.read_text() == 'retained primary baseline\n'
    assert (state/'asn-upcloud-test-203.0.113.77.state').exists()
