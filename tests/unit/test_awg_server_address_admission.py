"""Reserve every AWG server host address before peer delivery or mutation."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest
import yaml

from awg_client import enroll, export
from awg_device_binding import BindingError, resolve_binding
from test_awg_device_binding import document, key, public_key
from transport_semantics import awg_errors, transport_errors

ROOT = Path(__file__).resolve().parents[2]


def full_document():
    source = yaml.safe_load((ROOT / "tests/fixtures/secrets-sample.yml").read_text())
    source.update(document())
    return source


def collision(version, kind="device", *, same_instance=False):
    source = full_document()
    first, second = source["amneziawg_secrets"]["instances"]
    family = f"ipv{version}"
    if kind == "device":
        first[f"address_v{version}"] = "10.71.0.2/29" if version == 4 else "fd42:11::2/64"
        first["peers"][0]["allowed_ips"][family] = "10.71.0.3/32" if version == 4 else "fd42:11::3/128"
    else:
        target = first if same_instance else second
        target["peers"][0]["allowed_ips"][family] = (
            f"10.{70 if same_instance else 71}.0.6/32" if version == 4
            else f"fd42:{10 if same_instance else 11}::6/128"
        )
        prefix = (f"10.{70 if same_instance else 71}.0.0/30" if version == 4
                  else f"fd42:{10 if same_instance else 11}::/126")
        first["peers"].append({"name": "routed", "address_kind": "routed",
                               "public_key": public_key(key(30)), "preshared_key": key(31),
                               "allowed_ips": {family: prefix}})
    # Every regression input passes the complete public structural contract.
    schema = json.loads((ROOT / "secrets/schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(source)
    return source


@pytest.mark.parametrize("version", [4, 6])
@pytest.mark.parametrize("kind,same_instance", [("device", False), ("routed", False), ("routed", True)])
def test_peer_prefix_cannot_cover_any_instance_server(version, kind, same_instance):
    source = collision(version, kind, same_instance=same_instance)
    errors = awg_errors(source["amneziawg_secrets"])
    assert any(message == "peer prefix contains an instance server address" for _, message in errors)
    assert transport_errors(source, {}, sections=["awg"])
    diagnostic = json.dumps(errors)
    for instance in source["amneziawg_secrets"]["instances"]:
        assert instance[f"address_v{version}"].split("/")[0] not in diagnostic
        assert instance["server_private_key"] not in diagnostic


@pytest.mark.parametrize("version", [4, 6])
@pytest.mark.parametrize("kind", ["device", "routed"])
def test_binding_export_and_enrollment_refuse_without_mutating_input(version, kind):
    source = collision(version, kind)
    before = copy.deepcopy(source)
    for name, instance in (("device0", "awg0"), ("device1", "awg1")):
        with pytest.raises(BindingError, match="invalid-awg-contract"):
            resolve_binding(source, {}, name, "upcloud:fixture", instance)
        with pytest.raises(BindingError, match="invalid-awg-contract"):
            export(source, {}, name, "upcloud:fixture", instance, "192.0.2.1")
    with pytest.raises(BindingError, match="invalid-awg-contract"):
        enroll(source, {}, "new-device", "upcloud:fixture", "awg0")
    assert source == before


def test_nonconflicting_overlapping_pools_and_routed_prefixes_remain_supported():
    source = full_document()
    first, second = source["amneziawg_secrets"]["instances"]
    second.update(address_v4="10.70.0.3/29", address_v6="fd42:10::3/64")
    second["peers"][0]["allowed_ips"] = {"ipv4": "10.70.0.4/32", "ipv6": "fd42:10::4/128"}
    first["peers"].append({"name": "routed", "address_kind": "routed",
                           "public_key": public_key(key(30)), "preshared_key": key(31),
                           "allowed_ips": {"ipv4": "10.70.0.6/31", "ipv6": "fd42:10::6/127"}})
    assert not awg_errors(source["amneziawg_secrets"])
    assert not transport_errors(source, {}, sections=["awg"])
    for name, instance in (("device0", "awg0"), ("device1", "awg1")):
        selected = resolve_binding(source, {}, name, "upcloud:fixture", instance)
        assert selected.instance["name"] == instance
        assert export(source, {}, name, "upcloud:fixture", instance, "192.0.2.1")


@pytest.mark.parametrize("version", [4, 6])
@pytest.mark.parametrize("check_mode", [False, True])
def test_actual_ansible_preflight_refuses_collision_before_publication(tmp_path, version, check_mode):
    source = collision(version)
    marker = tmp_path / "publication"
    play = tmp_path / "preflight.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {"ansible_python_interpreter": sys.executable,
                 "role_path": str(ROOT / "ansible/roles/amneziawg"),
                 "transport_input_sections": ["awg"],
                 "amneziawg_secrets": source["amneziawg_secrets"],
                 "vpn": {"enable_xray_reality": False, "enable_hysteria": False, "enable_amneziawg": True}},
        "tasks": [{"ansible.builtin.import_tasks": str(ROOT / "ansible/playbooks/tasks/transport-input-preflight.yml")},
                  {"name": "Publish synthetic authority", "ansible.builtin.copy": {"dest": str(marker), "content": "published"}}],
    }]))
    play.chmod(0o600)
    argv = ["ansible-playbook", "-i", "localhost,", str(play)]
    if check_mode:
        argv.append("--check")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30,
                            env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                                 "ANSIBLE_NOCOLOR": "1", "ANSIBLE_STDOUT_CALLBACK": "default"})
    assert result.returncode != 0
    assert not marker.exists()
    assert "Validate enabled transport semantics before mutation" in result.stdout
    assert "Publish synthetic authority" not in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
