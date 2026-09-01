#!/usr/bin/env python3
"""Render the bounded expected-target inventory as Prometheus metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

MAX_INPUT_BYTES = 1024 * 1024
ALIAS = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
METRIC = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]{0,127}$")
LIFECYCLES = frozenset({"enabled", "disabled", "retired"})


class RendererError(Exception):
    """A redacted expected-target rendering failure."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _load_inventory(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RendererError("invalid inventory") from exc
    if len(payload) > MAX_INPUT_BYTES:
        raise RendererError("invalid inventory")
    try:
        document = json.loads(payload, object_pairs_hook=_unique_object)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise RendererError("invalid inventory") from exc
    if not isinstance(document, dict):
        raise RendererError("invalid inventory")
    return document


def _alias(value: Any) -> bool:
    return isinstance(value, str) and ALIAS.fullmatch(value) is not None


def _validate_inventory(document: dict[str, Any]) -> list[tuple[str, str]]:
    if set(document) != {
        "schema_version",
        "generation",
        "source_id",
        "max_future_seconds",
        "targets",
    }:
        raise RendererError("invalid inventory")
    if document["schema_version"] != 1:
        raise RendererError("invalid inventory")
    if not _alias(document["generation"]) or not _alias(document["source_id"]):
        raise RendererError("invalid inventory")
    future = document["max_future_seconds"]
    if (
        isinstance(future, bool)
        or not isinstance(future, int)
        or not 0 <= future <= 300
    ):
        raise RendererError("invalid inventory")
    targets = document["targets"]
    if not isinstance(targets, list) or not 1 <= len(targets) <= 256:
        raise RendererError("invalid inventory")
    identities: set[tuple[str, str]] = set()
    for target in targets:
        if not isinstance(target, dict) or set(target) != {
            "target",
            "role",
            "lifecycle",
            "ever_seen",
            "label_values",
            "required_families",
        }:
            raise RendererError("invalid inventory")
        identity = (target["target"], target["role"])
        if not all(_alias(value) for value in identity):
            raise RendererError("invalid inventory")
        if identity in identities or target["lifecycle"] not in LIFECYCLES:
            raise RendererError("invalid inventory")
        if not isinstance(target["ever_seen"], bool):
            raise RendererError("invalid inventory")
        labels = target["label_values"]
        if not isinstance(labels, dict) or not {"node", "role"}.issubset(labels):
            raise RendererError("invalid inventory")
        if set(labels) - {"node", "role", "profile", "policy", "severity", "vantage"}:
            raise RendererError("invalid inventory")
        for values in labels.values():
            if (
                not isinstance(values, list)
                or not 1 <= len(values) <= 32
                or len(values) != len(set(values))
                or not all(_alias(value) for value in values)
            ):
                raise RendererError("invalid inventory")
        families = target["required_families"]
        if (
            not isinstance(families, list)
            or not 1 <= len(families) <= 64
            or len(families) != len(set(families))
            or not all(
                isinstance(name, str) and METRIC.fullmatch(name) for name in families
            )
        ):
            raise RendererError("invalid inventory")
        if target["lifecycle"] == "enabled":
            identities.add(identity)
    return sorted(identities)


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render(document: dict[str, Any]) -> bytes:
    identities = _validate_inventory(document)
    lines = ["# TYPE vpn_observability_expected_target gauge"]
    lines.extend(
        "vpn_observability_expected_target"
        f'{{node="{_label(node)}",role="{_label(role)}"}} 1'
        for node, role in identities
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _matches_published_output(
    path: Path, previous: os.stat_result, parent: os.stat_result, payload: bytes
) -> bool:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        current = os.fstat(descriptor)
        if (
            current.st_dev != previous.st_dev
            or current.st_ino != previous.st_ino
            or not stat.S_ISREG(current.st_mode)
            or current.st_nlink != 1
            or current.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(current.st_mode) != 0o640
            or current.st_gid != parent.st_gid
        ):
            return False
        return os.read(descriptor, len(payload) + 1) == payload
    except OSError:
        return False
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _atomic_write(path: Path, payload: bytes) -> bool:
    parent = path.parent
    try:
        parent_metadata = parent.lstat()
    except OSError as exc:
        raise RendererError("invalid output") from exc
    strict_parent = (
        stat.S_ISDIR(parent_metadata.st_mode)
        and parent_metadata.st_uid in {0, os.geteuid()}
        and parent_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0
    )
    shared_textfile_parent = (
        stat.S_ISDIR(parent_metadata.st_mode)
        and parent_metadata.st_uid in {0, os.geteuid()}
        and parent_metadata.st_mode & stat.S_IWOTH == 0
        and parent_metadata.st_mode & stat.S_IWGRP != 0
        and parent_metadata.st_mode & stat.S_ISGID != 0
        and parent_metadata.st_mode & stat.S_ISVTX != 0
    )
    if not (strict_parent or shared_textfile_parent):
        raise RendererError("invalid output")
    try:
        previous = path.lstat()
    except FileNotFoundError:
        previous = None
    if previous is not None and (
        not stat.S_ISREG(previous.st_mode)
        or previous.st_nlink != 1
        or previous.st_uid not in {0, os.geteuid()}
    ):
        raise RendererError("invalid output")
    if previous is not None and _matches_published_output(
        path, previous, parent_metadata, payload
    ):
        return False
    descriptor = -1
    temporary: Path | None = None
    try:
        for index in range(64):
            candidate = parent / f".{path.name}.{os.getpid()}.{index}.tmp"
            try:
                descriptor = os.open(
                    candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                temporary = candidate
                break
            except FileExistsError:
                continue
        if descriptor < 0 or temporary is None:
            raise RendererError("invalid output")
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
        os.chmod(path, 0o640)
    except OSError as exc:
        raise RendererError("invalid output") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        changed = _atomic_write(args.output, render(_load_inventory(args.inventory)))
    except (RendererError, OSError):
        print(
            "observability-expected-target-renderer: validation failed", file=sys.stderr
        )
        return 2
    print("changed" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
