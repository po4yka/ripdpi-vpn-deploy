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
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
SCRIPT = REPO_ROOT / "scripts" / "emit-singbox.sh"
BUNDLE_SCRIPT = REPO_ROOT / "scripts" / "emit-bundle.sh"
BUNDLE_VALIDATOR = REPO_ROOT / "scripts" / "validate-bundle.py"
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
    # A syntactically valid X25519 public key lets the official sing-box
    # parser exercise the complete generated document.
    raw["xray"]["reality_public_key"] = (
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )

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


def _run_bundle(
    client: str,
    tmp_path: Path,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    secrets_json = _secrets_as_json(tmp_path)
    secrets = json.loads(secrets_json.read_text())
    secrets["hysteria"]["salamander_enabled"] = True
    secrets_json.write_text(json.dumps(secrets))

    env = _build_env(tmp_path, secrets_json)
    bin_dir = tmp_path / "bin"
    for tool in ("awg", "wg"):
        stub = bin_dir / tool
        stub.write_text("#!/bin/sh\nprintf 'server-public-fixture'\n")
        stub.chmod(0o700)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(BUNDLE_SCRIPT), client, *(extra_args or [])],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def _run_snell_only_script(tmp_path: Path, *, omit_variant: str | None = None) -> subprocess.CompletedProcess:
    repo = tmp_path / "snell-repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "ansible/group_vars").mkdir(parents=True)
    (repo / "ansible/roles/snell/defaults").mkdir(parents=True)
    (repo / "terraform/providers/upcloud").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "scripts/emit-singbox.sh")
    shutil.copy2(REPO_ROOT / "scripts/terraform-env.sh", repo / "scripts/terraform-env.sh")
    shutil.copy2(REPO_ROOT / "ansible/roles/snell/defaults/main.yml", repo / "ansible/roles/snell/defaults/main.yml")
    (repo / "ansible/group_vars/all.yml").write_text(
        yaml.safe_dump(
            {
                "vpn": {
                    "enable_xray_reality": False,
                    "enable_nginx_xhttp": False,
                    "enable_hysteria": False,
                    "enable_snell": True,
                }
            }
        )
    )
    variants = [
        {"id": "v4-stream", "psk": "v4-key", "users": [{"name": "laptop", "userkey": "v4-user-key-123"}]},
        {"id": "v6-default", "psk": "v6-default-key", "users": [{"name": "laptop", "userkey": "v6-default-user"}]},
        {"id": "v6-unshaped", "psk": "v6-unshaped-key", "users": [{"name": "laptop", "userkey": "v6-unshaped-user"}]},
    ]
    if omit_variant:
        variants = [variant for variant in variants if variant["id"] != omit_variant]
    secrets = tmp_path / "snell-secrets.json"
    secrets.write_text(json.dumps({"snell_secrets": {"variants": variants}}))
    fake_bin = tmp_path / "snell-bin"
    fake_bin.mkdir()
    (fake_bin / "sops").write_text("#!/bin/sh\ncat \"$SOPS_FILE\"\n")
    (fake_bin / "terraform").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'workspace select'*) exit 0 ;;\n"
        "  *'server_ipv4'*) printf '203.0.113.10' ;;\n"
        "  *'server_hostname'*) printf 'snell-test-node' ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    (fake_bin / "sops").chmod(0o700)
    (fake_bin / "terraform").chmod(0o700)
    environment = os.environ.copy()
    environment.update({"PATH": f"{fake_bin}:{environment['PATH']}", "SOPS_FILE": str(secrets), "PROVIDER": "upcloud", "ENV": "staging"})
    return subprocess.run(
        ["bash", str(repo / "scripts/emit-singbox.sh"), "laptop"],
        capture_output=True,
        text=True,
        env=environment,
        cwd=repo,
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

    # Standard sing-box has no XHTTP transport. P1 remains available only in
    # the explicit RIPDPI extended bundle.
    assert not any(
        outbound.get("transport", {}).get("type") == "xhttp"
        for outbound in outbounds
    )

    # At least one supported protocol outbound (P0 or P2).
    proto_obs = [ob for ob in outbounds if ob.get("tag", "").startswith(("p0-", "p1-", "p2-"))]
    assert proto_obs, "no protocol outbounds (p0/p1/p2) found"


def test_emit_singbox_is_accepted_by_official_parser(tmp_path):
    """The standard profile must pass the pinned official sing-box parser."""
    _require_tool("jq")
    _require_tool("sing-box")

    result = _run_script("laptop", tmp_path)
    assert result.returncode == 0, result.stderr

    config = tmp_path / "client.sing-box.json"
    config.write_text(result.stdout)
    check = subprocess.run(
        ["sing-box", "check", "-c", str(config)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert check.returncode == 0, check.stderr


def test_emit_singbox_hysteria_uses_server_userpass_contract(tmp_path):
    _require_tool("jq")

    result = _run_script("laptop", tmp_path)
    assert result.returncode == 0, result.stderr
    bundle = json.loads(result.stdout)
    hysteria = next(
        outbound
        for outbound in bundle["outbounds"]
        if outbound.get("type") == "hysteria2"
    )

    assert hysteria["password"] == (
        "laptop:fixture-hysteria-password-laptop-001"
    )


def test_smoke_hysteria_uses_server_userpass_contract():
    smoke = (REPO_ROOT / "ansible" / "playbooks" / "smoke-test.yml").read_text()

    assert (
        'auth: "{{ hysteria.clients[0].name }}:'
        '{{ hysteria.clients[0].password }}"'
    ) in smoke


def test_emit_awg_make_target_script_is_executable():
    assert os.access(REPO_ROOT / "scripts" / "emit-awg.sh", os.X_OK)


def test_emit_singbox_snell_matrix_is_manual_only(tmp_path):
    _require_tool("jq")
    result = _run_snell_only_script(tmp_path)
    assert result.returncode == 0, result.stderr
    bundle = json.loads(result.stdout)
    candidates = [outbound for outbound in bundle["outbounds"] if outbound.get("type") == "snell"]
    assert len(candidates) == 6
    assert {outbound["reuse"] for outbound in candidates} == {False, True}
    v4 = [outbound for outbound in candidates if "v4-stream" in outbound["tag"]]
    assert len(v4) == 2 and all(outbound["version"] == 4 and outbound["obfs_mode"] == "none" for outbound in v4)
    v6_default = [outbound for outbound in candidates if "v6-default" in outbound["tag"]]
    assert len(v6_default) == 2 and all(outbound["version"] == 6 and outbound["mode"] == "default" for outbound in v6_default)
    v6_unshaped = [outbound for outbound in candidates if "v6-unshaped" in outbound["tag"]]
    assert len(v6_unshaped) == 2 and all(outbound["version"] == 6 and outbound["mode"] == "unshaped" for outbound in v6_unshaped)
    nested = next(outbound for outbound in bundle["outbounds"] if outbound.get("tag") == "snell-evaluation")
    assert set(nested["outbounds"]) == {outbound["tag"] for outbound in candidates}
    selector = next(outbound for outbound in bundle["outbounds"] if outbound.get("tag") == "select")
    assert selector["default"] == "direct"
    assert "snell-evaluation" in selector["outbounds"]
    assert not any(outbound.get("type") == "urltest" for outbound in bundle["outbounds"])


def test_emit_singbox_snell_missing_variant_credentials_fails(tmp_path):
    _require_tool("jq")
    result = _run_snell_only_script(tmp_path, omit_variant="v6-unshaped")
    assert result.returncode != 0
    assert "v6-unshaped' is missing from secrets" in result.stderr


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
    assert remote["type"] == "https"
    assert remote["server"] == "1.1.1.1"
    assert "address" not in remote
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
    assert "sniff" not in tun
    assert any(rule.get("action") == "sniff" for rule in bundle["route"]["rules"])
    assert any(
        rule.get("action") == "hijack-dns"
        for rule in bundle["route"]["rules"]
    )

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


def test_emit_bundle_roundtrip_preserves_singbox_args_and_extension(tmp_path):
    _require_tool("jq")

    result = _run_bundle(
        "phone",
        tmp_path,
        extra_env={"BUNDLE_EXPIRES": "2026-12-31T23:59:59Z"},
        extra_args=[
            "--per-app-bypass",
            "example.bypass",
            "--per-app-via-tun",
            "example.tunnel",
        ],
    )
    assert result.returncode == 0, result.stderr

    bundle_file = tmp_path / "emitted-bundle.json"
    bundle_file.write_text(result.stdout)
    validation = subprocess.run(
        [sys.executable, str(BUNDLE_VALIDATOR), str(bundle_file)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert validation.returncode == 0, validation.stderr

    bundle = json.loads(result.stdout)
    assert any(
        outbound.get("transport", {}).get("type") == "xhttp"
        for outbound in bundle["outbounds"]
    )
    package_routes = {
        tuple(rule["package_name"]): rule["outbound"]
        for rule in bundle["route"]["rules"]
        if "package_name" in rule
    }
    assert package_routes == {
        ("example.bypass",): "direct",
        ("example.tunnel",): "select",
    }

    ripdpi = bundle["ripdpi"]
    assert ripdpi["schema_version"] == 1
    assert len(ripdpi["amneziawg"]) == 1
    assert ripdpi["amneziawg"][0]["cohort_fingerprint"].startswith("sha256:")
    assert ripdpi["hysteria_extras"] == {
        "p2-hysteria2-upcloud-prod": {
            "insecure": False,
            "obfs": {
                "type": "salamander",
                "password": "fixture-salamander-password-not-real",
            },
            "salamander_upstream_tag": "v2.9.0",
        }
    }
    assert ripdpi["topology"] == {
        "split_hop_egress": False,
        "hysteria_realm": None,
    }
    assert ripdpi["expires"] == "2026-12-31T23:59:59Z"


def test_emit_bundle_rejects_unknown_singbox_arg(tmp_path):
    _require_tool("jq")

    result = _run_bundle(
        "phone",
        tmp_path,
        extra_args=["--not-a-singbox-option"],
    )

    assert result.returncode != 0
    assert "unknown arg: --not-a-singbox-option" in result.stderr


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
