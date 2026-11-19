"""The journal size budget must be large enough to hold the stated retention."""

from configparser import ConfigParser
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "ansible" / "roles" / "monitoring" / "tasks" / "enable.yml"
DEFAULTS = REPO_ROOT / "ansible" / "roles" / "monitoring" / "defaults" / "main.yml"


def test_journald_policy_keeps_fourteen_days_within_a_one_gigabyte_budget() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    dropin = next(
        task["ansible.builtin.copy"]
        for task in tasks
        if task["name"] == "Drop journald hardening config"
    )
    policy = ConfigParser()
    policy.optionxform = str
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    policy.read_string(
        Environment(undefined=StrictUndefined).from_string(dropin["content"]).render(defaults)
    )

    assert dropin["dest"] == "/etc/systemd/journald.conf.d/vpn.conf"
    assert dict(policy["Journal"]) == {
        "Storage": "persistent",
        "SystemMaxUse": "1G",
        "MaxRetentionSec": "14day",
        "ForwardToSyslog": "no",
    }


def test_journal_is_flushed_to_disk_after_the_policy_is_written() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    names = [task["name"] for task in tasks]
    flush = tasks[names.index("Move the journal to persistent storage")]

    assert names.index("Drop journald hardening config") < names.index(flush["name"])
    assert flush["ansible.builtin.command"] == {
        "argv": ["journalctl", "--flush"],
        "creates": "/run/systemd/journal/flushed",
    }
    assert "when" not in flush
