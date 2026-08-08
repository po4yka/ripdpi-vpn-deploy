#!/usr/bin/env python3
"""Export redacted Xray StatsService counters for node_exporter textfile.

Inbound and outbound tags are deployment-owned technical identifiers and are
kept as labels. Per-user counters are disabled in Xray, so client identifiers
never enter the StatsService response consumed by this process.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

STAT_NAME = re.compile(r"^(inbound|outbound)>>>(.*?)>>>traffic>>>(uplink|downlink)$")
SAFE_TAG = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class CollectionError(RuntimeError):
    """A redacted collector failure safe to report to journald."""


def _label(value: str) -> str:
    if not SAFE_TAG.fullmatch(value):
        raise CollectionError("unsafe Xray stat tag")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def query_stats(xray_bin: str, server: str, timeout: float) -> dict:
    try:
        result = subprocess.run(
            [xray_bin, "api", "statsquery", f"--server={server}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        payload = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise CollectionError(type(exc).__name__) from exc
    if not isinstance(payload, dict):
        raise CollectionError("unexpected Xray response")
    return payload


def render_metrics(payload: dict, collected_at: int) -> str:
    entries = payload.get("stat", [])
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise CollectionError("unexpected Xray stat list")

    traffic: dict[tuple[str, str, str], int] = defaultdict(int)
    records = 0

    for entry in entries:
        if not isinstance(entry, dict):
            raise CollectionError("unexpected Xray stat record")
        name = entry.get("name")
        if not isinstance(name, str):
            raise CollectionError("missing Xray stat name")
        match = STAT_NAME.fullmatch(name)
        if match is None:
            continue
        try:
            value = int(entry.get("value", 0))
        except (TypeError, ValueError) as exc:
            raise CollectionError("invalid Xray stat value") from exc
        if value < 0:
            raise CollectionError("negative Xray stat value")

        scope, identifier, direction = match.groups()
        records += 1
        traffic[(scope, _label(identifier), direction)] += value

    lines = [
        "# HELP vpn_xray_stats_collection_success Whether the last local StatsService query succeeded.",
        "# TYPE vpn_xray_stats_collection_success gauge",
        "vpn_xray_stats_collection_success 1",
        "# HELP vpn_xray_stats_collected_timestamp_seconds Unix timestamp of the last StatsService query.",
        "# TYPE vpn_xray_stats_collected_timestamp_seconds gauge",
        f"vpn_xray_stats_collected_timestamp_seconds {collected_at}",
        "# HELP vpn_xray_stats_records Number of recognized records returned by Xray.",
        "# TYPE vpn_xray_stats_records gauge",
        f"vpn_xray_stats_records {records}",
    ]
    for (scope, identifier, direction), value in sorted(traffic.items()):
        metric = f"vpn_xray_{scope}_traffic_bytes_total"
        label_name = scope
        lines.append(
            f'{metric}{{{label_name}="{identifier}",direction="{direction}"}} {value}'
        )
    return "\n".join(lines) + "\n"


def render_failure(collected_at: int) -> str:
    return "\n".join(
        [
            "# HELP vpn_xray_stats_collection_success Whether the last local StatsService query succeeded.",
            "# TYPE vpn_xray_stats_collection_success gauge",
            "vpn_xray_stats_collection_success 0",
            "# HELP vpn_xray_stats_collected_timestamp_seconds Unix timestamp of the last StatsService query attempt.",
            "# TYPE vpn_xray_stats_collected_timestamp_seconds gauge",
            f"vpn_xray_stats_collected_timestamp_seconds {collected_at}",
            "",
        ]
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xray-bin", default="/usr/local/bin/xray")
    parser.add_argument("--server", default="127.0.0.1:10086")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    collected_at = int(time.time())
    try:
        payload = query_stats(args.xray_bin, args.server, args.timeout)
        metrics = render_metrics(payload, collected_at)
        atomic_write(args.output, metrics)
    except CollectionError as exc:
        try:
            atomic_write(args.output, render_failure(collected_at))
        except OSError:
            pass
        print(f"xray-stats-exporter: collection failed ({exc})", file=sys.stderr)
        return 1
    except OSError as exc:
        print(
            f"xray-stats-exporter: output update failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
