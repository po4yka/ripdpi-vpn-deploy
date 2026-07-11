from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
NORMALIZER = REPO_ROOT / "scripts" / "normalize-subscription-expiry.py"
ISSUER = REPO_ROOT / "scripts" / "issue-sub-token.sh"
BOOTSTRAP_ISSUER = REPO_ROOT / "scripts" / "issue-bootstrap.sh"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "secrets-sample.yml"
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("2027-01-01", "2027-01-01T00:00:00Z"),
        ("2027-01-01T00:00:00Z", "2027-01-01T00:00:00Z"),
        ("2027-01-01T03:59:59+04:00", "2026-12-31T23:59:59Z"),
        ("2026-12-31T18:59:59-05:00", "2026-12-31T23:59:59Z"),
    ],
)
def test_normalize_subscription_expiry(raw: str, canonical: str) -> None:
    result = subprocess.run(
        ["python3", str(NORMALIZER), raw],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == canonical


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-date",
        "2027-01-01T00:00:00",
        "2027-01-01 00:00:00Z",
        "2027-01-01T00:00:00+04",
        "1798761600",
    ],
)
def test_reject_invalid_subscription_expiry(raw: str) -> None:
    result = subprocess.run(
        ["python3", str(NORMALIZER), raw],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "expected YYYY-MM-DD or RFC 3339 timestamp with offset" in result.stderr


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def _issuer_env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    if not shutil.which("jq"):
        pytest.skip("jq is required")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(json.dumps(yaml.safe_load(FIXTURE.read_text())))
    payload_file = tmp_path / "payload.json"
    meta_file = tmp_path / "meta.json"
    _write_executable(
        bin_dir / "sops",
        f"#!/bin/sh\ncat {secrets_file}\n",
    )
    _write_executable(
        bin_dir / "wg",
        "#!/bin/sh\ncat >/dev/null\nprintf 'fixture-server-public-key'\n",
    )
    _write_executable(
        bin_dir / "ssh",
        f"#!/bin/sh\ncase \"$*\" in *.meta*) cat > {meta_file} ;; *) cat > {payload_file} ;; esac\n",
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
    return env, payload_file, meta_file


@pytest.mark.parametrize("format_name", ["singbox", "ripdpi"])
def test_issue_subscription_formats_share_canonical_expiry(tmp_path: Path, format_name: str) -> None:
    env, payload_file, meta_file = _issuer_env(tmp_path)
    result = subprocess.run(
        [
            "bash",
            str(ISSUER),
            "phone",
            "--format",
            format_name,
            "--expires",
            "2027-01-01T03:59:59+04:00",
            "--refresh-token",
            "fixture-token-for-contract-test",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(payload_file.read_text())
    meta = json.loads(meta_file.read_text())
    assert meta["expires"] == "2026-12-31T23:59:59Z"
    if format_name == "ripdpi":
        assert payload["ripdpi"]["expires"] == meta["expires"]
    else:
        assert "ripdpi" not in payload


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("2027-01-01T03:59:59+04:00", "2026-12-31T23:59:59Z"),
        ("2027-01-01", "2027-01-01T00:00:00Z"),
    ],
)
def test_issue_bootstrap_uses_canonical_expiry(tmp_path: Path, raw: str, canonical: str) -> None:
    env, payload_file, meta_file = _issuer_env(tmp_path)
    result = subprocess.run(
        ["bash", str(BOOTSTRAP_ISSUER), "phone", "--expires", raw],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    json.loads(payload_file.read_text())
    meta = json.loads(meta_file.read_text())
    assert meta == {"expires": canonical, "client": "phone"}
    assert canonical in result.stdout
    if "+04:00" in raw:
        assert raw not in result.stdout


@pytest.mark.parametrize("issuer", [ISSUER, BOOTSTRAP_ISSUER])
@pytest.mark.parametrize("raw", ["invalid", '2027-01-01\"}'])
def test_invalid_expiry_fails_before_remote_or_terraform(tmp_path: Path, issuer: Path, raw: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "called"
    for command in ("terraform", "ssh"):
        _write_executable(bin_dir / command, f"#!/bin/sh\ntouch {marker}\nexit 99\n")
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(issuer), "phone", "--expires", raw],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert not marker.exists()
