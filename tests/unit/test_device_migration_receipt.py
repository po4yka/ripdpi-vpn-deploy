"""Cross-repository receipt vectors and hostile/stale delivery evidence."""
import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

import device_migration_receipt as receipts

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = json.loads((ROOT / "contract/device-migration.golden.json").read_text())
NOW = 1792674003000


def delivery():
    return {"metadata": copy.deepcopy(GOLDEN["metadata"]),
            "payload_sha256": hashlib.sha256(GOLDEN["payload_utf8"].encode()).hexdigest(),
            "published_at_ms": 1792673999000}


@pytest.mark.parametrize("vector", GOLDEN["vectors"], ids=lambda v: v["name"])
def test_shared_exact_bytes_mac_and_schema(vector):
    receipt = receipts.decode(json.dumps(vector["receipt"]).encode())
    assert receipts.signing_bytes(receipt).decode() == vector["signing_utf8"]
    assert receipts.verify(receipt, delivery(), now_ms=NOW) == receipt
    assert receipts.path_is_current(receipt, now_ms=NOW) == (receipt["state"] == "path-tested")
    jsonschema.validate(receipt, json.loads((ROOT / "contract/device-migration-receipt.schema.json").read_text()))
    assert receipt["payload_sha256"] != hashlib.sha256(json.dumps(json.loads(GOLDEN["payload_utf8"])).encode()).hexdigest()


def test_bundle_metadata_contract_matches_standalone_schema():
    schema = json.loads((ROOT / "contract/device-migration-metadata.schema.json").read_text())
    jsonschema.validate(GOLDEN["metadata"], schema)
    schema.pop("$schema")
    schema.pop("title")
    bundle = json.loads((ROOT / "contract/ripdpi-bundle.schema.json").read_text())
    assert bundle["properties"]["migration"] == schema


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2), ("received_at_ms", True),
    ("received_at_ms", 0), ("received_at_ms", 2**53), ("tested_at_ms", -1),
    ("tested_tag", "wrong\nfield"), ("state", "published"),
    ("migration_id", "not-a-uuid"), ("mac", "A" * 64),
])
def test_malformed_receipts_fail_categorically(field, value):
    receipt = dict(GOLDEN["vectors"][1]["receipt"], **{field: value})
    with pytest.raises(ValueError, match="invalid-migration-receipt"):
        receipts.decode(json.dumps(receipt).encode())


@pytest.mark.parametrize("field", receipts.FIELDS)
def test_each_bound_field_cannot_be_tampered(field):
    receipt = dict(GOLDEN["vectors"][1]["receipt"])
    if field.endswith("_ms"):
        receipt[field] += 1
    elif field in ("migration_id", "delivery_id"):
        receipt[field] = "33333333-3333-4333-8333-333333333333"
    elif field == "payload_sha256":
        receipt[field] = "0" * 64
    elif field == "tested_tag":
        receipt[field] = GOLDEN["metadata"]["target_tags"][1]
    else:
        receipt.update(state="received", tested_at_ms=0, tested_tag="")
    with pytest.raises(ValueError):
        receipts.verify(receipt, delivery(), now_ms=NOW)


def test_duplicate_unknown_oversized_and_wrong_encoding_refuse():
    original = json.dumps(GOLDEN["vectors"][0]["receipt"]).encode()
    for content in (b'{"schema_version":1,' + original[1:], original[:-1] + b',"secret":"x"}',
                    b" " * (receipts.MAX_BYTES + 1), b"\xff", b"null", b"[]"):
        with pytest.raises(ValueError):
            receipts.decode(content)


def test_received_does_not_authorize_retirement_and_old_test_expires():
    assert not receipts.path_is_current(GOLDEN["vectors"][0]["receipt"], now_ms=NOW)
    assert not receipts.path_is_current(GOLDEN["vectors"][1]["receipt"], now_ms=NOW + 86_400_000)


def test_replay_for_other_payload_key_generation_or_before_publication_refuses():
    receipt = GOLDEN["vectors"][1]["receipt"]
    for field, value in (("payload_sha256", "0" * 64), ("published_at_ms", NOW + 300_000)):
        changed = delivery()
        changed[field] = value
        with pytest.raises(ValueError):
            receipts.verify(receipt, changed, now_ms=NOW)
    changed = delivery()
    changed["metadata"]["receipt_key"] = "0" * 64
    with pytest.raises(ValueError, match="authentication-failed"):
        receipts.verify(receipt, changed, now_ms=NOW)
    with pytest.raises(ValueError):
        receipts.verify(receipt, delivery(), now_ms=NOW - 400_000)


@pytest.mark.parametrize("tags", [[], ["a", "a"], ["x\n"], ["a"] * 129, [True]])
def test_target_set_is_bounded_unique_and_unambiguous(tags):
    with pytest.raises(ValueError, match="invalid-migration-metadata"):
        receipts.metadata(dict(GOLDEN["metadata"], target_tags=tags))
