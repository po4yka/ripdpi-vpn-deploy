"""Behavioral tests for changelog-driven Xray breaking-change guards."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check-xray-breaking-changes.py"
RELEASE_LINE = REPO_ROOT / "docs" / "XRAY-RELEASE-LINE.md"


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


def _pq_reality_hold_guard(checker) -> dict:
    guards = checker.parse_guard_blocks(RELEASE_LINE.read_text())
    return next(guard for guard in guards if guard["id"] == "pq-reality-hold")


def _render_xray(checker, cohorts: list[dict] | None = None) -> dict:
    variables = copy.deepcopy(checker.merge_render_vars())
    variables["xray_fallback_port"] = 0
    variables["xray"]["cohorts"] = cohorts or []
    return json.loads(checker.render_template(checker.XRAY_TEMPLATE, variables))


def _multi_cohorts() -> list[dict]:
    return [
        {
            "name": "vision-shape",
            "port": 443,
            "flow_mode": "vision",
            "finalmask": False,
            "clients": ["phone", "watchdog"],
        },
        {
            "name": "mux-shape",
            "port": 2053,
            "flow_mode": "mux",
            "finalmask": False,
            "clients": ["phone", "watchdog"],
        },
    ]


@pytest.mark.parametrize(
    "cohorts",
    [None, _multi_cohorts()],
)
def test_pq_reality_hold_accepts_current_single_and_multi_cohort_renders(cohorts):
    checker = _load_checker()
    guard = _pq_reality_hold_guard(checker)
    rendered = _render_xray(checker, cohorts)

    assert guard["activation"] == "always"
    assert checker.evaluate_guards(
        [guard], "v26.3.27", {"rendered-xray": rendered}
    ) == []


@pytest.mark.parametrize("violation_count", [1, 2])
def test_pq_reality_hold_reports_each_non_none_reality_inbound(violation_count):
    checker = _load_checker()
    guard = _pq_reality_hold_guard(checker)
    rendered = _render_xray(checker, _multi_cohorts())
    reality_inbounds = [
        inbound
        for inbound in rendered["inbounds"]
        if inbound.get("streamSettings", {}).get("security") == "reality"
    ]
    for inbound in reality_inbounds[:violation_count]:
        inbound["settings"]["decryption"] = "pq-enabled-test-value"

    issues = checker.evaluate_guards(
        [guard], "v26.3.27", {"rendered-xray": rendered}
    )

    assert len(issues) == violation_count
    for inbound in reality_inbounds[:violation_count]:
        assert f"tag {inbound['tag']!r}" in "\n".join(issues)


def test_pq_reality_hold_ignores_non_reality_vless_and_unrelated_protocols():
    checker = _load_checker()
    guard = _pq_reality_hold_guard(checker)
    rendered = _render_xray(checker)
    rendered["inbounds"].extend(
        [
            {
                "tag": "vless-xhttp-test",
                "protocol": "vless",
                "settings": {"decryption": "pq-enabled-test-value"},
                "streamSettings": {"security": "none"},
            },
            {
                "tag": "unrelated-test",
                "protocol": "socks",
                "settings": {"decryption": "pq-enabled-test-value"},
                "streamSettings": {"security": "reality"},
            },
        ]
    )

    assert checker.evaluate_guards(
        [guard], "v26.3.27", {"rendered-xray": rendered}
    ) == []


def test_malformed_pq_reality_hold_metadata_fails_closed():
    checker = _load_checker()
    release_line = """```yaml xray-ci-guards
guards:
  - id: pq-reality-hold
    applies_from: v26.5.3
    activation: operator-override
    document: rendered-xray
    select:
      path: inbounds
      where:
        protocol: vless
        streamSettings.security: reality
    require:
      path: settings.decryption
      equals: none
    message: Keep PQ-REALITY on HOLD.
```
"""

    with pytest.raises(checker.GuardDefinitionError, match="unsupported activation"):
        checker.parse_guard_blocks(release_line)


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
        {"example-secrets": {"xray": {"tag": secret_value, "removed": secret_value}}},
    )

    assert secret_value not in "\n".join(issues)


def test_exact_comparisons_do_not_coerce_booleans_to_numbers():
    checker = _load_checker()
    base = {
        "applies_from": "v1.0.0",
        "activation": "always",
        "document": "rendered-xray",
        "select": {"path": "outbounds", "where": {"protocol": "freedom"}},
        "message": "Use the exact declared type.",
    }
    guards = [
        base
        | {
            "id": "selector-type",
            "select": {
                "path": "outbounds",
                "where": {"protocol": "freedom", "priority": 1},
            },
            "require": {"path": "settings.enabled"},
        },
        base
        | {
            "id": "equals-type",
            "require": {"path": "settings.priority", "equals": 1},
        },
        base
        | {
            "id": "contains-type",
            "require": {"path": "settings.priorities", "contains": 1},
        },
    ]
    documents = {
        "rendered-xray": {
            "outbounds": [
                {
                    "tag": "direct",
                    "protocol": "freedom",
                    "priority": True,
                    "settings": {
                        "enabled": True,
                        "priority": True,
                        "priorities": [True],
                    },
                }
            ]
        }
    }

    issues = checker.evaluate_guards(guards, "v1.0.0", documents)

    assert {issue.split(":", 1)[0] for issue in issues} == {
        "selector-type",
        "equals-type",
        "contains-type",
    }


@pytest.mark.parametrize(
    "invalid_tags",
    [("direct",), ("direct-asis",), ("direct", "direct-asis")],
)
def test_future_pin_reports_each_invalid_freedom_outbound(
    invalid_tags: tuple[str, ...],
):
    checker = _load_checker()
    outbounds = []
    for tag in ("direct", "direct-asis"):
        settings = {} if tag in invalid_tags else {"finalRules": [{"action": "allow"}]}
        outbounds.append({"tag": tag, "protocol": "freedom", "settings": settings})

    issues = checker.evaluate_guards(
        [_future_freedom_guard()],
        "v26.5.3",
        {"rendered-xray": {"outbounds": outbounds}},
    )

    assert len(issues) == len(invalid_tags)
    for tag in invalid_tags:
        assert f"tag {tag!r}" in "\n".join(issues)


def test_cli_validates_the_current_checkout():
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Xray breaking-change guards satisfied" in result.stdout
