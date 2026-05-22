"""Unit tests for scripts/tspu-canary.sh.

The script probes network endpoints using openssl, curl, and python3.
Tests here create per-test stub scripts on PATH to control probe responses
and assert the correct pass/fail/skip classification is written to the TSV.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
SCRIPT = REPO_ROOT / "scripts" / "tspu-canary.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stub(bin_dir: Path, name: str, body: str) -> None:
    """Write an executable stub script into *bin_dir*."""
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_canary(tmp_path: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Run tspu-canary.sh with a hermetic stub environment."""
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()

    # openssl stub — default: returns "BEGIN CERTIFICATE" (pass for TLS probes).
    _make_stub(stub_bin, "openssl", 'printf "BEGIN CERTIFICATE\\n"')
    # curl stub — default: exits 0 (pass for baseline).
    _make_stub(stub_bin, "curl", "exit 0")
    # whois is not used by tspu-canary; include a no-op anyway.
    _make_stub(stub_bin, "whois", "exit 0")

    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{STUBS_BIN}:{env['PATH']}"
    # Redirect state dir to tmp so we never touch ~/.cache.
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)
    # Set canary endpoints to something harmless (skipped when empty).
    env.setdefault("CANARY_TLS_HOST", "www.example.com")
    env.setdefault("CANARY_TLS_PORT", "443")
    env.setdefault("CANARY_BASELINE_HOST", "www.cloudflare.com")
    # Leave CANARY_WG_HOST, CANARY_DTLS_HOST, CANARY_VLESS_HOST unset → skip.
    env.pop("CANARY_WG_HOST", None)
    env.pop("CANARY_DTLS_HOST", None)
    env.pop("CANARY_VLESS_HOST", None)

    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def _parse_tsv(tmp_path: Path) -> dict[str, str]:
    """Parse the TSV verdict file written by the canary script."""
    state_dir = tmp_path / "home" / ".cache" / "vpn-deploy" / "tspu-canary"
    tsv_files = list(state_dir.glob("*.tsv"))
    if not tsv_files:
        return {}
    # Take the most recent (there should only be one per run).
    tsv = sorted(tsv_files)[-1]
    verdicts: dict[str, str] = {}
    for line in tsv.read_text().splitlines():
        if "\t" in line:
            name, _, verdict = line.partition("\t")
            verdicts[name.strip()] = verdict.strip()
    return verdicts


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_canary_exits_zero_with_passing_stubs(tmp_path):
    """With stubs returning success, the canary script exits 0."""
    result = _run_canary(tmp_path)
    assert result.returncode == 0, (
        f"canary exited {result.returncode}:\n"
        f"stdout: {result.stdout[:1000]}\nstderr: {result.stderr[:500]}"
    )


def test_canary_writes_tsv_file(tmp_path):
    """Canary must persist a TSV verdict file to the state dir."""
    _run_canary(tmp_path)
    state_dir = tmp_path / "home" / ".cache" / "vpn-deploy" / "tspu-canary"
    tsv_files = list(state_dir.glob("*.tsv"))
    assert tsv_files, "no TSV verdict file written to state dir"


def test_canary_plain_https_pass(tmp_path):
    """plain-https probe: curl exits 0 → verdict 'pass'."""
    result = _run_canary(tmp_path)
    assert result.returncode == 0
    verdicts = _parse_tsv(tmp_path)
    assert verdicts.get("plain-https") == "pass", (
        f"expected plain-https=pass, got {verdicts}"
    )


def test_canary_tls_pass_when_openssl_emits_cert(tmp_path):
    """tls-no-utls probe: openssl outputs BEGIN CERTIFICATE → verdict 'pass'."""
    _run_canary(tmp_path)
    verdicts = _parse_tsv(tmp_path)
    assert verdicts.get("tls-no-utls") == "pass", (
        f"expected tls-no-utls=pass, got {verdicts}"
    )


def test_canary_tls_fail_when_openssl_returns_no_cert(tmp_path):
    """tls-no-utls probe: openssl outputs nothing → verdict 'fail'."""
    stub_bin = tmp_path / "bin2"
    stub_bin.mkdir()
    # openssl stub that does NOT print a certificate.
    _make_stub(stub_bin, "openssl", 'printf "no-cert-here"')
    _make_stub(stub_bin, "curl", "exit 0")

    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{STUBS_BIN}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home2")
    (tmp_path / "home2").mkdir(exist_ok=True)
    env["CANARY_TLS_HOST"] = "www.example.com"
    env["CANARY_TLS_PORT"] = "443"
    env["CANARY_BASELINE_HOST"] = "www.cloudflare.com"
    env.pop("CANARY_WG_HOST", None)
    env.pop("CANARY_DTLS_HOST", None)
    env.pop("CANARY_VLESS_HOST", None)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0

    state_dir = tmp_path / "home2" / ".cache" / "vpn-deploy" / "tspu-canary"
    tsv_files = list(state_dir.glob("*.tsv"))
    assert tsv_files
    verdicts: dict[str, str] = {}
    for line in sorted(tsv_files)[-1].read_text().splitlines():
        if "\t" in line:
            n, _, v = line.partition("\t")
            verdicts[n.strip()] = v.strip()

    assert verdicts.get("tls-no-utls") == "fail", (
        f"expected tls-no-utls=fail when openssl returns no cert, got {verdicts}"
    )


def test_canary_plain_https_fail_when_curl_fails(tmp_path):
    """plain-https probe: curl exits non-zero → verdict 'fail'."""
    stub_bin = tmp_path / "bin3"
    stub_bin.mkdir()
    _make_stub(stub_bin, "openssl", 'printf "BEGIN CERTIFICATE\\n"')
    _make_stub(stub_bin, "curl", "exit 1")

    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{STUBS_BIN}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home3")
    (tmp_path / "home3").mkdir(exist_ok=True)
    env["CANARY_TLS_HOST"] = "www.example.com"
    env["CANARY_TLS_PORT"] = "443"
    env["CANARY_BASELINE_HOST"] = "www.cloudflare.com"
    env.pop("CANARY_WG_HOST", None)
    env.pop("CANARY_DTLS_HOST", None)
    env.pop("CANARY_VLESS_HOST", None)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0

    state_dir = tmp_path / "home3" / ".cache" / "vpn-deploy" / "tspu-canary"
    tsv_files = list(state_dir.glob("*.tsv"))
    assert tsv_files
    verdicts: dict[str, str] = {}
    for line in sorted(tsv_files)[-1].read_text().splitlines():
        if "\t" in line:
            n, _, v = line.partition("\t")
            verdicts[n.strip()] = v.strip()

    assert verdicts.get("plain-https") == "fail", (
        f"expected plain-https=fail when curl exits 1, got {verdicts}"
    )


def test_canary_optional_probes_skipped_when_hosts_unset(tmp_path):
    """wg-handshake, dtls12, classic-vless are 'skip' when endpoints unset."""
    _run_canary(tmp_path)
    verdicts = _parse_tsv(tmp_path)
    assert verdicts.get("wg-handshake") == "skip"
    assert verdicts.get("dtls12") == "skip"
    assert verdicts.get("classic-vless") == "skip"
