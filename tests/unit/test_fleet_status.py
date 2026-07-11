"""Contract tests for manifest-driven fleet status normalization."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "fleet_status.py"
SCRIPT = ROOT / "scripts" / "fleet-status.sh"

_spec = importlib.util.spec_from_file_location("fleet_status", MODULE)
fleet_status = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = fleet_status
_spec.loader.exec_module(fleet_status)


def _manifest(**overrides):
    manifest = {
        "schema_version": 1,
        "generated_at": "2026-07-11T00:00:00Z",
        "hostname": "node-test",
        "provider": "upcloud",
        "environment": "prod",
        "enabled_transports": ["xray-reality", "nginx-xhttp"],
        "public_listeners": [{"proto": "tcp", "port": 443, "role": "xray"}],
        "security_controls": {"ssh_strict": True},
        "recovery": {"backup": {"enabled": True}},
    }
    manifest.update(overrides)
    return manifest


def test_schema_one_manifest_preserves_sanitized_capabilities_separate_from_observations():
    manifest = _manifest(extra_field="discarded")
    manifest["security_controls"]["unexpected_secret"] = "discarded"
    manifest["public_listeners"][0]["unexpected_secret"] = "discarded"
    record = fleet_status.build_record(
        provider="upcloud",
        environment="prod",
        address="192.0.2.10",
        terraform_output="ok",
        ssh="ok",
        asn="AS64500",
        xray_version="1.2.3",
        config_updated_at="2026-07-11 00:00:00",
        watchdog="ok",
        tcp_443="reachable",
        manifest_raw=json.dumps(manifest),
        manifest_available=True,
    )

    assert set(record) == {"identity", "declared", "observed"}
    assert set(record["declared"]) == set(fleet_status.DECLARED_KEYS)
    assert record["declared"]["status"] == "ok"
    assert record["declared"]["generated_at"] == "2026-07-11T00:00:00Z"
    assert record["declared"]["enabled_transports"] == ["xray-reality", "nginx-xhttp"]
    assert record["observed"]["ssh"] == "ok"
    assert "extra_field" not in json.dumps(record)
    assert "unexpected_secret" not in json.dumps(record)


def test_manifest_failure_states_do_not_leak_raw_input():
    cases = [
        ("", True, "missing"),
        ("not-json secret-marker", True, "invalid"),
        (json.dumps(["secret-marker"]), True, "invalid"),
        (json.dumps(_manifest(provider="vultr", secret="secret-marker")), True, "invalid"),
        (json.dumps(_manifest(enabled_transports={"secret-marker": True})), True, "invalid"),
        (json.dumps(_manifest(schema_version=2, secret="secret-marker")), True, "unsupported"),
        (json.dumps(_manifest(secret="secret-marker")), False, "unavailable"),
    ]
    for raw, available, expected_status in cases:
        declared = fleet_status.normalize_manifest(
            raw,
            expected_provider="upcloud",
            expected_environment="prod",
            available=available,
        )
        assert declared["status"] == expected_status
        assert "secret-marker" not in json.dumps(declared)
        if expected_status == "unsupported":
            assert declared["schema_version"] == 2
            assert declared["generated_at"] == "2026-07-11T00:00:00Z"
            assert declared["enabled_transports"] == []


def test_unknown_live_values_are_explicit_without_a_host_health_verdict():
    record = fleet_status.build_record(
        provider="upcloud",
        environment="prod",
        address="?",
        terraform_output="unexpected",
        ssh="unexpected",
        asn="?",
        xray_version="",
        config_updated_at="unknown",
        watchdog="?",
        tcp_443="?",
        manifest_raw="",
        manifest_available=False,
    )

    assert record["identity"]["address"] is None
    assert record["observed"] == {
        "terraform_output": "missing",
        "ssh": "not_attempted",
        "asn": None,
        "xray_version": None,
        "config_updated_at": None,
        "watchdog": "unknown",
        "tcp_443": "not_probed",
    }
    assert not ({"healthy", "status", "score", "recommendation"} & set(record))


def test_json_is_deterministic_and_table_uses_explicit_states():
    record = fleet_status.build_record(
        provider="upcloud",
        environment="prod",
        address=None,
        terraform_output="missing",
        ssh="not_attempted",
        asn=None,
        xray_version=None,
        config_updated_at=None,
        watchdog="unknown",
        tcp_443="not_probed",
        manifest_raw="",
        manifest_available=False,
    )
    rendered = fleet_status.render_json([record])
    assert rendered == fleet_status.render_json([record])
    assert set(json.loads(rendered)) == {"schema_version", "hosts"}
    table = fleet_status.render_table([record])
    assert "MANIFEST" in table and "TRANSPORTS" in table
    assert "unavailable" in table
    assert "not_probed" in table
    assert "unknown" in table
    assert "missing" in table


def test_real_bash_json_path_stops_after_supported_provider_output_is_missing(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    terraform = bin_dir / "terraform"
    terraform.write_text("#!/bin/sh\nexit 1\n")
    terraform.chmod(0o755)
    env = os.environ.copy()
    env["HOSTS"] = "upcloud:fleet-status-test"
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    result = subprocess.run(
        ["bash", str(SCRIPT), "--json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["schema_version"] == 1
    assert len(payload["hosts"]) == 1
    record = payload["hosts"][0]
    assert record["identity"] == {
        "provider": "upcloud",
        "environment": "fleet-status-test",
        "address": None,
    }
    assert record["declared"]["status"] == "unavailable"
    assert record["observed"]["terraform_output"] == "missing"
    assert record["observed"]["ssh"] == "not_attempted"
    assert record["observed"]["tcp_443"] == "not_probed"
