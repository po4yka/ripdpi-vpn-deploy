#!/usr/bin/env python3
"""Validate Xray breaking-change guards declared in the release-line tracker."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from template_render import EXAMPLE_FILE, REPO_ROOT, merge_render_vars, render_template

GUARD_BLOCK = re.compile(
    r"^```yaml xray-ci-guards\s*$\n(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)
MISSING = object()
VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
SUPPORTED_DOCUMENTS = {"example-secrets", "rendered-xray"}
SUPPORTED_ACTIVATIONS = {"always", "pinned-at-least"}
REQUIRED_GUARD_KEYS = {
    "id",
    "applies_from",
    "activation",
    "document",
    "select",
    "message",
}
RELEASE_LINE_FILE = REPO_ROOT / "docs" / "XRAY-RELEASE-LINE.md"
XRAY_TEMPLATE = (
    REPO_ROOT / "ansible" / "roles" / "xray" / "templates" / "config.json.j2"
)


class GuardDefinitionError(ValueError):
    """Raised when the release-line guard registry is absent or malformed."""


def parse_guard_blocks(release_line: str) -> list[dict]:
    """Return guards declared in fenced ``yaml xray-ci-guards`` blocks."""
    matches = list(GUARD_BLOCK.finditer(release_line))
    if not matches:
        raise GuardDefinitionError("no xray-ci-guards block found in release line")

    guards: list[dict] = []
    for block_number, match in enumerate(matches, start=1):
        try:
            block = yaml.safe_load(match.group("body"))
        except yaml.YAMLError as exc:
            raise GuardDefinitionError(
                f"invalid YAML in xray-ci-guards block {block_number}: {exc}"
            ) from exc
        if not isinstance(block, dict) or set(block) != {"guards"}:
            raise GuardDefinitionError(
                f"xray-ci-guards block {block_number} must contain only a guards list"
            )
        block_guards = block["guards"]
        if not isinstance(block_guards, list) or not block_guards:
            raise GuardDefinitionError(
                f"xray-ci-guards block {block_number} has no guard definitions"
            )
        guards.extend(block_guards)

    seen_ids: set[str] = set()
    for guard in guards:
        _validate_guard(guard, seen_ids)
    return guards


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GuardDefinitionError(f"{label} must be a non-empty string")
    return value


def _validate_path_assertion(assertion: object, label: str) -> None:
    if not isinstance(assertion, dict):
        raise GuardDefinitionError(f"{label} must be a mapping")
    _require_nonempty_string(assertion.get("path"), f"{label}.path")


def _validate_guard(guard: object, seen_ids: set[str]) -> None:
    if not isinstance(guard, dict):
        raise GuardDefinitionError("each guard definition must be a mapping")

    guard_id = _require_nonempty_string(guard.get("id"), "guard id")
    if guard_id in seen_ids:
        raise GuardDefinitionError(f"duplicate guard id {guard_id!r}")
    seen_ids.add(guard_id)

    operators = {name for name in ("require", "forbid") if name in guard}
    if len(operators) != 1:
        raise GuardDefinitionError(
            f"guard {guard_id!r} must declare exactly one of require or forbid"
        )

    missing = REQUIRED_GUARD_KEYS - set(guard)
    if missing:
        raise GuardDefinitionError(
            f"guard {guard_id!r} is missing keys: {', '.join(sorted(missing))}"
        )
    allowed = REQUIRED_GUARD_KEYS | operators
    unknown = set(guard) - allowed
    if unknown:
        raise GuardDefinitionError(
            f"guard {guard_id!r} has unsupported keys: {', '.join(sorted(unknown))}"
        )

    version = _require_nonempty_string(
        guard["applies_from"], f"guard {guard_id!r} applies_from"
    )
    try:
        parse_version(version)
    except ValueError as exc:
        raise GuardDefinitionError(str(exc)) from exc

    activation = guard["activation"]
    if activation not in SUPPORTED_ACTIVATIONS:
        raise GuardDefinitionError(
            f"guard {guard_id!r} has unsupported activation {activation!r}"
        )
    document = guard["document"]
    if document not in SUPPORTED_DOCUMENTS:
        raise GuardDefinitionError(
            f"guard {guard_id!r} has unsupported document {document!r}"
        )
    _require_nonempty_string(guard["message"], f"guard {guard_id!r} message")

    select = guard["select"]
    if not isinstance(select, dict) or not set(select) <= {"path", "where"}:
        raise GuardDefinitionError(
            f"guard {guard_id!r} select must contain path and optional where"
        )
    _require_nonempty_string(select.get("path"), f"guard {guard_id!r} select.path")
    if "where" in select and not isinstance(select["where"], dict):
        raise GuardDefinitionError(f"guard {guard_id!r} select.where must be a mapping")
    for path in select.get("where", {}):
        _require_nonempty_string(path, f"guard {guard_id!r} select.where path")

    operator = operators.pop()
    assertion = guard[operator]
    _validate_path_assertion(assertion, f"guard {guard_id!r} {operator}")
    if operator == "forbid":
        if set(assertion) != {"path"}:
            raise GuardDefinitionError(
                f"guard {guard_id!r} forbid supports only the path key"
            )
        return

    if not set(assertion) <= {"path", "equals", "contains"}:
        raise GuardDefinitionError(f"guard {guard_id!r} require has unsupported keys")
    if "equals" in assertion and "contains" in assertion:
        raise GuardDefinitionError(
            f"guard {guard_id!r} require cannot combine equals and contains"
        )


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse an exact Xray release tag into a numerically comparable tuple."""
    match = VERSION.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid Xray version {value!r}; expected vX.Y.Z")
    return tuple(int(part) for part in match.groups())


def resolve_path(document: object, path: str) -> object:
    """Resolve dotted mapping keys and list indexes, returning MISSING on drift."""
    current = document
    for part in path.split(".") if path else []:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return MISSING
    return current


def _exact_equal(actual: object, expected: object) -> bool:
    """Compare YAML/JSON values without Python's bool-number coercion."""
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return len(actual) == len(expected) and all(
            key in actual and _exact_equal(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _exact_equal(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected)
        )
    return actual == expected


def _selected_items(document: object, select: dict) -> list[object]:
    selected = resolve_path(document, select["path"])
    if selected is MISSING:
        return []
    items = selected if isinstance(selected, list) else [selected]
    where = select.get("where") or {}
    return [
        item
        for item in items
        if all(
            _exact_equal(resolve_path(item, path), expected)
            for path, expected in where.items()
        )
    ]


def _assertion_passes(item: object, guard: dict) -> bool:
    if "forbid" in guard:
        return resolve_path(item, guard["forbid"]["path"]) is MISSING

    requirement = guard["require"]
    actual = resolve_path(item, requirement["path"])
    if actual is MISSING:
        return False
    if "equals" in requirement:
        return _exact_equal(actual, requirement["equals"])
    if "contains" in requirement:
        return isinstance(actual, list) and any(
            _exact_equal(item, requirement["contains"]) for item in actual
        )
    return True


def evaluate_guards(
    guards: list[dict],
    pin_version: str,
    documents: dict[str, object],
) -> list[str]:
    """Return secret-safe diagnostics for active guards that do not hold."""
    pin = parse_version(pin_version)
    issues: list[str] = []
    for guard in guards:
        active = guard["activation"] == "always" or pin >= parse_version(
            guard["applies_from"]
        )
        if not active:
            continue
        selected = _selected_items(documents[guard["document"]], guard["select"])
        if not selected:
            issues.append(
                f"{guard['id']}: selector matched no objects. {guard['message']}"
            )
            continue
        for index, item in enumerate(selected):
            if _assertion_passes(item, guard):
                continue
            identity = (
                item.get("tag")
                if guard["document"] == "rendered-xray" and isinstance(item, dict)
                else None
            )
            target = f"tag {identity!r}" if identity else f"selection {index}"
            issues.append(
                f"{guard['id']}: assertion failed for {target}. {guard['message']}"
            )
    return issues


def _load_example_secrets(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise GuardDefinitionError(
            f"could not load example secrets from {path}"
        ) from exc
    if not isinstance(data, dict):
        raise GuardDefinitionError("example secrets root must be a mapping")
    return data


def main() -> int:
    """Load repository artifacts, evaluate active guards, and report status."""
    try:
        release_line = RELEASE_LINE_FILE.read_text()
        guards = parse_guard_blocks(release_line)
        example_secrets = _load_example_secrets(EXAMPLE_FILE)
        xray = example_secrets.get("xray")
        if not isinstance(xray, dict) or not isinstance(xray.get("version"), str):
            raise GuardDefinitionError(
                "example secrets must declare string xray.version"
            )
        pin_version = xray["version"]
        try:
            parse_version(pin_version)
        except ValueError as exc:
            raise GuardDefinitionError(str(exc)) from exc

        rendered_text = render_template(XRAY_TEMPLATE, merge_render_vars())
        rendered_xray = json.loads(rendered_text)
        documents = {
            "example-secrets": example_secrets,
            "rendered-xray": rendered_xray,
        }
        issues = evaluate_guards(guards, pin_version, documents)
    except GuardDefinitionError as exc:
        print(f"xray breaking-change guard: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(
            f"xray breaking-change guard: could not read {exc.filename}",
            file=sys.stderr,
        )
        return 1
    except json.JSONDecodeError as exc:
        print(
            "xray breaking-change guard: rendered Xray template is invalid JSON "
            f"at line {exc.lineno}, column {exc.colno}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            "xray breaking-change guard: could not render Xray template "
            f"({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1

    if issues:
        print("Xray breaking-change guard FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    print("OK — Xray breaking-change guards satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
