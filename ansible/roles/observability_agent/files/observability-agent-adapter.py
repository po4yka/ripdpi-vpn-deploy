#!/usr/bin/env python3
"""Publish a bounded, redacted schema-2 node-manifest adapter metric."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time


MAX_MANIFEST_BYTES = 64 * 1024
NODE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ENVIRONMENT = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AdapterError(RuntimeError):
    """A bounded, non-secret adapter failure."""


def _metric_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _read_manifest(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if not path.is_file() or path.is_symlink() or metadata.st_size > MAX_MANIFEST_BYTES:
        raise AdapterError("unsafe manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError("invalid manifest") from exc
    if not isinstance(payload, dict):
        raise AdapterError("invalid manifest")
    return payload


def _render(manifest: dict[str, object], node_id: str) -> str:
    if not NODE_ID.fullmatch(node_id):
        raise AdapterError("invalid node ID")
    if manifest.get("schema_version") != 2:
        raise AdapterError("unsupported node manifest schema")
    required = {
        "environment": ENVIRONMENT,
        "provider": PROVIDER,
        "source_revision": SHA1,
        "deployable_digest": SHA256,
    }
    labels: dict[str, str] = {"node_id": node_id}
    for key, pattern in required.items():
        value = manifest.get(key)
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise AdapterError("invalid manifest identity")
        labels[key] = value
    rendered_labels = ",".join(
        f'{key}="{_metric_label(value)}"' for key, value in sorted(labels.items())
    )
    now = int(time.time())
    return "\n".join(
        [
            "# HELP vpn_observability_adapter_collection_success Whether the schema-2 manifest adapter completed.",
            "# TYPE vpn_observability_adapter_collection_success gauge",
            "vpn_observability_adapter_collection_success 1",
            "# HELP vpn_observability_adapter_collected_timestamp_seconds Unix timestamp of the completed adapter collection.",
            "# TYPE vpn_observability_adapter_collected_timestamp_seconds gauge",
            f"vpn_observability_adapter_collected_timestamp_seconds {now}",
            "# HELP vpn_observability_node_manifest_info Redacted schema-2 node manifest identity.",
            "# TYPE vpn_observability_node_manifest_info gauge",
            f"vpn_observability_node_manifest_info{{{rendered_labels}}} 1",
            "",
        ]
    )


def _render_failure(collected_at: int) -> str:
    return "\n".join(
        [
            "# HELP vpn_observability_adapter_collection_success Whether the schema-2 manifest adapter completed.",
            "# TYPE vpn_observability_adapter_collection_success gauge",
            "vpn_observability_adapter_collection_success 0",
            "# HELP vpn_observability_adapter_collected_timestamp_seconds Unix timestamp of the adapter attempt.",
            "# TYPE vpn_observability_adapter_collected_timestamp_seconds gauge",
            f"vpn_observability_adapter_collected_timestamp_seconds {collected_at}",
            "",
        ]
    )


def _atomic_write(path: Path, content: str) -> None:
    parent = path.parent
    metadata = parent.lstat()
    if not parent.is_dir() or parent.is_symlink() or metadata.st_mode & 0o002:
        raise AdapterError("unsafe output directory")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node-id", required=True)
    args = parser.parse_args(argv)
    try:
        _atomic_write(args.output, _render(_read_manifest(args.manifest), args.node_id))
    except (AdapterError, OSError) as exc:
        try:
            _atomic_write(args.output, _render_failure(int(time.time())))
        except (AdapterError, OSError):
            pass
        print(f"observability-agent-adapter: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
