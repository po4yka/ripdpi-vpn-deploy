from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "snell-refinement.py"
SPEC = importlib.util.spec_from_file_location("snell_refinement", SCRIPT)
assert SPEC and SPEC.loader
snell_refinement = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = snell_refinement
SPEC.loader.exec_module(snell_refinement)


def test_snell_is_research_and_disabled_in_every_profile() -> None:
    manifest = yaml.safe_load((ROOT / "ansible/role-tiers.yml").read_text())
    assert manifest["tiers"]["snell"] == "research"
    assert manifest["toggle_role_map"]["enable_snell"] == "snell"
    for path in (ROOT / "ansible/group_vars").glob("vpn-*.yml"):
        data = yaml.safe_load(path.read_text()) or {}
        assert (data.get("vpn") or {}).get("enable_snell") is False


def test_snell_server_template_has_v5_and_v6_shapes() -> None:
    from scripts.template_render import merge_render_vars, render_template

    variables = merge_render_vars()
    rendered = render_template(ROOT / "ansible/roles/snell/templates/config.json.j2", variables)
    doc = json.loads(rendered)
    assert [item["listen_port"] for item in doc["inbounds"]] == [2443, 2444, 2445]
    assert [item["version"] for item in doc["inbounds"]] == [5, 6, 6]
    assert doc["inbounds"][0]["obfs_mode"] == "none"
    assert doc["inbounds"][1]["mode"] == "default"
    assert doc["inbounds"][2]["mode"] == "unshaped"


def test_snell_role_guards_the_exported_production_environment() -> None:
    tasks = (ROOT / "ansible/roles/snell/tasks/main.yml").read_text()
    assert "lookup('env', 'ENV')" in tasks
    assert "staging-only; refusing ENV=prod" in tasks
    assert tasks.index("Render validated Snell configuration") < tasks.index("Point Snell current symlink at validated release")
    assert "Preserve previous Snell release symlink" in tasks


def test_enabled_snell_surfaces_three_listener_contract_entries() -> None:
    from scripts.template_render import merge_render_vars, render_template

    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_snell": True}
    manifest = json.loads(render_template(ROOT / "ansible/templates/listener-manifest.json.j2", variables))
    snell = [item for item in manifest if item["role"].startswith("snell-") and item["enabled"]]
    assert [(item["protocol"], item["port"]) for item in snell] == [("tcp", 2443), ("tcp", 2444), ("tcp", 2445)]


def test_node_manifest_exposes_snell_without_credentials() -> None:
    from scripts.template_render import merge_render_vars, render_template

    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_snell": True}
    variables["snell_secrets"] = {"variants": [{"id": "v4-stream", "psk": "must-not-appear", "users": [{"name": "probe", "userkey": "also-secret"}]}]}
    rendered = render_template(ROOT / "ansible/roles/node_manifest/templates/manifest.json.j2", variables)
    manifest = json.loads(rendered)
    assert "snell" in manifest["enabled_transports"]
    assert "must-not-appear" not in rendered
    assert "also-secret" not in rendered


def test_backup_restore_drill_requires_valid_snell_config() -> None:
    from scripts.template_render import merge_render_vars, render_template

    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_snell": True}
    rendered = render_template(ROOT / "ansible/roles/backup/templates/vpn-backup-restore-drill.sh.j2", variables)
    assert 'require_file "etc/snell/config.json"' in rendered
    assert 'python3 -m json.tool "$restore_target/etc/snell/config.json"' in rendered


def test_client_emitter_keeps_snell_out_of_automatic_selection() -> None:
    source = (ROOT / "scripts/emit-singbox.sh").read_text()
    assert 'tag:"snell-evaluation"' in source
    assert 'SNELL_TAGS=' in source
    assert 'p3-snell-${variant_id}-${reuse_label}' in source
    assert '($snell | index($tag) | not)' in source
    liveness = json.loads((ROOT / "contract/protocol-liveness.schema.json").read_text())
    assert not any(profile.startswith("p3-snell") for profile in liveness["$defs"]["profile"]["enum"])


def _observations(profile: str, completed: list[bool], control: bool = True, duration: int = 20) -> list[dict]:
    rows = []
    for value in completed:
        rows.append({"profile": "direct", "bytes": 16384, "completed": control, "duration_ms": 10})
        rows.append({"profile": profile, "bytes": 16384, "completed": value, "duration_ms": duration if value else None})
        rows.append({"profile": "direct", "bytes": 16384, "completed": control, "duration_ms": 10})
    return rows


def test_refinement_classifier_requires_control_and_two_of_three() -> None:
    profile = "p3-snell-v6-default-fresh-test"
    assert snell_refinement.classify_profile(profile, [16384], 3, _observations(profile, [True, False, False]))["verdict"] == "blocked"
    assert snell_refinement.classify_profile(profile, [16384], 3, _observations(profile, [True, True, True], control=False))["verdict"] == "unknown"
    assert snell_refinement.classify_profile(profile, [16384], 3, _observations(profile, [True, True, True], duration=30))["verdict"] == "throttled"


def test_authentication_failure_is_error_not_blocked() -> None:
    profile = "p3-snell-v6-default-fresh-test"
    observations = _observations(profile, [False, False, False])
    reports = [snell_refinement.classify_profile(profile, [16384], 3, observations)]
    snell_refinement.mark_authentication_errors(reports, observations, "authentication failed for user")
    assert reports[0]["verdict"] == "error"
    assert reports[0]["first_failure_bytes"] is None


def test_snell_schema_limits_v6_psks_and_secret_path_alphabet() -> None:
    import jsonschema

    schema = json.loads((ROOT / "secrets/schema.json").read_text())
    document = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    base = {"linux_amd64_sha256": "a" * 64, "linux_arm64_sha256": "b" * 64}
    v4 = {**base, "evaluation_path_token": "safe_token-123456", "variants": [{"id": "v4-stream", "psk": "short", "users": [{"name": "a", "userkey": "long-user-key"}]}]}
    jsonschema.validate({**document, "snell_secrets": v4}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**document, "snell_secrets": {**base, "variants": [{"id": "v6-default", "psk": "short", "users": [{"name": "a", "userkey": "long-user-key"}]}]}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**document, "snell_secrets": {**v4, "evaluation_path_token": "unsafe|token-12345"}}, schema)


def test_result_schema_accepts_redacted_report() -> None:
    import jsonschema

    schema = json.loads((ROOT / "contract/snell-refinement-result.schema.json").read_text())
    profile = "p3-snell-v4-stream-fresh-test"
    report = {"schema_version": 1, "observed_at": 1, "vantage": "size-cliff-a", "verdict": "ok", "config_sha256": "a" * 64, "profiles": [snell_refinement.classify_profile(profile, [16384], 3, _observations(profile, [True, True, True]))]}
    jsonschema.validate(report, schema)
    assert "endpoint" not in json.dumps(report)


def test_result_schema_accepts_profileless_configuration_error() -> None:
    import jsonschema

    schema = json.loads((ROOT / "contract/snell-refinement-result.schema.json").read_text())
    report = snell_refinement.report_payload("size-cliff-a", b"invalid config", "error", [])
    jsonschema.validate(report, schema)
    assert report["verdict"] == "error"


def test_curl_probe_rejects_a_short_success_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    curl = tmp_path / "curl"
    curl.write_text("#!/bin/sh\nprintf '200 7 0.010\\n'\n")
    curl.chmod(0o700)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    assert snell_refinement.curl_probe("https://control.invalid/8.bin", 8, 1)["completed"] is False


def test_error_report_is_atomic_private_and_redacted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = type("Args", (), {"state_dir": tmp_path, "vantage": "size-cliff-a"})()
    report = snell_refinement.report_payload("size-cliff-a", b"config with secret endpoint", "error", [])
    snell_refinement.emit_report(args, report)
    output = capsys.readouterr().out
    saved = next((tmp_path / "size-cliff-a").glob("*.json"))
    assert saved.stat().st_mode & 0o777 == 0o600
    assert "secret endpoint" not in output
    assert "secret endpoint" not in saved.read_text()
