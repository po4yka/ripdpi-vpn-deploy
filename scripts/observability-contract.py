#!/usr/bin/env python3
"""Validate the versioned observability contract and render bounded metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contract"
MAX_INPUT_BYTES = 1024 * 1024
SAFE_VALUE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
IPV4 = re.compile(r"(?:^|[^0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?:$|[^0-9])")
DOMAIN = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$", re.IGNORECASE)
UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
TOKEN = re.compile(
    r"(?:token|secret|password|private|credential|^gh[opusr]_)", re.IGNORECASE
)
LONG_OPAQUE = re.compile(r"^(?:[0-9a-f]{24,}|[A-Za-z0-9_+=/-]{32,})$")
SECRET_IDENTIFIER = re.compile(
    r"(?:^|_)(?:token|secret|password|credential|private_key|key)(?:_|$)",
    re.IGNORECASE,
)
FORBIDDEN_LABEL = re.compile(
    r"(?:^|_)(?:ip|address|endpoint|domain|sni|uuid|short_id|password|token|chat_id|client|user|username|destination|path|args|command|log)(?:_|$)",
    re.IGNORECASE,
)
SCHEMAS = {
    "manifest": "observability-metric-manifest.schema.json",
    "inventory": "observability-expected-inventory.schema.json",
    "evidence": "observability-evidence.schema.json",
}


class ContractError(Exception):
    """A redacted observability contract failure."""


def validate_document(schema: dict[str, Any], document: Any) -> None:
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise ContractError("jsonschema is unavailable") from exc
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(document))
    if errors:
        raise ContractError("document does not match its schema")


def _load_json(path: Path) -> Any:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_INPUT_BYTES:
            raise ContractError("invalid input")
        raw = b""
        while len(raw) <= MAX_INPUT_BYTES:
            chunk = os.read(descriptor, min(65536, MAX_INPUT_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > MAX_INPUT_BYTES:
            raise ContractError("invalid input")
        return json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError("invalid input") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _schema(name: str) -> dict[str, Any]:
    value = _load_json(CONTRACT_ROOT / SCHEMAS[name])
    if not isinstance(value, dict):
        raise ContractError("invalid schema")
    return value


def _forbidden_value(value: str) -> bool:
    return (
        not SAFE_VALUE.fullmatch(value)
        or IPV4.search(value) is not None
        or ":" in value
        or "/" in value
        or DOMAIN.fullmatch(value) is not None
        or UUID.fullmatch(value) is not None
        or TOKEN.search(value) is not None
        or LONG_OPAQUE.fullmatch(value) is not None
    )


def _unique(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        identity = item[key]
        if identity in result:
            raise ContractError("duplicate identity")
        result[identity] = item
    return result


def _validate_semantics(
    manifest: dict[str, Any], inventory: dict[str, Any], evidence: dict[str, Any]
) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]
]:
    families = _unique(manifest["families"], "name")
    targets = _unique(inventory["targets"], "target")
    observations = _unique(evidence["targets"], "target")
    if set(observations) - set(targets):
        raise ContractError("unexpected evidence target")
    for target in targets.values():
        if _forbidden_value(target["target"]) or _forbidden_value(target["role"]):
            raise ContractError("unsafe inventory identity")
        if any(name not in families for name in target["required_families"]):
            raise ContractError("unknown required family")
    for family in families.values():
        if SECRET_IDENTIFIER.search(family["name"]):
            raise ContractError("unsafe metric family")
        if any(FORBIDDEN_LABEL.search(label) for label in family["labels"]):
            raise ContractError("unsafe metric label")
        if family["stale_after_seconds"] < family["cadence_seconds"]:
            raise ContractError("staleness precedes cadence")
    return families, targets, observations


def _labels(labels: dict[str, str]) -> str:
    escaped = []
    for name, value in sorted(labels.items()):
        safe = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        escaped.append(f'{name}="{safe}"')
    return "{" + ",".join(escaped) + "}"


def _number(value: int | float) -> str:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ContractError("invalid metric number")
    return format(value, ".17g")


def _evaluate_target(
    target: dict[str, Any],
    observation: dict[str, Any] | None,
    families: dict[str, dict[str, Any]],
    now: int,
    max_future: int,
) -> tuple[str, list[tuple[str, dict[str, str], int | float]]]:
    lifecycle = target["lifecycle"]
    if lifecycle != "enabled":
        return lifecycle, []
    if observation is None:
        return ("absent" if target["ever_seen"] else "never-seen"), []
    if observation["status"] == "malformed":
        return "malformed", []
    observed_at = observation["observed_at"]
    if observed_at > now + max_future:
        return "future", []

    valid_samples: list[tuple[str, dict[str, str], int | float]] = []
    seen_series: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    family_series: dict[str, set[tuple[tuple[str, str], ...]]] = {}
    seen_families: set[str] = set()
    for sample in observation["samples"]:
        family = families.get(sample["family"])
        if family is None:
            return "malformed", []
        labels = sample["labels"]
        if set(labels) != set(family["labels"]):
            return "malformed", []
        if any(_forbidden_value(value) for value in labels.values()):
            return "malformed", []
        label_key = tuple(sorted(labels.items()))
        series_key = (sample["family"], label_key)
        if series_key in seen_series:
            return "malformed", []
        seen_series.add(series_key)
        current = family_series.setdefault(sample["family"], set())
        current.add(label_key)
        if len(current) > family["max_series"]:
            return "malformed", []
        try:
            _number(sample["value"])
        except ContractError:
            return "malformed", []
        seen_families.add(sample["family"])
        valid_samples.append((sample["family"], labels, sample["value"]))

    required = set(target["required_families"])
    if not required.issubset(seen_families):
        return "malformed", []
    stale_after = min(families[name]["stale_after_seconds"] for name in required)
    if now - observed_at > stale_after:
        return "stale", []
    return "fresh", valid_samples


def _render(
    manifest: dict[str, Any],
    inventory: dict[str, Any],
    evidence: dict[str, Any],
    now: int,
) -> tuple[bytes, dict[str, int], int]:
    families, targets, observations = _validate_semantics(manifest, inventory, evidence)
    results: list[
        tuple[dict[str, Any], str, list[tuple[str, dict[str, str], int | float]]]
    ] = []
    global_series: dict[str, set[tuple[tuple[str, str], ...]]] = {}
    malformed_families: set[str] = set()
    for target_name in sorted(targets):
        target = targets[target_name]
        state, samples = _evaluate_target(
            target,
            observations.get(target_name),
            families,
            now,
            inventory["max_future_seconds"],
        )
        for family_name, labels, _value in samples:
            keys = global_series.setdefault(family_name, set())
            label_key = tuple(sorted(labels.items()))
            if label_key in keys:
                malformed_families.add(family_name)
            keys.add(label_key)
            if len(keys) > families[family_name]["max_series"]:
                malformed_families.add(family_name)
        results.append((target, state, samples))
    if malformed_families:
        results = [
            (
                (target, "malformed", [])
                if any(
                    name in malformed_families
                    for name, _labels_value, _value in samples
                )
                else (target, state, samples)
            )
            for target, state, samples in results
        ]

    lines = [
        "# TYPE vpn_observability_expected_target gauge",
        "# TYPE vpn_observability_evidence_state gauge",
    ]
    states: dict[str, int] = {}
    emitted = 0
    producer_samples: list[tuple[str, dict[str, str], int | float]] = []
    for target, state, samples in results:
        identity = {"role": target["role"], "target": target["target"]}
        lines.append(f"vpn_observability_expected_target{_labels(identity)} 1")
        state_labels = {**identity, "state": state}
        lines.append(f"vpn_observability_evidence_state{_labels(state_labels)} 1")
        emitted += 2
        states[state] = states.get(state, 0) + 1
        if state != "fresh":
            continue
        producer_samples.extend(samples)
    previous_family: str | None = None
    for family_name, labels, value in sorted(
        producer_samples, key=lambda item: (item[0], tuple(sorted(item[1].items())))
    ):
        if family_name != previous_family:
            lines.append(f"# TYPE {family_name} {families[family_name]['type']}")
            previous_family = family_name
        lines.append(f"{family_name}{_labels(labels)} {_number(value)}")
        emitted += 1
    return ("\n".join(lines) + "\n").encode("utf-8"), states, emitted


def _atomic_write(path: Path, payload: bytes) -> None:
    if not path.parent.is_dir():
        raise ContractError("output parent is unavailable")
    descriptor = -1
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise ContractError("publication failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="observability-contract.py")
    subcommands = parser.add_subparsers(dest="command", required=True)
    render = subcommands.add_parser("render")
    render.add_argument("--manifest", type=Path, required=True)
    render.add_argument("--inventory", type=Path, required=True)
    render.add_argument("--evidence", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--now", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        manifest = _load_json(args.manifest)
        inventory = _load_json(args.inventory)
        evidence = _load_json(args.evidence)
        validate_document(_schema("manifest"), manifest)
        validate_document(_schema("inventory"), inventory)
        validate_document(_schema("evidence"), evidence)
        now = int(time.time()) if args.now is None else args.now
        if now < 0:
            raise ContractError("invalid clock")
        payload, states, samples = _render(manifest, inventory, evidence, now)
        _atomic_write(args.output, payload)
        summary = {
            "digest": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            "samples": samples,
            "states": dict(sorted(states.items())),
            "targets": len(inventory["targets"]),
        }
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
        return 0
    except (ContractError, OSError, TypeError, ValueError, KeyError):
        print("observability-contract: validation failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
