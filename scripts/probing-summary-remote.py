#!/usr/bin/env python3
"""Daily probing-event aggregator. Reads the local Xray, nginx, and
honeypot logs on the VPS; produces a Markdown summary + a Prometheus
textfile with the time-series breakdown.

Designed to be invoked over ssh by scripts/probing-summary.sh, but
runs equally well as a systemd timer on the VPS for self-reporting.

Outputs:
  /var/lib/node_exporter/textfile/vpn_probing.prom
  /var/log/vpn-probing-summary-YYYY-MM-DD.md
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import pathlib
import re
import sys
WINDOW_HOURS = 7 * 24
NOW = dt.datetime.now(tz=dt.timezone.utc)
SINCE = NOW - dt.timedelta(hours=WINDOW_HOURS)

XRAY_ACCESS = pathlib.Path("/var/log/xray/access.log")
NGINX_ACCESS = pathlib.Path("/var/log/nginx/access.log")
HONEYPOT_LOG = pathlib.Path("/var/log/honeypot/connections.log")
TEXTFILE_DIR = pathlib.Path("/var/lib/node_exporter/textfile")
REPORT_DIR = pathlib.Path("/var/log")

# Xray access.log lines that indicate a rejected or blackholed connection:
#   2026/05/11 12:34:56 1.2.3.4:53456 rejected  ...   (VLESS-layer AccessRejected)
#   2026/05/11 12:34:56 1.2.3.4:53456 [... block] ... (blackhole detour)
XRAY_TS_RE = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\s")
XRAY_EVENT_RE = re.compile(r"(\[[^\]]*\bblock\])|(^| )rejected( |$)")


def _bucket_hour(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H")


def _read_xray_events() -> list[tuple[dt.datetime, str]]:
    if not XRAY_ACCESS.is_file():
        return []
    events: list[tuple[dt.datetime, str]] = []
    try:
        with XRAY_ACCESS.open("r", errors="replace") as fh:
            for line in fh:
                m = XRAY_TS_RE.match(line)
                if not m:
                    continue
                if not XRAY_EVENT_RE.search(line):
                    continue
                try:
                    ts = dt.datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S").replace(
                        tzinfo=dt.timezone.utc)
                except ValueError:
                    continue
                if ts < SINCE:
                    continue
                ip = ""
                ip_m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", line)
                if ip_m:
                    ip = ip_m.group(1)
                events.append((ts, ip))
    except FileNotFoundError:
        return []
    return events


def _read_nginx_403() -> list[tuple[dt.datetime, str]]:
    if not NGINX_ACCESS.is_file():
        return []
    events: list[tuple[dt.datetime, str]] = []
    # nginx default combined log format
    log_re = re.compile(
        r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
        r'"\S+ \S+ \S+" (?P<status>\d+) '
    )
    try:
        with NGINX_ACCESS.open("r", errors="replace") as fh:
            for line in fh:
                m = log_re.match(line)
                if not m:
                    continue
                if m.group("status") not in {"403", "444"}:
                    continue
                try:
                    ts = dt.datetime.strptime(
                        m.group("time"), "%d/%b/%Y:%H:%M:%S %z")
                except ValueError:
                    continue
                if ts < SINCE:
                    continue
                events.append((ts, m.group("ip")))
    except FileNotFoundError:
        return []
    return events


def _read_honeypot() -> list[tuple[dt.datetime, str, str | None]]:
    if not HONEYPOT_LOG.is_file():
        return []
    events = []
    try:
        with HONEYPOT_LOG.open("r", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = dt.datetime.fromtimestamp(rec.get("ts", 0), tz=dt.timezone.utc)
                if ts < SINCE:
                    continue
                events.append((ts, rec.get("src_ip", ""), rec.get("sni")))
    except FileNotFoundError:
        return []
    return events


def _classify(ip_counts: collections.Counter, sni_counts: collections.Counter,
              total: int) -> str:
    if total == 0:
        return "none"
    top_ip_share = (ip_counts.most_common(1)[0][1] / total) if ip_counts else 0
    distinct_snis = len(sni_counts)
    if top_ip_share > 0.6:
        return "single-IP repeat"
    if distinct_snis > 20:
        return "SNI-varying"
    if top_ip_share < 0.2 and total > 100:
        return "distributed scan"
    return "mixed"


def main() -> int:
    TEXTFILE_DIR.mkdir(parents=True, exist_ok=True)
    xray_events = _read_xray_events()
    nginx_events = _read_nginx_403()
    honeypot_events = _read_honeypot()

    xray_n = len(xray_events)
    nginx_n = len(nginx_events)
    honey_n = len(honeypot_events)

    per_hour: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"xray": 0, "nginx": 0, "honey": 0})
    for ts, _ip in xray_events:
        per_hour[_bucket_hour(ts)]["xray"] += 1
    for ts, _ip in nginx_events:
        per_hour[_bucket_hour(ts)]["nginx"] += 1
    for ts, _ip, _sni in honeypot_events:
        per_hour[_bucket_hour(ts)]["honey"] += 1

    ip_counts = collections.Counter(ip for _, ip in xray_events if ip)
    sni_counts = collections.Counter(sni for _, _, sni in honeypot_events if sni)
    cls = _classify(ip_counts, sni_counts, xray_n + honey_n)

    # ----------------- markdown report ---------------------
    today = NOW.strftime("%Y-%m-%d")
    md_path = REPORT_DIR / f"vpn-probing-summary-{today}.md"
    with md_path.open("w") as fh:
        fh.write(f"# Probing summary — {today} (last {WINDOW_HOURS} h)\n\n")
        fh.write(f"* Xray blackhole/VLESS-reject events: **{xray_n}**\n")
        fh.write(f"* nginx 403/444 responses: **{nginx_n}**\n")
        fh.write(f"* Honeypot connections: **{honey_n}**\n")
        fh.write(f"* Classification: **{cls}**\n\n")
        fh.write("## Hourly breakdown\n\n")
        fh.write("| hour (UTC) | xray | nginx | honey |\n")
        fh.write("|---|---|---|---|\n")
        for hour in sorted(per_hour):
            row = per_hour[hour]
            fh.write(f"| {hour} | {row['xray']} | {row['nginx']} | {row['honey']} |\n")
        fh.write("\n## Top source IPs (Xray rejects)\n\n")
        for ip, n in ip_counts.most_common(15):
            fh.write(f"* `{ip}` — {n}\n")
        fh.write("\n## Top SNIs (honeypot)\n\n")
        for sni, n in sni_counts.most_common(15):
            fh.write(f"* `{sni}` — {n}\n")

    # ----------------- prometheus textfile -----------------
    prom_path = TEXTFILE_DIR / "vpn_probing.prom"
    tmp_path = prom_path.with_suffix(".prom.tmp")
    with tmp_path.open("w") as fh:
        fh.write("# HELP vpn_probing_xray_events_7d Xray blackhole/VLESS-reject events in last 7d\n")
        fh.write("# TYPE vpn_probing_xray_events_7d gauge\n")
        fh.write(f"vpn_probing_xray_events_7d {xray_n}\n")
        fh.write("# HELP vpn_probing_nginx_4xx_7d nginx 403/444 in last 7d\n")
        fh.write("# TYPE vpn_probing_nginx_4xx_7d gauge\n")
        fh.write(f"vpn_probing_nginx_4xx_7d {nginx_n}\n")
        fh.write("# HELP vpn_probing_honeypot_7d Honeypot connections in last 7d\n")
        fh.write("# TYPE vpn_probing_honeypot_7d gauge\n")
        fh.write(f"vpn_probing_honeypot_7d {honey_n}\n")
        fh.write(f'vpn_probing_classification{{class="{cls}"}} 1\n')
    os.replace(tmp_path, prom_path)

    print(f"wrote {md_path}")
    print(f"wrote {prom_path}")
    print(f"summary: xray={xray_n} nginx={nginx_n} honey={honey_n} class={cls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
