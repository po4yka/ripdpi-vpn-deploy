"""Bundle v3 generation: endpoint health, field-report block and cohort token rotation (SCR-1795086521848661)."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.test_emit_bundle_host_selection import (
    test_bundle_uses_feature_host_and_emits_ingress_topology as _emit_setup,
)
from tests.unit.test_field_report_ingest import (  # noqa: F401 - ingest is a fixture
    GOLDEN,
    _post,
    ingest,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bundle_health

NOW = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.timezone.utc)
FRESH = int((NOW - dt.timedelta(minutes=5)).timestamp())
STALE = int((NOW - dt.timedelta(hours=2)).timestamp())


def _liveness(tmp_path: Path, evidence: list[dict]) -> str:
    path = tmp_path / "last-evidence.json"
    path.write_text(json.dumps({"schema_version": 2, "evidence": evidence}))
    return str(path)


def _evidence(sentinel: str, observed_at: int, **profiles: str) -> dict:
    verdicts = {name.replace("_", "-"): verdict for name, verdict in profiles.items()}
    return {"sentinel": sentinel, "policy": "vpn-p0", "observed_at": observed_at, "profiles": verdicts,
            "endpoint_variants": {name: [{"variant": 1, "server_ref": name + "-upcloud-prod", "verdict": verdict}]
                                  for name, verdict in verdicts.items() if name != "p2-amneziawg"}}


ENDPOINTS = {
    "p0-reality-upcloud-prod": ("upcloud:prod", "p0-reality"),
    "p2-hysteria2-upcloud-prod": ("upcloud:prod", "p2-hysteria2"),
    "p1-xhttp-upcloud-prod": ("upcloud:prod", "p1-xhttp"),
    "p2-awg-phone": ("upcloud:prod", "p2-amneziawg"),
    "p3-snell-a-fresh-upcloud-prod": ("upcloud:prod", None),
}


def test_health_follows_the_liveness_quorum_and_marks_missing_input_unknown(tmp_path):
    config = {"liveness": _liveness(tmp_path, [
        _evidence("sentinel-a", FRESH, p0_reality="ok", p2_hysteria2="blocked", p2_amneziawg="throttled"),
        _evidence("sentinel-b", FRESH - 60, p0_reality="ok", p2_hysteria2="blocked", p2_amneziawg="ok"),
    ]), "policies": {"upcloud:prod": "vpn-p0"}, "ttl_seconds": 600}
    health = bundle_health.endpoint_health(ENDPOINTS, config, NOW)
    assert {tag: value["health"]["status"] for tag, value in health.items()} == {
        "p0-reality-upcloud-prod": "healthy",
        "p2-hysteria2-upcloud-prod": "down",
        "p1-xhttp-upcloud-prod": "unknown",
        "p2-awg-phone": "degraded",
        "p3-snell-a-fresh-upcloud-prod": "unknown",
    }
    observed = (NOW - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert health["p0-reality-upcloud-prod"]["health"] == {"status": "healthy", "observed_at": observed, "ttl_seconds": 600}


@pytest.mark.parametrize("config", [
    lambda tmp_path: {"liveness": _liveness(tmp_path, [_evidence("sentinel-a", STALE, p0_reality="ok")]),
                      "policies": {"upcloud:prod": "vpn-p0"}},
    lambda tmp_path: {"liveness": str(tmp_path / "absent.json"), "policies": {"upcloud:prod": "vpn-p0"}},
    lambda tmp_path: {"liveness": _liveness(tmp_path, [_evidence("sentinel-a", FRESH, p0_reality="ok")])},
    lambda tmp_path: {"liveness": _liveness(tmp_path, [{"sentinel": "sentinel-a", "policy": "vpn-p0",
                                                       "observed_at": FRESH, "profiles": {"p0-reality": "ok"}}]),
                      "policies": {"upcloud:prod": "vpn-p0"}},
], ids=["stale", "absent-file", "no-policy-for-host", "no-endpoint-observation"])
def test_stale_absent_or_unmapped_input_is_unknown(tmp_path, config):
    health = bundle_health.endpoint_health({"p0-reality-upcloud-prod": ("upcloud:prod", "p0-reality")}, config(tmp_path), NOW)
    assert health["p0-reality-upcloud-prod"]["health"]["status"] == "unknown"


def test_unproven_cascade_leg_cannot_certify_an_endpoint(tmp_path):
    config = {"liveness": _liveness(tmp_path, [_evidence("sentinel-a", FRESH, p0_reality="ok")]),
              "policies": {"upcloud:prod": "vpn-p0"}, "min_failed_vantages": 1,
              "cascade_leg_health": {"upcloud:prod": str(tmp_path / "missing-leg.json")}}
    health = bundle_health.endpoint_health({"p0-reality-upcloud-prod": ("upcloud:prod", "p0-reality")}, config, NOW)
    assert health["p0-reality-upcloud-prod"]["health"]["status"] == "unknown"


@pytest.mark.parametrize(("settings", "error"), [
    ({"ttl_seconds": 7200, "max_ttl_seconds": 3600}, "health-ttl-exceeds-maximum"),
    ({"ttl_seconds": 90000}, "health-ttl-exceeds-maximum"),
    ({"ttl_seconds": 30}, "invalid-health-config"),
    ({"max_ttl_seconds": 90000}, "invalid-health-config"),
    ({"unexpected": 1}, "invalid-health-config"),
])
def test_health_ttl_above_the_maximum_fails_generation(tmp_path, settings, error):
    path = tmp_path / "health.json"
    path.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match=error):
        bundle_health.load_config(str(path))


@pytest.mark.parametrize("source", [None, {"enabled": False, "cohort_token": "a" * 43}])
def test_disabled_field_reports_publish_no_block(source):
    assert bundle_health.field_report_block({} if source is None else {"field_report": source}) is None


def test_enabled_field_reports_publish_only_the_client_fields():
    source = {"enabled": True, "endpoint": "https://sub.example.test:8444/v1/field-report", "max_reports_per_day": 4,
              "cohort_token": "a" * 43, "previous_cohort_token": "b" * 43, "previous_cohort_token_valid_until": "2026-11-26T00:00:00Z"}
    assert bundle_health.field_report_block({"field_report": source}) == {
        "endpoint": "https://sub.example.test:8444/v1/field-report", "cohort_token": "a" * 43, "max_reports_per_day": 4}
    with pytest.raises(ValueError, match="invalid-field-report-config"):
        bundle_health.field_report_block({"field_report": {**source, "endpoint": "http://sub.example.test/v1/field-report"}})
    hinted = {**source, "network_hint_endpoint": "https://sub.example.test:8444/v1/network-hint"}
    assert bundle_health.field_report_block({"field_report": hinted})["network_hint_endpoint"] == \
        "https://sub.example.test:8444/v1/network-hint"
    with pytest.raises(ValueError, match="invalid-field-report-config"):
        bundle_health.field_report_block({"field_report": {**hinted, "network_hint_endpoint": "http://sub.example.test/v1/network-hint"}})


def _rerun_emit(tmp_path: Path, extra_env: dict, field_report: dict | None) -> subprocess.CompletedProcess:
    secrets = tmp_path / "secrets.json"
    document = json.loads(secrets.read_text())
    if field_report is not None:
        document["field_report"] = field_report
    secrets.write_text(json.dumps(document))
    repo = tmp_path / "repo"
    for name in ("bundle_health.py", "check-cascade-leg-health.py"):
        (repo / "scripts" / name).write_bytes((ROOT / "scripts" / name).read_bytes())
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "SOPS_FILE": str(secrets),
           "HOSTS": "upcloud:p0,vultr:p2", "COHORTS": "p0,p2", **extra_env}
    return subprocess.run(["bash", str(repo / "scripts/emit-bundle.sh"), "android-ripdpi"], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=60)


def _validate(tmp_path: Path, bundle: str) -> subprocess.CompletedProcess:
    path = tmp_path / "bundle.json"
    path.write_text(bundle)
    return subprocess.run([sys.executable, str(ROOT / "scripts/validate-bundle.py"), str(path)], capture_output=True, text=True)


def test_generator_emits_v3_with_health_and_field_report_that_validates(tmp_path):
    _emit_setup(tmp_path, "upcloud:p0,vultr:p2", "p0,p2", 0)
    observed = int(dt.datetime.now(dt.timezone.utc).timestamp()) - 60
    liveness = tmp_path / "last-evidence.json"
    liveness.write_text(json.dumps({"evidence": [
        {"sentinel": "sentinel-a", "policy": "vpn-p2", "observed_at": observed, "profiles": {"p2-amneziawg": "blocked"}},
        {"sentinel": "sentinel-b", "policy": "vpn-p2", "observed_at": observed, "profiles": {"p2-amneziawg": "blocked"}},
    ]}))
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"liveness": str(liveness), "policies": {"vultr:p2": "vpn-p2"}, "ttl_seconds": 900}))
    token = "c" * 43
    result = _rerun_emit(tmp_path, {"BUNDLE_HEALTH_FILE": str(health)}, {
        "enabled": True, "endpoint": "https://sub.example.test:8444/v1/field-report", "max_reports_per_day": 4,
        "cohort_token": token})
    assert result.returncode == 0, result.stderr
    ripdpi = json.loads(result.stdout)["ripdpi"]
    assert ripdpi["schema_version"] == 3
    awg_tag = ripdpi["amneziawg"][0]["tag"]
    assert set(ripdpi["endpoints"]) == {awg_tag}
    assert ripdpi["endpoints"][awg_tag]["health"]["status"] == "down"
    assert ripdpi["field_report"] == {"endpoint": "https://sub.example.test:8444/v1/field-report",
                                      "cohort_token": token, "max_reports_per_day": 4}
    assert token not in result.stderr
    validation = _validate(tmp_path, result.stdout)
    assert validation.returncode == 0, validation.stderr


def test_generator_without_health_input_or_enabled_reports_omits_both_blocks(tmp_path):
    _emit_setup(tmp_path, "upcloud:p0,vultr:p2", "p0,p2", 0)
    result = _rerun_emit(tmp_path, {}, {"enabled": False, "cohort_token": "c" * 43})
    assert result.returncode == 0, result.stderr
    ripdpi = json.loads(result.stdout)["ripdpi"]
    assert ripdpi["schema_version"] == 3 and "field_report" not in ripdpi and "endpoints" not in ripdpi
    validation = _validate(tmp_path, result.stdout)
    assert validation.returncode == 0, validation.stderr


def test_generator_refuses_a_ttl_above_the_configured_maximum(tmp_path):
    _emit_setup(tmp_path, "upcloud:p0,vultr:p2", "p0,p2", 0)
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"ttl_seconds": 7200, "max_ttl_seconds": 3600}))
    result = _rerun_emit(tmp_path, {"BUNDLE_HEALTH_FILE": str(health)}, None)
    assert result.returncode == 2 and not result.stdout
    assert "client-payload: health-ttl-exceeds-maximum" in result.stderr


# A plaintext JSON stand-in for sops: decrypt prints the file, set writes one key read from stdin.
SOPS_STUB = r'''#!/usr/bin/env python3
import json, re, sys
args = sys.argv[1:]
if "--decrypt" in args:
    sys.stdout.write(open(args[-1]).read()); sys.exit(0)
if args[0] == "set" and "--value-stdin" in args:
    path, index = args[-2], args[-1]
    document = json.load(open(path))
    keys = re.findall(r'\["([^"]+)"\]', index)
    node = document
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = json.loads(sys.stdin.read())
    json.dump(document, open(path, "w")); sys.exit(0)
sys.exit("unexpected sops call")
'''


def _rotate(tmp_path: Path, secrets: Path, **extra_env: str) -> subprocess.CompletedProcess:
    stub = tmp_path / "stub-bin"
    stub.mkdir(exist_ok=True)
    (stub / "sops").write_text(SOPS_STUB)
    (stub / "sops").chmod(0o700)
    inherited = {key: value for key, value in os.environ.items() if key != "FORCE"}
    env = {**inherited, "PATH": f"{stub}:{os.environ['PATH']}", "SOPS_FILE": str(secrets), "HOME": str(tmp_path),
           "AUDIT_LOG_FILE": str(tmp_path / "audit.log.age"), **extra_env}
    return subprocess.run(["bash", str(ROOT / "scripts/rotate-cohort-token.sh")], env=env, capture_output=True,
                          text=True, timeout=30)


def test_rotation_keeps_one_previous_token_and_the_ingest_honours_the_overlap(tmp_path, ingest):  # noqa: F811
    secrets = tmp_path / "prod.secrets.sops.json"
    secrets.write_text(json.dumps({"other": "kept"}))
    secrets.chmod(0o600)
    tokens = []
    # The third rotation replaces a previous token whose overlap is still open, which needs FORCE=1.
    for force in ("", "", "1"):
        result = _rotate(tmp_path, secrets, **({"FORCE": force} if force else {}))
        assert result.returncode == 0, result.stderr
        document = json.loads(secrets.read_text())
        tokens.append(document["field_report"]["cohort_token"])
        assert tokens[-1] not in result.stdout + result.stderr
    field_report = document["field_report"]
    assert document["other"] == "kept"
    assert len(set(tokens)) == 3 and all(len(token) == 43 for token in tokens)
    assert field_report["previous_cohort_token"] == tokens[1]
    until = dt.datetime.fromisoformat(field_report["previous_cohort_token_valid_until"].replace("Z", "+00:00"))
    assert dt.timedelta(days=6) < until - dt.datetime.now(dt.timezone.utc) <= dt.timedelta(days=7)
    assert not list(tmp_path.glob("prod.secrets.sops.json.rotate.*"))
    # The ingest reads the same keys the subscription-host role publishes as its credential.
    _, config = ingest({"current": field_report["cohort_token"], "previous": field_report["previous_cohort_token"],
                        "previous_valid_until": field_report["previous_cohort_token_valid_until"]})
    body = json.dumps(GOLDEN).encode()
    assert [_post(config, body, token=token) for token in reversed(tokens)] == [202, 202, 401]


def test_rotation_refuses_to_drop_a_previous_token_inside_its_overlap(tmp_path):
    secrets = tmp_path / "prod.secrets.sops.json"
    secrets.write_text(json.dumps({}))
    secrets.chmod(0o600)
    for _ in range(2):
        assert _rotate(tmp_path, secrets).returncode == 0
    before = secrets.read_text()
    result = _rotate(tmp_path, secrets)
    assert result.returncode == 1 and "FORCE=1" in result.stderr
    assert secrets.read_text() == before
    assert json.loads(before)["field_report"]["previous_cohort_token"] not in result.stdout + result.stderr
    assert not list(tmp_path.glob("prod.secrets.sops.json.rotate.*"))


def test_rotation_refuses_an_overlap_outside_its_bounds(tmp_path):
    secrets = tmp_path / "prod.secrets.sops.json"
    secrets.write_text(json.dumps({}))
    result = subprocess.run(["bash", str(ROOT / "scripts/rotate-cohort-token.sh")], capture_output=True, text=True,
                            env={**os.environ, "SOPS_FILE": str(secrets), "OVERLAP_DAYS": "31"}, timeout=30)
    assert result.returncode == 2 and "OVERLAP_DAYS" in result.stderr
    assert json.loads(secrets.read_text()) == {}
