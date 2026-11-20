"""Derive ripdpi bundle v3 endpoint health and field-report configuration.

Health comes from artifacts the sentinels already publish: the
protocol-liveness evaluation (scripts/protocol-liveness.py output, normally
its state directory's last-evidence.json) and an optional cascade-leg health
record checked by scripts/check-cascade-leg-health.py. The generator never
probes. Absent, stale or indeterminate input is published as ``unknown``.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Contract bounds for health.ttl_seconds (contract/ripdpi-bundle.schema.json).
TTL_FLOOR, TTL_CEILING = 60, 86400
DEFAULT_TTL = 900
DEFAULT_MAX_AGE = 1800
# Outbound tag prefix -> sentinel profile; AWG entries use p2-amneziawg.
PROFILES = (("p0-reality-", "p0-reality"), ("p1-xhttp-", "p1-xhttp"), ("p2-hysteria2-", "p2-hysteria2"))
ALIVE = {"ok"}
DEGRADED = {"throttled"}
VERDICTS = ALIVE | DEGRADED | {"blocked", "unknown", "error"}
TOKEN = re.compile(r"^[A-Za-z0-9_-]{22,64}$")


def _instant(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(path: str) -> dict:
    """Read and bound the operator health configuration (BUNDLE_HEALTH_FILE)."""
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict) or set(config) - {"liveness", "policies", "cascade_leg_health", "max_age_seconds",
                                                      "ttl_seconds", "max_ttl_seconds", "min_failed_vantages"}:
        raise ValueError("invalid-health-config")
    max_ttl = config.get("max_ttl_seconds", TTL_CEILING)
    ttl = config.get("ttl_seconds", DEFAULT_TTL)
    if type(max_ttl) is not int or not TTL_FLOOR <= max_ttl <= TTL_CEILING:
        raise ValueError("invalid-health-config")
    if type(ttl) is not int or ttl < TTL_FLOOR:
        raise ValueError("invalid-health-config")
    if ttl > max_ttl:
        raise ValueError("health-ttl-exceeds-maximum")
    age = config.get("max_age_seconds", DEFAULT_MAX_AGE)
    quorum = config.get("min_failed_vantages", 2)
    policies = config.get("policies", {})
    legs = config.get("cascade_leg_health", {})
    if (type(age) is not int or age < 60 or type(quorum) is not int or quorum < 1
            or not isinstance(policies, dict) or not isinstance(legs, dict)
            or any(not isinstance(v, str) for v in (*policies.values(), *legs.values()))
            or ("liveness" in config and not isinstance(config["liveness"], str))):
        raise ValueError("invalid-health-config")
    return config


def _liveness(config: dict) -> dict:
    path = config.get("liveness")
    if not path or not Path(path).is_file():
        return {}
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _leg_healthy(path: str | None, now: dt.datetime) -> bool | None:
    """None when no leg is configured; otherwise whether the leg is proven healthy."""
    if path is None:
        return None
    spec = importlib.util.spec_from_file_location("check_cascade_leg_health", ROOT / "scripts/check-cascade-leg-health.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.validate_leg_health(Path(path), now)
    except module.LegHealthBlocked:
        return False
    return True


def profile_status(evidence: list, policy: str, profile: str, tag: str, quorum: int, now: dt.datetime, max_age: int):
    """Status and newest observation time for the exact endpoint in the liveness policy."""
    verdicts, newest = [], None
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict) or item.get("policy") != policy:
            continue
        observed = item.get("observed_at")
        if profile == "p2-amneziawg":
            profiles = item.get("profiles")
            verdict = profiles.get(profile) if isinstance(profiles, dict) else None
        else:
            variants = item.get("endpoint_variants")
            rows = variants.get(profile) if isinstance(variants, dict) else None
            if not isinstance(rows, list):
                continue
            verdict = next((row.get("verdict") for row in rows
                            if isinstance(row, dict) and row.get("server_ref") == tag), None)
        if type(observed) is not int or not isinstance(verdict, str) or verdict not in VERDICTS:
            continue
        try:
            observed_at = dt.datetime.fromtimestamp(observed, dt.timezone.utc)
        except (ValueError, OverflowError, OSError):
            continue
        if observed_at > now or (now - observed_at).total_seconds() > max_age:
            continue
        verdicts.append(verdict)
        newest = observed_at if newest is None else max(newest, observed_at)
    if not verdicts:
        return "unknown", None
    if sum(verdict == "blocked" for verdict in verdicts) >= quorum:
        return "down", newest
    if all(verdict in ALIVE for verdict in verdicts):
        return "healthy", newest
    # Below the blocked quorum, any failed, throttled or indeterminate vantage beside a working one is degraded.
    if any(verdict in ALIVE | DEGRADED for verdict in verdicts) or "blocked" in verdicts:
        return "degraded", newest
    return "unknown", newest


def profile_for(tag: str, awg: bool) -> str | None:
    if awg:
        return "p2-amneziawg"
    return next((name for prefix, name in PROFILES if tag.startswith(prefix)), None)


def endpoint_health(endpoints: dict[str, tuple[str, str | None]], config: dict | None, now: dt.datetime) -> dict:
    """Map each server_ref to its health object.

    ``endpoints`` maps an outbound or AWG tag to its ``provider:environment``
    host and sentinel profile (None when no sentinel probes that transport).
    """
    config = config or {}
    ttl = config.get("ttl_seconds", DEFAULT_TTL)
    evidence = _liveness(config).get("evidence", [])
    hosts = {host for host, _ in endpoints.values()}
    legs = {host: _leg_healthy(config.get("cascade_leg_health", {}).get(host), now) for host in hosts}
    result = {}
    for tag, (host, profile) in sorted(endpoints.items()):
        policy = config.get("policies", {}).get(host)
        status, observed = ("unknown", None)
        if profile is not None and policy is not None:
            status, observed = profile_status(evidence, policy, profile, tag, config.get("min_failed_vantages", 2), now,
                                              config.get("max_age_seconds", DEFAULT_MAX_AGE))
        if legs[host] is False and status != "down":
            # A cascade leg that is not proven healthy cannot certify the endpoint behind it.
            status = "unknown"
        result[tag] = {"health": {"status": status, "observed_at": _instant(observed or now), "ttl_seconds": ttl}}
    return result


def field_report_block(document: dict) -> dict | None:
    """The ripdpi.field_report block from the SOPS field_report key, or None when it is off."""
    source = document.get("field_report")
    if source is None or not source.get("enabled", False):
        return None
    endpoint, token, per_day = source.get("endpoint"), source.get("cohort_token"), source.get("max_reports_per_day")
    if (not isinstance(endpoint, str) or not re.fullmatch(r"https://[^\s/?#@]+(/[^\s#]*)?", endpoint)
            or not isinstance(token, str) or not TOKEN.fullmatch(token)
            or type(per_day) is not int or not 1 <= per_day <= 24):
        raise ValueError("invalid-field-report-config")
    block = {"endpoint": endpoint, "cohort_token": token, "max_reports_per_day": per_day}
    hint = source.get("network_hint_endpoint")
    if hint is not None:
        if not isinstance(hint, str) or not re.fullmatch(r"https://[^\s/?#@]+(/[^\s#]*)?", hint):
            raise ValueError("invalid-field-report-config")
        block["network_hint_endpoint"] = hint
    return block
