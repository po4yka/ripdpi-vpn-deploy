#!/usr/bin/env python3
"""Pull authenticated sentinel reports and evaluate rotation policy.

Usage:
    scripts/protocol-liveness.py --config ~/.config/vpn-provision/liveness.yaml
    scripts/protocol-liveness.py --config FILE --state-dir DIR
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "contract" / "protocol-liveness.schema.json"
PROFILES = set(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["profile"]["enum"])
VERDICTS = {"ok", "throttled", "blocked", "unknown", "error"}
ALIVE = {"ok", "throttled"}
REMOTE_COMMAND = ["sudo", "-n", "/usr/local/sbin/vpn-protocol-liveness"]


class ConfigError(ValueError):
    """Configuration cannot be evaluated safely."""


def load_config(path: Path) -> dict:
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read configuration: {exc}") from exc
    try:
        import jsonschema
    except ImportError as exc:
        raise ConfigError("missing jsonschema") from exc
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(config),
        key=lambda error: list(error.absolute_path),
    )
    messages = [
        f"{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in errors
    ]
    messages.extend(semantic_errors(config))
    if messages:
        raise ConfigError("; ".join(messages))
    return config


def semantic_errors(config: dict) -> list[str]:
    messages: list[str] = []
    policies = config.get("policies") or []
    sentinels = config.get("sentinels") or []
    policy_ids = [policy.get("id") for policy in policies if isinstance(policy, dict)]
    sentinel_ids = [sentinel.get("id") for sentinel in sentinels if isinstance(sentinel, dict)]
    for name, values in (("policy", policy_ids), ("sentinel", sentinel_ids)):
        duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
        messages.extend(f"duplicate {name} id: {value}" for value in duplicates)
    known_policies = set(policy_ids)
    assigned = Counter()
    for sentinel in sentinels:
        policy_id = sentinel.get("policy")
        assigned[policy_id] += 1
        if policy_id not in known_policies:
            messages.append(f"sentinel {sentinel.get('id')} references unknown policy: {policy_id}")
    for policy in policies:
        policy_id = policy.get("id")
        quorum = policy.get("min_failed_vantages", 2)
        if quorum > assigned[policy_id]:
            messages.append(
                f"policy {policy_id} quorum {quorum} exceeds assigned sentinels {assigned[policy_id]}"
            )
    return messages


def pull_report(sentinel: dict, timeout: int) -> tuple[str, str, str]:
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"ConnectTimeout={min(timeout, 10)}",
        sentinel["ssh_target"],
        *REMOTE_COMMAND,
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout + 5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return sentinel["id"], "", f"ssh: {type(exc).__name__}"
    if result.returncode != 0:
        return sentinel["id"], "", f"ssh exited {result.returncode}"
    return sentinel["id"], result.stdout.strip(), ""


def validate_report(raw: str, sentinel: dict, config: dict, now: int) -> tuple[dict | None, str]:
    try:
        report = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, f"{sentinel['id']}: malformed report"
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        return None, f"{sentinel['id']}: unsupported report schema"
    if report.get("sentinel") != sentinel["id"]:
        return None, f"{sentinel['id']}: sentinel identity mismatch"
    observed_at = report.get("observed_at")
    if not isinstance(observed_at, int) or abs(now - observed_at) > config.get("stale_after_seconds", 120):
        return None, f"{sentinel['id']}: stale report"
    control = report.get("control") or {}
    if control.get("verdict") not in VERDICTS:
        return None, f"{sentinel['id']}: invalid control verdict"
    runtime = report.get("runtime") or {}
    for key, expected in config["expected_runtime"].items():
        if runtime.get(key) != expected:
            return None, f"{sentinel['id']}: {key} runtime mismatch"
    seen: set[str] = set()
    for profile in report.get("profiles") or []:
        name = profile.get("profile")
        verdict = profile.get("verdict")
        if name not in PROFILES or verdict not in VERDICTS or name in seen:
            return None, f"{sentinel['id']}: invalid profile result"
        seen.add(name)
    policy = next(policy for policy in config["policies"] if policy["id"] == sentinel["policy"])
    missing = sorted(set(policy["required_profiles"]) - seen)
    if missing:
        return None, f"{sentinel['id']}: missing required profiles: {','.join(missing)}"
    return report, ""


def aggregate(config: dict, reports: dict[str, dict], errors: list[str]) -> dict:
    policy_map = {policy["id"]: policy for policy in config["policies"]}
    sentinels = {sentinel["id"]: sentinel for sentinel in config["sentinels"]}
    failed_by_policy: Counter[str] = Counter()
    degraded = False
    evidence: list[dict] = []

    for sentinel_id, report in sorted(reports.items()):
        sentinel = sentinels[sentinel_id]
        policy = policy_map[sentinel["policy"]]
        profiles = {item["profile"]: item["verdict"] for item in report["profiles"]}
        required = policy["required_profiles"]
        control_alive = report["control"]["verdict"] in ALIVE
        profile_verdicts = [profiles[name] for name in required]
        all_blocked = control_alive and all(verdict == "blocked" for verdict in profile_verdicts)
        if all_blocked:
            failed_by_policy[policy["id"]] += 1
        if any(verdict in {"blocked", "throttled"} for verdict in profile_verdicts):
            degraded = True
        if not control_alive or any(verdict in {"unknown", "error"} for verdict in profile_verdicts):
            errors.append(f"{sentinel_id}: indeterminate protocol evidence")
        evidence.append(
            {
                "sentinel": sentinel_id,
                "policy": policy["id"],
                "control": report["control"]["verdict"],
                "profiles": {name: profiles[name] for name in required},
            }
        )

    candidates = sorted(
        policy_id
        for policy_id, count in failed_by_policy.items()
        if count >= policy_map[policy_id].get("min_failed_vantages", 2)
    )
    if candidates:
        decision = "rotation_candidate"
    elif errors:
        decision = "unknown"
    elif degraded:
        decision = "degraded"
    else:
        decision = "healthy"
    return {
        "schema_version": 1,
        "evaluated_at": int(time.time()),
        "decision": decision,
        "candidate_policies": candidates,
        "failed_vantages": dict(sorted(failed_by_policy.items())),
        "monitoring_errors": sorted(set(errors)),
        "evidence": evidence,
    }


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_state(payload: dict, config: dict, config_path: Path, state_dir: Path) -> None:
    state_path = state_dir / "decision-state.json"
    previous: dict = {}
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Missing or malformed advisory state is equivalent to no prior evidence.
        pass
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    same_candidate = (
        previous.get("config_sha256") == config_hash
        and previous.get("candidate_policies") == payload["candidate_policies"]
    )
    interval = config.get("evaluation_interval_seconds", 120)
    minimum_spacing = max(1, interval - min(15, interval // 8))
    previous_accepted_at = previous.get("last_candidate_evaluated_at")
    if payload["decision"] == "rotation_candidate":
        elapsed = (
            payload["evaluated_at"] - previous_accepted_at
            if same_candidate and isinstance(previous_accepted_at, int)
            else None
        )
        if elapsed is not None and 0 <= elapsed < minimum_spacing:
            streak = previous.get("candidate_streak", 0)
            accepted_at = previous_accepted_at
        elif elapsed is not None and elapsed <= interval * 2:
            streak = previous.get("candidate_streak", 0) + 1
            accepted_at = payload["evaluated_at"]
        else:
            streak = 1
            accepted_at = payload["evaluated_at"]
    else:
        streak = 0
        accepted_at = None
    state = {
        "schema_version": 1,
        "candidate_streak": streak,
        "failure_threshold": config.get("failure_threshold", 3),
        "otp_ttl_seconds": config.get("otp_ttl_seconds", 3600),
        "config_sha256": config_hash,
        "candidate_policies": payload["candidate_policies"],
        "evaluated_at": payload["evaluated_at"],
        "last_candidate_evaluated_at": accepted_at,
    }
    atomic_json(state_path, state)
    atomic_json(state_dir / "last-evidence.json", payload)
    payload.update(state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--state-dir", type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"protocol-liveness: {exc}", file=sys.stderr)
        return 2

    timeout = config.get("probe_timeout_seconds", 15)
    raw_reports: dict[str, str] = {}
    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(config["sentinels"])) as pool:
        futures = [pool.submit(pull_report, sentinel, timeout) for sentinel in config["sentinels"]]
        for future in concurrent.futures.as_completed(futures):
            sentinel_id, raw, error = future.result()
            if error:
                errors.append(f"{sentinel_id}: {error}")
            else:
                raw_reports[sentinel_id] = raw

    now = int(time.time())
    sentinel_map = {sentinel["id"]: sentinel for sentinel in config["sentinels"]}
    reports: dict[str, dict] = {}
    for sentinel_id, raw in raw_reports.items():
        report, error = validate_report(raw, sentinel_map[sentinel_id], config, now)
        if error:
            errors.append(error)
        elif report is not None:
            reports[sentinel_id] = report
    payload = aggregate(config, reports, errors)
    if os.environ.get("PROTOCOL_LIVENESS_EVALUATED_AT"):
        payload["evaluated_at"] = int(os.environ["PROTOCOL_LIVENESS_EVALUATED_AT"])
    payload.update(
        {
            "candidate_streak": 0,
            "failure_threshold": config.get("failure_threshold", 3),
            "otp_ttl_seconds": config.get("otp_ttl_seconds", 3600),
            "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        }
    )
    if args.state_dir:
        record_state(payload, config, args.config, args.state_dir)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
