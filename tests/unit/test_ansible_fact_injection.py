from __future__ import annotations

import configparser
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ANSIBLE_ROOT = REPO_ROOT / "ansible"
ANSIBLE_CONFIG = ANSIBLE_ROOT / "ansible.cfg"

INJECTED_FACT_ALIASES = {
    "ansible_architecture",
    "ansible_date_time",
    "ansible_default_ipv4",
    "ansible_distribution_release",
    "ansible_hostname",
    "ansible_os_family",
    "ansible_virtualization_type",
}


def test_ansible_fact_injection_is_disabled_and_unused() -> None:
    config = configparser.ConfigParser()
    config.read(ANSIBLE_CONFIG)
    assert config.getboolean("defaults", "inject_facts_as_vars", fallback=True) is False

    pattern = re.compile(r"\b(" + "|".join(sorted(INJECTED_FACT_ALIASES)) + r")\b")
    offenders: list[str] = []
    for path in sorted(ANSIBLE_ROOT.rglob("*")):
        if path.suffix not in {".yml", ".yaml", ".j2"} or "inventory" in path.parts:
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if match := pattern.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {match.group(1)}")

    assert offenders == [], "legacy injected Ansible facts remain:\n" + "\n".join(offenders)
