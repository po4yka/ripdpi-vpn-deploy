"""Bounded offline device-migration evidence; never serialize delivery keys."""
from __future__ import annotations

import hashlib
import hmac
import json
import re

from device_migration_errors import MigrationRefused

UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
TAG = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
FIELDS = ("migration_id", "delivery_id", "payload_sha256", "state",
          "received_at_ms", "tested_at_ms", "tested_tag")
MAX_BYTES = 4096
CLOCK_SKEW_MS = 300_000
MAX_EVIDENCE_AGE_MS = 86_400_000


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MigrationRefused("duplicate-migration-field")
        result[key] = value
    return result


def metadata(value):
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "migration_id", "delivery_id", "target_tags", "receipt_key", "awg_previous_tags"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not all(matches(UUID, value[key]) for key in ("migration_id", "delivery_id"))
            or not matches(HEX, value["receipt_key"])
            or not isinstance(value["target_tags"], list) or not 1 <= len(value["target_tags"]) <= 128
            or not all(matches(TAG, tag) for tag in value["target_tags"])
            or len(set(value["target_tags"])) != len(value["target_tags"])
            or not isinstance(value["awg_previous_tags"], dict) or len(value["awg_previous_tags"]) > 128
            or any(key not in value["target_tags"] or not matches(TAG, previous)
                   for key, previous in value["awg_previous_tags"].items())
            or len(set(value["awg_previous_tags"].values())) != len(value["awg_previous_tags"])):
        raise MigrationRefused("invalid-migration-metadata")
    return value


def validate(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "mac", *FIELDS}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not all(matches(UUID, value[key]) for key in ("migration_id", "delivery_id"))
            or not all(matches(HEX, value[key]) for key in ("payload_sha256", "mac"))
            or value["state"] not in ("received", "path-tested")
            or type(value["received_at_ms"]) is not int or not 0 < value["received_at_ms"] <= 2**53 - 1
            or type(value["tested_at_ms"]) is not int or not 0 <= value["tested_at_ms"] <= 2**53 - 1
            or (value["state"] == "received" and (value["tested_at_ms"] != 0 or value["tested_tag"] != ""))
            or (value["state"] == "path-tested" and
                (value["tested_at_ms"] < value["received_at_ms"] or not matches(TAG, value["tested_tag"])))):
        raise MigrationRefused("invalid-migration-receipt")
    return value


def decode(content):
    if not isinstance(content, bytes) or len(content) > MAX_BYTES:
        raise MigrationRefused("invalid-migration-receipt")
    try:
        return validate(json.loads(content.decode("utf-8"), object_pairs_hook=unique_object))
    except (UnicodeError, RecursionError, TypeError, json.JSONDecodeError):
        raise MigrationRefused("invalid-migration-receipt") from None


def signing_bytes(receipt):
    validate(receipt)
    return ("ripdpi-device-migration-receipt-v1\n" +
            "\n".join(str(receipt[key]) for key in FIELDS) + "\n").encode("utf-8")


def verify(receipt, delivery, *, now_ms):
    """Return authenticated evidence, without claiming a trustworthy handset."""
    validate(receipt)
    proof = metadata(delivery["metadata"])
    if (receipt["migration_id"] != proof["migration_id"]
            or receipt["delivery_id"] != proof["delivery_id"]
            or not hmac.compare_digest(receipt["payload_sha256"], delivery["payload_sha256"])
            or receipt["received_at_ms"] < delivery["published_at_ms"] - CLOCK_SKEW_MS
            or receipt["received_at_ms"] > now_ms + CLOCK_SKEW_MS
            or receipt["tested_at_ms"] > now_ms + CLOCK_SKEW_MS
            or (receipt["state"] == "path-tested" and receipt["tested_tag"] not in proof["target_tags"])):
        raise MigrationRefused("migration-receipt-does-not-match-delivery")
    expected = hmac.new(bytes.fromhex(proof["receipt_key"]), signing_bytes(receipt), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, receipt["mac"]):
        raise MigrationRefused("migration-receipt-authentication-failed")
    return dict(receipt)


def path_is_current(receipt, *, now_ms):
    validate(receipt)
    return (receipt["state"] == "path-tested"
            and -CLOCK_SKEW_MS <= now_ms - receipt["tested_at_ms"] <= MAX_EVIDENCE_AGE_MS)
