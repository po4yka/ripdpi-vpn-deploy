"""The journal size budget must be large enough to hold the stated retention."""

from configparser import ConfigParser
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "ansible" / "roles" / "monitoring" / "tasks" / "enable.yml"


def test_journald_policy_keeps_fourteen_days_within_a_one_gigabyte_budget() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    dropin = next(
        task["ansible.builtin.copy"]
        for task in tasks
        if task["name"] == "Drop journald hardening config"
    )
    policy = ConfigParser()
    policy.optionxform = str
    policy.read_string(dropin["content"])

    assert dropin["dest"] == "/etc/systemd/journald.conf.d/vpn.conf"
    assert dict(policy["Journal"]) == {
        "Storage": "persistent",
        "SystemMaxUse": "1G",
        "MaxRetentionSec": "14day",
        "ForwardToSyslog": "no",
    }
