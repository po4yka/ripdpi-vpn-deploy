#!/usr/bin/env python3
"""Validate the fail-closed AmneziaWG arm64 S3/S4 policy against the repo."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

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
        ("amnezia-vpn/amneziawg-go", 110),
        ("amnezia-vpn/amnezia-client", 2582),
    }
    if not isinstance(issues, list):
        errors.append("expected_issue_states must be a list")
    else:
        actual = {
            (item.get("repository"), item.get("number"))
            for item in issues
            if isinstance(item, dict)
        }
        if actual != expected:
            errors.append(f"expected_issue_states must be exactly {sorted(expected)}")
        if any(
            not isinstance(item, dict) or item.get("state") not in {"open", "closed"}
            for item in issues
        ):
            errors.append("tracked issue states must be open or closed")
    requirements = policy.get("revalidation_requirements")
    if not isinstance(requirements, list) or len(requirements) < 5:
        errors.append(
            "revalidation_requirements must contain the five physical-test gates"
        )
    return errors


def _yaml_tasks(path: Path) -> list[dict]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(task, dict) for task in value):
        raise ValueError(f"{path} must contain a YAML task list")
    return value


def _task_shape_errors(
    task: dict, description: str, allowed_keys: set[str]
) -> list[str]:
    controls = sorted(set(task) - allowed_keys)
    if not controls:
        return []
    return [f"{description} must be unconditional; remove {', '.join(controls)}"]


def _non_comment_text(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(
        line for line in lines if not line.lstrip().startswith(("#", "{#"))
    )


def _repo_errors(repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    schema = _load_json(repo_root / "secrets" / "schema.json")
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

    role_tasks = repo_root / "ansible" / "roles" / "amneziawg" / "tasks"
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

    main_tasks = _yaml_tasks(role_tasks / "main.yml")
    imports = [
        task
        for task in main_tasks
        if task.get("ansible.builtin.import_tasks") == "guard-s34.yml"
    ]
    if len(imports) != 1:
        errors.append("main.yml must import guard-s34.yml exactly once")
    else:
        errors.extend(
            _task_shape_errors(
                imports[0],
                "guard-s34.yml import",
                {"name", "ansible.builtin.import_tasks"},
            )
        )

    guard_tasks = _yaml_tasks(role_tasks / "guard-s34.yml")
    if len(guard_tasks) != 1 or "ansible.builtin.assert" not in guard_tasks[0]:
        errors.append("guard-s34.yml must contain exactly one assertion task")
    else:
        guard = guard_tasks[0]
        errors.extend(
            _task_shape_errors(
                guard,
                "S3/S4 assertion",
                {"name", "vars", "ansible.builtin.assert"},
            )
        )
        conditions = guard["ansible.builtin.assert"].get("that", [])
        expected_condition = "_awg_s34 | select('ne', 0) | list | length == 0"
        if conditions != [expected_condition]:
            errors.append("S3/S4 assertion must reject every non-zero effective value")

    emitter_paths = (
        repo_root / "scripts" / "emit-awg.sh",
        repo_root / "scripts" / "emit-bundle.sh",
        repo_root / "ansible" / "roles" / "amneziawg" / "templates" / "awg0.conf.j2",
    )
    for path in emitter_paths:
        if re.search(r"(?i)\bs[34]\b", _non_comment_text(path)):
            errors.append(
                f"{path.relative_to(repo_root)} must not resolve or serialize S3/S4"
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
