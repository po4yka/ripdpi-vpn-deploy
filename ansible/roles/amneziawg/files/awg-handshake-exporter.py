#!/usr/bin/env python3
"""Export aggregate AmneziaWG handshake counts for the node_exporter textfile.

Only two counts leave this process: all configured peers and peers whose
latest handshake is inside the freshness window. Peer keys, addresses and
interface membership are read and discarded; they never reach the output or
the journal.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


class CollectionError(RuntimeError):
    """A redacted collector failure safe to report to journald."""


def query_handshakes(awg_bin: str, timeout: float) -> str:
    try:
        result = subprocess.run(
            [awg_bin, "show", "all", "latest-handshakes"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # The exception text can quote output, so only the type is kept.
        raise CollectionError(type(exc).__name__) from None
    return result.stdout


def count_peers(output: str, *, now: int, window: int) -> tuple[int, int]:
    """Return (total, fresh) from `awg show all latest-handshakes` lines."""
    total = fresh = 0
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not fields[2].isdigit():
            raise CollectionError("unexpected handshake record")
        total += 1
        latest = int(fields[2])
        # 0 means the peer never completed a handshake.
        if latest and 0 <= now - latest <= window:
            fresh += 1
    return total, fresh


def render_metrics(total: int, fresh: int, collected_at: int) -> str:
    return "\n".join(
        [
            "# HELP vpn_awg_handshake_collection_success Whether the last AmneziaWG handshake query succeeded.",
            "# TYPE vpn_awg_handshake_collection_success gauge",
            "vpn_awg_handshake_collection_success 1",
            "# HELP vpn_awg_handshake_collected_timestamp_seconds Unix timestamp of the last handshake query.",
            "# TYPE vpn_awg_handshake_collected_timestamp_seconds gauge",
            f"vpn_awg_handshake_collected_timestamp_seconds {collected_at}",
            "# HELP vpn_awg_peers Configured AmneziaWG peers on all interfaces.",
            "# TYPE vpn_awg_peers gauge",
            f"vpn_awg_peers {total}",
            "# HELP vpn_awg_peers_fresh_handshake Peers whose latest handshake is inside the freshness window.",
            "# TYPE vpn_awg_peers_fresh_handshake gauge",
            f"vpn_awg_peers_fresh_handshake {fresh}",
            "",
        ]
    )


def render_failure(collected_at: int) -> str:
    return "\n".join(
        [
            "# HELP vpn_awg_handshake_collection_success Whether the last AmneziaWG handshake query succeeded.",
            "# TYPE vpn_awg_handshake_collection_success gauge",
            "vpn_awg_handshake_collection_success 0",
            "# HELP vpn_awg_handshake_collected_timestamp_seconds Unix timestamp of the last handshake query attempt.",
            "# TYPE vpn_awg_handshake_collected_timestamp_seconds gauge",
            f"vpn_awg_handshake_collected_timestamp_seconds {collected_at}",
            "",
        ]
    )


def atomic_write(path: Path, content: str) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # Root writes into the setgid textfile directory; node_exporter reads through its group.
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--awg-bin", default="/usr/bin/awg")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fresh-window", type=int, default=180)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    if not 30 <= args.fresh_window <= 86400:
        print("awg-handshake-exporter: invalid freshness window", file=sys.stderr)
        return 2

    collected_at = int(time.time())
    try:
        total, fresh = count_peers(
            query_handshakes(args.awg_bin, args.timeout), now=collected_at, window=args.fresh_window
        )
        atomic_write(args.output, render_metrics(total, fresh, collected_at))
    except CollectionError as exc:
        try:
            atomic_write(args.output, render_failure(collected_at))
        except OSError as write_exc:
            print(
                f"awg-handshake-exporter: failure metric update failed ({type(write_exc).__name__})",
                file=sys.stderr,
            )
        print(f"awg-handshake-exporter: collection failed ({exc})", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"awg-handshake-exporter: output update failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
