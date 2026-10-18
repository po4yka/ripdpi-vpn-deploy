"""DNS-Morph refuses invalid private authority before local host changes."""

from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/dns-morph-bridge"
VALIDATOR = ROOT / "ansible/roles/runtime-release/files/validate_yaml_mapping.py"
SEED = base64.b64encode(bytes(range(32))).decode()
EXAMPLE_SEED = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())["dns_morph_bridge_secrets"]["signing_key"]


def document():
    return {
        "listen": {"address": "0.0.0.0", "port": 53},
        "forward": {"address": "127.0.0.1", "port": 5353, "protocol": "udp"},
        "morph": {"signing_key": SEED, "upstream_endpoint": "127.0.0.1:443"},
        "limits": {"events_per_minute_max": 5000},
        "log": {"dir": "/var/log/dns-morph-bridge"},
    }


def validate(value, *options):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--profile", "dns-morph", *options, "-"],
        input=json.dumps(value), text=True, capture_output=True, timeout=5,
    )


@pytest.mark.parametrize("key", [
    "not-base64-and-not-an-ed25519-key", EXAMPLE_SEED, "",
    base64.b64encode(bytes(31)).decode(), base64.b64encode(bytes(33)).decode(),
    base64.b64encode(bytes(64)).decode(), "A" * 42 + "B=",
    SEED + "\n", "-" + SEED[1:], 42,
])
def test_key_admission_rejects_invalid_seed_without_disclosure(key):
    candidate = document()
    candidate["morph"]["signing_key"] = key
    result = validate(candidate)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "configuration validation failed\n"


@pytest.mark.parametrize("endpoint", ["127.0.0.1:443", "[::1]:443", "bridge.example.com:443"])
def test_canonical_seed_and_data_plane_endpoint_are_admitted(endpoint):
    candidate = document()
    candidate["morph"]["upstream_endpoint"] = endpoint
    assert validate(candidate).returncode == 0


@pytest.mark.parametrize("endpoint", ["", "host", "host:0", "host:65536", "256.0.0.1:443", "[invalid]:443", "-host:443", "https://host:443", 443])
def test_invalid_or_missing_data_plane_endpoint_refuses(endpoint):
    candidate = document()
    candidate["morph"]["upstream_endpoint"] = endpoint
    assert validate(candidate).returncode == 1


def test_echo_only_requires_explicit_selector_and_still_requires_valid_seed():
    candidate = document()
    candidate["morph"]["upstream_endpoint"] = ""
    assert validate(candidate).returncode == 1
    assert validate(candidate, "--allow-dns-morph-echo-only").returncode == 0
    candidate["morph"]["signing_key"] = "invalid"
    assert validate(candidate, "--allow-dns-morph-echo-only").returncode == 1


def test_schema_rejects_noncanonical_seed_and_retains_disabled_placeholders():
    schema = json.loads((ROOT / "secrets/schema.json").read_text())["properties"]["dns_morph_bridge_secrets"]["properties"]["signing_key"]
    for seed in (SEED, "", EXAMPLE_SEED):
        jsonschema.validate(seed, schema)
    for seed in ("invalid", "A" * 42 + "B=", SEED + "\n", base64.b64encode(bytes(64)).decode()):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(seed, schema)


@pytest.mark.parametrize("payload", ["x" * (1024 * 1024 + 1), "morph: {}\nmorph: {}\n"], ids=["oversized", "duplicate-key"])
def test_controller_stdin_retains_size_and_duplicate_key_boundaries(payload):
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--profile", "dns-morph", "-"],
        input=payload, text=True, capture_output=True, timeout=5,
    )
    assert result.returncode == 1
    assert result.stderr == "configuration validation failed\n"


@pytest.mark.parametrize("check_mode", [False, True])
@pytest.mark.parametrize("case", ["invalid-key", "quoted-key", "implicit-echo", "string-selector", "valid", "explicit-echo"])
@pytest.mark.parametrize("entrypoint", ["standalone", "site"])
def test_actual_role_preflight_precedes_mutation_in_normal_and_check_mode(tmp_path, check_mode, case, entrypoint):
    candidate = document()
    selector = False
    if case == "invalid-key":
        candidate["morph"]["signing_key"] = "PRIVATE_INVALID_SEED_MUST_NOT_LEAK"
    if case == "quoted-key":
        candidate["morph"]["signing_key"] = SEED + '\" #'
    if case in ("implicit-echo", "explicit-echo"):
        candidate["morph"]["upstream_endpoint"] = ""
    if case == "explicit-echo":
        profile = yaml.safe_load((ROOT / "ansible/group_vars/vpn-ci-p0p4.yml").read_text())
        selector = profile["dns_morph_bridge_allow_echo_only"]
        assert selector is True
    if case == "string-selector":
        selector = "true"
    first = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())[0]
    assert first["ansible.builtin.import_tasks"] == "preflight.yml"
    first = copy.deepcopy(first)
    first["ansible.builtin.import_tasks"] = str(ROLE / "tasks/preflight.yml")
    if entrypoint == "site":
        site = yaml.safe_load((ROOT / "ansible/playbooks/site.yml").read_text())[0]
        first = next(task for task in site["pre_tasks"]
                     if task.get("ansible.builtin.import_role") == {"name": "dns-morph-bridge", "tasks_from": "preflight"})
        ownership = next(task for task in site["pre_tasks"]
                         if "ansible_play_hosts_all | length == 1"
                         in task.get("ansible.builtin.assert", {}).get("that", []))
        assert site["pre_tasks"].index(ownership) < site["pre_tasks"].index(first)
    sentinel = tmp_path / "host-mutation"
    play = tmp_path / "play.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "gather_facts": False, "become": False,
        "vars": {
            **({"role_path": str(ROLE)} if entrypoint == "standalone" else {}),
            "ansible_python_interpreter": sys.executable,
            "vpn": {"enable_dns_morph_bridge": True},
            "dns_morph_bridge_allow_echo_only": selector,
            "dns_morph_bridge_secrets": {"signing_key": candidate["morph"]["signing_key"]},
            "dns_morph_bridge": {
                "listen_addr": "0.0.0.0", "listen_port": 53,
                "recursor_addr": "127.0.0.1", "recursor_port": 5353,
                "upstream_endpoint": candidate["morph"]["upstream_endpoint"],
                "events_per_minute_max": 5000, "log_dir": "/var/log/dns-morph-bridge",
            },
        },
        "tasks": [first, {
            "name": "Synthetic mutation after admission", "check_mode": False,
            "ansible.builtin.command": {"argv": [sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('changed')", str(sentinel)]},
            "changed_when": True,
        }],
    }]))
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", "-c", "local", "-vvv", *( ["--check"] if check_mode else []), str(play)],
        env={**os.environ, "ANSIBLE_NOCOLOR": "1", "ANSIBLE_STDOUT_CALLBACK": "default",
             "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        text=True, capture_output=True, timeout=30,
    )
    accepted = case in ("valid", "explicit-echo")
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    assert sentinel.exists() is accepted
    assert SEED not in result.stdout + result.stderr
    assert "PRIVATE_INVALID_SEED_MUST_NOT_LEAK" not in result.stdout + result.stderr
