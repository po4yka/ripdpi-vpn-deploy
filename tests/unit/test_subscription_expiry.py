from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NORMALIZER = REPO_ROOT / "scripts" / "normalize-subscription-expiry.py"
ISSUER = REPO_ROOT / "scripts" / "issue-sub-token.sh"


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
    from test_client_registry import _harness
    env, payload, _marker, _source = _harness(tmp_path)
    return env, payload, tmp_path / 'meta.json'


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


def test_invalid_expiry_fails_before_remote_or_terraform(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "called"
    for command in ("terraform", "ssh"):
        _write_executable(bin_dir / command, f"#!/bin/sh\ntouch {marker}\nexit 99\n")
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(ISSUER), "phone", "--expires", "invalid"],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert not marker.exists()
