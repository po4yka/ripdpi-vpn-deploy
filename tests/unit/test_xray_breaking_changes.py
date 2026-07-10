"""Behavioral tests for changelog-driven Xray breaking-change guards."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check-xray-breaking-changes.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_xray_breaking_changes", CHECK_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parses_guard_block_from_release_line():
    checker = _load_checker()
    release_line = """
## v26.5.3

```yaml xray-ci-guards
guards:
  - id: removed-field
    applies_from: v26.5.3
    activation: always
    document: example-secrets
    select:
      path: xray
    forbid:
      path: removedField
    message: Remove the obsolete field.
```
"""

    guards = checker.parse_guard_blocks(release_line)

    assert guards == [
        {
            "id": "removed-field",
            "applies_from": "v26.5.3",
            "activation": "always",
            "document": "example-secrets",
            "select": {"path": "xray"},
            "forbid": {"path": "removedField"},
            "message": "Remove the obsolete field.",
        }
    ]


def test_activation_and_assertions_follow_the_pinned_version():
    checker = _load_checker()
    guards = [
        {
            "id": "removed-field",
            "applies_from": "v26.5.3",
            "activation": "always",
            "document": "example-secrets",
            "select": {"path": "xray"},
            "forbid": {"path": "removedField"},
            "message": "Remove the obsolete field.",
        },
        {
            "id": "freedom-allow",
            "applies_from": "v26.5.3",
            "activation": "pinned-at-least",
            "document": "rendered-xray",
            "select": {"path": "outbounds", "where": {"protocol": "freedom"}},
            "require": {
                "path": "settings.finalRules.0",
                "equals": {"action": "allow"},
            },
            "message": "Add the catch-all allow rule.",
        },
    ]
    documents = {
        "example-secrets": {"xray": {"removedField": True}},
        "rendered-xray": {
            "outbounds": [
                {"tag": "direct", "protocol": "freedom", "settings": {}},
                {"tag": "block", "protocol": "blackhole", "settings": {}},
            ]
        },
    }

    current_issues = checker.evaluate_guards(guards, "v26.3.27", documents)
    future_issues = checker.evaluate_guards(guards, "v26.5.3", documents)

    assert len(current_issues) == 1
    assert "removed-field" in current_issues[0]
    assert {issue.split(":", 1)[0] for issue in future_issues} == {
        "removed-field",
        "freedom-allow",
    }


@pytest.mark.parametrize(
    ("release_line", "expected"),
    [
        ("# no guard registry", "no xray-ci-guards"),
        ("```yaml xray-ci-guards\nguards: [\n```", "invalid YAML"),
        (
            """```yaml xray-ci-guards
guards:
  - &guard
    id: duplicate
    applies_from: v26.5.3
    activation: always
    document: example-secrets
    select: {path: xray}
    forbid: {path: old}
    message: Remove it.
  - <<: *guard
```
""",
            "duplicate guard id",
        ),
        (
            """```yaml xray-ci-guards
guards:
  - id: invalid-version
    applies_from: v26.5.x
    activation: always
    document: example-secrets
    select: {path: xray}
    forbid: {path: old}
    message: Remove it.
```
""",
            "expected vX.Y.Z",
        ),
        (
            """```yaml xray-ci-guards
guards:
  - id: invalid-document
    applies_from: v26.5.3
    activation: always
    document: arbitrary-file
    select: {path: xray}
    forbid: {path: old}
    message: Remove it.
```
""",
            "unsupported document",
        ),
        (
            """```yaml xray-ci-guards
guards:
  - id: invalid-operator
    applies_from: v26.5.3
    activation: always
    document: example-secrets
    select: {path: xray}
    rewrite: {path: old}
    message: Remove it.
```
""",
            "exactly one of require or forbid",
        ),
    ],
)
def test_invalid_guard_metadata_fails_closed(release_line: str, expected: str):
    checker = _load_checker()

    with pytest.raises(checker.GuardDefinitionError, match=expected):
        checker.parse_guard_blocks(release_line)


def _future_freedom_guard() -> dict:
    return {
        "id": "freedom-final-rules-allow",
        "applies_from": "v26.5.3",
        "activation": "pinned-at-least",
        "document": "rendered-xray",
        "select": {"path": "outbounds", "where": {"protocol": "freedom"}},
        "require": {
            "path": "settings.finalRules.0",
            "equals": {"action": "allow"},
        },
        "message": "Add an unconstrained first allow rule.",
    }


def test_versions_are_compared_numerically():
    checker = _load_checker()
    guard = _future_freedom_guard() | {"applies_from": "v26.10.1"}
    documents = {
        "rendered-xray": {
            "outbounds": [{"tag": "direct", "protocol": "freedom", "settings": {}}]
        }
    }

    assert checker.evaluate_guards([guard], "v26.9.99", documents) == []
    assert checker.evaluate_guards([guard], "v26.10.1", documents)


@pytest.mark.parametrize(
    ("final_rules", "fails"),
    [
        (None, True),
        ([{"action": "allow", "network": "tcp"}], True),
        ([{"action": "block", "port": "22"}, {"action": "allow"}], True),
        ([{"action": "allow"}], False),
    ],
)
def test_future_pin_requires_exact_first_allow_rule_on_every_freedom_outbound(
    final_rules: list[dict] | None,
    fails: bool,
):
    checker = _load_checker()
    settings = {} if final_rules is None else {"finalRules": final_rules}
    documents = {
        "rendered-xray": {
            "outbounds": [
                {"tag": "direct", "protocol": "freedom", "settings": settings},
                {
                    "tag": "direct-asis",
                    "protocol": "freedom",
                    "settings": {"finalRules": [{"action": "allow"}]},
                },
                {"tag": "block", "protocol": "blackhole", "settings": {}},
            ]
        }
    }

    issues = checker.evaluate_guards([_future_freedom_guard()], "v26.5.3", documents)

    assert bool(issues) is fails
    if fails:
        assert "tag 'direct'" in issues[0]
        assert "direct-asis" not in "\n".join(issues)
        assert "block" not in "\n".join(issues)


def test_selector_must_match_at_least_one_object():
    checker = _load_checker()
    documents = {"rendered-xray": {"outbounds": []}}

    issues = checker.evaluate_guards([_future_freedom_guard()], "v26.5.3", documents)

    assert len(issues) == 1
    assert "selector matched no objects" in issues[0]


def test_require_supports_presence_and_list_containment():
    checker = _load_checker()
    base = {
        "applies_from": "v1.0.0",
        "activation": "always",
        "document": "rendered-xray",
        "select": {"path": "outbounds", "where": {"protocol": "freedom"}},
        "message": "Update the rendered config.",
    }
    guards = [
        base | {"id": "presence", "require": {"path": "settings.finalRules"}},
        base
        | {
            "id": "containment",
            "require": {
                "path": "settings.finalRules",
                "contains": {"action": "allow"},
            },
        },
    ]
    documents = {
        "rendered-xray": {
            "outbounds": [
                {
                    "tag": "direct",
                    "protocol": "freedom",
                    "settings": {"finalRules": [{"action": "allow"}]},
                }
            ]
        }
    }

    assert checker.evaluate_guards(guards, "v1.0.0", documents) == []


def test_diagnostics_never_include_document_values():
    checker = _load_checker()
    secret_value = "do-not-print-this-value"
    guard = {
        "id": "removed-secret",
        "applies_from": "v1.0.0",
        "activation": "always",
        "document": "example-secrets",
        "select": {"path": "xray"},
        "forbid": {"path": "removed"},
        "message": "Remove the obsolete path.",
    }

    issues = checker.evaluate_guards(
        [guard],
        "v1.0.0",
        {"example-secrets": {"xray": {"removed": secret_value}}},
    )

    assert secret_value not in "\n".join(issues)


def test_cli_validates_the_current_checkout():
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Xray breaking-change guards satisfied" in result.stdout
