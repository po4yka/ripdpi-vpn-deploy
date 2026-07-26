from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("provider", "server_resource"),
    (
        ("upcloud", 'resource "upcloud_server" "vpn"'),
        ("hetzner", 'resource "hcloud_server" "vpn"'),
        ("vultr", 'resource "vultr_instance" "vpn"'),
        ("scaleway", 'resource "scaleway_instance_server" "vpn"'),
    ),
)
def test_ssh_port_change_forces_disposable_node_replacement(
    provider: str,
    server_resource: str,
) -> None:
    source = (ROOT / "terraform" / "providers" / provider / "main.tf").read_text()
    server = source.split(server_resource, 1)[1]

    assert 'resource "terraform_data" "ssh_port"' in source
    assert "input = var.ssh_port" in source
    assert "terraform_data.ssh_port" in server
    assert server.index("replace_triggered_by") < server.index("ignore_changes")
    assert "prevent_destroy = true" in server
