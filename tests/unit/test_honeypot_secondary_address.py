"""Dedicated IPv4 inputs and unit dependencies must preserve primary networking."""

from __future__ import annotations

import importlib.util
import json
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
    assert "ExecStop=/usr/bin/python3 -I -B /usr/local/libexec/vpn-honeypot-remove-address.py 198.51.100.20 eth0" in address
    assert "CapabilityBoundingSet=CAP_NET_ADMIN" in address
    assert "RemainAfterExit=yes" in address
    assert "PartOf=honeypot.service" in address
    assert f"Requires={variables['_honeypot_secondary_unit']}" in listener
    assert f"After={variables['_honeypot_secondary_unit']}" in listener
    assert "CAP_NET_ADMIN" not in listener
    variables["_honeypot_secondary_required"] = False
    assert "vpn-honeypot-address-" not in renderer.render_template(ROLE / "templates/honeypot.service.j2", variables)


def cleanup_module():
    spec = importlib.util.spec_from_file_location("honeypot_address_cleanup", ROLE / "files/remove-secondary-address.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("addresses,deleted", [
    ([{"local": "198.51.100.20", "prefixlen": 32}], True),
    ([], False),
    ([{"local": "192.0.2.10", "prefixlen": 32}], False),
    ([{"local": "198.51.100.20", "prefixlen": 24}], False),
])
def test_stop_removes_only_the_owned_prefix_and_accepts_absence(monkeypatch, addresses, deleted):
    module = cleanup_module()
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs == {"capture_output": True, "text": True, "check": True, "timeout": 15}
        return subprocess.CompletedProcess(argv, 0, json.dumps([{"ifname": "eth0", "addr_info": addresses}]), "")
    monkeypatch.setattr(module.subprocess, "run", run)
    module.remove("198.51.100.20", "eth0")
    assert calls[0] == ["/usr/sbin/ip", "-j", "-4", "address", "show", "dev", "eth0"]
    assert calls[1:] == ([["/usr/sbin/ip", "address", "del", "198.51.100.20/32", "dev", "eth0"]] if deleted else [])


@pytest.mark.parametrize("phase", ["inspect", "delete"])
def test_stop_preserves_inspection_and_deletion_errors(monkeypatch, phase):
    module = cleanup_module()
    calls = []
    failure = subprocess.CalledProcessError(2, ["ip"], stderr="Operation not permitted")
    def run(argv, **kwargs):
        calls.append(argv)
        if phase == "inspect" or len(calls) == 2:
            raise failure
        return subprocess.CompletedProcess(argv, 0, json.dumps([{"ifname": "eth0", "addr_info": [{"local": "198.51.100.20", "prefixlen": 32}]}]), "")
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        module.remove("198.51.100.20", "eth0")
    assert caught.value is failure
    assert len(calls) == (1 if phase == "inspect" else 2)


@pytest.mark.parametrize("reply", ["invalid-json", "[]", "{}", '[{"ifname":"other","addr_info":[]}]', '[{"ifname":"eth0","addr_info":[{}]}]'])
def test_stop_rejects_malformed_or_wrong_interface_inspection(monkeypatch, reply):
    module = cleanup_module()
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, reply, "")
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(ValueError):
        module.remove("198.51.100.20", "eth0")
    assert len(calls) == 1
