"""Regression tests for service handlers exercised by Ansible check mode."""

from pathlib import Path

import pytest
import yaml
from jinja2 import DictLoader
from template_render import template_environment

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
        (
            "naive",
            (
                "Restart caddy-naive",
                "Wait for caddy-naive to become active",
            ),
        ),
        (
            "dns-morph-bridge",
            (
                "Restart dns-morph-bridge",
                "Wait for dns-morph-bridge to become active",
                "Restart unbound",
            ),
        ),
        ("geodata", ("Reload xray geodata",)),
        ("nginx-xhttp", ("Reload nginx-xhttp",)),
        ("amneziawg", ("Restart amneziawg",)),
    ],
)
def test_restart_handlers_skip_runtime_checks_in_check_mode(
    role: str, handler_names: tuple[str, ...]
) -> None:
    handlers_path = REPO_ROOT / "ansible" / "roles" / role / "handlers" / "main.yml"
    handlers = yaml.safe_load(handlers_path.read_text())

    by_name = {handler["name"]: handler for handler in handlers}
    environment = template_environment(DictLoader({}))
    selector = role.replace("-", "_") + "_role_enabled"
    for name in handler_names:
        conditions = by_name[name]["when"]
        if isinstance(conditions, str):
            conditions = [conditions]

        def selected(*, check: bool, enabled: bool) -> bool:
            values = {"ansible_check_mode": check, selector: enabled}
            return all(
                environment.compile_expression(condition)(**values)
                for condition in conditions
            )

        assert not selected(
            check=True, enabled=True
        ), f"{role}:{name} runs in check mode"
        assert not selected(
            check=True, enabled=False
        ), f"{role}:{name} runs in disabled check mode"
        assert selected(
            check=False, enabled=True
        ), f"{role}:{name} lost ordinary positive activation"
        if role not in {"geodata", "nginx-xhttp"}:
            assert not selected(
                check=False, enabled=False
            ), f"{role}:{name} can revive retired authority"
