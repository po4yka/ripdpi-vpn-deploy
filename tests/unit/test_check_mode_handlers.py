"""Regression tests for service handlers exercised by Ansible check mode."""

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("role", "handler_names"),
    [
        (
            "hysteria",
            (
                "Restart hysteria-server",
                "Wait for hysteria-server to become active",
            ),
        ),
        (
            "hysteria-realm",
            (
                "Restart hysteria-realm",
                "Wait for hysteria-realm to become active",
            ),
        ),
    ],
)
def test_restart_handlers_skip_runtime_checks_in_check_mode(
    role: str, handler_names: tuple[str, ...]
) -> None:
    handlers_path = REPO_ROOT / "ansible" / "roles" / role / "handlers" / "main.yml"
    handlers = yaml.safe_load(handlers_path.read_text())

    by_name = {handler["name"]: handler for handler in handlers}
    for name in handler_names:
        assert by_name[name]["when"] == "not ansible_check_mode"
