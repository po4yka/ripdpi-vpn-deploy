"""Behavior tests for the protocol-liveness operator interface."""

from __future__ import annotations

import json
import os
import runpy
import stat
import subprocess
import time
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "protocol-liveness.py"
SCHEMA = REPO_ROOT / "contract" / "protocol-liveness.schema.json"
PROFILES = ["p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"]


@pytest.fixture(autouse=True)
def scripts_import_path(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))


def _report(sentinel: str, verdicts: dict[str, str], *, control: str = "ok", age: int = 0) -> dict:
    return {
        "schema_version": 1,
        "sentinel": sentinel,
        "observed_at": int(time.time()) - age,
        "control": {"verdict": control, "duration_ms": 20},
        "profiles": [
            {
                "profile": profile,
                "verdict": verdict,
                "duration_ms": 40,
                "payload_transport": "tcp-https",
                "target_address_family": "ipv4" if profile == "p2-amneziawg" else "unknown",
                **({"fresh_handshake": True} if profile == "p2-amneziawg" and verdict in {"ok", "throttled"} else {}),
                **(
                    {"variants": [{"variant": 1, "verdict": verdict, "duration_ms": 40}]}
                    if profile != "p2-amneziawg"
                    else {}
                ),
            }
            for profile, verdict in verdicts.items()
        ],
        "runtime": {"sing_box": "1.14.0", "awg": "1.0.0", "xray": "26.3.27", "awg_toolchain": "a" * 64},
        "provenance": {"controller_revision": "b" * 40, "runner_sha256": "c" * 64,
                       "client_generation_id": "7f574d16-931e-42b4-a940-853b92f53a14",
                       "public_profile_digest": "d" * 64, "vantage": "external"},
    }


def _config(tmp_path: Path, *, quorum: int = 2) -> Path:
    path = tmp_path / "liveness.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "probe_url": "https://www.gstatic.com/generate_204",
                "expected_status": 204,
                "probe_timeout_seconds": 15,
                "degraded_after_ms": 3000,
                "stale_after_seconds": 120,
                "failure_threshold": 3,
                "otp_ttl_seconds": 3600,
                "expected_runtime": {"sing_box": "1.14.0", "awg": "1.0.0", "xray": "26.3.27", "awg_toolchain": "a" * 64},
                "policies": [
                    {
                        "id": "fullstack",
                        "required_profiles": PROFILES,
                        "min_failed_vantages": quorum,
                    }
                ],
                "sentinels": [
                    {"id": "tls-freeze-a", "ssh_target": "sentinel-a", "policy": "fullstack", "vantage": "external", "awg_target": {"provider": "vultr", "environment": "test", "instance": "awg0"}},
                    {"id": "udp-filtered-b", "ssh_target": "sentinel-b", "policy": "fullstack", "vantage": "external", "awg_target": {"provider": "vultr", "environment": "test", "instance": "awg0"}},
                ],
            },
            sort_keys=False,
        )
    )
    return path


def _fake_ssh(tmp_path: Path, reports: dict[str, dict | str]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    reports_path = tmp_path / "reports.json"
    reports_path.write_text(json.dumps(reports))
    ssh = bin_dir / "ssh"
    ssh.write_text(
        """#!/usr/bin/env python3
import json, pathlib, sys, time
reports = json.loads((pathlib.Path(__file__).parent.parent / 'reports.json').read_text())
target = next((arg for arg in sys.argv[1:] if arg in reports), '')
value = reports.get(target)
if isinstance(value, dict) and 'payload' in value:
    time.sleep(value.get('delay_seconds', 0))
    value = value['payload']
if isinstance(value, str):
    print(value)
    raise SystemExit(0)
if value is None:
    print('unreachable', file=sys.stderr)
    raise SystemExit(255)
print(json.dumps(value))
"""
    )
    ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _run(
    tmp_path: Path,
    config: Path,
    reports: dict[str, dict | str],
    *extra: str,
    evaluated_at: int | None = None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = _fake_ssh(tmp_path, reports)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    if evaluated_at is not None:
        env["PROTOCOL_LIVENESS_EVALUATED_AT"] = str(evaluated_at)
    return subprocess.run(
        ["python3", str(SCRIPT), "--config", str(config), *extra],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _all(verdict: str) -> dict[str, str]:
    return dict.fromkeys(PROFILES, verdict)


def test_schema_accepts_the_documented_configuration(tmp_path: Path) -> None:
    import jsonschema

    schema = json.loads(SCHEMA.read_text())
    config = yaml.safe_load(_config(tmp_path).read_text())
    jsonschema.Draft202012Validator(schema).validate(config)
    module = runpy.run_path(str(SCRIPT))
    assert module["remote_probe_deadline"](config, config["sentinels"][0]) == 335


def test_collector_deadline_matches_engine_without_summing_parallel_vantages(tmp_path):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["probe_timeout_seconds"] = 60
    for sentinel in config["sentinels"]:
        deadline = module["remote_probe_deadline"](config, sentinel)
        assert module["probe_deadline"](60, config["policies"][0]["required_profiles"]) < deadline == 560


def test_schema_requires_transport_and_host_key_alias_together(tmp_path: Path) -> None:
    import jsonschema

    schema = json.loads(SCHEMA.read_text())
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["sentinels"][0]["ssh_transport_host"] = "sentinel-direct"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(config)


@pytest.mark.parametrize("missing", ["xray", "awg_toolchain", "awg_target", "vantage"])
def test_fullstack_configuration_requires_explicit_runtime_and_target_binding(tmp_path, missing):
    config_path = _config(tmp_path)
    config = yaml.safe_load(config_path.read_text())
    config["expected_runtime"].update({"xray": "26.3.27", "awg_toolchain": "a" * 64})
    for sentinel in config["sentinels"]:
        sentinel.update({"vantage": "external", "awg_target": {"provider": "vultr", "environment": "test", "instance": "awg0"}})
    if missing in config["expected_runtime"]:
        del config["expected_runtime"][missing]
    else:
        del config["sentinels"][0][missing]
    config_path.write_text(yaml.safe_dump(config))
    module = runpy.run_path(str(SCRIPT))
    with pytest.raises(module["ConfigError"], match=missing):
        module["load_config"](config_path)


@pytest.mark.parametrize("url", ["https://example.test:8443/check", "https://user:password@example.test/check", "https://[::1]/check",
                                "https://exam\tple.test/check", "https://example.test/check\n", "https://example.test/check path"])
def test_awg_policy_rejects_unsupported_probe_url_contract(tmp_path, url):
    path = _config(tmp_path)
    config = yaml.safe_load(path.read_text())
    config["probe_url"] = url
    path.write_text(yaml.safe_dump(config))
    module = runpy.run_path(str(SCRIPT))
    assert any("IPv4 HTTPS port 443" in e for e in module["semantic_errors"](config))


@pytest.mark.parametrize("direct", [False, True])
def test_pull_report_uses_direct_transport_with_pinned_host_identity(monkeypatch, direct) -> None:
    module = runpy.run_path(str(SCRIPT))
    captured: list[str] = []
    monkeypatch.setattr(os, "environ", {"PATH": "/usr/bin:/bin", "HOME": "/fixture/home",
                                     "SSH_AUTH_SOCK": "/fixture/agent", "PROVIDER_TOKEN": "DO_NOT_LEAK_ENV_TOKEN"})

    def fake_run(command: list[str], **kwargs: object) -> bytes:
        captured.extend(command)
        assert kwargs["timeout"] == 30
        assert kwargs["limit"] == 65536
        assert set(kwargs["environment"]) <= {"PATH", "HOME", "SSH_AUTH_SOCK", "LANG", "LC_ALL"}
        assert "DO_NOT_LEAK_ENV_TOKEN" not in str(kwargs["environment"])
        return b"{}\n"

    monkeypatch.setitem(module["pull_report"].__globals__, "bounded_command", fake_run)
    def legacy_run(command, **_kwargs):
        captured.extend(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}\n", stderr="")
    monkeypatch.setattr(subprocess, "run", legacy_run)
    sentinel = {
        "id": "tls-freeze-a",
        "ssh_target": "sentinel-a",
        "policy": "fullstack",
    }
    if direct:
        sentinel.update(ssh_transport_host="sentinel-direct", ssh_host_key_alias="sentinel-a")

    sentinel_id, raw, error = module["pull_report"](sentinel, 10, 30)

    assert (sentinel_id, raw, error) == ("tls-freeze-a", "{}", "")
    for option in (
        "ProxyCommand=none",
        "ProxyJump=none",
        "ControlMaster=no",
        "ControlPath=none",
        "ControlPersist=no",
        "ClearAllForwardings=yes", "ForwardAgent=no", "ForwardX11=no",
        "PermitLocalCommand=no", "RemoteCommand=none", "RequestTTY=no",
        "PasswordAuthentication=no", "KbdInteractiveAuthentication=no", "GSSAPIAuthentication=no",
        "PreferredAuthentications=publickey",
    ):
        assert option in captured
    assert "StrictHostKeyChecking=yes" in captured
    assert "-F" not in captured
    assert captured[captured.index("sentinel-a") - 1] == "--"
    if direct:
        assert "HostName=sentinel-direct" in captured
        assert "HostKeyAlias=sentinel-a" in captured


@pytest.mark.parametrize("required,keys", [(["p0-reality"], {"sing_box"}),
    (["p2-hysteria2"], {"sing_box"}), (["p1-xhttp"], {"xray"}),
    (["p2-amneziawg"], {"awg", "awg_toolchain"})])
def test_report_runtime_is_scoped_to_its_sentinel_policy(tmp_path, required, keys):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["policies"][0]["required_profiles"] = required
    report = _report("tls-freeze-a", dict.fromkeys(required, "ok"))
    report["runtime"] = {key: value for key, value in report["runtime"].items() if key in keys}
    valid, error = module["validate_report"](json.dumps(report), config["sentinels"][0], config, int(time.time()))
    assert valid == report and error == ""
    report["runtime"].pop(next(iter(keys)))
    valid, error = module["validate_report"](json.dumps(report), config["sentinels"][0], config, int(time.time()))
    assert valid is None and "runtime mismatch" in error


@pytest.mark.parametrize("profile,key,pin", [("p0-reality", "sing_box", "1.14.0"), ("p1-xhttp", "xray", "26.3.27")])
def test_configuration_only_needs_pins_for_assigned_profiles(tmp_path, profile, key, pin):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["policies"][0]["required_profiles"] = [profile]
    config["expected_runtime"] = {key: pin}
    assert module["validate_config"](config) == config
    config["expected_runtime"] = {"awg": "1.0.0"}
    with pytest.raises(module["ConfigError"], match="expected_runtime." + key):
        module["validate_config"](config)


def test_invalid_configuration_diagnostic_does_not_echo_values(tmp_path):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["sentinels"][0]["ssh_target"] = "DO_NOT_LEAK_CONFIG_TOKEN invalid"
    with pytest.raises(module["ConfigError"]) as failure:
        module["validate_config"](config)
    assert "DO_NOT_LEAK_CONFIG_TOKEN" not in str(failure.value)
    assert "sentinels.0.ssh_target" in str(failure.value)
    assert "pattern" in str(failure.value)


@pytest.mark.parametrize("field,value", [("schema_version", True), ("observed_at", True),
    ("observed_at", "future"), ("control", ["secret-marker"]), ("control", {"verdict": []}),
    ("runtime", ["secret-marker"]), ("profiles", {"secret-marker": "ok"}),
    ("profiles", [None]), ("profiles", [{"profile": [], "verdict": "ok"}]),
    ("profiles", [{"profile": "p0-reality", "verdict": []}])])
def test_malformed_report_is_categorical_not_an_exception(tmp_path, field, value):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    report = _report("tls-freeze-a", _all("ok"))
    report[field] = int(time.time()) + 1 if value == "future" else value
    valid, error = module["validate_report"](json.dumps(report), config["sentinels"][0], config, int(time.time()))
    assert valid is None and error
    assert "secret-marker" not in error


@pytest.mark.parametrize("field,value", [("controller_revision", "z" * 40),
    ("runner_sha256", "secret-marker"), ("client_generation_id", "not-uuid"),
    ("public_profile_digest", []), ("vantage", "filtered"), ("vantage", ["external"]),
    ("secret", "secret-marker"), ("all", None), ("all", []), ("all", {})])
def test_report_requires_strict_public_provenance(tmp_path, field, value):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    report = _report("tls-freeze-a", _all("ok"))
    if field == "all":
        report["provenance"] = value
    else:
        report["provenance"][field] = value
    valid, error = module["validate_report"](json.dumps(report), config["sentinels"][0], config, int(time.time()))
    assert valid is None and "provenance" in error
    assert "secret-marker" not in error


@pytest.mark.parametrize("variants,verdict", [(["blocked", "blocked"], "blocked"),
    (["blocked", "ok"], "ok"), (["error", "throttled"], "throttled"),
    (["blocked", "error"], "error"), (["unknown", "blocked"], "unknown")])
def test_profile_verdict_must_match_runner_variant_semantics(tmp_path, variants, verdict):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    report = _report("tls-freeze-a", _all("ok"))
    profile = report["profiles"][0]
    profile["verdict"] = verdict
    profile["variants"] = [{"variant": i, "verdict": v} for i, v in enumerate(variants, 1)]
    validate = lambda: module["validate_report"](json.dumps(report), config["sentinels"][0], config, int(time.time()))
    assert validate() == (report, "")
    profile["verdict"] = "blocked" if verdict == "ok" else "ok"
    assert validate()[0] is None
    profile["verdict"] = verdict
    profile["variants"][0]["variant"] = True
    assert validate()[0] is None


def test_aggregate_whitelists_public_identity_without_claiming_server_source(tmp_path):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    report = _report("tls-freeze-a", _all("ok"))
    report["secret"] = "secret-marker"
    report["runtime"]["secret"] = "secret-marker"
    report["provenance"]["secret"] = "secret-marker"
    report["profiles"][0]["secret"] = "secret-marker"
    report["profiles"][0]["variants"][0]["secret"] = "secret-marker"
    payload = module["aggregate"](config, {"tls-freeze-a": report}, [])
    item = payload["evidence"][0]
    assert item["provenance"] == {k: v for k, v in report["provenance"].items() if k != "secret"}
    assert item["runtime"] == {k: v for k, v in report["runtime"].items() if k != "secret"}
    assert item["deployed_server_identity"] == {"status": "unknown"}
    assert item["observed_at"] == report["observed_at"]
    assert item["profile_observations"]["p2-amneziawg"] == {
        "payload_transport": "tcp-https", "target_address_family": "ipv4", "fresh_handshake": True}
    assert item["profile_observations"]["p1-xhttp"] == {
        "payload_transport": "tcp-https", "target_address_family": "unknown"}
    assert "secret-marker" not in json.dumps(payload)


@pytest.mark.parametrize("field,value", [("fresh_handshake", None), ("fresh_handshake", False),
    ("fresh_handshake", 1), ("target_address_family", "ipv6"), ("target_address_family", "unknown"),
    ("payload_transport", "udp"), ("payload_transport", ["tcp-https"])])
def test_awg_success_requires_exact_observed_transport_and_handshake(tmp_path, field, value):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    report = _report("tls-freeze-a", _all("ok"))
    report["profiles"][-1][field] = value
    valid, error = module["validate_report"](json.dumps(report), config["sentinels"][0], config, int(time.time()))
    assert valid is None and error


def test_remote_json_resource_errors_are_categorical(tmp_path):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    depth = 10000
    for raw in ('{"number":' + '1' * 5000 + '}', '[' * depth + ']' * depth):
        valid, error = module["validate_report"](raw, config["sentinels"][0], config, int(time.time()))
        assert valid is None and "malformed report" in error


def test_runtime_error_report_does_not_invent_unobserved_transport(tmp_path):
    module = runpy.run_path(str(SCRIPT))
    config = yaml.safe_load(_config(tmp_path).read_text())
    report = _report("tls-freeze-a", _all("error"))
    report["profiles"] = [{"profile": name, "verdict": "error"} for name in PROFILES]
    valid, error = module["validate_report"](json.dumps(report), config["sentinels"][0], config, int(time.time()))
    assert valid == report and error == ""
    payload = module["aggregate"](config, {"tls-freeze-a": report}, [])
    assert payload["decision"] == "unknown"
    assert all(observed == {"payload_transport": "unknown", "target_address_family": "unknown"}
               for observed in payload["evidence"][0]["profile_observations"].values())


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_pull_report_bounds_output_and_redacts_stderr(tmp_path, monkeypatch, stream):
    module = runpy.run_path(str(SCRIPT))
    executable = tmp_path / "ssh"
    executable.write_text(f"#!/usr/bin/env python3\nimport sys\nsys.{stream}.write('secret-marker' * 7000)\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    sid, raw, error = module["pull_report"]({"id": "probe", "ssh_target": "alias"}, 1, 2)
    assert sid == "probe" and raw == "" and error
    assert "secret-marker" not in error


@pytest.mark.parametrize(
    ("reports", "decision"),
    [
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("ok")),
                "sentinel-b": _report("udp-filtered-b", _all("ok")),
            },
            "healthy",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", {**_all("ok"), "p0-reality": "blocked"}),
                "sentinel-b": _report("udp-filtered-b", _all("ok")),
            },
            "degraded",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("blocked")),
                "sentinel-b": _report("udp-filtered-b", _all("blocked")),
            },
            "rotation_candidate",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("blocked"), control="unknown"),
                "sentinel-b": _report("udp-filtered-b", _all("blocked")),
            },
            "unknown",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("error")),
                "sentinel-b": _report("udp-filtered-b", _all("blocked")),
            },
            "unknown",
        ),
    ],
)
def test_evaluator_returns_the_expected_decision(
    tmp_path: Path, reports: dict[str, dict], decision: str
) -> None:
    for report in reports.values():
        report["observed_at"] = int(time.time())
    result = _run(tmp_path, _config(tmp_path), reports)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == decision


def test_collector_budget_covers_probe_stages_and_preserves_degraded(tmp_path: Path) -> None:
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["probe_timeout_seconds"] = 1
    config_path = tmp_path / "short-timeout.yaml"
    config_path.write_text(yaml.safe_dump(config))
    reports = {
        "sentinel-a": {
            "delay_seconds": 7,
            "payload": _report("tls-freeze-a", {**_all("ok"), "p0-reality": "throttled"}),
        },
        "sentinel-b": {"delay_seconds": 7, "payload": _report("udp-filtered-b", _all("ok"))},
    }

    result = _run(tmp_path, config_path, reports)

    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "degraded"


def test_one_fully_blocked_vantage_is_below_quorum(tmp_path: Path) -> None:
    reports = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("ok")),
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    payload = json.loads(result.stdout)
    assert payload["decision"] == "degraded"
    assert payload["candidate_policies"] == []
    assert payload["failed_vantages"] == {"fullstack": 1}


def test_policy_defaults_to_two_failed_vantages(tmp_path: Path) -> None:
    config = yaml.safe_load(_config(tmp_path).read_text())
    del config["policies"][0]["min_failed_vantages"]
    path = tmp_path / "default-quorum.yaml"
    path.write_text(yaml.safe_dump(config))
    reports = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }

    result = _run(tmp_path, path, reports)

    assert json.loads(result.stdout)["decision"] == "rotation_candidate"


def test_stale_and_malformed_reports_never_create_a_candidate(tmp_path: Path) -> None:
    reports = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked"), age=121),
        "sentinel-b": "not-json",
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    payload = json.loads(result.stdout)
    assert payload["decision"] == "unknown"
    assert len(payload["monitoring_errors"]) == 2


def test_missing_required_profile_never_counts_toward_quorum(tmp_path: Path) -> None:
    incomplete = _all("blocked")
    incomplete.pop("p2-amneziawg")
    reports = {
        "sentinel-a": _report("tls-freeze-a", incomplete),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    assert json.loads(result.stdout)["decision"] == "unknown"


def test_configuration_rejects_duplicate_ids_and_impossible_quorum(tmp_path: Path) -> None:
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["sentinels"][1]["id"] = config["sentinels"][0]["id"]
    config["policies"][0]["min_failed_vantages"] = 3
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(config))

    result = _run(tmp_path, path, {})

    assert result.returncode == 2
    assert "duplicate sentinel id" in result.stderr
    assert "exceeds assigned sentinels" in result.stderr


def test_recorded_candidate_streak_resets_on_recovery(tmp_path: Path) -> None:
    config = _config(tmp_path)
    state_dir = tmp_path / "state"
    blocked = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }
    healthy = {
        "sentinel-a": _report("tls-freeze-a", _all("ok")),
        "sentinel-b": _report("udp-filtered-b", _all("ok")),
    }

    base = int(time.time())
    for index, expected in enumerate((1, 2, 3)):
        result = _run(
            tmp_path,
            config,
            blocked,
            "--state-dir",
            str(state_dir),
            evaluated_at=base + index * 120,
        )
        assert json.loads(result.stdout)["candidate_streak"] == expected

    recovered = _run(tmp_path, config, healthy, "--state-dir", str(state_dir))

    assert json.loads(recovered.stdout)["candidate_streak"] == 0
    assert stat.S_IMODE((state_dir / "decision-state.json").stat().st_mode) == 0o600


def test_duplicate_evaluation_in_the_same_interval_does_not_advance_streak(tmp_path: Path) -> None:
    config = _config(tmp_path)
    state_dir = tmp_path / "state"
    blocked = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }
    slot_time = int(time.time())

    first = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=slot_time)
    duplicate = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=slot_time + 1)

    assert json.loads(first.stdout)["candidate_streak"] == 1
    assert json.loads(duplicate.stdout)["candidate_streak"] == 1


def test_crossing_a_wall_clock_boundary_early_does_not_advance_streak(tmp_path: Path) -> None:
    config = _config(tmp_path)
    state_dir = tmp_path / "state"
    blocked = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }
    first_at = 119

    first = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=first_at)
    too_soon = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=121)
    next_interval = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=239)

    assert json.loads(first.stdout)["candidate_streak"] == 1
    assert json.loads(too_soon.stdout)["candidate_streak"] == 1
    assert json.loads(next_interval.stdout)["candidate_streak"] == 2


def test_unknown_profile_in_report_is_monitoring_error(tmp_path: Path) -> None:
    invalid = _report("tls-freeze-a", _all("blocked"))
    invalid["profiles"].append({"profile": "p9-unknown", "verdict": "blocked"})
    reports = {
        "sentinel-a": invalid,
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    payload = json.loads(result.stdout)
    assert payload["decision"] == "unknown"
    assert any("invalid profile result" in error for error in payload["monitoring_errors"])
