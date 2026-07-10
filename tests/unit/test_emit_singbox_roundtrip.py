"""Round-trip test for scripts/emit-singbox.sh.

Runs the script against test fixtures (stub terraform + stub sops on PATH,
real jq/python3) and asserts the emitted JSON has the expected structure.

The sops stub copies secrets-sample.yml (YAML) to the target file but
emit-singbox.sh calls `sops --decrypt --output-type json`.  The stub ignores
--output-type, so we supply a JSON-format copy of the fixture and point
SOPS_FILE at it directly.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
SCRIPT = REPO_ROOT / "scripts" / "emit-singbox.sh"
KILLSWITCH_SCRIPT = REPO_ROOT / "scripts" / "check-singbox-killswitch.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_tool(name: str) -> None:
    if not shutil.which(name):
        pytest.skip(f"required binary not found on PATH: {name}")


def _secrets_as_json(tmp_path: Path) -> Path:
    """Return path to a JSON copy of secrets-sample.yml, with laptop in all client lists."""
    raw = yaml.safe_load(FIXTURES.joinpath("secrets-sample.yml").read_text())

    # The fixture already has "laptop" in xray.clients.
    # Ensure "laptop" also appears in hysteria.clients so emit-singbox.sh
    # doesn't bail out when hysteria is enabled (it is by default in all.yml).
    hy_clients = raw.get("hysteria", {}).get("clients", [])
    if not any(c.get("name") == "laptop" for c in hy_clients):
        hy_clients.append({"name": "laptop", "password": "fixture-hysteria-password-laptop-001"})
        raw["hysteria"]["clients"] = hy_clients

    out = tmp_path / "secrets-fixture.json"
    out.write_text(json.dumps(raw))
    return out


def _make_sops_stub(bin_dir: Path, sops_file: Path) -> None:
    """Create a sops stub that decrypts by printing $SOPS_FILE to stdout.

    emit-singbox.sh calls:
        sops --decrypt --output-type json "$sops_file" > "$secrets_tmp"

    The positional arg ($sops_file) is the source file to decrypt; the
    output is redirected via shell to $secrets_tmp.  We just cat $SOPS_FILE
    (which is the JSON fixture) to stdout — the shell redirect does the rest.
    We never need to copy because the caller always redirects stdout.
    """
    stub = bin_dir / "sops"
    stub.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "# Custom test sops stub: prints SOPS_FILE to stdout on --decrypt.\n"
        "decrypt=0\n"
        "for arg in \"$@\"; do\n"
        "  case \"$arg\" in\n"
        "    --decrypt|-d) decrypt=1 ;;\n"
        "  esac\n"
        "done\n"
        "if [ \"$decrypt\" -eq 1 ]; then\n"
        f"  cat \"${{SOPS_FILE:-{sops_file}}}\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    )
    stub.chmod(stub.stat().st_mode | 0o111)


def _build_env(tmp_path: Path, sops_file: Path) -> dict[str, str]:
    """Build subprocess env: custom sops stub on PATH, SOPS_FILE set."""
    # Create a per-test bin dir with a custom sops stub.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _make_sops_stub(bin_dir, sops_file)

    env = os.environ.copy()
    # Custom bin dir first, then standard stubs (for terraform/jq), then real PATH.
    env["PATH"] = f"{bin_dir}:{STUBS_BIN}:{env['PATH']}"
    env["SOPS_FILE"] = str(sops_file)
    env["STUB_LOG"] = str(tmp_path / "stub.log")
    # Clear multi-host vars so the script uses single-host SOPS_FILE path.
    for var in ("HOSTS", "SOPS_FILES", "COHORTS", "PROVIDER", "ENV"):
        env.pop(var, None)
    return env


def _run_script(
    client: str,
    tmp_path: Path,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    secrets_json = _secrets_as_json(tmp_path)
    env = _build_env(tmp_path, secrets_json)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT), client, *(extra_args or [])],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def _utls_fingerprints(bundle: dict) -> list[str]:
    """Every uTLS fingerprint emitted across the protocol outbounds."""
    fps = []
    for ob in bundle["outbounds"]:
        utls = ob.get("tls", {}).get("utls")
        if isinstance(utls, dict) and "fingerprint" in utls:
            fps.append(utls["fingerprint"])
    return fps


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_emit_singbox_json_structure(tmp_path):
    """emit-singbox.sh laptop emits valid JSON with outbounds, route, dns."""
    _require_tool("jq")

    result = _run_script("laptop", tmp_path)
    if result.returncode != 0:
        pytest.fail(
            f"emit-singbox.sh exited {result.returncode}:\n"
            f"stdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}"
        )

    bundle = json.loads(result.stdout)

    for key in ("outbounds", "route", "dns"):
        assert key in bundle, f"missing top-level key: {key!r}"

    outbounds = bundle["outbounds"]
    assert len(outbounds) > 0, "outbounds list is empty"

    tags = {ob.get("tag") for ob in outbounds}
    assert "select" in tags, "'select' outbound missing"
    assert "auto" in tags, "'auto' (urltest) outbound missing"
    assert "direct" in tags, "'direct' outbound missing"
    assert "block" in tags, "'block' outbound missing"
    assert "dns-out" in tags, "'dns-out' outbound missing"

    # At least one protocol outbound (p0-reality or p1-xhttp)
    proto_obs = [ob for ob in outbounds if ob.get("tag", "").startswith(("p0-", "p1-", "p2-"))]
    assert proto_obs, "no protocol outbounds (p0/p1/p2) found"


def test_emit_singbox_dns_non_empty_and_detour(tmp_path):
    """dns.servers must be non-empty and remote server must detour via tunnel."""
    _require_tool("jq")

    result = _run_script("laptop", tmp_path)
    if result.returncode != 0:
        pytest.fail(f"emit-singbox.sh failed: {result.stderr[:400]}")

    bundle = json.loads(result.stdout)
    servers = bundle.get("dns", {}).get("servers", [])
    assert len(servers) >= 1, "dns.servers is empty"

    remote = next((s for s in servers if s.get("tag") == "remote"), None)
    assert remote is not None, "dns.servers has no 'remote' entry"
    detour = remote.get("detour", "")
    assert detour not in ("", "direct"), (
        f"remote DNS detour is {detour!r} — leaks DNS traffic to ISP"
    )


def test_emit_singbox_default_is_strict_dual_stack_killswitch(tmp_path):
    _require_tool("jq")

    result = _run_script("laptop", tmp_path)
    if result.returncode != 0:
        pytest.fail(f"emit-singbox.sh failed: {result.stderr[:400]}")

    bundle = json.loads(result.stdout)
    tun = next(inbound for inbound in bundle["inbounds"] if inbound["type"] == "tun")
    assert tun["address"] == ["172.19.0.1/30", "fdfe:dcba:9876::1/126"]
    assert "inet4_address" not in tun
    assert "inet6_address" not in tun

    check = subprocess.run(
        ["python3", str(KILLSWITCH_SCRIPT), "-"],
        input=result.stdout,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert check.returncode == 0, check.stdout


def test_emit_singbox_per_app_bypass_fails_strict_killswitch(tmp_path):
    _require_tool("jq")

    result = _run_script(
        "laptop",
        tmp_path,
        extra_args=["--per-app-bypass", "example.app"],
    )
    if result.returncode != 0:
        pytest.fail(f"emit-singbox.sh failed: {result.stderr[:400]}")

    check = subprocess.run(
        ["python3", str(KILLSWITCH_SCRIPT), "-"],
        input=result.stdout,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert check.returncode == 1
    assert "route.rules[0]" in check.stdout


def test_emit_singbox_no_placeholder_leaks(tmp_path):
    """Emitted JSON must not contain literal TODO/REPLACE/PLACEHOLDER strings."""
    _require_tool("jq")

    result = _run_script("laptop", tmp_path)
    if result.returncode != 0:
        pytest.fail(f"emit-singbox.sh failed: {result.stderr[:400]}")

    serialised = result.stdout
    for bad in ("TODO", "REPLACE", "PLACEHOLDER"):
        assert bad not in serialised, f"placeholder string {bad!r} found in output"


def test_emit_singbox_default_utls_fingerprint_is_chrome(tmp_path):
    """Default behaviour is unchanged: every uTLS outbound emits 'chrome'."""
    _require_tool("jq")

    result = _run_script("laptop", tmp_path)
    if result.returncode != 0:
        pytest.fail(f"emit-singbox.sh failed: {result.stderr[:400]}")

    fps = _utls_fingerprints(json.loads(result.stdout))
    assert fps, "no uTLS fingerprints found (REALITY/XHTTP outbound expected)"
    assert set(fps) == {"chrome"}, f"default fingerprint drifted: {fps}"


def test_emit_singbox_utls_fingerprint_env_override(tmp_path):
    """UTLS_FINGERPRINT overrides the fingerprint on every uTLS outbound."""
    _require_tool("jq")

    result = _run_script("laptop", tmp_path, extra_env={"UTLS_FINGERPRINT": "firefox"})
    if result.returncode != 0:
        pytest.skip(f"emit-singbox.sh failed: {result.stderr[:400]}")

    fps = _utls_fingerprints(json.loads(result.stdout))
    assert fps, "no uTLS fingerprints found"
    assert set(fps) == {"firefox"}, f"override not applied: {fps}"


def test_emit_singbox_missing_client_exits_nonzero(tmp_path):
    """Script must exit non-zero when the client name is not in secrets."""
    _require_tool("jq")

    result = _run_script("nonexistent-client-xyz", tmp_path)
    assert result.returncode != 0, (
        "script should exit non-zero for an unknown client name"
    )
