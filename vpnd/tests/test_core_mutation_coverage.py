"""Exercise inventory subprocess boundaries directly for mutation associations."""

import asyncio
import json
import os
import sys

import pytest

from artifact_helpers import context, executable, scaffold
from vpnd.runner import ansible
from vpnd.state import Host


@pytest.mark.parametrize(
    "builder,name", [(ansible.verify, "verify"), (ansible.smoke, "smoke-test")]
)
def test_public_playbook_builders_keep_inventory_and_secret_delivery(tmp_path, builder, name):
    ctx = context(scaffold(tmp_path))
    command = builder(ctx)
    assert command.program == "ansible-playbook"
    assert command.argv == [
        str(ctx.ansible_dir / "playbooks" / f"{name}.yml"),
        "--inventory",
        str(ctx.ansible_dir / "inventory/generated.ini"),
    ]
    assert command.directory == ctx.root
    assert dict(command.environment) == {
        "ANSIBLE_CONFIG": str(ctx.ansible_cfg()),
        "VPN_SECRETS_FILE": str(ctx.secrets_file),
    }
    assert str(ctx.secrets_file) not in command.redacted_explain()


def inventory_program(tmp_path, monkeypatch, inventory):
    scaffold(tmp_path)
    marker = tmp_path / "inventory-call.json"
    executable(
        tmp_path,
        "ansible-inventory",
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(json.dumps({{'args': sys.argv[1:], 'cwd': os.getcwd(), 'config': os.environ.get('ANSIBLE_CONFIG')}}))\n"
        f"print({json.dumps(inventory)!r})\n",
    )
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    return context(tmp_path), marker


def inventory():
    return {
        "vpn": {"hosts": ["selected", "second", "foreign"]},
        "_meta": {
            "hostvars": {
                "selected": {
                    "env": "test",
                    "provider": "upcloud",
                    "ansible_host": "203.0.113.8",
                    "vpn_service_address": "192.0.2.1",
                },
                "second": {"env": "test", "provider": "upcloud", "ansible_host": "192.0.2.2"},
                "foreign": {"env": "test", "provider": "hetzner", "ansible_host": "192.0.2.3"},
            }
        },
    }


def test_inventory_scope_uses_selected_provider_and_service_address(tmp_path, monkeypatch):
    ctx, marker = inventory_program(tmp_path, monkeypatch, inventory())
    selected = asyncio.run(ansible.scoped_limit(ctx))
    assert selected == "second,selected"
    host = ("registered", Host("test", "upcloud", ipv4="192.0.2.1"))
    selected_host = asyncio.run(ansible.scoped_limit(ctx, host))
    assert selected_host == "selected"
    assert json.loads(marker.read_text()) == {
        "args": ["--inventory", str(ctx.ansible_dir / "inventory/generated.ini"), "--list"],
        "cwd": str(ctx.root),
        "config": str(ctx.ansible_cfg()),
    }
    assert os.environ["PATH"] == str(tmp_path / "bin")


def test_inventory_scope_refuses_ambiguous_service_address(tmp_path, monkeypatch):
    data = inventory()
    data["_meta"]["hostvars"]["second"]["vpn_service_address"] = "192.0.2.1"
    ctx, marker = inventory_program(tmp_path, monkeypatch, data)
    host = ("registered", Host("test", "upcloud", ipv4="192.0.2.1"))
    with pytest.raises(ValueError, match="exactly one matching inventory hosts, found 2"):
        asyncio.run(ansible.scoped_limit(ctx, host))
    assert marker.is_file()


def test_inventory_scope_explain_does_not_spawn_inventory_program(tmp_path, monkeypatch):
    ctx, marker = inventory_program(tmp_path, monkeypatch, inventory())
    ctx.explain = True
    selected = asyncio.run(ansible.scoped_limit(ctx))
    assert selected == "<validated inventory host keys>"
    assert not marker.exists()
