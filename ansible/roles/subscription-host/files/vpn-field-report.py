#!/usr/bin/env python3
"""Aggregate anonymous client field reports into bounded Prometheus counters.

One loopback POST route behind the subscription vhost. A request carries the
cohort token as ``Authorization: Bearer <token>`` and one report body that
follows contract/client-field-report.schema.json. The shared contract
validator checks the body; the aggregate is written to the node_exporter
textfile and the report itself is discarded. The process logs no request:
no address, token, header or body reaches a log line, a metric label or a
file.

Status codes: 202 accepted, 400 invalid body, 401 unknown cohort token,
404 other path, 411 missing length, 413 body over the limit. Rate limiting
is nginx limit_req per address (429) in front of this process and nowhere
else, so an unauthenticated flood cannot use up intake for token holders.
"""
from __future__ import annotations

import argparse
import hmac
import importlib.util
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TOKEN = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
# Candidate keys tracked per window for the top-N choice; bounds memory under a flood of distinct values.
CANDIDATE_CAP = 4096
OTHER = "other"
# A report with network.source none, or with no country, has no identity to rank.
UNKNOWN = "unknown"
# The server handles one connection at a time, so each connection gets a total deadline: a client that
# sends one byte inside every per-read timeout would otherwise hold the process. nginx buffers the whole
# body before it connects, so a real request finishes far inside it.
REQUEST_DEADLINE_SECONDS = 5


def load_validator(validator_path: str, schema_path: str):
    """Return violations(report) from the shared contract validator module."""
    spec = importlib.util.spec_from_file_location("validate_field_report", validator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = json.loads(Path(schema_path).read_text())
    checker = module.validator(schema)
    bounds = schema["x-latency-bounds-ms"]
    return (lambda report: module.violations(report, checker)), bounds


def load_tokens(path: str) -> tuple[bytes, bytes | None, float]:
    """Current token, optional previous token and the end of its overlap (epoch seconds)."""
    data = json.loads(Path(path).read_text())
    current, previous = data.get("current"), data.get("previous")
    if not isinstance(current, str) or not TOKEN.fullmatch(current):
        raise ValueError("cohort token file: current token is missing or malformed")
    if previous is None:
        return current.encode(), None, 0.0
    if not isinstance(previous, str) or not TOKEN.fullmatch(previous):
        raise ValueError("cohort token file: previous token is malformed")
    until = datetime.fromisoformat(str(data.get("previous_valid_until", "")).replace("Z", "+00:00"))
    if until.tzinfo is None:
        raise ValueError("cohort token file: previous_valid_until needs an explicit offset")
    return current.encode(), previous.encode(), until.astimezone(timezone.utc).timestamp()


class TopN:
    """Label a value by itself only when it was in the top N of the previous window.

    Candidates are ranked by accepted reports, not attempts, and need at least
    min_reports of them: every token holder shares one cohort token, so one large
    report must not promote a network label by itself.
    """

    def __init__(self, n: int, window: float, min_reports: int) -> None:
        self.n, self.window, self.min_reports = n, window, min_reports
        self.top: frozenset[str] = frozenset()
        self.counts: dict[str, int] = {}
        self.started: float | None = None

    def _roll(self, now: float) -> None:
        if self.started is None:
            self.started = now
        elif now - self.started >= self.window:
            fresh = now - self.started < 2 * self.window
            ranked = sorted((key for key in self.counts if self.counts[key] >= self.min_reports),
                            key=lambda key: (-self.counts[key], key))
            self.top = frozenset(ranked[: self.n]) if fresh else frozenset()
            self.counts, self.started = {}, now

    def label(self, key: str, now: float) -> str:
        self._roll(now)
        return key if key in self.top else OTHER

    def observe(self, key: str, now: float) -> None:
        self._roll(now)
        if key in self.counts or len(self.counts) < CANDIDATE_CAP:
            self.counts[key] = self.counts.get(key, 0) + 1


class Aggregate:
    def __init__(self, config: dict, bounds: list) -> None:
        self.server_refs = frozenset(config["server_refs"])
        # Operators and ASNs rank separately, so many Wi-Fi ASNs cannot push every SIM operator into "other".
        self.asn = TopN(config["asn_top_n"], config["window_seconds"], config["top_n_min_reports"])
        self.operator = TopN(config["operator_top_n"], config["window_seconds"], config["top_n_min_reports"])
        self.country = TopN(config["country_top_n"], config["window_seconds"], config["top_n_min_reports"])
        self.max_attempts = config["max_attempts_per_report"]
        self.bounds = ["+Inf" if bound == "+Inf" else f"{bound / 1000:g}" for bound in bounds]
        self.attempts: dict[tuple, int] = {}
        self.failures: dict[tuple, int] = {}
        self.endpoint_attempts: dict[tuple, int] = {}
        self.endpoint_failures: dict[tuple, int] = {}
        self.network_reports: dict[tuple, int] = {}
        self.latency: dict[str, list[int]] = {}
        self.reports = 0
        self.dropped_buckets = 0
        self.capped_reports = 0
        self.max_series = config["max_series"]
        self.series = 0

    def _network(self, network: dict) -> tuple[TopN | None, str | None]:
        """The ranking and key of the one identity that network.source names; the contract forbids the others."""
        if network["source"] == "sim":
            return self.operator, f'{network["operator"]["mcc"]}-{network["operator"]["mnc"]}'
        if network["source"] == "server_hint":
            return self.asn, f'as{network["asn"]}'
        return None, None

    def add(self, report: dict, now: float) -> None:
        network = report["network"]
        ranking, network_key = self._network(network)
        network_label = ranking.label(network_key, now) if ranking else UNKNOWN
        country_key = network.get("country")
        country = self.country.label(country_key, now) if country_key else UNKNOWN
        # One report adds at most max_attempts attempts: past it every bucket and histogram count is
        # scaled down by the same factor, so one token holder's report cannot outweigh many devices.
        total = sum(bucket["attempts"] for bucket in report["buckets"])
        scale = (lambda count: count * self.max_attempts // total) if total > self.max_attempts else (lambda count: count)
        self.capped_reports += total > self.max_attempts
        for protocol in sorted({bucket["protocol"] for bucket in report["buckets"]}):
            self._bump(self.network_reports, (protocol, network_label), (protocol, OTHER), 1)
        for bucket in report["buckets"]:
            protocol, attempts = bucket["protocol"], scale(bucket["attempts"])
            if not attempts:
                continue
            server_ref = bucket["server_ref"] if bucket["server_ref"] in self.server_refs else OTHER
            self._bump(self.attempts, (protocol, network_label, country), (protocol, OTHER, OTHER), attempts)
            self._bump(self.endpoint_attempts, (protocol, server_ref), (protocol, OTHER), attempts)
            if bucket["outcome"] == "failure":
                stage = bucket["failure_stage"]
                self._bump(self.failures, (protocol, stage, network_label), (protocol, stage, OTHER), attempts)
                self._bump(self.endpoint_failures, (protocol, server_ref), (protocol, OTHER), attempts)
            counts = self.latency.setdefault(protocol, [0] * len(self.bounds))
            for index, count in enumerate(bucket["latency_ms_histogram"]):
                counts[index] += scale(count)
        if report["buckets"]:
            if ranking:
                ranking.observe(network_key, now)
            if country_key:
                self.country.observe(country_key, now)
        self.reports += 1

    def _bump(self, table: dict, key: tuple, overflow: tuple, value: int) -> None:
        # Past the series budget a new label set folds into its protocol's "other" set,
        # so the export stays under the node scrape sample limit whatever clients send.
        if key not in table and self.series >= self.max_series:
            key = overflow
        if key not in table:
            self.series += 1
        table[key] = table.get(key, 0) + value

    def render(self) -> str:
        lines: list[str] = []

        def family(name: str, kind: str, help_text: str, samples) -> None:
            lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"])
            for labels, value in samples:
                body = ",".join(f'{key}="{_escape(val)}"' for key, val in labels)
                lines.append(f"{name}{{{body}}} {value}" if body else f"{name} {value}")

        family("vpn_field_report_reports_total", "counter", "Accepted field reports.", [((), self.reports)])
        family("vpn_field_report_dropped_buckets_total", "counter",
               "Report buckets dropped under the minimum attempts floor.", [((), self.dropped_buckets)])
        family("vpn_field_report_capped_reports_total", "counter",
               "Accepted reports scaled down to the per-report attempts cap.", [((), self.capped_reports)])
        family("vpn_field_report_network_reports_total", "counter",
               "Accepted reports by protocol and network (MCC-MNC, AS number, other or unknown); alerts need several reports, not one large one.",
               [((("protocol", p), ("network", a)), v) for (p, a), v in sorted(self.network_reports.items())])
        family("vpn_field_report_attempts_total", "counter", "Client connection attempts by protocol and network.",
               [((("protocol", p), ("network", a), ("country", c)), v) for (p, a, c), v in sorted(self.attempts.items())])
        family("vpn_field_report_failures_total", "counter", "Failed client attempts by protocol, stage and network.",
               [((("protocol", p), ("failure_stage", s), ("network", a)), v) for (p, s, a), v in sorted(self.failures.items())])
        family("vpn_field_report_endpoint_attempts_total", "counter", "Client attempts by protocol and endpoint.",
               [((("protocol", p), ("server_ref", r)), v) for (p, r), v in sorted(self.endpoint_attempts.items())])
        family("vpn_field_report_endpoint_failures_total", "counter", "Failed client attempts by protocol and endpoint.",
               [((("protocol", p), ("server_ref", r)), v) for (p, r), v in sorted(self.endpoint_failures.items())])
        # Reports carry bucket counts only, so the histogram has no _sum series.
        lines.extend(["# HELP vpn_field_report_latency_seconds Client connect latency by protocol.",
                      "# TYPE vpn_field_report_latency_seconds histogram"])
        for protocol, counts in sorted(self.latency.items()):
            running = 0
            for bound, count in zip(self.bounds, counts):
                running += count
                lines.append(f'vpn_field_report_latency_seconds_bucket{{protocol="{_escape(protocol)}",le="{bound}"}} {running}')
            lines.append(f'vpn_field_report_latency_seconds_count{{protocol="{_escape(protocol)}"}} {running}')
        return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    """Escape a label value per the Prometheus text exposition format."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def write_textfile(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".vpn_field_report.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


class Ingest:
    def __init__(self, config: dict, tokens: tuple, validate, bounds: list) -> None:
        self.config, self.validate = config, validate
        self.current, self.previous, self.previous_until = tokens
        self.aggregate = Aggregate(config, bounds)

    def token_ok(self, header: str | None, now: float) -> bool:
        scheme, _, value = (header or "").partition(" ")
        presented = value.strip().encode() if scheme == "Bearer" else b""
        # Compare against both slots every time so timing does not reveal which one matched.
        current = hmac.compare_digest(presented, self.current)
        previous = self.previous is not None and hmac.compare_digest(presented, self.previous)
        return current or (previous and now < self.previous_until)

    def handle(self, path: str, headers, read_body) -> int:
        if path != self.config["path"]:
            return 404
        try:
            length = int(headers.get("Content-Length", ""))
        except ValueError:
            return 411
        if length < 0:
            return 411
        if length > self.config["max_body_bytes"]:
            return 413
        now = time.time()
        if not self.token_ok(headers.get("Authorization"), now):
            return 401
        try:
            report = json.loads(read_body(length))
        except (ValueError, RecursionError):
            return 400
        # The whole report is validated before anything is counted; the floor applies only to an accepted report.
        if self.validate(report):
            return 400
        floor = self.config["min_attempts"]
        kept = [bucket for bucket in report["buckets"] if bucket["attempts"] >= floor]
        self.aggregate.dropped_buckets += len(report["buckets"]) - len(kept)
        report["buckets"] = kept
        self.aggregate.add(report, now)
        self.flush()
        return 202

    def flush(self) -> None:
        write_textfile(self.config["textfile"], self.aggregate.render())


def make_handler(ingest: Ingest):
    class Handler(BaseHTTPRequestHandler):
        server_version = "field-report"
        sys_version = ""
        timeout = 10

        def log_message(self, format, *args):
            """Request logging is off: a log line would hold the client address."""

        def setup(self):
            super().setup()
            self.deadline = threading.Timer(REQUEST_DEADLINE_SECONDS, self.expire)
            self.deadline.daemon = True
            self.deadline.start()

        def expire(self):
            # Shutting the socket down makes the blocked read return at once; the request then fails closed.
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        def finish(self):
            self.deadline.cancel()
            super().finish()

        def do_POST(self):
            status = ingest.handle(self.path, self.headers, self.rfile.read)
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            if status != 202:
                self.close_connection = True
            self.end_headers()

    return Handler


class QuietServer(HTTPServer):
    def handle_error(self, request, client_address):
        """The default handler prints the client address with the traceback."""
        print(f"vpn-field-report: request failed: {sys.exc_info()[0].__name__}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--tokens", required=True, help="Cohort token JSON file, normally a systemd credential.")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text())
    try:
        tokens = load_tokens(args.tokens)
    except (OSError, ValueError) as error:
        # The message names the failed field, never a token value.
        print(f"vpn-field-report: {error if isinstance(error, ValueError) else 'cohort token file is unreadable'}", file=sys.stderr)
        return 2
    validate, bounds = load_validator(config["validator"], config["schema"])
    ingest = Ingest(config, tokens, validate, bounds)
    ingest.flush()
    server = QuietServer((config["listen"], config["port"]), make_handler(ingest))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
