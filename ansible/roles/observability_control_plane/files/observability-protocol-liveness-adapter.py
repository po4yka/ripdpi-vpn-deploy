#!/usr/bin/env python3
"""Adapt canonical published protocol-liveness evidence without evaluating it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any

MAX_INPUT_BYTES = 1024 * 1024
MAX_EVIDENCE = 16
MAX_VARIANTS = 16
ALIAS = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
DECISIONS = frozenset({"healthy", "degraded", "unknown", "rotation_candidate"})
VERDICTS = frozenset({"ok", "blocked", "throttled", "error", "unknown"})
# Sentinel profile -> client field-report protocol enum value.
PROTOCOLS = {
    "p0-reality": "vless-reality",
    "p1-xhttp": "xhttp",
    "p2-hysteria2": "hysteria2",
    "p2-amneziawg": "amneziawg",
}
SUCCESS = {"ok": 1, "throttled": 1, "blocked": 0, "error": 0}
# Upper bounds in seconds; the same bounds as the client field-report latency histogram.
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
MAX_DURATION_MS = 600_000
MAX_STATE_BYTES = 256 * 1024


class AdapterError(Exception):
    """The published evidence cannot be adapted safely."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, Any]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_nlink != 1
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise AdapterError("invalid evidence")
        payload = os.read(descriptor, MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise AdapterError("invalid evidence") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > MAX_INPUT_BYTES:
        raise AdapterError("invalid evidence")
    try:
        document = json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise AdapterError("invalid evidence") from exc
    if not isinstance(document, dict):
        raise AdapterError("invalid evidence")
    return document


def _alias(value: Any) -> bool:
    return isinstance(value, str) and ALIAS.fullmatch(value) is not None


def _integer(value: Any, *, maximum: int | None = None) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and value >= 0
        and (maximum is None or value <= maximum)
    )


def _role(*parts: str) -> str:
    value = "-".join(parts)
    if not _alias(value):
        raise AdapterError("invalid evidence")
    return value


def _validate(
    document: dict[str, Any],
) -> tuple[int, str, list[dict[str, Any]], list[str], dict[str, int]]:
    required = {
        "schema_version",
        "evaluated_at",
        "decision",
        "candidate_policies",
        "failed_vantages",
        "monitoring_errors",
        "evidence",
    }
    if not required.issubset(document) or document["schema_version"] != 2:
        raise AdapterError("invalid evidence")
    evaluated_at = document["evaluated_at"]
    decision = document["decision"]
    if (
        not _integer(evaluated_at)
        or not isinstance(decision, str)
        or decision not in DECISIONS
    ):
        raise AdapterError("invalid evidence")
    candidates = document["candidate_policies"]
    failures = document["failed_vantages"]
    evidence = document["evidence"]
    if (
        not isinstance(candidates, list)
        or len(candidates) > MAX_EVIDENCE
        or not all(_alias(value) for value in candidates)
        or len(candidates) != len(set(candidates))
        or not isinstance(failures, dict)
        or len(failures) > MAX_EVIDENCE
        or not all(
            _alias(key) and _integer(value, maximum=MAX_EVIDENCE)
            for key, value in failures.items()
        )
        or not isinstance(evidence, list)
        or len(evidence) > MAX_EVIDENCE
    ):
        raise AdapterError("invalid evidence")
    identities: set[tuple[str, str]] = set()
    sentinels: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict) or not {
            "sentinel",
            "policy",
            "control",
            "profiles",
            "observed_at",
        }.issubset(item):
            raise AdapterError("invalid evidence")
        sentinel = item["sentinel"]
        policy = item["policy"]
        control = item["control"]
        profiles = item["profiles"]
        if (
            not _alias(sentinel)
            or not _alias(policy)
            or not isinstance(control, str)
            or control not in VERDICTS
            or not _integer(item["observed_at"])
            or not isinstance(profiles, dict)
            or not 1 <= len(profiles) <= 4
            or not all(
                _alias(name) and isinstance(verdict, str) and verdict in VERDICTS
                for name, verdict in profiles.items()
            )
        ):
            raise AdapterError("invalid evidence")
        if sentinel in sentinels:
            raise AdapterError("invalid evidence")
        sentinels.add(sentinel)
        for profile in profiles:
            identity = (sentinel, profile)
            if identity in identities:
                raise AdapterError("invalid evidence")
            identities.add(identity)
        variants = item.get("endpoint_variants", {})
        if not isinstance(variants, dict) or set(variants) - set(profiles):
            raise AdapterError("invalid evidence")
        for profile, rows in variants.items():
            if not isinstance(rows, list) or len(rows) > MAX_VARIANTS:
                raise AdapterError("invalid evidence")
            seen_variants: set[int] = set()
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or set(row) != {"variant", "verdict"}
                    or not _integer(row["variant"], maximum=MAX_VARIANTS)
                    or row["variant"] < 1
                    or row["variant"] in seen_variants
                    or not isinstance(row["verdict"], str)
                    or row["verdict"] not in VERDICTS
                ):
                    raise AdapterError("invalid evidence")
                seen_variants.add(row["variant"])
        durations = item.get("profile_durations_ms", {})
        if (
            not isinstance(durations, dict)
            or set(durations) - set(profiles)
            or not all(
                _integer(value, maximum=MAX_DURATION_MS) for value in durations.values()
            )
        ):
            raise AdapterError("invalid evidence")
    return evaluated_at, decision, evidence, sorted(candidates), failures


def _metric(node: str, role: str, state: str, value: int) -> str:
    return f'vpn_observability_evidence_state{{node="{node}",role="{role}",state="{state}"}} {value}'


def _failure(state: str, stale_after: int) -> bytes:
    return (
        "# TYPE vpn_observability_evidence_state gauge\n"
        + f'vpn_observability_evidence_max_age_seconds{{node="protocol-liveness",role="liveness-published-evidence"}} {stale_after}\n'
        + _metric("protocol-liveness", "liveness-published-evidence", state, 1)
        + "\n"
    ).encode("utf-8")


def _probe_labels(protocol: str, node: str, vantage: str) -> str:
    return f'node="{node}",protocol="{protocol}",vantage="{vantage}"'


def _probe_lines(
    evidence: list[dict[str, Any]],
    *,
    now: int,
    stale_after: int,
    histogram: dict[str, dict[str, Any]],
) -> list[str]:
    """Per-protocol probe gauges plus cumulative latency histograms.

    `histogram` maps "protocol|node|vantage" to the last counted observed_at,
    per-bucket counts and the millisecond sum. It is replaced with the current
    series only, so an absent series restarts from zero (a counter reset).
    """
    success: list[str] = []
    observed: list[str] = []
    durations: list[str] = []
    current: dict[str, dict[str, Any]] = {}
    for item in sorted(evidence, key=lambda value: (value["policy"], value["sentinel"])):
        fresh = now - item["observed_at"] <= stale_after
        for profile, verdict in sorted(item["profiles"].items()):
            protocol = PROTOCOLS.get(profile)
            if protocol is None:
                continue
            key = f"{protocol}|{item['policy']}|{item['sentinel']}"
            labels = _probe_labels(protocol, item["policy"], item["sentinel"])
            observed.append(
                f"vpn_protocol_probe_observed_timestamp_seconds{{{labels}}} {item['observed_at']}"
            )
            series = histogram.get(key)
            if series is None:
                series = {"observed_at": -1, "bins": [0] * (len(BUCKETS) + 1), "sum_ms": 0}
            current[key] = series
            # A stale or indeterminate probe is unknown: no success value is published.
            if not fresh or verdict not in SUCCESS:
                continue
            success.append(f"vpn_protocol_probe_success{{{labels}}} {SUCCESS[verdict]}")
            duration = item.get("profile_durations_ms", {}).get(profile)
            if SUCCESS[verdict] and duration is not None and item["observed_at"] > series["observed_at"]:
                seconds = duration / 1000
                index = next(
                    (i for i, bound in enumerate(BUCKETS) if seconds <= bound), len(BUCKETS)
                )
                series["bins"][index] += 1
                series["sum_ms"] += duration
                series["observed_at"] = item["observed_at"]
    for key, series in sorted(current.items()):
        labels = _probe_labels(*key.split("|"))
        cumulative = 0
        for bound, count in zip((*BUCKETS, None), series["bins"]):
            cumulative += count
            le = "+Inf" if bound is None else repr(bound)
            durations.append(
                f'vpn_protocol_probe_duration_seconds_bucket{{{labels},le="{le}"}} {cumulative}'
            )
        durations.append(
            f"vpn_protocol_probe_duration_seconds_sum{{{labels}}} {series['sum_ms'] / 1000}"
        )
        durations.append(f"vpn_protocol_probe_duration_seconds_count{{{labels}}} {cumulative}")
    histogram.clear()
    histogram.update(current)
    return [
        "# TYPE vpn_protocol_probe_success gauge",
        *success,
        "# TYPE vpn_protocol_probe_observed_timestamp_seconds gauge",
        *observed,
        "# TYPE vpn_protocol_probe_duration_seconds histogram",
        *durations,
    ]


def _load_histogram(path: Path | None) -> dict[str, dict[str, Any]]:
    """Read bounded adapter-owned histogram state; anything unexpected starts from zero."""
    if path is None:
        return {}
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise AdapterError("invalid state") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise AdapterError("invalid state")
        payload = os.read(descriptor, MAX_STATE_BYTES + 1)
    finally:
        os.close(descriptor)
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, ValueError):
        return {}
    if not isinstance(document, dict) or len(payload) > MAX_STATE_BYTES:
        return {}
    valid: dict[str, dict[str, Any]] = {}
    for key, series in document.items():
        parts = key.split("|") if isinstance(key, str) else []
        if (
            len(parts) != 3
            or parts[0] not in PROTOCOLS.values()
            or not all(_alias(part) for part in parts[1:])
            or not isinstance(series, dict)
            or set(series) != {"observed_at", "bins", "sum_ms"}
            or not isinstance(series["observed_at"], int)
            or isinstance(series["observed_at"], bool)
            or not isinstance(series["bins"], list)
            or len(series["bins"]) != len(BUCKETS) + 1
            or not all(_integer(count) for count in series["bins"])
            or not _integer(series["sum_ms"])
        ):
            return {}
        valid[key] = series
    return valid


def render(
    document: dict[str, Any],
    *,
    now: int,
    stale_after: int,
    max_future: int,
    histogram: dict[str, dict[str, Any]] | None = None,
) -> bytes:
    evaluated_at, decision, evidence, candidates, failures = _validate(document)
    if evaluated_at > now + max_future:
        raise AdapterError("future evidence")
    if now - evaluated_at > stale_after:
        raise AdapterError("stale evidence")
    lines = [
        "# TYPE vpn_observability_evidence_state gauge",
        f'vpn_observability_evidence_timestamp_seconds{{node="protocol-liveness",role="liveness-published-evidence"}} {evaluated_at}',
        f'vpn_observability_evidence_max_age_seconds{{node="protocol-liveness",role="liveness-published-evidence"}} {stale_after}',
    ]
    lines.append(
        _metric(
            "protocol-liveness",
            _role("liveness", "decision", decision.replace("_", "-")),
            "fresh",
            1,
        )
    )
    lines.append(
        _metric("protocol-liveness", "liveness-evaluated-at", "fresh", evaluated_at)
    )
    for policy, failures_count in sorted(failures.items()):
        lines.append(
            _metric(policy, "liveness-failed-vantages", "fresh", failures_count)
        )
    for policy in candidates:
        lines.append(_metric(policy, "liveness-rotation-candidate", "fresh", 1))
    for item in sorted(
        evidence, key=lambda value: (value["sentinel"], value["policy"])
    ):
        sentinel = item["sentinel"]
        lines.append(
            _metric(sentinel, _role("liveness", "control", item["control"]), "fresh", 1)
        )
        lines.append(
            _metric(sentinel, "liveness-observed-at", "fresh", item["observed_at"])
        )
        for profile, verdict in sorted(item["profiles"].items()):
            lines.append(
                _metric(sentinel, _role("liveness", profile, verdict), "fresh", 1)
            )
        for profile, variants in sorted(item.get("endpoint_variants", {}).items()):
            for variant in variants:
                lines.append(
                    _metric(
                        sentinel,
                        _role(
                            "liveness",
                            profile,
                            "variant",
                            str(variant["variant"]),
                            variant["verdict"],
                        ),
                        "fresh",
                        1,
                    )
                )
    lines.extend(
        _probe_lines(
            evidence,
            now=now,
            stale_after=stale_after,
            histogram={} if histogram is None else histogram,
        )
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    parent = path.parent
    try:
        metadata = parent.lstat()
    except OSError as exc:
        raise AdapterError("invalid output") from exc
    strict_parent = (
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0
    )
    shared_textfile_parent = (
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and metadata.st_mode & stat.S_IWOTH == 0
        and metadata.st_mode & stat.S_IWGRP != 0
        and metadata.st_mode & stat.S_ISGID != 0
        and metadata.st_mode & stat.S_ISVTX != 0
    )
    if not (strict_parent or shared_textfile_parent):
        raise AdapterError("invalid output")
    try:
        previous = path.lstat()
    except FileNotFoundError:
        previous = None
    if previous is not None and (
        not stat.S_ISREG(previous.st_mode)
        or previous.st_nlink != 1
        or previous.st_uid not in {0, os.geteuid()}
    ):
        raise AdapterError("invalid output")
    temporary: Path | None = None
    descriptor = -1
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
            raise AdapterError("invalid output")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fchmod(descriptor, 0o640)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise AdapterError("invalid output") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                # Atomic replacement or concurrent cleanup may have consumed this name.
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--now", type=int, default=int(time.time()))
    parser.add_argument("--stale-after", type=int, required=True)
    parser.add_argument("--max-future", type=int, required=True)
    args = parser.parse_args(argv)
    if (
        args.now < 0
        or not 30 <= args.stale_after <= 3600
        or not 0 <= args.max_future <= 300
    ):
        print(
            "observability-protocol-liveness-adapter: validation failed",
            file=sys.stderr,
        )
        return 2
    try:
        histogram = _load_histogram(args.state)
        payload = render(
            _load(args.evidence),
            now=args.now,
            stale_after=args.stale_after,
            max_future=args.max_future,
            histogram=histogram,
        )
        if args.state is not None:
            _atomic_write(
                args.state, json.dumps(histogram, sort_keys=True).encode("utf-8")
            )
        _atomic_write(args.output, payload)
    except AdapterError as exc:
        state = (
            "future"
            if str(exc) == "future evidence"
            else "stale"
            if str(exc) == "stale evidence"
            else "malformed"
        )
        try:
            _atomic_write(args.output, _failure(state, args.stale_after))
        except AdapterError:
            # Preserve the original invalid-evidence result if failure exposition fails.
            pass
        print(
            "observability-protocol-liveness-adapter: validation failed",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
