"""Regression coverage for the AmneziaWG arm64 S3/S4 policy and watcher."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = REPO_ROOT / "contract" / "amneziawg-arm64-version-floor.json"
VALIDATOR = REPO_ROOT / "scripts" / "check-amneziawg-arm64-version-floor.py"
WATCHER = REPO_ROOT / "scripts" / "check-amneziawg-arm64-upstream.py"
ROLE_GUARD = REPO_ROOT / "ansible" / "roles" / "amneziawg" / "tasks" / "guard-s34.yml"


def _load_watcher():
    spec = importlib.util.spec_from_file_location("awg_upstream", WATCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _issues(*, go_state: str = "open", client_state: str = "closed") -> list[dict]:
    return [
        {
            "repository": "amnezia-vpn/amneziawg-go",
            "number": 110,
            "state": go_state,
            "html_url": "https://github.com/amnezia-vpn/amneziawg-go/issues/110",
        },
        {
            "repository": "amnezia-vpn/amnezia-client",
            "number": 2582,
            "state": client_state,
            "html_url": "https://github.com/amnezia-vpn/amnezia-client/issues/2582",
        },
    ]


def _reviewed_release(policy: dict) -> dict:
    cursor = policy["release_watch"]["last_reviewed_release"]
    return {
        "tag_name": cursor,
        "name": cursor,
        "body": "Last reviewed release.",
        "html_url": "https://example.invalid/reviewed",
    }


def test_policy_validator_accepts_the_committed_fail_closed_state():
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_policy_validator_rejects_disabled_guard_without_verified_floor(tmp_path):
    policy = json.loads(POLICY.read_text())
    policy["guard_required"] = False
    bad_policy = tmp_path / "policy.json"
    bad_policy.write_text(json.dumps(policy))

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--policy", str(bad_policy)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "verified_safe_floor is null" in result.stderr


@pytest.mark.parametrize(
    ("variables", "accepted"),
    [
        ({"amneziawg_cohort": {"s3": 1}, "amneziawg_secrets": {}}, False),
        ({"amneziawg_cohort": {"s4": -1}, "amneziawg_secrets": {}}, False),
        ({"amneziawg_cohort": {}, "amneziawg_secrets": {"s3": 1}}, False),
        ({"amneziawg_cohort": {}, "amneziawg_secrets": {"s4": -1}}, False),
        (
            {"amneziawg_cohort": {}, "amneziawg_secrets": {"instances": [{"s3": 1}]}},
            False,
        ),
        (
            {"amneziawg_cohort": {}, "amneziawg_secrets": {"instances": [{"s4": -1}]}},
            False,
        ),
        (
            {
                "amneziawg_cohort": {"s3": 0, "s4": 0},
                "amneziawg_secrets": {
                    "s3": 0,
                    "s4": 0,
                    "instances": [{"s3": 0, "s4": 0}],
                },
            },
            True,
        ),
    ],
)
def test_role_guard_rejects_every_supported_s3_s4_source(tmp_path, variables, accepted):
    playbook = tmp_path / "guard.yml"
    playbook.write_text(
        "---\n"
        "- name: Exercise the committed AmneziaWG arm64 guard\n"
        "  hosts: localhost\n"
        "  gather_facts: false\n"
        "  tasks:\n"
        f"    - ansible.builtin.import_tasks: {ROLE_GUARD}\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "ansible-playbook",
            "--inventory",
            "localhost,",
            "--connection",
            "local",
            "--extra-vars",
            json.dumps(variables),
            str(playbook),
        ],
        capture_output=True,
        text=True,
    )

    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


def test_expected_issue_states_and_unrelated_release_are_clean():
    watcher = _load_watcher()
    policy = json.loads(POLICY.read_text())
    releases = [
        {
            "tag_name": "v0.2.19",
            "name": "v0.2.19",
            "body": "Handle empty I1-I5 parameters on receive.",
            "html_url": "https://example.invalid/v0.2.19",
        },
        _reviewed_release(policy),
    ]

    result = watcher.classify(policy, _issues(), releases)

    assert result.review_required is False
    assert result.reasons == []


@pytest.mark.parametrize(
    ("go_state", "client_state", "issue_number"),
    [("closed", "closed", 110), ("open", "open", 2582)],
)
def test_issue_state_change_requires_review(go_state, client_state, issue_number):
    watcher = _load_watcher()
    policy = json.loads(POLICY.read_text())

    result = watcher.classify(
        policy,
        _issues(go_state=go_state, client_state=client_state),
        [_reviewed_release(policy)],
    )

    assert result.review_required is True
    assert any(f"#{issue_number}" in reason for reason in result.reasons)


def test_matching_release_claim_requires_review():
    watcher = _load_watcher()
    policy = json.loads(POLICY.read_text())
    releases = [
        {
            "tag_name": "4.8.20.0",
            "name": "4.8.20.0",
            "body": "Fix arm64 S3/S4 H4 transport header alignment.",
            "html_url": "https://example.invalid/4.8.20.0",
        },
        _reviewed_release(policy),
    ]

    result = watcher.classify(policy, _issues(), releases)

    assert result.review_required is True
    assert any("4.8.20.0" in reason for reason in result.reasons)


def test_missing_release_cursor_is_indeterminate():
    watcher = _load_watcher()
    policy = json.loads(POLICY.read_text())
    releases = [
        {
            "tag_name": "4.8.20.0",
            "name": "4.8.20.0",
            "body": "Routine release.",
            "html_url": "https://example.invalid/4.8.20.0",
        }
    ]

    result = watcher.classify(policy, _issues(), releases)

    assert result.indeterminate is True
    assert any("cursor" in reason.lower() for reason in result.reasons)


def test_malformed_issue_response_is_indeterminate():
    watcher = _load_watcher()
    policy = json.loads(POLICY.read_text())
    issues = _issues()
    issues[0]["state"] = None

    result = watcher.classify(policy, issues, [_reviewed_release(policy)])

    assert result.indeterminate is True
    assert result.review_required is False
    assert any("malformed" in reason.lower() for reason in result.reasons)


def test_empty_release_response_is_indeterminate():
    watcher = _load_watcher()
    policy = json.loads(POLICY.read_text())

    result = watcher.classify(policy, _issues(), [])

    assert result.indeterminate is True
    assert any("empty" in reason.lower() for reason in result.reasons)


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("offline"),
        urllib.error.HTTPError("https://api.github.com", 429, "rate limited", {}, None),
    ],
)
def test_live_api_failures_exit_indeterminate(monkeypatch, error):
    watcher = _load_watcher()

    def fail_live(_policy):
        raise error

    monkeypatch.setattr(watcher, "_live_payloads", fail_live)

    assert watcher.main([]) == 2
