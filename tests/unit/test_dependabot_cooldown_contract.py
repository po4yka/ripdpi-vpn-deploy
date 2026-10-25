"""Routine dependency updates must age before Dependabot opens a PR."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT = ROOT / ".github/dependabot.yml"


def test_every_dependabot_ecosystem_has_seven_day_default_cooldown():
    config = yaml.safe_load(DEPENDABOT.read_text())
    updates = config["updates"]

    assert {(u['package-ecosystem'], u['directory']) for u in updates} == {
        ('github-actions', '/'), ('terraform', '/terraform/providers/upcloud'),
        ('terraform', '/terraform/providers/hetzner'), ('terraform', '/terraform/providers/vultr'),
        ('terraform', '/terraform/providers/scaleway'), ('pip', '/'), ('pip', '/vpnd'),
        ('npm', '/tools/tasking'), ('gomod', '/tools/probe-matrix-mtproto'),
    }
    for update in updates:
        assert update["cooldown"] == {"default-days": 7}
        assert update['schedule']['interval'] == 'weekly'
        assert update['groups'] == {'routine': {'patterns': ['*']}}
        assert update['commit-message'] == {'prefix': 'chore', 'include': 'scope'}
