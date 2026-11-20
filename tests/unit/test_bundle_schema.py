"""Lock the contract for contract/ripdpi-bundle.schema.json.

This is the server half of a paired, cross-repo contract test. The RIPDPI
Android client runs an equivalent test against a byte-identical vendored copy
of the same schema and the same cohort-fingerprint golden. Together they make
the bundle contract machine-checkable on both sides instead of prose that can
drift silently between the two repos.

Threats caught here:
  1. The committed schema examples and negative fixtures drift from the schema.
  2. The cohort-fingerprint algorithm drifts between the emit side (bash +
     ripdpi_cohort_fingerprint.py) and the parse side (Kotlin): the paired
     golden pins the exact hash both must produce.
  3. The schema's contract version drifts from the version the client supports.
  4. The client field-report v1 contract (contract/client-field-report.schema.json
     plus scripts/validate-field-report.py) admits identifying data, a
     mis-paired failure_stage or a histogram that does not sum to attempts.

The executable emitter guarantee lives in test_emit_singbox_roundtrip.py: it
runs emit-bundle.sh through emit-singbox.sh, then validates the emitted result
with validate-bundle.py and asserts the optional extension semantics.
"""
from __future__ import annotations

import base64
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from ripdpi_cohort_fingerprint import ORDER, cohort_fingerprint  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "contract" / "ripdpi-bundle.schema.json"
EXAMPLE = REPO_ROOT / "contract" / "ripdpi-bundle.example.json"
GOLDEN = REPO_ROOT / "contract" / "cohort-fingerprint.golden.json"
GOLDEN_FULL = REPO_ROOT / "contract" / "ripdpi-bundle.golden-full.json"
NEGATIVE_DIR = REPO_ROOT / "contract" / "negative"
VALIDATOR = REPO_ROOT / "scripts" / "validate-bundle.py"
HEALTH_EXPIRED = REPO_ROOT / "contract" / "ripdpi-bundle.health-expired.json"
REPORT_SCHEMA = REPO_ROOT / "contract" / "client-field-report.schema.json"
REPORT_GOLDEN = REPO_ROOT / "contract" / "client-field-report.golden.json"
REPORT_GOLDEN_SIM = REPO_ROOT / "contract" / "client-field-report.golden-sim.json"
HINT_SCHEMA = REPO_ROOT / "contract" / "client-network-hint.schema.json"
HINT_GOLDEN = REPO_ROOT / "contract" / "client-network-hint.golden.json"
REPORT_VALIDATOR = REPO_ROOT / "scripts" / "validate-field-report.py"


def _ripdpi(doc):
    """Return the ripdpi object from a full bundle, or the doc if it is one."""
    return doc["ripdpi"] if isinstance(doc, dict) and "ripdpi" in doc else doc

# Cross-repo drift pin. The client's SingBoxSubscriptionParser.RipdpiSchemaVersion
# and its vendored schema's x-contract-version must equal this. Bumping it is a
# coordinated, breaking change across both repos.
CONTRACT_VERSION = 3


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA.read_text())


@pytest.fixture(scope="module")
def example():
    return json.loads(EXAMPLE.read_text())


def _validator(schema):
    import jsonschema  # local import — present via requirements pin

    return jsonschema.Draft202012Validator(schema)


# ---------------------------------------------------------------------------
# Schema shape and version pin
# ---------------------------------------------------------------------------
def test_schema_contract_version_pin(schema):
    assert schema["x-contract-version"] == CONTRACT_VERSION
    assert schema["properties"]["schema_version"]["const"] == CONTRACT_VERSION


def test_example_validates(schema, example):
    errors = list(_validator(schema).iter_errors(example))
    assert errors == [], [e.message for e in errors]


def test_example_validates_via_cli():
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(EXAMPLE)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_payload_failover_bundle_validates_via_cli():
    fixture = REPO_ROOT / "contract/ripdpi-bundle.payload-failover.json"
    proc = subprocess.run([sys.executable, str(VALIDATOR), str(fixture)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("field,value", [("h1", "11\n"), ("h1", "11-99\n"),
                                        ("i1", "<b 0xaabb>\n"), ("i5", "<t>\n")])
def test_wire_profile_schema_rejects_trailing_newline(schema, example, field, value):
    bundle = copy.deepcopy(example)
    bundle["amneziawg"][0][field] = value
    assert list(_validator(schema).iter_errors(bundle))


# ---------------------------------------------------------------------------
# Paired cohort-fingerprint golden (the client recomputes the same value)
# ---------------------------------------------------------------------------
def test_cohort_fingerprint_golden():
    golden = json.loads(GOLDEN.read_text())
    assert cohort_fingerprint(golden["params"]) == golden["fingerprint"]


def test_example_awg_fingerprint_recomputes(example):
    entry = example["amneziawg"][0]
    params = {k: entry[k] for k in ORDER if k in entry}
    assert entry["cohort_fingerprint"] == cohort_fingerprint(params)


def test_absent_wire_profile_is_the_contract_constant_and_other_gaps_refuse():
    golden = json.loads(GOLDEN.read_text())
    params = {key: value for key, value in golden["params"].items() if key != "wire_profile"}
    assert cohort_fingerprint(params) == golden["fingerprint"]
    assert cohort_fingerprint({**params, "wire_profile": None}) == golden["fingerprint"]
    script = REPO_ROOT / "scripts" / "ripdpi_cohort_fingerprint.py"
    for key in ("jc", "h4"):
        partial = {name: value for name, value in params.items() if name != key}
        with pytest.raises(ValueError):
            cohort_fingerprint(partial)
        result = subprocess.run([sys.executable, str(script), "-"], input=json.dumps(partial),
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 2 and not result.stdout


def test_fingerprint_is_order_stable():
    a = {"wire_profile": "awg-3.1-ranges-v1", "jc": 4, "jmin": 10, "jmax": 50, "s1": 0, "s2": 0,
         "h1": '1', "h2": '2', "h3": '3', "h4": '4'}
    b = {k: a[k] for k in reversed(list(a))}
    assert cohort_fingerprint(a) == cohort_fingerprint(b)


# ---------------------------------------------------------------------------
# Required-field class
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("drop", ["schema_version", "amneziawg", "hysteria_extras"])
def test_dropping_required_top_level_fails(schema, example, drop):
    doc = copy.deepcopy(example)
    del doc[drop]
    assert list(_validator(schema).iter_errors(doc))


@pytest.mark.parametrize(
    "drop",
    ["tag", "address", "mtu", "jc", "h1", "h4", "private_key_placeholder", "peer"],
)
def test_dropping_required_awg_field_fails(schema, example, drop):
    doc = copy.deepcopy(example)
    del doc["amneziawg"][0][drop]
    assert list(_validator(schema).iter_errors(doc))


@pytest.mark.parametrize("drop", ["public_key", "preshared_key", "endpoint", "allowed_ips"])
def test_dropping_required_peer_field_fails(schema, example, drop):
    doc = copy.deepcopy(example)
    del doc["amneziawg"][0]["peer"][drop]
    assert list(_validator(schema).iter_errors(doc))


# ---------------------------------------------------------------------------
# Version 3 rejects unknown fields at every level, including the top level.
# ---------------------------------------------------------------------------
def test_unknown_top_level_field_rejected(schema, example):
    doc = copy.deepcopy(example)
    doc["some_future_field"] = {"anything": 1}
    assert [e.validator for e in _validator(schema).iter_errors(doc)] == ["additionalProperties"]


def test_typo_in_awg_entry_rejected(schema, example):
    doc = copy.deepcopy(example)
    doc["amneziawg"][0]["jcc"] = 4  # typo for jc
    assert list(_validator(schema).iter_errors(doc))


# ---------------------------------------------------------------------------
# Field-format class
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("version", [1, 2, 4])
def test_other_schema_versions_rejected(schema, example, version):
    doc = copy.deepcopy(example)
    doc["schema_version"] = version
    assert list(_validator(schema).iter_errors(doc))


def test_insecure_true_rejected(schema, example):
    doc = copy.deepcopy(example)
    tag = next(iter(doc["hysteria_extras"]))
    doc["hysteria_extras"][tag]["insecure"] = True
    assert list(_validator(schema).iter_errors(doc))


def test_bad_salamander_tag_rejected(schema, example):
    doc = copy.deepcopy(example)
    tag = next(iter(doc["hysteria_extras"]))
    doc["hysteria_extras"][tag]["salamander_upstream_tag"] = "latest"
    assert list(_validator(schema).iter_errors(doc))


def test_bad_cohort_fingerprint_format_rejected(schema, example):
    doc = copy.deepcopy(example)
    doc["amneziawg"][0]["cohort_fingerprint"] = "deadbeef"
    assert list(_validator(schema).iter_errors(doc))


def test_bad_expires_rejected(schema, example):
    doc = copy.deepcopy(example)
    doc["expires"] = "next tuesday"
    assert list(_validator(schema).iter_errors(doc))


# ---------------------------------------------------------------------------
# Realistic full bundle (sing-box document + ripdpi object) — the emit->parse
# golden the client also consumes. Validates a populated outbounds list plus
# i1..i5, salamander_upstream_tag, and a non-default topology.
# ---------------------------------------------------------------------------
def test_golden_full_ripdpi_validates(schema):
    ripdpi = _ripdpi(json.loads(GOLDEN_FULL.read_text()))
    errors = list(_validator(schema).iter_errors(ripdpi))
    assert errors == [], [e.message for e in errors]


def test_v2_golden_rejected_on_schema_version_only(schema):
    ripdpi = _ripdpi(json.loads(GOLDEN_FULL.read_text()))
    ripdpi["schema_version"] = 2
    for name in ("endpoints", "field_report"):
        ripdpi.pop(name)
    errors = list(_validator(schema).iter_errors(ripdpi))
    assert [(e.validator, list(e.absolute_path)) for e in errors] == [("const", ["schema_version"])]


@pytest.mark.parametrize("endpoint", [
    "http://reports.example.test/v1/field-report",
    "https://user@reports.example.test/v1",
    "https://reports.example.test/v1 x",
    "reports.example.test/v1",
])
def test_field_report_endpoint_requires_plain_https(schema, example, endpoint):
    doc = copy.deepcopy(example)
    doc["field_report"]["endpoint"] = endpoint
    assert [list(e.absolute_path) for e in _validator(schema).iter_errors(doc)] == [["field_report", "endpoint"]]


@pytest.mark.parametrize("field,value", [
    ("ttl_seconds", 59), ("ttl_seconds", 86401), ("observed_at", "2026-11-19T10:00:00+03:00"),
    ("observed_at", "2026-11-19"),
])
def test_health_shape_bounds_rejected(schema, example, field, value):
    doc = copy.deepcopy(example)
    next(iter(doc["endpoints"].values()))["health"][field] = value
    assert list(_validator(schema).iter_errors(doc))


def test_health_invalid_calendar_instant_refuses(tmp_path, example):
    doc = copy.deepcopy(example)
    next(iter(doc["endpoints"].values()))["health"]["observed_at"] = "2026-02-30T10:00:00Z"
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    proc = _run_validator(path)
    assert proc.returncode == 1
    assert "observed_at: requires a valid calendar instant" in proc.stderr


def test_full_bundle_endpoint_key_must_name_a_bundle_tag(tmp_path):
    doc = json.loads(GOLDEN_FULL.read_text())
    doc["ripdpi"]["endpoints"]["p9-unlisted"] = copy.deepcopy(doc["ripdpi"]["endpoints"]["p2-awg-phone"])
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    proc = _run_validator(path)
    assert proc.returncode == 1
    assert "key names no outbound or AWG tag" in proc.stderr


def test_expired_health_fixture_is_the_expiry_case():
    from datetime import datetime, timedelta

    doc = json.loads(HEALTH_EXPIRED.read_text())
    assert _run_validator(HEALTH_EXPIRED).returncode == 0
    clock = datetime.fromisoformat(doc["_evaluated_at"])
    endpoints = doc["ripdpi"]["endpoints"]
    assert {health["health"]["status"] for health in endpoints.values()} >= {"healthy", "down"}
    for endpoint in endpoints.values():
        health = endpoint["health"]
        assert datetime.fromisoformat(health["observed_at"]) + timedelta(seconds=health["ttl_seconds"]) < clock
    assert doc["_expected_effective_status"] == {ref: "unknown" for ref in endpoints}


def test_expired_health_rule_is_documented():
    text = (REPO_ROOT / "docs/reference/ripdpi-bundle.md").read_text()
    assert "`observed_at` plus `ttl_seconds` is in the past" in text
    assert "ripdpi-bundle.health-expired.json" in text


def test_golden_full_awg_fingerprint_recomputes():
    ripdpi = _ripdpi(json.loads(GOLDEN_FULL.read_text()))
    entry = ripdpi["amneziawg"][0]
    params = {k: entry[k] for k in ORDER if k in entry}
    assert entry["cohort_fingerprint"] == cohort_fingerprint(params)


def test_golden_full_validates_via_cli():
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(GOLDEN_FULL)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# Local runtime materialization. The canonical schema remains redacted; the
# explicit CLI mode validates and removes a local AWG key in memory first.
# ---------------------------------------------------------------------------
def _materialized_bundle(example):
    doc = copy.deepcopy(example)
    entry = doc["amneziawg"][0]
    del entry["private_key_placeholder"]
    entry["private_key"] = base64.b64encode(bytes(range(32))).decode("ascii")
    return doc


def _run_validator(path, *args):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args, str(path)],
        capture_output=True,
        text=True,
    )


def _write_runtime(path, doc):
    path.write_text(json.dumps(doc))
    path.chmod(0o600)


def test_materialized_runtime_key_is_rejected_without_explicit_mode(tmp_path, example):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(_materialized_bundle(example)))

    proc = _run_validator(path)

    assert proc.returncode == 1


@pytest.mark.parametrize("full_bundle", [False, True])
def test_runtime_mode_accepts_valid_materialized_key(tmp_path, example, full_bundle):
    ripdpi = _materialized_bundle(example)
    doc = {"ripdpi": ripdpi, "outbounds": []} if full_bundle else ripdpi
    if full_bundle:
        doc['outbounds'] = [{'type': 'hysteria2', 'tag': tag} for tag in ripdpi['hysteria_extras']]
    path = tmp_path / "runtime.json"
    _write_runtime(path, doc)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 0, proc.stderr


def test_runtime_mode_rejects_key_and_placeholder_without_printing_key(tmp_path, example):
    doc = _materialized_bundle(example)
    key = doc["amneziawg"][0]["private_key"]
    doc["amneziawg"][0]["private_key_placeholder"] = True
    path = tmp_path / "runtime.json"
    _write_runtime(path, doc)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 1
    assert "requires private_key" in proc.stderr
    assert key not in proc.stdout + proc.stderr


def test_runtime_mode_rejects_missing_key_state(tmp_path, example):
    doc = copy.deepcopy(example)
    del doc["amneziawg"][0]["private_key_placeholder"]
    path = tmp_path / "runtime.json"
    _write_runtime(path, doc)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 1
    assert "requires private_key" in proc.stderr


def test_runtime_mode_rejects_redacted_placeholder_only_bundle(tmp_path, example):
    path = tmp_path / "redacted.json"
    _write_runtime(path, example)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 1
    assert "requires private_key" in proc.stderr


def test_runtime_mode_rejects_mixed_materialization_state(tmp_path, example):
    doc = _materialized_bundle(example)
    redacted_entry = copy.deepcopy(example["amneziawg"][0])
    redacted_entry["tag"] = "second-awg"
    doc["amneziawg"].append(redacted_entry)
    path = tmp_path / "mixed.json"
    _write_runtime(path, doc)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 1
    assert "amneziawg[1]" in proc.stderr


@pytest.mark.parametrize(
    "private_key",
    [
        None,
        "not-base64",
        base64.b64encode(bytes(31)).decode("ascii"),
        base64.b64encode(bytes(range(32))).decode("ascii")[:-2] + "9=",
    ],
)
def test_runtime_mode_rejects_malformed_private_key(tmp_path, example, private_key):
    doc = _materialized_bundle(example)
    doc["amneziawg"][0]["private_key"] = private_key
    path = tmp_path / "runtime.json"
    _write_runtime(path, doc)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 1
    assert "private_key" in proc.stderr
    if isinstance(private_key, str):
        assert private_key not in proc.stdout + proc.stderr


def test_runtime_mode_still_rejects_fingerprint_mismatch(tmp_path, example):
    doc = _materialized_bundle(example)
    doc["amneziawg"][0]["cohort_fingerprint"] = "sha256:" + "0" * 64
    path = tmp_path / "runtime.json"
    _write_runtime(path, doc)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 1
    assert "cohort_fingerprint" in proc.stderr


def test_runtime_mode_rejects_group_readable_file(tmp_path, example):
    path = tmp_path / "runtime.json"
    _write_runtime(path, _materialized_bundle(example))
    path.chmod(0o640)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 2
    assert "mode 0600" in proc.stderr


def test_runtime_mode_rejects_symlinked_file(tmp_path, example):
    private = tmp_path / "private.json"
    _write_runtime(private, _materialized_bundle(example))
    path = tmp_path / "runtime.json"
    path.symlink_to(private)

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 2
    assert "symlink" in proc.stderr


def test_runtime_mode_rejects_symlinked_parent(tmp_path, example):
    private_dir = tmp_path / "private"
    private_dir.mkdir(mode=0o700)
    private = private_dir / "runtime.json"
    _write_runtime(private, _materialized_bundle(example))
    linked_dir = tmp_path / "linked"
    linked_dir.symlink_to(private_dir, target_is_directory=True)

    proc = _run_validator(linked_dir / "runtime.json", "--runtime-materialized")

    assert proc.returncode == 2
    assert "symlink" in proc.stderr


def test_runtime_mode_rejects_writable_parent(tmp_path, example):
    writable_dir = tmp_path / "writable"
    writable_dir.mkdir()
    writable_dir.chmod(0o777)
    path = writable_dir / "runtime.json"
    _write_runtime(path, _materialized_bundle(example))

    proc = _run_validator(path, "--runtime-materialized")

    assert proc.returncode == 2
    assert "ancestry is not owner-controlled" in proc.stderr


# ---------------------------------------------------------------------------
# Negative fixtures — the contract's strict half. Every fixture's ripdpi object
# MUST be rejected by the schema (the client repo vendors the same files and
# asserts the lenient parser handles each without throwing).
# ---------------------------------------------------------------------------
def _negative_files():
    return sorted(NEGATIVE_DIR.glob("neg-*.json"))


def test_negative_fixtures_present():
    assert _negative_files(), "no negative fixtures found"


@pytest.mark.parametrize("path", _negative_files(), ids=lambda p: p.name)
def test_negative_fixture_is_rejected(path):
    # Assert via the real validator so BOTH rejection classes are covered:
    # schema violations AND a format-valid-but-wrong cohort_fingerprint (which
    # the schema alone accepts — only _fingerprint_errors catches it).
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1, (
        f"{path.name} should be rejected by validate-bundle.py "
        f"(schema or fingerprint) but it passed:\n{proc.stdout}{proc.stderr}"
    )


@pytest.mark.parametrize("field,value", [
    ("public_key", "not-a-key"), ("preshared_key", "not-a-key"),
    ("public_key", base64.b64encode(bytes(31)).decode()),
    ("public_key", base64.b64encode(bytes(32)).decode()[:-2] + "B="),
    ("endpoint", "host.test:0"), ("endpoint", "host.test:65536"),
    ("endpoint", "bad host:443"), ("endpoint", "999.1.1.1:443"),
    ("endpoint", "-bad.test:443"), ("endpoint", "[not-ip]:443"),
    ("endpoint", "2001:db8::1:443"),
    ("allowed_ips", ["192.0.2.1/24"]), ("allowed_ips", ["192.0.2.1"]),
    ("allowed_ips", ["2001:db8::/129"]),
])
def test_shape_valid_peer_semantics_refuse_without_echo(tmp_path, example, field, value):
    doc = copy.deepcopy(example)
    doc["amneziawg"][0]["peer"][field] = value
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    proc = _run_validator(path)
    assert proc.returncode == 1
    if isinstance(value, str):
        assert value not in proc.stdout + proc.stderr


@pytest.mark.parametrize("field,value", [
    ("jmin", 51), ("h2", 1), ("dns", ["999.1.1.1"]),
])
def test_awg_relational_semantics_refuse(tmp_path, example, field, value):
    doc = copy.deepcopy(example)
    doc["amneziawg"][0][field] = value
    entry = doc["amneziawg"][0]
    entry["cohort_fingerprint"] = cohort_fingerprint({key: entry[key] for key in ORDER if key in entry})
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    assert _run_validator(path).returncode == 1


@pytest.mark.parametrize("field,value", [
    ("ports", "50000:20000"), ("ports", "0:50000"), ("ports", "1:65536"),
    ("ports", "1:" + "9" * 5000), ("interval", "0s"),
    ("interval", "9" * 5000 + "s"), ("interval", "4s"),
    ("interval", "9223372037s"), ("interval", "2562048h"),
])
def test_hopping_semantics_refuse_without_traceback(tmp_path, example, field, value):
    doc = copy.deepcopy(example)
    next(iter(doc["hysteria_extras"].values()))["port_hopping"][field] = value
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    proc = _run_validator(path)
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert value not in proc.stderr


@pytest.mark.parametrize("expiry", ["2026-02-30", "2026-13-01", "2026-12-01T25:00:00Z", "2026-12-01T00:00:00+24:00"])
def test_shape_valid_invalid_calendar_expiry_refuses(tmp_path, example, expiry):
    doc = copy.deepcopy(example)
    doc["expires"] = expiry
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    proc = _run_validator(path)
    assert proc.returncode == 1
    assert expiry not in proc.stderr


@pytest.mark.parametrize("endpoint", ["peer.test:1", "203.0.113.5:65535", "[2001:db8::1]:51820"])
def test_valid_endpoint_boundaries_pass(tmp_path, example, endpoint):
    doc = copy.deepcopy(example)
    doc["amneziawg"][0]["peer"]["endpoint"] = endpoint
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    proc = _run_validator(path)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("doc", [[], None, "synthetic-secret-marker", {"schema_version": "synthetic-secret-marker"}])
def test_schema_diagnostics_never_echo_values_or_crash(tmp_path, doc):
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    proc = _run_validator(path)
    assert proc.returncode == 1
    assert "synthetic-secret-marker" not in proc.stderr
    assert "Traceback" not in proc.stderr


@pytest.mark.parametrize('doc', [None, [], 'synthetic-private-marker'])
def test_runtime_mode_nonobject_refuses_without_traceback(tmp_path, doc):
    path = tmp_path / 'runtime.json'
    _write_runtime(path, doc)
    proc = _run_validator(path, '--runtime-materialized')
    assert proc.returncode == 1
    assert 'Traceback' not in proc.stderr and 'synthetic-private-marker' not in proc.stderr


@pytest.mark.parametrize("interval", ["5s", "1m", "25h", "9223372036s", "2562047h"])
def test_hopping_interval_bounds_are_admitted(tmp_path, example, interval):
    doc = copy.deepcopy(example)
    next(iter(doc["hysteria_extras"].values()))["port_hopping"]["interval"] = interval
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    assert _run_validator(path).returncode == 0


@pytest.mark.parametrize("fields,accepted", [
    ({"server_ports": ["20000:21000"], "hop_interval": "45s"}, True),
    ({"server_ports": ["20500:21000", "20000:20500"], "hop_interval": "45000ms"}, True),
    ({"server_ports": "20000:21000", "hop_interval": "0.75m", "hop_interval_max": "45s"}, True),
    ({"server_ports": ["20000:21000"], "hop_interval": "44s1000ms"}, True),
    ({}, True),
    ({"server_ports": ["20000:21001"], "hop_interval": "45s"}, False),
    ({"server_ports": ["20000:21000"], "hop_interval": "46s"}, False),
    ({"server_ports": ["20000:21000"], "hop_interval": "45s", "hop_interval_max": "46s"}, False),
    ({"server_ports": ["20000:21000"], "hop_interval": "45s", "hop_interval_max": "44s"}, False),
    ({"server_ports": ["20000:21000"], "hop_interval": "45000000us"}, True),
    ({"server_ports": ["20000:21000"], "hop_interval": "45.0000001s"}, False),
    ({"server_ports": ["20000:21000"], "hop_interval": "44.9999999999s0.0000000001s"}, False),
    ({"server_ports": ["20000:21000"], "hop_interval": None}, False),
    ({"server_ports": ["20000:21000"], "hop_interval": "9" * 129 + "s"}, False),
    ({"server_ports": None}, False),
    ({"server_ports": []}, False),
    ({"server_ports": [20000]}, False),
    ({"server_ports": ["21000:20000"]}, False),
    ({"server_ports": ["20000:65536"]}, False),
    ({"hop_interval": "45s"}, False),
])
def test_full_bundle_hopping_policies_agree_by_semantics(tmp_path, fields, accepted):
    doc = json.loads((REPO_ROOT / "contract/ripdpi-bundle.hysteria-port-hopping.json").read_text())
    outbound = next(value for value in doc["outbounds"] if value["type"] == "hysteria2")
    for name in ("server_ports", "hop_interval"):
        outbound.pop(name)
    outbound.update(fields)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    result = _run_validator(path)
    assert result.returncode == (0 if accepted else 1), result.stderr
    assert "Traceback" not in result.stderr
    assert "synthetic-obfs-first" not in result.stderr


@pytest.mark.parametrize("mode", ["standard-only", "default-interval", "equivalent-units", "missing-tag", "duplicate-tag", "wrong-type"])
def test_full_bundle_hopping_matches_one_outbound(tmp_path, mode):
    doc = json.loads((REPO_ROOT / "contract/ripdpi-bundle.hysteria-port-hopping.json").read_text())
    outbound = next(value for value in doc["outbounds"] if value["type"] == "hysteria2")
    extra = doc["ripdpi"]["hysteria_extras"][outbound["tag"]]
    if mode == "standard-only":
        extra.pop("port_hopping")
    elif mode == "default-interval":
        outbound.pop("hop_interval")
        extra["port_hopping"]["interval"] = "30s"
    elif mode == "equivalent-units":
        outbound["hop_interval"] = "60s"
        extra["port_hopping"]["interval"] = "1m"
    elif mode == "missing-tag":
        outbound["tag"] = "different"
    elif mode == "duplicate-tag":
        doc["outbounds"].append(copy.deepcopy(outbound))
    else:
        outbound["type"] = "socks"
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(doc))
    result = _run_validator(path)
    assert result.returncode == (0 if mode in {"standard-only", "default-interval", "equivalent-units"} else 1)
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# Client field report v1. Every report-*.json negative fixture is rejected for
# its named reason, and diagnostics never echo the rejected value.
# ---------------------------------------------------------------------------
def _run_report_validator(path):
    return subprocess.run([sys.executable, str(REPORT_VALIDATOR), str(path)], capture_output=True, text=True)


REPORT_NEGATIVE_REASONS = {
    "report-extra-root-property.json": "additionalProperties constraint failed at /\n",
    "report-extra-window-property.json": "additionalProperties constraint failed at /window\n",
    "report-extra-client-property.json": "additionalProperties constraint failed at /client\n",
    "report-extra-network-property.json": "additionalProperties constraint failed at /network\n",
    "report-extra-bucket-property.json": "additionalProperties constraint failed at /buckets/0\n",
    "report-failure-without-stage.json": "required constraint failed at /buckets/1\n",
    "report-success-with-stage.json": "not constraint failed at /buckets/0\n",
    "report-unknown-failure-stage.json": "enum constraint failed at /buckets/1/failure_stage\n",
    "report-histogram-extra-bound.json": "maxItems constraint failed at /buckets/0/latency_ms_histogram\n",
    "report-histogram-sum-mismatch.json": "buckets[0].latency_ms_histogram: counts must sum to attempts",
    "report-server-ref-ipv4.json": "pattern constraint failed at /buckets/0/server_ref\n",
    "report-server-ref-ipv6.json": "pattern constraint failed at /buckets/0/server_ref\n",
    "report-server-ref-hostname.json": "pattern constraint failed at /buckets/0/server_ref\n",
    "report-start-not-hour.json": "pattern constraint failed at /window/start_utc\n",
    "report-start-seconds.json": "pattern constraint failed at /window/start_utc\n",
    "report-attempts-below-5.json": "minimum constraint failed at /buckets/2/attempts\n",
    "report-app-version-patch.json": "pattern constraint failed at /client/app_version\n",
    "report-schema-version-2.json": "const constraint failed at /schema_version\n",
    # Python's $ also matches before a trailing newline; the contract keeps the ECMA-262 end-of-input anchor.
    "report-country-trailing-newline.json": "pattern constraint failed at /network/country\n",
    # Draft 2020-12 counts 64500.0 as an integer; the contract admits only a JSON integer.
    "report-asn-float.json": "type constraint failed at /network/asn\n",
    # network.source names the one identity a report carries (sim operator, server hint or none).
    "report-missing-source.json": "required constraint failed at /network\n",
    "report-unknown-source.json": "enum constraint failed at /network/source\n",
    "report-sim-without-operator.json": "required constraint failed at /network\n",
    "report-sim-with-asn.json": "not constraint failed at /network\n",
    "report-sim-on-wifi.json": "const constraint failed at /network/network_type\n",
    "report-server-hint-without-asn.json": "required constraint failed at /network\n",
    "report-server-hint-with-operator.json": "not constraint failed at /network\n",
    "report-none-with-asn.json": "not constraint failed at /network\n",
    "report-none-with-operator.json": "not constraint failed at /network\n",
    "report-extra-operator-property.json": "additionalProperties constraint failed at /network/operator\n",
    "report-operator-mcc-two-digits.json": "pattern constraint failed at /network/operator/mcc\n",
    "report-operator-mnc-four-digits.json": "pattern constraint failed at /network/operator/mnc\n",
    "report-operator-mnc-trailing-newline.json": "pattern constraint failed at /network/operator/mnc\n",
    "report-operator-mcc-number.json": "type constraint failed at /network/operator/mcc\n",
}


def test_report_schema_version_pin():
    schema = json.loads(REPORT_SCHEMA.read_text())
    assert schema["x-contract-version"] == 1
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["x-latency-bounds-ms"] == [50, 100, 250, 500, 1000, 2500, 5000, "+Inf"]


@pytest.mark.parametrize("golden", [REPORT_GOLDEN, REPORT_GOLDEN_SIM], ids=["server-hint", "sim"])
def test_report_golden_validates_via_cli(golden):
    proc = _run_report_validator(golden)
    assert proc.returncode == 0, proc.stderr


def test_every_report_negative_fixture_has_a_reason():
    assert sorted(path.name for path in NEGATIVE_DIR.glob("report-*.json")) == sorted(REPORT_NEGATIVE_REASONS)


@pytest.mark.parametrize("name,reason", sorted(REPORT_NEGATIVE_REASONS.items()))
def test_report_negative_fixture_is_rejected_for_its_reason(name, reason):
    path = NEGATIVE_DIR / name
    doc = json.loads(path.read_text())
    proc = _run_report_validator(path)
    assert proc.returncode == 1
    assert reason in proc.stderr
    assert "violation(s)" in proc.stderr and proc.stderr.count("\n  ") == 1
    for bucket in doc["buckets"]:
        assert bucket["server_ref"] not in proc.stderr


@pytest.mark.parametrize("start", ["2026-02-30T10:00:00Z", "2026-13-01T10:00:00Z", "2026-11-19T24:00:00Z"])
def test_report_invalid_calendar_window_refuses(tmp_path, start):
    doc = json.loads(REPORT_GOLDEN.read_text())
    doc["window"]["start_utc"] = start
    path = tmp_path / "report.json"
    path.write_text(json.dumps(doc))
    assert _run_report_validator(path).returncode == 1


@pytest.mark.parametrize("hours,accepted", [(0, False), (1, True), (24, True), (25, False)])
def test_report_window_duration_bounds(tmp_path, hours, accepted):
    doc = json.loads(REPORT_GOLDEN.read_text())
    doc["window"]["duration_hours"] = hours
    path = tmp_path / "report.json"
    path.write_text(json.dumps(doc))
    assert _run_report_validator(path).returncode == (0 if accepted else 1)


@pytest.mark.parametrize("doc", [[], None, "synthetic-secret-marker", {"schema_version": "synthetic-secret-marker"}])
def test_report_diagnostics_never_echo_values_or_crash(tmp_path, doc):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(doc))
    proc = _run_report_validator(path)
    assert proc.returncode == 1
    assert "synthetic-secret-marker" not in proc.stderr
    assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------------------
# Client network hint v1: the subscription host's ASN answer for the request
# source address. The same strict checker as the field report applies.
# ---------------------------------------------------------------------------
HINT_NEGATIVE_REASONS = {
    "hint-extra-property.json": ("additionalProperties", []),
    "hint-observed-at-minutes.json": ("pattern", ["observed_at"]),
    "hint-asn-float.json": ("type", ["asn"]),
    "hint-country-trailing-newline.json": ("pattern", ["country"]),
    "hint-ttl-below-floor.json": ("minimum", ["ttl_seconds"]),
    "hint-schema-version-2.json": ("const", ["schema_version"]),
}


def _hint_errors(doc):
    spec = importlib.util.spec_from_file_location("validate_field_report_for_hint", REPORT_VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checker = module.validator(json.loads(HINT_SCHEMA.read_text()))
    return [(error.validator, list(error.absolute_path)) for error in checker.iter_errors(doc)]


def test_hint_schema_version_pin_and_golden():
    schema = json.loads(HINT_SCHEMA.read_text())
    assert schema["x-contract-version"] == 1
    assert schema["properties"]["schema_version"]["const"] == 1
    assert _hint_errors(json.loads(HINT_GOLDEN.read_text())) == []


def test_every_hint_negative_fixture_has_a_reason():
    assert sorted(path.name for path in NEGATIVE_DIR.glob("hint-*.json")) == sorted(HINT_NEGATIVE_REASONS)


@pytest.mark.parametrize("name,reason", sorted(HINT_NEGATIVE_REASONS.items()))
def test_hint_negative_fixture_is_rejected_for_its_reason(name, reason):
    assert _hint_errors(json.loads((NEGATIVE_DIR / name).read_text())) == [reason]
