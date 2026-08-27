"""Registry-resolved refresh semantics for scripts/issue-sub-token.sh.

Covers REQ-REFRESH-OPTIONS and the registry-write side of
REQ-REGISTRY-LIFECYCLE:
  * a bare --refresh-token reuses format/hosts recorded in client_registry;
  * an unregistered token fails closed before any remote write;
  * a successful issuance records status/options in the encrypted document.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUER = REPO_ROOT / "scripts" / "issue-sub-token.sh"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "secrets-sample.yml"
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
REGISTERED_TOKEN = "fixture-token-for-contract-test"


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def _sops_stub(secrets_file: Path) -> str:
    body = """#!/bin/sh
set -eu
if [ "${ARG1:-}" = "set" ]; then
  value=$(cat)
  file="$3"
  path="$4"
  VALUE="$value" python3 - "$file" "$path" <<'PY'
import json, os, re, sys

file, path = sys.argv[1], sys.argv[2]
doc = json.load(open(file))
keys = re.findall(r'\["([^"]+)"\]', path)
node = doc
for key in keys[:-1]:
    node = node.setdefault(key, {})
node[keys[-1]] = json.loads(os.environ["VALUE"])
open(file, "w").write(json.dumps(doc))
PY
  exit 0
fi
cat @SECRETS_FILE@
"""
    return body.replace("${ARG1:-}", "${1:-}").replace("@SECRETS_FILE@", str(secrets_file))



def _harness(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    if not shutil_which("jq"):
        pytest.skip("jq is required")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(json.dumps(yaml.safe_load(FIXTURE.read_text())))
    payload_file = tmp_path / "payload.json"
    meta_file = tmp_path / "meta.json"
    ssh_marker = tmp_path / "ssh-called"
    _write_executable(bin_dir / "sops", _sops_stub(secrets_file))
    _write_executable(
        bin_dir / "wg",
        "#!/bin/sh\ncat >/dev/null\nprintf 'fixture-server-public-key'\n",
    )
    _write_executable(
        bin_dir / "ssh",
        f"""#!/bin/sh
touch {ssh_marker}
case "$*" in *.meta*) cat > {meta_file} ;; *) cat > {payload_file} ;; esac
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{STUBS_BIN}:{env['PATH']}",
            "HOME": str(tmp_path),
            "SOPS_FILE": str(secrets_file),
            "STUB_LOG": str(tmp_path / "stub.log"),
        }
    )
    return env, payload_file, ssh_marker, secrets_file


def shutil_which(name: str):
    from shutil import which

    return which(name)


def _run_issuer(env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(ISSUER), "phone", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )


def test_bare_refresh_reuses_registry_format_and_hosts(tmp_path: Path) -> None:
    env, payload_file, _, _ = _harness(tmp_path)
    result = _run_issuer(env, "--refresh-token", REGISTERED_TOKEN)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "reused: format,expires" in result.stdout
    # Registry records formats [singbox, ripdpi]; last issued wins.
    payload = json.loads(payload_file.read_text())
    assert "ripdpi" in payload


def test_refresh_unregistered_token_fails_closed(tmp_path: Path) -> None:
    env, payload_file, ssh_marker, _ = _harness(tmp_path)
    result = _run_issuer(env, "--refresh-token", "totally-unregistered-token")
    assert result.returncode != 0
    assert "client_registry entry" in result.stderr
    assert not payload_file.exists()
    assert not ssh_marker.exists()


def test_refresh_explicit_override_wins_and_is_logged(tmp_path: Path) -> None:
    env, payload_file, _, _ = _harness(tmp_path)
    result = _run_issuer(
        env,
        "--format",
        "singbox",
        "--refresh-token",
        REGISTERED_TOKEN,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "overridden: format" in result.stdout
    payload = json.loads(payload_file.read_text())
    assert "ripdpi" not in payload


def test_fresh_issuance_records_registry_entry(tmp_path: Path) -> None:
    env, _, _, secrets_file = _harness(tmp_path)
    result = _run_issuer(env, "--format", "singbox", "--print-token-only")
    assert result.returncode == 0, result.stderr + result.stdout
    token = result.stdout.strip().splitlines()[-1]
    prefix = hashlib.sha256(token.encode()).hexdigest()[:8]
    doc = json.loads(secrets_file.read_text())
    entry = doc["client_registry"]["phone"]
    assert entry["status"] == "delivered"
    assert entry["token_hash_prefix"] == prefix
    assert entry["hosts"] == ["upcloud:prod"]
    assert "singbox" in entry["formats"]


def test_fresh_issuance_records_multi_host_env(tmp_path: Path) -> None:
    """HOSTS from the emitter environment must land in the registry.

    Regression: first issuance recorded only PROVIDER:ENV while the emitter
    consumed HOSTS, so a bare refresh downgraded a multi-host subscription
    to a single-host payload.
    """
    env, payload_file, _, secrets_file = _harness(tmp_path)
    multi_hosts = "upcloud:p0-upcloud,scaleway:p1-scaleway,vultr:p2-vultr"
    env["HOSTS"] = multi_hosts
    result = _run_issuer(env, "--format", "singbox", "--print-token-only")
    assert result.returncode == 0, result.stderr + result.stdout
    doc = json.loads(secrets_file.read_text())
    assert doc["client_registry"]["phone"]["hosts"] == multi_hosts.split(",")


def test_refresh_reports_ignored_emitter_environment(tmp_path: Path) -> None:
    """A refresh must say that env HOSTS/COHORTS lost to the registry.

    The registry is authoritative on refresh by design, but silently
    discarding an operator-supplied HOSTS= produced a payload that did not
    match the invocation with nothing in the output to explain it.
    """
    env, _, _, _ = _harness(tmp_path)
    env["HOSTS"] = "vultr:some-other-host"
    result = _run_issuer(env, "--refresh-token", REGISTERED_TOKEN)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ignored: emitter HOSTS/COHORTS" in result.stdout


def test_refresh_without_emitter_environment_is_quiet(tmp_path: Path) -> None:
    env, _, _, _ = _harness(tmp_path)
    result = _run_issuer(env, "--refresh-token", REGISTERED_TOKEN)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ignored:" not in result.stdout


def test_issuer_revoke_hint_names_the_key_the_role_consumes() -> None:
    """The printed revoke instruction must name the consumed secrets key.

    The role renders the revocation file from `subscription.revoked_tokens`;
    the issuer used to tell operators to append the hash to
    `subscription.revoked_token_hashes`, which nothing reads — so a leaked
    token stayed valid after a by-the-book revocation.
    """
    role_tasks = (REPO_ROOT / "ansible/roles/subscription-host/tasks/main.yml").read_text()
    iterated = set(re.findall(r"for \w+ in subscription\.(\w+)", role_tasks))
    assert iterated == {"revoked_tokens"}
    assert set(re.findall(r"subscription\.(revoked_\w+)", ISSUER.read_text())) == iterated


@pytest.mark.parametrize('script_name,arguments,artifact', [
    ('issue-sub-token.sh', ['--qr'], 'phone.sub.qr.png'),
    ('issue-bootstrap.sh', ['--qr'], 'phone.bootstrap.qr.png'),
    ('emit-qr.sh', [], 'phone.qr.png'),
])
@pytest.mark.parametrize('legacy_output', [False, True])
def test_qr_output_is_private_at_creation(tmp_path, script_name, arguments, artifact, legacy_output):
    env, _, _, _ = _harness(tmp_path)
    env['QR_MODE_LOG'] = str(tmp_path / 'qr-mode')
    if legacy_output:
        (tmp_path / artifact).write_text('old credential')
        (tmp_path / artifact).chmod(0o644)
    _write_executable(tmp_path / 'bin/qrencode', '''#!/usr/bin/env python3
import os, pathlib, stat, sys
output = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
with output.open('wb') as stream:
    stream.write(sys.stdin.buffer.read())
    pathlib.Path(os.environ['QR_MODE_LOG']).write_text(str(stat.S_IMODE(os.fstat(stream.fileno()).st_mode)))
''')
    result = subprocess.run(
        ['bash', str(REPO_ROOT / 'scripts' / script_name), 'phone', *arguments],
        env=env, cwd=tmp_path, text=True, capture_output=True, timeout=20, umask=0o022,
    )
    assert result.returncode == 0, result.stderr
    assert int((tmp_path / 'qr-mode').read_text()) == 0o600
    assert (tmp_path / artifact).stat().st_mode & 0o777 == 0o600
