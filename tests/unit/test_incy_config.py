"""The recipient config lists every issued server once, under names that hide the infrastructure."""
import base64
import json
import stat
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import pytest
from test_client_payload_incy_links import _fixture_payload
from test_emit_singbox_roundtrip import REPO_ROOT

SCRIPT = REPO_ROOT / 'scripts/incy_config.py'
CONF = '[Interface]\nPrivateKey = fixture-private\n\n[Peer]\nEndpoint = 198.51.100.10:51820\n'


def _recipient(tmp_path, mode=0o600, **changes):
    path = tmp_path / 'recipient.json'
    path.write_text(json.dumps({'profile': _fixture_payload(tmp_path), 'amneziawg_configs': {'node:prod': CONF}, **changes}))
    path.chmod(mode)
    output = tmp_path / 'out'
    output.mkdir(mode=0o700)
    return path, output / 'config.txt'


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, cwd=REPO_ROOT)


def test_config_orders_and_names_every_server(tmp_path):
    recipient, output = _recipient(tmp_path)
    result = _run(recipient, output)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f'wrote 4 INCY servers to {output}\n'
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    lines = [urlsplit(line) for line in output.read_text().splitlines()]
    assert [line.scheme for line in lines] == ['vless', 'vless', 'hysteria2', 'amneziawg']
    assert [unquote(line.fragment) for line in lines] == ['Основной', 'Запасной 1', 'Запасной 2 (UDP)', 'Запасной 3 (AWG)']
    assert 'security=reality' in lines[0].query and 'type=xhttp' in lines[1].query
    encoded = lines[3].netloc + lines[3].path
    assert base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode() == CONF
    assert 'upcloud' not in output.read_text()


@pytest.mark.parametrize(('mode', 'changes', 'refusal'), [
    (0o644, {}, 'incy-config: unsafe-recipient-input\n'),
    (0o600, {'profile': {'outbounds': []}}, 'incy-config: unsupported-incy-outbound\n'),
])
def test_config_refuses_without_writing(tmp_path, mode, changes, refusal):
    recipient, output = _recipient(tmp_path, mode, **changes)
    result = _run(recipient, output)
    assert (result.returncode, result.stdout, result.stderr) == (2, '', refusal)
    assert not output.exists()


def test_make_target_needs_both_paths():
    result = subprocess.run(['make', '--no-print-directory', 'emit-incy-config', 'OUTPUT=/private/config.txt'],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode != 0
    assert 'usage: make emit-incy-config RECIPIENT=<recipient.json> OUTPUT=<new file in a 0700 directory>' in result.stdout + result.stderr
