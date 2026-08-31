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
SHORT_HEX = re.compile(r"^[0-9a-f]{16,23}$", re.IGNORECASE)
COMPACT_OPAQUE = re.compile(r"^[a-z0-9]{16,}$")
SECRET_IDENTIFIER = re.compile(
    r"(?:^|_)(?:token|secret|password|credential|private_key|key)(?:_|$)",
    re.IGNORECASE,
)
FORBIDDEN_LABEL = re.compile(
    r"(?:^|_)(?:ip|address|endpoint|domain|sni|uuid|short_id|password|token|chat_id|client|user|username|destination|path|args|command|log)(?:_|$)",
    re.IGNORECASE,
)
ALLOWED_LABELS = frozenset({"node", "role", "profile", "policy", "severity", "vantage"})
EVIDENCE_STATES = frozenset(
    {
        "fresh",
        "stale",
        "absent",
        "never-seen",
        "future",
        "malformed",
        "disabled",
        "retired",
    }
)
INTERNAL_FAMILIES = {
    "vpn_observability_expected_target": {
        "name": "vpn_observability_expected_target",
        "owner": "observability_contract",
        "type": "gauge",
        "unit": None,
        "labels": ["node", "role"],
        "max_series": 256,
        "cadence_seconds": 60,
        "stale_after_seconds": 180,
        "alert_use": True,
    },
    "vpn_observability_evidence_state": {
        "name": "vpn_observability_evidence_state",
        "owner": "observability_contract",
        "type": "gauge",
        "unit": None,
        "labels": ["node", "role", "state"],
        "max_series": 2048,
        "cadence_seconds": 60,
        "stale_after_seconds": 180,
        "alert_use": True,
    },
}
SCHEMAS = {
    "manifest": "observability-metric-manifest.schema.json",
    "inventory": "observability-expected-inventory.schema.json",
    "evidence": "observability-evidence.schema.json",
}


class ContractError(Exception):
    """A redacted observability contract failure."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def validate_document(schema: dict[str, Any], document: Any) -> None:
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise ContractError("jsonschema is unavailable") from exc
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(document))
    if errors:
        raise ContractError("document does not match its schema")


def _trusted_input_directory(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0
    )


def _open_trusted_input(path: Path) -> int:
    absolute = Path(os.path.abspath(os.fspath(path)))
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    file_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    parent_descriptor = -1
    try:
        parent_descriptor = os.open(absolute.anchor, directory_flags)
        if not _trusted_input_directory(os.fstat(parent_descriptor)):
            raise ContractError("invalid input")
        for component in absolute.parts[1:-1]:
            child_descriptor = os.open(
                component, directory_flags, dir_fd=parent_descriptor
            )
            os.close(parent_descriptor)
            parent_descriptor = child_descriptor
            if not _trusted_input_directory(os.fstat(parent_descriptor)):
                raise ContractError("invalid input")
        descriptor = os.open(absolute.name, file_flags, dir_fd=parent_descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_nlink != 1
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or metadata.st_size > MAX_INPUT_BYTES
        ):
            os.close(descriptor)
            raise ContractError("invalid input")
        return descriptor
    except OSError as exc:
        raise ContractError("invalid input") from exc
    finally:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _open_bounded_repository_file(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_INPUT_BYTES:
            os.close(descriptor)
            raise ContractError("invalid input")
        return descriptor
    except OSError as exc:
        raise ContractError("invalid input") from exc


def _load_json(path: Path, *, external: bool = True) -> Any:
    descriptor = -1
    try:
        descriptor = (
            _open_trusted_input(path)
            if external
            else _open_bounded_repository_file(path)
        )
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
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError("invalid input") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _schema(name: str) -> dict[str, Any]:
    value = _load_json(CONTRACT_ROOT / SCHEMAS[name], external=False)
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
        or SHORT_HEX.fullmatch(value) is not None
        or COMPACT_OPAQUE.fullmatch(value) is not None
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
    if any(
        families.get(name) != specification
        for name, specification in INTERNAL_FAMILIES.items()
    ):
        raise ContractError("invalid internal metric family")
    for target in targets.values():
        if _forbidden_value(target["target"]) or _forbidden_value(target["role"]):
            raise ContractError("unsafe inventory identity")
        label_values = target["label_values"]
        if label_values["node"] != [target["target"]] or label_values["role"] != [
            target["role"]
        ]:
            raise ContractError("inventory identity allowlist mismatch")
        if any(
            _forbidden_value(value)
            for values in label_values.values()
            for value in values
        ):
            raise ContractError("unsafe inventory label value")
        if any(
            name not in families or name in INTERNAL_FAMILIES
            for name in target["required_families"]
        ):
            raise ContractError("unknown required family")
        if any(
            not set(families[name]["labels"]).issubset(label_values)
            for name in target["required_families"]
        ):
            raise ContractError("required family has no label allowlist")
    for family in families.values():
        if family["name"] in INTERNAL_FAMILIES:
            continue
        if SECRET_IDENTIFIER.search(family["name"]):
            raise ContractError("unsafe metric family")
        if any(FORBIDDEN_LABEL.search(label) for label in family["labels"]):
            raise ContractError("unsafe metric label")
        if not set(family["labels"]).issubset(ALLOWED_LABELS):
            raise ContractError("unknown metric label")
        if family["stale_after_seconds"] < family["cadence_seconds"]:
            raise ContractError("staleness precedes cadence")
    return families, targets, observations


def _labels(labels: dict[str, str]) -> str:
    escaped = []
    for name, value in sorted(labels.items()):
        safe = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        escaped.append(f'{name}="{safe}"')
    return "{" + ",".join(escaped) + "}"


def _internal_labels(name: str, labels: dict[str, str]) -> dict[str, str]:
    if tuple(sorted(labels)) != tuple(INTERNAL_FAMILIES[name]["labels"]):
        raise ContractError("invalid internal metric labels")
    if "state" in labels and labels["state"] not in EVIDENCE_STATES:
        raise ContractError("invalid internal metric state")
    return labels


def _number(value: int | float) -> str:
    if isinstance(value, bool):
        raise ContractError("invalid metric number")
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ContractError("invalid metric number") from error
    if not math.isfinite(numeric):
        raise ContractError("invalid metric number")
    if isinstance(value, int):
        if int(numeric) != value:
            raise ContractError("invalid metric number")
        return str(value)
    return format(value, ".17g")


def _evaluate_target(
    target: dict[str, Any],
    observation: dict[str, Any] | None,
    families: dict[str, dict[str, Any]],
    now: int,
    max_future: int,
    binding_valid: bool,
) -> tuple[str, list[tuple[str, dict[str, str], int | float]]]:
    if not binding_valid:
        return "malformed", []
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
        if family is None or sample["family"] in INTERNAL_FAMILIES:
            return "malformed", []
        labels = sample["labels"]
        if set(labels) != set(family["labels"]):
            return "malformed", []
        if any(_forbidden_value(value) for value in labels.values()):
            return "malformed", []
        if any(
            value not in target["label_values"].get(name, [])
            for name, value in labels.items()
        ):
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
        if family["type"] == "counter" and sample["value"] < 0:
            return "malformed", []
        seen_families.add(sample["family"])
        valid_samples.append((sample["family"], labels, sample["value"]))

    required = set(target["required_families"])
    if not required.issubset(seen_families):
        return "malformed", []
    stale_after = min(
        families[name]["stale_after_seconds"] for name in seen_families
    )
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
    binding_valid = (
        evidence["manifest_generation"] == manifest["generation"]
        and evidence["manifest_source_id"] == manifest["source_id"]
        and evidence["inventory_generation"] == inventory["generation"]
        and evidence["inventory_source_id"] == inventory["source_id"]
    )
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
            binding_valid,
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

    lines = [f"# TYPE {name} {families[name]['type']}" for name in INTERNAL_FAMILIES]
    states: dict[str, int] = {}
    emitted = 0
    producer_samples: list[tuple[str, dict[str, str], int | float]] = []
    for target, state, samples in results:
        identity = _internal_labels(
            "vpn_observability_expected_target",
            {"node": target["target"], "role": target["role"]},
        )
        lines.append(f"vpn_observability_expected_target{_labels(identity)} 1")
        state_labels = _internal_labels(
            "vpn_observability_evidence_state", {**identity, "state": state}
        )
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


def _trusted_directory(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0
    )


def _trusted_output(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0
        and metadata.st_nlink == 1
    )


def _directory_chain(path: Path) -> tuple[Path, os.stat_result]:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    try:
        metadata = os.lstat(current)
        if not _trusted_directory(metadata):
            raise ContractError("unsafe output ancestry")
        for component in absolute.parts[1:]:
            current /= component
            metadata = os.lstat(current)
            if not _trusted_directory(metadata):
                raise ContractError("unsafe output ancestry")
    except OSError as exc:
        raise ContractError("output parent is unavailable") from exc
    return absolute, metadata


def _same_node(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _target_metadata(parent_descriptor: int, name: str) -> os.stat_result | None:
    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not _trusted_output(metadata):
        raise ContractError("unsafe output target")
    return metadata


def _revalidate_target(
    parent_descriptor: int, name: str, previous: os.stat_result | None
) -> None:
    current = _target_metadata(parent_descriptor, name)
    if (previous is None) != (current is None):
        raise ContractError("output target changed")
    if (
        previous is not None
        and current is not None
        and not _same_node(previous, current)
    ):
        raise ContractError("output target changed")


def _create_temporary(parent_descriptor: int, target_name: str) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(32):
        name = f".{target_name}.{os.urandom(12).hex()}"
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            os.close(descriptor)
            try:
                os.unlink(name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                # A concurrent cleanup may have removed our unpublished temp file.
                pass
            raise
        return descriptor, name
    raise ContractError("temporary output is unavailable")


def _atomic_write(
    path: Path, payload: bytes, *, require_existing: bool = False
) -> None:
    if path.name in {"", ".", ".."}:
        raise ContractError("invalid output name")
    parent_path, expected_parent = _directory_chain(path.parent)
    parent_descriptor = -1
    descriptor = -1
    temporary: str | None = None
    try:
        parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        parent_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        parent_descriptor = os.open(parent_path, parent_flags)
        opened_parent = os.fstat(parent_descriptor)
        if not _trusted_directory(opened_parent) or not _same_node(
            expected_parent, opened_parent
        ):
            raise ContractError("output parent changed")
        previous = _target_metadata(parent_descriptor, path.name)
        if require_existing and previous is None:
            return
        descriptor, temporary = _create_temporary(parent_descriptor, path.name)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1

        current_parent_path, current_parent = _directory_chain(parent_path)
        if current_parent_path != parent_path or not _same_node(
            opened_parent, current_parent
        ):
            raise ContractError("output parent changed")
        _revalidate_target(parent_descriptor, path.name, previous)
        os.replace(
            temporary,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary = None
        published_parent_path, published_parent = _directory_chain(parent_path)
        if published_parent_path != parent_path or not _same_node(
            opened_parent, published_parent
        ):
            raise ContractError("output parent changed")
        published = _target_metadata(parent_descriptor, path.name)
        if published is None or published.st_uid != os.geteuid():
            raise ContractError("published output is invalid")
        if stat.S_IMODE(published.st_mode) != 0o600:
            raise ContractError("published output is invalid")
        os.fsync(parent_descriptor)
    except OSError as exc:
        raise ContractError("publication failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None and parent_descriptor >= 0:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                # The temporary output may already be absent after a failed publish.
                pass
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


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
        try:
            _atomic_write(args.output, b"", require_existing=True)
        except (ContractError, OSError):
            # An unsafe or unavailable output path cannot be withdrawn safely.
            pass
        print("observability-contract: validation failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
