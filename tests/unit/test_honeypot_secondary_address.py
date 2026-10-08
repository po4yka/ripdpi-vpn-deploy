"""Dedicated IPv4 inputs and unit dependencies must preserve primary networking."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/honeypot"
spec = importlib.util.spec_from_file_location("secondary_address_renderer", ROOT / "scripts/template_render.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def validate(address: str, interface: str, primary: str = "192.0.2.10"):
    tasks = yaml.safe_load((ROLE / "tasks/secondary-address.yml").read_text())
    code = tasks[1]["ansible.builtin.command"]["argv"][2]
    return subprocess.run(
        [sys.executable, "-c", code, address, interface, primary],
        capture_output=True, text=True,
    )


def test_valid_secondary_address_on_an_existing_interface_passes():
    interface = socket.if_nameindex()[0][1]
    assert validate("198.51.100.20", interface).returncode == 0


@pytest.mark.parametrize("address", ["192.0.2.10", "0.0.0.0", "127.0.0.1", "224.0.0.1", "198.51.100.999", "198.51.100.20/32", "198.51.100.20\nExecStart=/bin/false"])
def test_invalid_or_primary_addresses_refuse_before_network_changes(address):
    assert validate(address, socket.if_nameindex()[0][1]).returncode != 0


@pytest.mark.parametrize("interface", ["", "missing-device", "lo;false", "lo\nExecStart=/bin/false", "-x"])
def test_absent_or_noncanonical_interface_is_rejected(interface):
    assert validate("198.51.100.20", interface).returncode != 0


def test_address_unit_is_a_least_privilege_dependency_of_the_listener():
    variables = renderer.merge_render_vars()
    variables.update({
        "_honeypot_secondary_address": "198.51.100.20",
        "_honeypot_secondary_interface": "eth0",
        "_honeypot_secondary_required": True,
        "_honeypot_secondary_unit": "vpn-honeypot-address-198.51.100.20-eth0.service",
    })
    address = renderer.render_template(ROLE / "templates/secondary-address.service.j2", variables)
    listener = renderer.render_template(ROLE / "templates/honeypot.service.j2", variables)
    assert "ExecStart=/usr/sbin/ip address replace 198.51.100.20/32 dev eth0" in address
    assert "ExecStop=/usr/sbin/ip address del 198.51.100.20/32 dev eth0" in address
    assert "CapabilityBoundingSet=CAP_NET_ADMIN" in address
    assert "RemainAfterExit=yes" in address
    assert "PartOf=honeypot.service" in address
    assert f"Requires={variables['_honeypot_secondary_unit']}" in listener
    assert f"After={variables['_honeypot_secondary_unit']}" in listener
    assert "CAP_NET_ADMIN" not in listener
    variables["_honeypot_secondary_required"] = False
    assert "vpn-honeypot-address-" not in renderer.render_template(ROLE / "templates/honeypot.service.j2", variables)
