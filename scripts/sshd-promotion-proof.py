#!/usr/bin/env python3
"""Fail-closed exact-node VPN promotion proof using the fixed evaluator."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile

import yaml


EVALUATOR = Path(__file__).with_name("protocol-liveness.py")
PROFILES = {"p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"}
TARGET_FIELDS = {"inventory_alias", "public_service_address_sha256", "deployable_digest", "applied_at",
                 "required_profiles", "source_revision", "runner_sha256", "public_profile_digest"}
MAX_CONFIG = 65536
MAX_OUTPUT = 1024 * 1024
EVALUATOR_TIMEOUT = 600
PROOF_MAX_STALE_SECONDS = 300
EXECUTOR_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


class ProofError(Exception):
    """Categorical refusal that never includes private input or child output."""


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-key")
        value[key] = item
    return value


def private_bytes(path: Path) -> bytes:
    if not path.is_absolute():
        raise ProofError("configuration-refused")
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_size > MAX_CONFIG):
            raise ProofError("configuration-refused")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            current = os.fstat(fd)
            if ((before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
                    or not stat.S_ISREG(current.st_mode) or current.st_uid != os.geteuid()
                    or current.st_nlink != 1 or stat.S_IMODE(current.st_mode) != 0o600):
                raise ProofError("configuration-refused")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                raw = handle.read(MAX_CONFIG + 1)
            if len(raw) > MAX_CONFIG:
                raise ProofError("configuration-refused")
            return raw
        finally:
            os.close(fd)
    except ProofError:
        raise
    except OSError:
        raise ProofError("configuration-refused") from None


def target_identity(value: object) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != TARGET_FIELDS
        or type(value.get("applied_at")) is not int
        or value["applied_at"] < 1
        or not isinstance(value.get("inventory_alias"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value["inventory_alias"]) is None
        or not isinstance(value.get("required_profiles"), list)
        or value["required_profiles"] != sorted(value["required_profiles"])
        or set(value["required_profiles"]) - PROFILES
        or len(value["required_profiles"]) != len(set(value["required_profiles"]))
        or not value["required_profiles"]
        or any(not isinstance(value.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None
               for key in ("public_service_address_sha256", "deployable_digest", "runner_sha256", "public_profile_digest"))
        or not isinstance(value.get("source_revision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", value["source_revision"]) is None
    ):
        raise ProofError("configuration-refused")
    return value


def validate_liveness_config(document: object) -> dict:
    previous_bytecode_setting = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("promotion_liveness_evaluator", EVALUATOR)
        if spec is None or spec.loader is None:
            raise ImportError
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.validate_config(document)
    except Exception:
        raise ProofError("configuration-refused") from None
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting


def load_config(path: Path) -> tuple[dict, bytes]:
    try:
        config = json.loads(private_bytes(path), object_pairs_hook=unique_object)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ProofError("configuration-refused") from None
    if not isinstance(config, dict) or set(config) != {
        "schema_version", "liveness_config", "expected_sentinels", "target_identity"
    } or config.get("schema_version") != 1:
        raise ProofError("configuration-refused")
    expected = config["expected_sentinels"]
    if (not isinstance(expected, list) or not expected or expected != sorted(expected)
            or len(expected) != len(set(expected))
            or any(not isinstance(item, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", item) is None for item in expected)):
        raise ProofError("configuration-refused")
    liveness = config.get("liveness_config")
    if not isinstance(liveness, str):
        raise ProofError("configuration-refused")
    target_identity(config.get("target_identity"))
    liveness_bytes = private_bytes(Path(liveness))
    try:
        liveness_document = yaml.safe_load(liveness_bytes)
    except (yaml.YAMLError, UnicodeError):
        raise ProofError("configuration-refused") from None
    liveness_document = validate_liveness_config(liveness_document)
    stale_after = liveness_document.get("stale_after_seconds", 120)
    expected_target = config["target_identity"]
    public_target = {key: expected_target[key] for key in (
        "inventory_alias", "public_service_address_sha256", "deployable_digest", "applied_at")}
    policies = {policy["id"]: policy for policy in liveness_document["policies"]}
    sentinels = liveness_document["sentinels"]
    if (
        sorted(sentinel["id"] for sentinel in sentinels) != expected
        or any(sentinel["target"] != public_target for sentinel in sentinels)
        or any(sorted(policies[sentinel["policy"]]["required_profiles"]) != expected_target["required_profiles"]
               for sentinel in sentinels)
    ):
        raise ProofError("configuration-refused")
    config["_stale_after_seconds"] = min(stale_after, PROOF_MAX_STALE_SECONDS)
    return config, liveness_bytes


def evaluate(liveness: bytes) -> dict:
    with tempfile.TemporaryDirectory(prefix="vpn-promotion-proof-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        config = root / "liveness.yaml"
        fd = os.open(config, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(liveness)
            handle.flush()
            os.fsync(handle.fileno())
        environment = {"PATH": EXECUTOR_PATH, "LANG": "C", "LC_ALL": "C"}
        if "HOME" in os.environ:
            environment["HOME"] = os.environ["HOME"]
        process = subprocess.Popen(
            [sys.executable, str(EVALUATOR), "--config", str(config)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=EVALUATOR_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise ProofError("proof-refused") from None
        if process.returncode != 0 or len(output) > MAX_OUTPUT:
            raise ProofError("proof-refused")
        try:
            value = json.loads(output)
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ProofError("proof-refused") from None
        if not isinstance(value, dict):
            raise ProofError("proof-refused")
        return value


def validate_evaluation(payload: object, config: dict) -> dict:
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 2
        or payload.get("decision") != "healthy"
        or payload.get("candidate_policies") != []
        or payload.get("monitoring_errors") != []
        or type(payload.get("evaluated_at")) is not int
        or not isinstance(payload.get("evidence"), list)
    ):
        raise ProofError("proof-refused")
    expected_target = config["target_identity"]
    required = expected_target["required_profiles"]
    evidence = payload["evidence"]
    sentinels = [item.get("sentinel") for item in evidence if isinstance(item, dict)]
    if len(sentinels) != len(evidence) or sorted(sentinels) != config["expected_sentinels"]:
        raise ProofError("proof-refused")
    observed: list[int] = []
    for item in evidence:
        observations = item.get("profile_observations")
        provenance = item.get("provenance")
        timestamp = item.get("observed_at")
        if (
            item.get("target_identity") != expected_target
            or item.get("control") != "ok"
            or not isinstance(item.get("profiles"), dict)
            or set(item["profiles"]) != set(required)
            or any(item["profiles"][profile] != "ok" for profile in required)
            or not isinstance(observations, dict)
            or set(observations) != set(required)
            or not isinstance(provenance, dict)
            or provenance.get("controller_revision") != expected_target["source_revision"]
            or provenance.get("runner_sha256") != expected_target["runner_sha256"]
            or provenance.get("public_profile_digest") != expected_target["public_profile_digest"]
            or type(timestamp) is not int
            or not expected_target["applied_at"] <= timestamp <= payload["evaluated_at"]
            or payload["evaluated_at"] - timestamp > config["_stale_after_seconds"]
        ):
            raise ProofError("proof-refused")
        for profile in required:
            proof = observations[profile]
            if (not isinstance(proof, dict) or proof.get("dns_through_tunnel") is not True
                    or proof.get("authenticated_handshake") is not True
                    or (profile == "p2-amneziawg" and proof.get("fresh_handshake") is not True)):
                raise ProofError("proof-refused")
        observed.append(timestamp)
    public_target = {key: expected_target[key] for key in (
        "inventory_alias", "public_service_address_sha256", "deployable_digest")}
    return {"schema_version": 1, "status": "passed", "target_identity": public_target,
            "observed_at": min(observed)}


def prove(path: Path) -> dict:
    config, liveness = load_config(path)
    try:
        payload = evaluate(liveness)
    except ProofError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise ProofError("proof-refused") from None
    return validate_evaluation(payload, config)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.validate_config:
            load_config(args.config)
            return 0
        receipt = prove(args.config)
    except ProofError as exc:
        print(f"sshd-promotion-proof: {exc}", file=sys.stderr)
        return 2 if str(exc) == "configuration-refused" else 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
