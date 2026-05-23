#!/usr/bin/env python3
"""Correlate a client-side idle-cycle measurement run against the
server-side SYN + TLS access logs.

The client driver (`scripts/idle-cycle-measure.sh`) records the wall-
clock window around every probe. This tool walks each probe record,
finds every inbound SYN to the listener port within the window's
expanded match envelope, and tags whether the client's source IP
appears in the SYN log.

Most usefully, it surfaces SYNs from *other* source IPs that fall
inside the cold-probe wait window — the active-probe hypothesis from
the source concept doc. If the server sees SYNs from a non-client
source IP between the moment the client started the cold handshake
and the moment the handshake completed, that is a direct measurement
of an upstream probe interleaved into the cycle.

Inputs:
  --client-report   path to the JSON file the driver wrote
  --syn-log         path to the SYN log (one line per SYN; see runbook
                    for the iptables LOG rule that produces the
                    expected format)
  --tls-access-log  path to the TLS server's access log
  --client-ip       the client's expected source IP (so the
                    "other source IPs" set excludes legitimate
                    client connections)
  --window-ms       expand each probe envelope by this much on each
                    side before searching the logs (default 5000)

Output: a single JSON object on stdout with the original client
report under `client_report` plus a `server_correlation` block per
cycle.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime, timezone


SYN_LINE = re.compile(
    r'(?P<ts>\S+)\s+\S+\s+kernel:.*idle-cycle-syn:.*?'
    r'SRC=(?P<src>\S+)\s+DST=(?P<dst>\S+).*?DPT=(?P<dpt>\d+)'
)
TLS_LINE = re.compile(
    r'(?P<ts>\S+)\s+(?P<ip>\S+)\s+sni=(?P<sni>\S+)\s+'
    r'tls_complete_ms=(?P<elapsed>\d+)'
)


def _ts_to_epoch_ms(ts: str) -> int | None:
    # Accepts ISO 8601 with `Z`, syslog-style `Mon DD HH:MM:SS`, or
    # plain unix-seconds. Returns None on a parse miss; the caller
    # then drops the line.
    if ts.isdigit():
        return int(ts) * 1000
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        pass
    try:
        # syslog default: "May 22 14:03:12"
        dt = datetime.strptime(ts, "%b %d %H:%M:%S").replace(
            year=datetime.now(timezone.utc).year, tzinfo=timezone.utc
        )
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def parse_syn_log(path: pathlib.Path) -> list[dict]:
    out = []
    for line in path.read_text(errors="replace").splitlines():
        m = SYN_LINE.search(line)
        if not m:
            continue
        epoch_ms = _ts_to_epoch_ms(m.group("ts"))
        if epoch_ms is None:
            continue
        out.append({
            "ts_ms": epoch_ms,
            "src": m.group("src"),
            "dst": m.group("dst"),
            "dpt": int(m.group("dpt")),
        })
    return out


def parse_tls_log(path: pathlib.Path) -> list[dict]:
    out = []
    for line in path.read_text(errors="replace").splitlines():
        m = TLS_LINE.search(line)
        if not m:
            continue
        epoch_ms = _ts_to_epoch_ms(m.group("ts"))
        if epoch_ms is None:
            continue
        out.append({
            "ts_ms": epoch_ms,
            "ip": m.group("ip"),
            "sni": m.group("sni"),
            "elapsed_ms": int(m.group("elapsed")),
        })
    return out


def correlate(args: argparse.Namespace) -> dict:
    client = json.loads(pathlib.Path(args.client_report).read_text())
    syns = parse_syn_log(pathlib.Path(args.syn_log))
    tlss = parse_tls_log(pathlib.Path(args.tls_access_log))

    per_probe = []
    for r in client.get("results", []):
        lo = r["pre_ms"] - args.window_ms
        hi = r["post_ms"] + args.window_ms

        window_syns = [s for s in syns if lo <= s["ts_ms"] <= hi]
        window_tlss = [t for t in tlss if lo <= t["ts_ms"] <= hi]

        # SYNs from a source IP that is *not* the client's expected
        # IP, inside the probe envelope. These are the active-probe
        # candidates the source concept's third hypothesis predicts.
        other_syns = [s for s in window_syns if s["src"] != args.client_ip]
        client_syns = [s for s in window_syns if s["src"] == args.client_ip]

        per_probe.append({
            "cycle_idx": r["cycle_idx"],
            "attempt_kind": r["attempt_kind"],
            "attempt_idx": r["attempt_idx"],
            "client_syn_count": len(client_syns),
            "other_source_syn_count": len(other_syns),
            "other_source_syn_sample": other_syns[:5],
            "tls_completed_count": len(window_tlss),
        })

    return {
        "schema_version": 1,
        "client_report": client,
        "correlation_window_ms": args.window_ms,
        "client_ip": args.client_ip,
        "syn_log_records": len(syns),
        "tls_log_records": len(tlss),
        "per_probe": per_probe,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--client-report", required=True)
    ap.add_argument("--syn-log", required=True)
    ap.add_argument("--tls-access-log", required=True)
    ap.add_argument("--client-ip", required=True)
    ap.add_argument("--window-ms", type=int, default=5000)
    args = ap.parse_args()

    out = correlate(args)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
