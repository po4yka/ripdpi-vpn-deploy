"""The state lock probe passes only when the backend lock refuses a second writer and the reader."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/state-lock-probe.sh"

# `sops exec-env DOC CMD`: export the plain fixture document, then run CMD in a shell.
SOPS = """#!/usr/bin/env python3
import json, os, subprocess, sys
assert sys.argv[1] == "exec-env"
env = dict(os.environ, **json.load(open(sys.argv[2])))
sys.exit(subprocess.call(["sh", "-c", sys.argv[3]], env=env))
"""

# A backend with one lock file in STUB_BACKEND. STUB_MODE=nolock never refuses;
# STUB_MODE=reader-can-lock lets the reader identity lock.
TOFU = """#!/usr/bin/env python3
import json, os, sys, time
args = [a for a in sys.argv[1:] if not a.startswith("-chdir=")]
backend = os.environ["STUB_BACKEND"]
lock = os.path.join(backend, "lock")
mode = os.environ.get("STUB_MODE", "locking")
if os.environ.get("PROBE_HOLDER_READY") is None:
    if args == ["state", "pull"]:
        if mode == "unreadable":
            sys.exit(1)
        print(json.dumps({"version":4,"serial":1,"lineage":"synthetic","resources":[]}))
    sys.exit(0)
role = os.environ.get("PROBE_ROLE", "")
if args[0] == "init":
    assert "-backend-config=skip_s3_checksum=false" in args
    sys.exit(0)
if args[0] == "workspace":
    assert args[1] == ("new" if role == "writer" else "select")
    assert args[2].startswith("probe-")
    sys.exit(0)
if "-lock=false" in args:
    print("No changes.")
    sys.exit(0)
refused = (role == "reader" and mode != "reader-can-lock") or (os.path.exists(lock) and mode != "nolock")
if refused:
    print("Error: Error acquiring the state lock")
    sys.exit(1)
open(lock, "w").close()
hold = next((int(a.split("=")[1]) for a in args if a.startswith("hold=")), 0)
if args[0] == "apply":
    open(os.environ["PROBE_HOLDER_READY"], "w").close()
    time.sleep(hold)
os.remove(lock)
sys.exit(0)
"""


def executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def probe(tmp_path: Path, mode: str = "locking", *, omit: str | None = None) -> subprocess.CompletedProcess[str]:
    binary = tmp_path / "bin"
    binary.mkdir()
    executable(binary / "sops", SOPS)
    executable(binary / "tofu", TOFU)
    executable(binary / "curl", """#!/usr/bin/env python3
import json, os, sys, urllib.parse
query = urllib.parse.parse_qs(urllib.parse.urlsplit(sys.argv[-1]).query, keep_blank_values=True)
if "versions" in query:
    key = query["prefix"][0]
    with open(os.path.join(os.environ["STUB_BACKEND"], "objects.log"), "a") as log:
        print(key, file=log)
    ids = ["v1"] if os.environ["STUB_MODE"] == "no-history" else ["v1", "v2"]
    versions = "".join(f"<Version><Key>{key}</Key><VersionId>{i}</VersionId><LastModified>now</LastModified><IsLatest>false</IsLatest></Version>" for i in ids)
    print("<ListVersionsResult>" + versions + "</ListVersionsResult>")
else:
    result = {"encrypted_data": "synthetic"}
    if os.environ["STUB_MODE"] == "plaintext":
        result["resources"] = []
    print(json.dumps(result))
""")
    (tmp_path / "backend").mkdir()
    docs = {}
    for role in ("writer", "other", "reader", "passphrase"):
        docs[role] = tmp_path / f"{role}.json"
        docs[role].write_text(json.dumps({"PROBE_ROLE": role, "AWS_ACCESS_KEY_ID": "fixture", "AWS_SECRET_ACCESS_KEY": "fixture"} if role != "passphrase" else {"TF_VAR_state_passphrase": "x" * 16}))
    backend = tmp_path / "probe.s3.tfbackend"
    backend.write_text('bucket = "fixture"\nuse_lockfile = true\nkey = "fixture"\nworkspace_key_prefix = "state/workspaces"\nregion = "test"\nendpoints = { s3 = "https://test.invalid" }\n')
    arguments = {"--backend-config": backend, "--writer": docs["writer"], "--other-writer": docs["other"],
                 "--reader": docs["reader"], "--passphrase": docs["passphrase"], "--hold": "3"}
    if omit:
        del arguments[omit]
    command = ["bash", str(SCRIPT)] + [str(item) for pair in arguments.items() for item in pair]
    env = {**os.environ, "PATH": f"{binary}:{os.environ['PATH']}", "STUB_BACKEND": str(tmp_path / "backend"),
           "STUB_MODE": mode, "TMPDIR": str(tmp_path)}
    return subprocess.run(command, env=env, text=True, capture_output=True, timeout=60, check=False)


def test_locking_backend_passes_every_check(tmp_path: Path) -> None:
    result = probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "other writer refused while the lock is held: pass" in result.stdout
    assert "reader cannot take the lock: pass" in result.stdout
    assert "lock probe passed" in result.stdout
    assert result.stdout.count("verified 2 encrypted probe versions") == 2
    default, named = (tmp_path / "backend/objects.log").read_text().splitlines()
    run_id = default.split("/")[2]
    assert default == f"state/_probe/{run_id}/terraform.tfstate"
    assert named == f"state/workspaces/probe-{run_id}/{default}"


@pytest.mark.parametrize("mode", ["plaintext", "no-history", "unreadable"])
def test_plaintext_or_missing_version_history_fails_the_probe(tmp_path: Path, mode: str):
    result = probe(tmp_path, mode)
    assert result.returncode == 1
    assert "bucket retains encrypted state versions: fail" in result.stdout


def test_backend_without_contention_fails(tmp_path: Path) -> None:
    result = probe(tmp_path, "nolock")
    assert result.returncode == 1
    assert "other writer refused while the lock is held: fail" in result.stdout


def test_reader_that_can_lock_fails(tmp_path: Path) -> None:
    result = probe(tmp_path, "reader-can-lock")
    assert result.returncode == 1
    assert "reader cannot take the lock: fail" in result.stdout


@pytest.mark.parametrize("omit", ["--reader", "--passphrase", "--backend-config"])
def test_missing_inputs_refuse_before_tofu(tmp_path: Path, omit: str) -> None:
    result = probe(tmp_path, omit=omit)
    assert result.returncode == 2
    assert "missing or unreadable" in result.stderr
