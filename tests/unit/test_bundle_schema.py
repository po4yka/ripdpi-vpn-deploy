"""Lock the contract for contract/ripdpi-bundle.schema.json.

This is the server half of a paired, cross-repo contract test. The RIPDPI
Android client runs an equivalent test against a byte-identical vendored copy
of the same schema and the same cohort-fingerprint golden. Together they make
the bundle contract machine-checkable on both sides instead of prose that can
drift silently between the two repos.

Threats caught:
  1. emit-bundle.sh gains/loses a field without the schema being updated.
  2. The cohort-fingerprint algorithm drifts between the emit side (bash +
     ripdpi_cohort_fingerprint.py) and the parse side (Kotlin): the paired
     golden pins the exact hash both must produce.
  3. The schema's contract version drifts from the version the client supports.
"""
from __future__ import annotations

import copy
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


def _ripdpi(doc):
    """Return the ripdpi object from a full bundle, or the doc if it is one."""
    return doc["ripdpi"] if isinstance(doc, dict) and "ripdpi" in doc else doc

# Cross-repo drift pin. The client's SingBoxSubscriptionParser.RipdpiSchemaVersion
# and its vendored schema's x-contract-version must equal this. Bumping it is a
# coordinated, breaking change across both repos.
CONTRACT_VERSION = 1


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


def test_fingerprint_is_order_stable():
    a = {"jc": 4, "jmin": 10, "jmax": 50, "s1": 0, "s2": 0,
         "h1": 1, "h2": 2, "h3": 3, "h4": 4}
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
# Forward-compat: additive top-level fields allowed; typos in structured
# sub-objects rejected.
# ---------------------------------------------------------------------------
def test_unknown_top_level_field_allowed(schema, example):
    doc = copy.deepcopy(example)
    doc["some_future_field"] = {"anything": 1}
    assert list(_validator(schema).iter_errors(doc)) == []


def test_typo_in_awg_entry_rejected(schema, example):
    doc = copy.deepcopy(example)
    doc["amneziawg"][0]["jcc"] = 4  # typo for jc
    assert list(_validator(schema).iter_errors(doc))


# ---------------------------------------------------------------------------
# Field-format class
# ---------------------------------------------------------------------------
def test_schema_version_2_rejected(schema, example):
    doc = copy.deepcopy(example)
    doc["schema_version"] = 2
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
