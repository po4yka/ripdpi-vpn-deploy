"""Dependency-update PR ownership must remain exclusive to Renovate."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MANAGERS = {
    "cargo",
    "custom.regex",
    "github-actions",
    "pip_requirements",
    "terraform",
}


def _renovate_config() -> dict:
    return json.loads((ROOT / "renovate.json").read_text())


def test_dependabot_config_is_absent_to_prevent_duplicate_ownership():
    assert not (ROOT / ".github" / "dependabot.yml").exists(), (
        "Dependabot version-update configuration would duplicate Renovate ownership"
    )


def test_enabled_managers_define_the_exact_sorted_ownership_boundary():
    enabled_managers = _renovate_config()["enabledManagers"]

    assert set(enabled_managers) == EXPECTED_MANAGERS
    assert enabled_managers == sorted(enabled_managers)


def test_package_rules_and_custom_managers_stay_within_enabled_boundary():
    config = _renovate_config()
    enabled_managers = set(config["enabledManagers"])
    rule_managers = {
        manager
        for rule in config["packageRules"]
        for manager in rule.get("matchManagers", [])
    }

    assert rule_managers <= enabled_managers
    if config.get("customManagers"):
        assert "custom.regex" in enabled_managers


def test_docs_record_renovate_as_the_sole_version_update_owner():
    testing = (ROOT / "docs" / "TESTING.md").read_text()
    contributing = (ROOT / "CONTRIBUTING.md").read_text()

    assert "Renovate is the sole automated version-update PR owner" in testing
    assert "`.github/dependabot.yml` is intentionally absent" in testing
    assert "Dependabot uses this automatically" not in contributing
