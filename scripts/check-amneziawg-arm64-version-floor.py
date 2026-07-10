#!/usr/bin/env python3
"""Validate the fail-closed AmneziaWG arm64 S3/S4 policy against the repo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = REPO_ROOT / "contract" / "amneziawg-arm64-version-floor.json"


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _policy_errors(policy: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "policy_id",
        "guard_required",
        "candidate_safe_floor",
        "verified_safe_floor",
        "expected_issue_states",
        "release_watch",
        "last_confirmed_broken",
        "ripdpi_reference",
        "revalidation_requirements",
    }
    missing = sorted(required - policy.keys())
    if missing:
        errors.append(f"policy is missing required fields: {', '.join(missing)}")
    if policy.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if (
        policy.get("verified_safe_floor") is None
        and policy.get("guard_required") is not True
    ):
        errors.append("verified_safe_floor is null, so guard_required must remain true")
    issues = policy.get("expected_issue_states")
    expected = {
        ("amnezia-vpn/amneziawg-go", 110, "open"),
        ("amnezia-vpn/amnezia-client", 2582, "closed"),
    }
    if not isinstance(issues, list):
        errors.append("expected_issue_states must be a list")
    else:
        actual = {
            (item.get("repository"), item.get("number"), item.get("state"))
            for item in issues
            if isinstance(item, dict)
        }
        if actual != expected:
            errors.append(f"expected_issue_states must be exactly {sorted(expected)}")
    requirements = policy.get("revalidation_requirements")
    if not isinstance(requirements, list) or len(requirements) < 5:
        errors.append(
            "revalidation_requirements must contain the five physical-test gates"
        )
    return errors


def _repo_errors() -> list[str]:
    errors: list[str] = []
    schema = _load_json(REPO_ROOT / "secrets" / "schema.json")
    awg = schema["properties"]["amneziawg_secrets"]
    for location, node in (
        ("amneziawg_secrets", awg),
        ("amneziawg_secrets.instances[]", awg["properties"]["instances"]["items"]),
    ):
        for field in ("s3", "s4"):
            field_schema = node["properties"].get(field, {})
            if field_schema.get("type") != "integer" or field_schema.get("const") != 0:
                errors.append(
                    f"secrets/schema.json {location}.{field} must remain integer const 0"
                )

    role_tasks = REPO_ROOT / "ansible" / "roles" / "amneziawg" / "tasks"
    role = (role_tasks / "main.yml").read_text(encoding="utf-8") + (
        role_tasks / "guard-s34.yml"
    ).read_text(encoding="utf-8")
    required_role_fragments = (
        "ansible.builtin.import_tasks: guard-s34.yml",
        "_awg_s34 | select('ne', 0) | list | length == 0",
        "amneziawg_cohort",
        "amneziawg_secrets | default({})",
        "_awg_instances_raw",
    )
    for fragment in required_role_fragments:
        if fragment not in role:
            errors.append(
                f"AmneziaWG role guard no longer covers required source: {fragment}"
            )

    emit_awg = (
        (REPO_ROOT / "scripts" / "emit-awg.sh").read_text(encoding="utf-8").lower()
    )
    emit_bundle = (
        (REPO_ROOT / "scripts" / "emit-bundle.sh").read_text(encoding="utf-8").lower()
    )
    if "resolve_param s3" in emit_awg or "resolve_param s4" in emit_awg:
        errors.append(
            "emit-awg.sh must not resolve or emit S3/S4 while the guard is required"
        )
    if "--argjson s3" in emit_bundle or "--argjson s4" in emit_bundle:
        errors.append(
            "emit-bundle.sh must not serialize S3/S4 while the guard is required"
        )

    override_tokens = ("amneziawg_arm64_guard_required", "amneziawg_allow_nonzero_s34")
    override_files = [
        REPO_ROOT / "ansible" / "roles" / "amneziawg" / "defaults" / "main.yml",
        REPO_ROOT / "ansible" / "group_vars" / "all.yml",
    ]
    for path in override_files:
        text = path.read_text(encoding="utf-8")
        for token in override_tokens:
            if token in text:
                errors.append(
                    f"operator override {token} is forbidden in {path.relative_to(REPO_ROOT)}"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args(argv)
    try:
        policy = _load_json(args.policy)
        errors = _policy_errors(policy)
        if not errors:
            errors.extend(_repo_errors())
    except (KeyError, TypeError, ValueError) as error:
        errors = [str(error)]

    if errors:
        print("AmneziaWG arm64 version-floor validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "AmneziaWG arm64 version-floor validation: OK (guard active; verified floor unset)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
