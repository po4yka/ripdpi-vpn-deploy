"""Routine dependency updates must age before Dependabot opens a PR."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT = ROOT / ".github/dependabot.yml"


def test_every_dependabot_ecosystem_has_seven_day_default_cooldown():
    config = yaml.safe_load(DEPENDABOT.read_text())
    updates = config["updates"]

    assert len(updates) == 5
    for update in updates:
        assert update["cooldown"] == {"default-days": 7}
