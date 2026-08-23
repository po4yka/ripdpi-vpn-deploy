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
