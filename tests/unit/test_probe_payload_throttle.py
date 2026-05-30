"""Unit tests for scripts/probe-payload-throttle.sh.

The script drives an escalating ladder of payload sizes against an
operator endpoint, resolves the target ASN via scripts/probe-asn.sh
(whois → Team Cymru), and classifies the path's behaviour into the
project probe verdict enum.

Tests create per-test stub scripts on PATH (curl, whois, getent) to
control completion / RTT / ASN-lookup behaviour and assert the verdict
JSON shape and classification. Stdlib only — no network, no ~/ writes.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "probe-payload-throttle.sh"

# A literal-IP host avoids getent name resolution inside probe-asn.sh.
PROBE_HOST = "203.0.113.7"
# A small ladder straddling the ~16 KiB throttle window.
SIZES = "1024,4096,16384,32768"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stub(bin_dir: Path, name: str, body: str) -> None:
    """Write an executable /bin/sh stub into *bin_dir*."""
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _whois_stub_body() -> str:
    """Emit a Team-Cymru `-v` style pipe-delimited line on the last row.

    probe-asn.sh reads `whois -h whois.cymru.com " -v <ip>" | tail -1`
    and parses fields by '|': AS | IP | PREFIX | CC | Registry | Alloc | Org
    """
    line = "64500   | 203.0.113.7    | 203.0.113.0/24    | XX | testreg | 2020-01-01 | EXAMPLE-ASN"
    return f'printf "%s\\n" "{line}"'


def _run(
    tmp_path: Path,
    curl_body: str,
    *,
    sizes: str = SIZES,
    whois_body: str | None = None,
    extra_args: list[str] | None = None,
    drop_whois: bool = False,
) -> subprocess.CompletedProcess:
    """Run the probe with a hermetic stub environment."""
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()

    _make_stub(stub_bin, "curl", curl_body)
    if not drop_whois:
        _make_stub(stub_bin, "whois", whois_body or _whois_stub_body())
    # getent is only hit for non-IP hosts; provide a no-op for safety.
    _make_stub(stub_bin, "getent", "exit 0")

    env = os.environ.copy()
    # Hermetic PATH but keep python3 reachable via the inherited tail.
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")

    args = ["bash", str(SCRIPT), "--host", PROBE_HOST, "--sizes", sizes]
    if extra_args:
        args.extend(extra_args)

    return subprocess.run(
        args, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT)
    )


def _verdict(result: subprocess.CompletedProcess) -> dict:
    """Parse the single JSON object the probe writes to stdout."""
    out = result.stdout.strip()
    assert out, f"empty stdout; stderr={result.stderr[:500]}"
    # The probe emits exactly one JSON object on stdout.
    last = out.splitlines()[-1]
    return json.loads(last)


# ---------------------------------------------------------------------------
# Schema-shape tests
# ---------------------------------------------------------------------------

VERDICT_ENUM = {"ok", "throttled", "blocked", "unknown", "error"}


def test_verdict_shape_is_valid(tmp_path):
    """Verdict must be in the 5-value enum and rtt_ms int|null."""
    result = _run(tmp_path, "exit 0")
    assert result.returncode == 0, result.stderr[:500]
    v = _verdict(result)
    assert v["verdict"] in VERDICT_ENUM
    assert v["rtt_ms"] is None or isinstance(v["rtt_ms"], int)


def test_asn_keyed_not_brand(tmp_path):
    """The verdict is keyed by AS<num>; no ORG/COUNTRY brand leaks."""
    result = _run(tmp_path, "exit 0")
    v = _verdict(result)
    assert v.get("asn") == "AS64500"
    blob = json.dumps(v)
    # The whois ORG/COUNTRY columns must never propagate into output.
    assert "EXAMPLE-ASN" not in blob
    assert "testreg" not in blob


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

def test_all_sizes_complete_is_ok(tmp_path):
    """Every payload size completes cleanly → verdict 'ok'."""
    result = _run(tmp_path, "exit 0")
    v = _verdict(result)
    assert v["verdict"] == "ok", v
    assert all(s["completed"] for s in v["sizes"])


def test_cliff_at_16k_is_throttled(tmp_path):
    """Small payloads succeed, the 16384+ steps fail → 'throttled'.

    The curl stub fails (exit 22, like an HTTP error / reset) when the
    requested ?bytes= value is >= 16384, mirroring a size-threshold
    throttle. Small requests succeed.
    """
    body = (
        'case "$*" in\n'
        '  *bytes=16384*|*bytes=24576*|*bytes=32768*) exit 22 ;;\n'
        '  *) exit 0 ;;\n'
        'esac'
    )
    result = _run(tmp_path, body)
    v = _verdict(result)
    assert v["verdict"] == "throttled", v
    assert v["threshold_bytes"] == 16384, v


def test_all_drop_is_blocked(tmp_path):
    """No size completes at all → verdict 'blocked'."""
    result = _run(tmp_path, "exit 7")  # curl: failed to connect
    v = _verdict(result)
    assert v["verdict"] == "blocked", v


def test_whois_failure_is_error(tmp_path):
    """probe-asn.sh failing (Cymru unreachable) → verdict 'error'."""
    # whois stub returns an error envelope probe-asn.sh treats as failure.
    result = _run(tmp_path, "exit 0", whois_body='echo "error: unreachable"; exit 0')
    v = _verdict(result)
    assert v["verdict"] == "error", v
    assert "error_kind" in v


def test_missing_curl_is_error(tmp_path):
    """Missing curl tool → verdict 'error' with error_kind.

    Uses a constrained PATH containing only the stub dir plus the
    directories needed for bash/python3, so the inherited system curl
    is not visible to the script's tool-presence check.
    """
    import shutil

    bash_abs = shutil.which("bash") or "/bin/bash"

    # Build a hermetic bin dir holding ONLY the binaries the script
    # legitimately needs PLUS our stubs — deliberately NOT curl. Each
    # tool is symlinked individually so a coreutils dir cannot smuggle
    # the system curl onto PATH (which broke a whole-dir approach on
    # macOS). bash is invoked by absolute path so it need not be linked.
    hermetic = tmp_path / "hermetic-bin"
    hermetic.mkdir()
    for tool in ("python3", "sh", "env", "mktemp", "awk", "mkdir", "mv",
                 "chmod", "cat", "sed", "rm", "dirname", "tail", "head",
                 "grep", "getent"):
        src = shutil.which(tool)
        if src:
            (hermetic / tool).symlink_to(src)
    # whois stub (so probe-asn.sh succeeds and we exercise the curl check).
    _make_stub(hermetic, "whois", _whois_stub_body())

    env = os.environ.copy()
    env["PATH"] = str(hermetic)
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")

    result = subprocess.run(
        [bash_abs, str(SCRIPT), "--host", PROBE_HOST, "--sizes", SIZES],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )
    v = _verdict(result)
    assert v["verdict"] == "error", v
    assert "curl" in v.get("error_kind", "")


def test_asn_override_skips_lookup(tmp_path):
    """--asn override bypasses whois entirely (no whois stub needed)."""
    result = _run(
        tmp_path, "exit 0", drop_whois=True, extra_args=["--asn", "AS64500"]
    )
    v = _verdict(result)
    assert v["verdict"] == "ok", v
    assert v["asn"] == "AS64500"


def test_state_written_keyed_by_asn(tmp_path):
    """A state file keyed by AS<num> is persisted under XDG_STATE_HOME."""
    _run(tmp_path, "exit 0")
    state_dir = tmp_path / "state" / "vpn-deploy" / "payload-throttle"
    files = list(state_dir.glob("*.json"))
    assert files, "no state file written"
    assert files[0].name == "AS64500.json"
    # Persisted content is the same verdict JSON shape.
    persisted = json.loads(files[0].read_text())
    assert persisted["verdict"] in VERDICT_ENUM
    assert persisted["asn"] == "AS64500"
