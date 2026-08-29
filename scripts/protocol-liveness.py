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
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import yaml
from fleet_inspection import InspectionError, bounded_command
from liveness_generation import probe_deadline


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "contract" / "protocol-liveness.schema.json"
PROFILES = set(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["profile"]["enum"])
VERDICTS = {"ok", "throttled", "blocked", "unknown", "error"}
ALIVE = {"ok", "throttled"}
REMOTE_COMMAND = ["sudo", "-n", "/usr/local/sbin/vpn-protocol-liveness"]
RUNTIME_KEYS = {"sing_box", "xray", "awg", "awg_toolchain"}
PROVENANCE_KEYS = {"controller_revision", "runner_sha256", "client_generation_id", "public_profile_digest", "vantage"}
TARGET_IDENTITY_KEYS = {
    "inventory_alias", "public_service_address_sha256", "deployable_digest", "applied_at",
    "required_profiles", "source_revision", "runner_sha256", "public_profile_digest",
}


class ConfigError(ValueError):
    """Configuration cannot be evaluated safely."""


def required_runtime(policy: dict) -> set[str]:
    profiles = set(policy["required_profiles"])
    return ({"sing_box"} if profiles & {"p0-reality", "p2-hysteria2"} else set()) | (
        {"xray"} if "p1-xhttp" in profiles else set()) | (
        {"awg", "awg_toolchain"} if "p2-amneziawg" in profiles else set())


def load_config(path: Path) -> dict:
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        raise ConfigError("cannot read configuration") from None
    return validate_config(config)


def validate_config(config: dict) -> dict:
    try:
        import jsonschema
    except ImportError as exc:
        raise ConfigError("missing jsonschema") from exc
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(config),
        key=lambda error: tuple(map(str, error.absolute_path)),
    )
    messages = []
    for error in errors:
        path = list(error.absolute_path)
        if error.validator == "required" and isinstance(error.instance, dict):
            path += [key for key in error.validator_value if key not in error.instance][:1]
        messages.append(f"{'.'.join(map(str, path)) or '<root>'}: invalid {error.validator}")
    if not errors:
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
        policy = next((p for p in policies if p.get("id") == policy_id), {})
        if "p2-amneziawg" in policy.get("required_profiles", []) and not sentinel.get("awg_target"):
            messages.append(f"sentinel {sentinel.get('id')}: migration required: explicit awg_target provider/environment/instance")
    for policy in policies:
        policy_id = policy.get("id")
        quorum = policy.get("min_failed_vantages", 2)
        if quorum > assigned[policy_id]:
            messages.append(
                f"policy {policy_id} quorum {quorum} exceeds assigned sentinels {assigned[policy_id]}"
            )
        required = policy.get("required_profiles", [])
        runtime = config.get("expected_runtime", {})
        for key in required_runtime(policy) - {"xray", "awg_toolchain"}:
            if not runtime.get(key):
                messages.append(f"migration required: expected_runtime.{key} pin")
        if "p1-xhttp" in required and not runtime.get("xray"):
            messages.append("migration required: expected_runtime.xray pin for p1-xhttp")
        if "p2-amneziawg" in required:
            if not runtime.get("awg_toolchain"):
                messages.append("migration required: expected_runtime.awg_toolchain source-input digest")
            try:
                raw_url = config.get("probe_url", "")
                if not isinstance(raw_url, str) or any(ord(char) <= 32 for char in raw_url):
                    raise ValueError
                url = urlparse(raw_url)
                valid_url = (url.scheme == "https" and url.hostname and ":" not in url.hostname
                             and url.port in (None, 443) and url.username is None and url.password is None
                             and not url.fragment)
            except ValueError:
                valid_url = False
            if not valid_url:
                messages.append("AWG probe requires IPv4 HTTPS port 443 without credentials or fragment")
    return messages


def remote_probe_deadline(config: dict, sentinel: dict) -> int:
    policy = next(policy for policy in config["policies"] if policy["id"] == sentinel["policy"])
    # SSH connection and fixed remote startup must not consume the probe budget.
    return probe_deadline(config.get("probe_timeout_seconds", 15), policy["required_profiles"]) + 20


def ssh_options(sentinel: dict, connect_timeout: int) -> list[str]:
    values = ["BatchMode=yes", "StrictHostKeyChecking=yes", "UpdateHostKeys=no",
              "VerifyHostKeyDNS=no", f"ConnectTimeout={min(connect_timeout, 10)}", "ConnectionAttempts=1",
              "ProxyCommand=none", "ProxyJump=none", "ControlMaster=no", "ControlPath=none", "ControlPersist=no",
              "ClearAllForwardings=yes", "ForwardAgent=no", "ForwardX11=no", "PermitLocalCommand=no",
              "RemoteCommand=none", "RequestTTY=no", "PasswordAuthentication=no", "KbdInteractiveAuthentication=no",
              "GSSAPIAuthentication=no", "HostbasedAuthentication=no", "PreferredAuthentications=publickey",
              "NumberOfPasswordPrompts=0", "LogLevel=ERROR"]
    transport_host = sentinel.get("ssh_transport_host")
    if transport_host:
        values.extend([f"HostName={transport_host}", f"HostKeyAlias={sentinel['ssh_host_key_alias']}"])
    return [argument for value in values for argument in ("-o", value)]


def pull_report(sentinel: dict, connect_timeout: int, command_timeout: int) -> tuple[str, str, str]:
    command = [
        "ssh",
        *ssh_options(sentinel, connect_timeout),
        "--",
        sentinel["ssh_target"],
        *REMOTE_COMMAND,
    ]
    try:
        environment = {key: os.environ[key] for key in ("PATH", "HOME", "SSH_AUTH_SOCK") if key in os.environ}
        environment.update({"LANG": "C", "LC_ALL": "C"})
        raw = bounded_command(command, timeout=command_timeout, limit=65536, environment=environment)
        return sentinel["id"], raw.decode("utf-8").strip(), ""
    except (InspectionError, UnicodeError):
        return sentinel["id"], "", "ssh: unavailable or invalid bounded report"


def validate_report(raw: str, sentinel: dict, config: dict, now: int) -> tuple[dict | None, str]:
    if not isinstance(raw, str) or len(raw) > 65536:
        return None, f"{sentinel['id']}: malformed report"
    try:
        report = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        return None, f"{sentinel['id']}: malformed report"
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 2:
        return None, f"{sentinel['id']}: unsupported report schema"
    if report.get("sentinel") != sentinel["id"]:
        return None, f"{sentinel['id']}: sentinel identity mismatch"
    observed_at = report.get("observed_at")
    if type(observed_at) is not int or not now - config.get("stale_after_seconds", 120) <= observed_at <= now:
        return None, f"{sentinel['id']}: stale report"
    control = report.get("control")
    if not isinstance(control, dict) or not isinstance(control.get("verdict"), str) or control["verdict"] not in VERDICTS:
        return None, f"{sentinel['id']}: invalid control verdict"
    provenance = report.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_KEYS:
        return None, f"{sentinel['id']}: invalid provenance"
    for key, size in (("controller_revision", 40), ("runner_sha256", 64), ("public_profile_digest", 64)):
        if not isinstance(provenance[key], str) or re.fullmatch(r"[0-9a-f]{" + str(size) + "}", provenance[key]) is None:
            return None, f"{sentinel['id']}: invalid provenance"
    identity = provenance["client_generation_id"]
    try:
        if not isinstance(identity, str) or str(UUID(identity)) != identity:
            raise ValueError
    except ValueError:
        return None, f"{sentinel['id']}: invalid provenance"
    if provenance["vantage"] not in ("external", "filtered") or provenance["vantage"] != sentinel["vantage"]:
        return None, f"{sentinel['id']}: provenance vantage mismatch"
    policy = next(policy for policy in config["policies"] if policy["id"] == sentinel["policy"])
    target = report.get("target_identity")
    required = sorted(policy["required_profiles"])
    if not isinstance(target, dict) or set(target) != TARGET_IDENTITY_KEYS:
        return None, f"{sentinel['id']}: invalid target identity"
    declared = sentinel["target"]
    if any(target.get(key) != declared[key] for key in declared):
        return None, f"{sentinel['id']}: target identity mismatch"
    if (
        target.get("required_profiles") != required
        or target.get("source_revision") != provenance["controller_revision"]
        or target.get("runner_sha256") != provenance["runner_sha256"]
        or target.get("public_profile_digest") != provenance["public_profile_digest"]
        or type(target.get("applied_at")) is not int
        or target["applied_at"] < 1
        or observed_at < target["applied_at"]
        or not isinstance(target.get("inventory_alias"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", target["inventory_alias"]) is None
        or any(not isinstance(target.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", target[key]) is None
               for key in ("public_service_address_sha256", "deployable_digest", "runner_sha256", "public_profile_digest"))
        or not isinstance(target.get("source_revision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", target["source_revision"]) is None
    ):
        return None, f"{sentinel['id']}: invalid target identity"
    runtime = report.get("runtime")
    if (not isinstance(runtime, dict) or set(runtime) - RUNTIME_KEYS
            or any(not isinstance(value, str) or re.fullmatch(
                r"[0-9a-f]{64}" if key == "awg_toolchain" else r"(?:\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?|missing|unknown)", value) is None
                   for key, value in runtime.items())):
        return None, f"{sentinel['id']}: invalid runtime evidence"
    for key in sorted(required_runtime(policy)):
        if runtime.get(key) != config["expected_runtime"].get(key) or key not in runtime:
            return None, f"{sentinel['id']}: {key} runtime mismatch"
    if not isinstance(report.get("profiles"), list):
        return None, f"{sentinel['id']}: invalid profile result"
    seen: set[str] = set()
    for profile in report["profiles"]:
        if not isinstance(profile, dict):
            return None, f"{sentinel['id']}: invalid profile result"
        name = profile.get("profile")
        verdict = profile.get("verdict")
        if not isinstance(name, str) or not isinstance(verdict, str) or name not in PROFILES or verdict not in VERDICTS or name in seen:
            return None, f"{sentinel['id']}: invalid profile result"
        transport = profile.get("payload_transport", "unknown")
        family = profile.get("target_address_family", "unknown")
        if transport not in ("tcp-https", "unknown") or (transport == "unknown" and verdict != "error"):
            return None, f"{sentinel['id']}: invalid payload transport evidence"
        if family not in (("ipv4", "unknown") if name == "p2-amneziawg" else ("unknown",)):
            return None, f"{sentinel['id']}: invalid target address family evidence"
        if type(profile.get("dns_through_tunnel")) is not bool or type(profile.get("authenticated_handshake")) is not bool:
            return None, f"{sentinel['id']}: invalid positive proof evidence"
        if verdict in ALIVE and (profile["dns_through_tunnel"] is not True or profile["authenticated_handshake"] is not True):
            return None, f"{sentinel['id']}: missing positive proof evidence"
        if "fresh_handshake" in profile and (name != "p2-amneziawg" or type(profile["fresh_handshake"]) is not bool):
            return None, f"{sentinel['id']}: invalid handshake evidence"
        if name == "p2-amneziawg" and verdict in ALIVE and (family != "ipv4" or profile.get("fresh_handshake") is not True):
            return None, f"{sentinel['id']}: missing authenticated AWG evidence"
        variants = profile.get("variants")
        if name != "p2-amneziawg" and verdict != "error" and not variants:
            return None, f"{sentinel['id']}: missing endpoint variant evidence"
        if variants is not None:
            if not isinstance(variants, list) or not variants:
                return None, f"{sentinel['id']}: invalid endpoint variant evidence"
            variant_ids: set[int] = set()
            for variant in variants:
                if not isinstance(variant, dict):
                    return None, f"{sentinel['id']}: invalid endpoint variant evidence"
                variant_id = variant.get("variant")
                if (
                    type(variant_id) is not int
                    or variant_id < 1
                    or variant_id in variant_ids
                    or not isinstance(variant.get("verdict"), str) or variant["verdict"] not in VERDICTS
                ):
                    return None, f"{sentinel['id']}: invalid endpoint variant evidence"
                variant_ids.add(variant_id)
            variant_verdicts = {variant["verdict"] for variant in variants}
            expected_verdict = next(value for value in ("ok", "throttled", "error", "unknown", "blocked") if value in variant_verdicts)
            if verdict != expected_verdict:
                return None, f"{sentinel['id']}: inconsistent endpoint variant verdict"
        seen.add(name)
    if seen != set(policy["required_profiles"]):
        return None, f"{sentinel['id']}: profile set mismatch"
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
        profile_results = {item["profile"]: item for item in report["profiles"]}
        profiles = {name: item["verdict"] for name, item in profile_results.items()}
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
        endpoint_variants = {
            name: [
                {"variant": variant["variant"], "verdict": variant["verdict"]}
                for variant in profile_results[name].get("variants") or []
            ]
            for name in required
            if profile_results[name].get("variants")
        }
        item = {
            "sentinel": sentinel_id,
            "policy": policy["id"],
            "control": report["control"]["verdict"],
            "profiles": {name: profiles[name] for name in required},
            "observed_at": report["observed_at"],
            "runtime": {key: report["runtime"][key] for key in sorted(RUNTIME_KEYS & report["runtime"].keys())},
            "provenance": {key: report["provenance"][key] for key in sorted(PROVENANCE_KEYS)},
            "target_identity": report["target_identity"],
            "profile_observations": {
                name: {
                    "payload_transport": profile_results[name].get("payload_transport", "unknown"),
                    "target_address_family": profile_results[name].get("target_address_family", "unknown"),
                    "dns_through_tunnel": profile_results[name]["dns_through_tunnel"],
                    "authenticated_handshake": profile_results[name]["authenticated_handshake"],
                    **({"fresh_handshake": True} if name == "p2-amneziawg" and profiles[name] in ALIVE
                       and profile_results[name].get("fresh_handshake") is True else {}),
                } for name in required
            },
        }
        if endpoint_variants:
            item["endpoint_variants"] = endpoint_variants
        evidence.append(item)

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
        "schema_version": 2,
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
    payload.update({key: value for key, value in state.items() if key != "schema_version"})


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
        futures = [
            pool.submit(pull_report, sentinel, timeout, remote_probe_deadline(config, sentinel))
            for sentinel in config["sentinels"]
        ]
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
