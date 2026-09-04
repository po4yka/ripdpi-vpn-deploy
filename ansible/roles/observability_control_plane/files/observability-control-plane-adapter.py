#!/usr/bin/env python3
"""Publish bounded control-plane identity, capacity, and pipeline evidence."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import sys

ROLE = Path(__file__).resolve().parent
RENDERER_PATH = ROLE / "observability-expected-target-renderer.py"
SPEC = importlib.util.spec_from_file_location("expected_target_renderer", RENDERER_PATH)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)

REVISION = re.compile(r"^[0-9a-f]{40,64}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _state(observed: str, expected: str) -> str:
    return "match" if observed == expected else "mismatch"


def render(args: argparse.Namespace) -> bytes:
    if not all(
        pattern.fullmatch(value)
        for pattern, value in (
            (REVISION, args.expected_source_revision),
            (REVISION, args.observed_source_revision),
            (DIGEST, args.expected_deployable_digest),
            (DIGEST, args.observed_deployable_digest),
        )
    ):
        raise renderer.RendererError("invalid identity")
    if args.required_free_bytes < 0:
        raise renderer.RendererError("invalid capacity")
    renderer._validate_inventory(renderer._load_inventory(args.inventory))
    try:
        filesystem = os.statvfs(args.data_dir)
        available = filesystem.f_bavail * filesystem.f_frsize
    except OSError:
        available = -1
    capacity = "fresh" if available >= args.required_free_bytes else "stale"
    states = (
        (
            "source-revision",
            _state(args.observed_source_revision, args.expected_source_revision),
        ),
        (
            "deployable-digest",
            _state(args.observed_deployable_digest, args.expected_deployable_digest),
        ),
        ("tsdb-capacity", capacity),
        ("expected-target-pipeline", "fresh"),
    )
    lines = ["# TYPE vpn_observability_evidence_state gauge"]
    lines.extend(
        "vpn_observability_evidence_state"
        f'{{node="observability-control-plane",role="{role}",state="{state}"}} 1'
        for role, state in states
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _render_failure() -> bytes:
    return (
        "# TYPE vpn_observability_evidence_state gauge\n"
        'vpn_observability_evidence_state{node="observability-control-plane",role="expected-target-pipeline",state="stale"} 1\n'
    ).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--required-free-bytes", type=int, required=True)
    parser.add_argument("--expected-source-revision", required=True)
    parser.add_argument("--observed-source-revision", required=True)
    parser.add_argument("--expected-deployable-digest", required=True)
    parser.add_argument("--observed-deployable-digest", required=True)
    args = parser.parse_args(argv)
    try:
        renderer._atomic_write(args.output, render(args))
    except (renderer.RendererError, OSError):
        try:
            renderer._atomic_write(args.output, _render_failure())
        except (renderer.RendererError, OSError):
            # Preserve the original validation failure when fallback publication fails.
            pass
        print("observability-control-plane-adapter: validation failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
