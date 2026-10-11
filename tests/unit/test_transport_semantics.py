"""One validator owns relationships across every transport input boundary."""
from __future__ import annotations

import base64
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from transport_semantics import awg_errors, cohort_errors, hysteria_errors, transport_errors

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/transport_semantics.py"


def key(value):
    return base64.b64encode(bytes([value]) * 32).decode()


def awg():
    return {"server_private_key": key(1), "jc": 4, "jmin": 40, "jmax": 70,
            "s1": 50, "s2": 100, "h1": 11, "h2": 12, "h3": 13, "h4": 14,
            "peers": [{"name": "device", "public_key": key(2), "preshared_key": key(3),
                       "allowed_ips": "10.66.66.2/32"}]}


@pytest.mark.parametrize("refs", [None, [], ["device", "device"], ["missing"], [None], [{"secret": "marker"}]])
def test_incoherent_cohort_membership_is_rejected_without_values(refs):
    cohort = {"name": "technical", "port": 443, "flow_mode": "xtls-rprx-vision"}
    if refs is not None:
        cohort["clients"] = refs
    errors = cohort_errors({"clients": [{"name": "device"}], "cohorts": [cohort]})
    assert errors and "marker" not in json.dumps(errors)


def test_complete_known_cohort_membership_is_accepted():
    assert not cohort_errors({"clients": [{"name": "first"}, {"name": "second"}],
                              "cohorts": [{"name": "technical", "clients": ["second", "first"]}]})


def test_duplicate_client_names_cannot_resolve_an_ambiguous_cohort():
    raw = {"clients": [{"name": "sensitive-marker", "uuid": "first"},
                       {"name": "sensitive-marker", "uuid": "second"}],
           "cohorts": [{"name": "technical", "clients": ["sensitive-marker"]}]}
    assert cohort_errors(raw) == [("xray.clients", "duplicate name")]
    assert "sensitive-marker" not in json.dumps(cohort_errors(raw))
    result = subprocess.run([sys.executable, str(SCRIPT), "--section", "xray"],
                            input=json.dumps({"secrets": {"xray": raw},
                                              "context": {"vpn": {"enable_xray_reality": True}}}),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1 and "duplicate name" in result.stderr
    assert "sensitive-marker" not in result.stdout + result.stderr


@pytest.mark.parametrize("field,value", [("jmin", 71), ("h2", 11), ("h4", True), ("jc", -1),
                                         ("s3", 1), ("s4", -1), ("server_private_key", "sensitive-marker")])
def test_awg_parameter_and_key_failures_are_categorical(field, value):
    raw = awg()
    raw[field] = value
    errors = awg_errors(raw)
    assert errors and "sensitive-marker" not in json.dumps(errors)


@pytest.mark.parametrize("name", ["a" * 16, "../private-marker", "bad/name", "", {"private-marker": True}])
def test_effective_interface_name_uses_runtime_grammar(name):
    errors = awg_errors(awg(), {"interface": name})
    assert errors and "private-marker" not in json.dumps(errors)


@pytest.mark.parametrize("mutation", ["address", "prefix", "public-key", "preshared-key", "key-shape", "key-roles"])
def test_peer_claim_and_key_relationship_failures(mutation):
    raw = awg()
    peer = copy.deepcopy(raw["peers"][0])
    peer.update(name="other", public_key=key(4), preshared_key=key(5), allowed_ips="10.66.66.3/32")
    if mutation == "address":
        peer["allowed_ips"] = "10.66.66.2/32"
    elif mutation == "prefix":
        peer["allowed_ips"] = "10.66.66.0/24"
    elif mutation == "key-shape":
        peer["public_key"] = "private-marker"
    elif mutation == "key-roles":
        peer["preshared_key"] = raw["server_private_key"]
    else:
        field = mutation.replace("-", "_")
        peer[field] = raw["peers"][0][field]
    raw["peers"].append(peer)
    errors = awg_errors(raw)
    assert errors and "private-marker" not in json.dumps(errors)


def test_explicit_routed_prefix_is_legal_but_colliding_device_is_not():
    raw = awg()
    raw["peers"][0].update(address_kind="routed", allowed_ips="10.77.0.0/24")
    assert not awg_errors(raw)
    raw["peers"].append({"name": "other", "public_key": key(4), "preshared_key": key(5),
                         "allowed_ips": "10.77.0.2/32"})
    assert any("conflicting" in message for _, message in awg_errors(raw))


def test_distinct_multi_instances_accept_the_same_effective_validation():
    first = {**awg(), "name": "awg-first", "listen_port": 51900}
    second = copy.deepcopy(first)
    second.update(name="awg-second", listen_port=51901, server_private_key=key(6))
    second["peers"][0].update(name="other", public_key=key(4), preshared_key=key(5), allowed_ips="10.77.0.2/32")
    assert not awg_errors({"instances": [first, second]})
    second["peers"][0]["allowed_ips"] = first["peers"][0]["allowed_ips"]
    assert awg_errors({"instances": [first, second]})


@pytest.mark.parametrize("kind", ["404", "file", "string", "private-marker"])
def test_hysteria_accepts_only_owned_proxy_without_echo(kind):
    errors = hysteria_errors({"masquerade_type": kind, "masquerade_url": "https://owned.example"}, "https://owned.example")
    assert errors and "private-marker" not in json.dumps(errors)


@pytest.mark.parametrize("origin", ["http://owned.example", "https://name:private-marker@owned.example", "https://owned.example/path", "https://owned.example/#private-marker", "https://other.example"])
def test_hysteria_origin_and_ownership_are_shared(origin):
    errors = hysteria_errors({"masquerade_type": "proxy", "masquerade_url": origin}, "https://owned.example")
    assert errors and "private-marker" not in json.dumps(errors)


def test_owned_https_origin_has_positive_acceptance():
    assert not hysteria_errors({"masquerade_type": "proxy", "masquerade_url": "https://owned.example:8443"}, "https://owned.example:8443")


def test_disabled_transport_material_is_not_consulted():
    assert not transport_errors({"xray": "private-marker", "hysteria": "private-marker", "amneziawg_secrets": "private-marker"},
                                {"vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": False,
                                         "enable_hysteria": False, "enable_amneziawg": False}})


def test_shared_cli_consumes_stdin_only_and_reports_categorical_fields():
    raw = awg()
    raw["peers"][0]["public_key"] = "sensitive-marker"
    result = subprocess.run([sys.executable, str(SCRIPT), "--section", "awg"],
                            input=json.dumps({"amneziawg_secrets": raw}), text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 1
    assert "amneziawg_secrets.peers.0.public_key" in result.stderr
    assert "sensitive-marker" not in result.stdout + result.stderr


def test_early_controller_preflight_precedes_every_mutation_boundary(tmp_path):
    preflight = ROOT / "ansible/playbooks/tasks/transport-input-preflight.yml"
    task = yaml.safe_load(preflight.read_text())[0]
    assert task["delegate_to"] == "localhost" and task["become"] is False
    assert task["check_mode"] is False and task["no_log"] is True
    assert "always" in task["tags"] and "stdin" in task["ansible.builtin.command"]
    for name in ("site.yml", "rotate-credentials.yml"):
        play = yaml.safe_load((ROOT / "ansible/playbooks" / name).read_text())[0]
        first = (play.get("pre_tasks") or play["tasks"])[0]
        assert first["ansible.builtin.import_tasks"] == "tasks/transport-input-preflight.yml"
    for role in ("xray", "hysteria", "amneziawg"):
        tasks = yaml.safe_load((ROOT / "ansible/roles" / role / "tasks/enable.yml").read_text())
        assert "transport-input-preflight.yml" in tasks[0]["ansible.builtin.import_tasks"]


@pytest.mark.parametrize("input_kind", ["accepted", "empty-membership", "duplicate-client-name"])
@pytest.mark.parametrize("check_mode", [False, True])
def test_actual_controller_preflight_preserves_before_mutation_and_check_mode(tmp_path, input_kind, check_mode):
    marker = tmp_path / "mutation"
    valid = input_kind == "accepted"
    xray = {"clients": [{"name": "device", "uuid": "00000000-0000-4000-8000-000000000001"}],
            "cohorts": [{"name": "technical", "clients": [] if input_kind == "empty-membership" else ["device"]}]}
    if input_kind == "duplicate-client-name":
        xray["clients"].append({"name": "device", "uuid": "00000000-0000-4000-8000-000000000002"})
    play = tmp_path / "preflight.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {"ansible_python_interpreter": sys.executable, "role_path": str(ROOT / "ansible/roles/xray"),
                 "transport_input_sections": ["xray"], "xray": xray, "vpn": {"enable_xray_reality": True, "enable_hysteria": False, "enable_amneziawg": False}},
        "tasks": [{"ansible.builtin.import_tasks": str(ROOT / "ansible/playbooks/tasks/transport-input-preflight.yml")},
                  {"name": "Publish mutation marker", "ansible.builtin.copy": {"dest": str(marker), "content": "mutated"}}],
    }]))
    argv = ["ansible-playbook", "-i", "localhost,", str(play)]
    if check_mode:
        argv.append("--check")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) is valid, result.stdout + result.stderr
    assert marker.exists() is (valid and not check_mode)
    if not valid:
        assert "Publish mutation marker" not in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.parametrize("prefix", [1, True, ["sensitive-marker"], {"sensitive-marker": True}])
def test_peer_cidr_types_refuse_before_native_render(prefix):
    raw = awg()
    raw["peers"][0]["allowed_ips"] = prefix
    errors = awg_errors(raw)
    assert errors and "sensitive-marker" not in json.dumps(errors)


def test_duplicate_cohort_names_remain_rejected_by_every_semantic_consumer():
    raw = {"clients": [{"name": "device"}], "cohorts": [
        {"name": "same", "clients": ["device"]}, {"name": "same", "clients": ["device"]}]}
    assert ("xray.cohorts", "duplicate name") in cohort_errors(raw)


def test_native_provisioning_is_version_pinned_and_precedes_selected_tests():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["native-runtime"]["steps"]
    build = next(index for index, task in enumerate(steps) if task.get("run") == "make native-transport-semantics-build")
    run = next(index for index, task in enumerate(steps) if "make test-native-runtime" in task.get("run", ""))
    assert build < run
    script = (ROOT / "scripts/build-native-transport-semantics.sh").read_text()
    assert "8225c8380f1ae8122921d4986c2b70976e9c6e6f87a977e7d0498a813f4f3e37" in script
    assert "sha256sum -c -" in script and "GOTOOLCHAIN=local" in script
    assert script.index("git -C \"$destination\" rev-parse HEAD") < script.index('make -C "${native_root}/amneziawg-go-')
    for field in ("amneziawg_go_commit", "amneziawg_tools_commit"):
        assert yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())[field] in steps[run]["run"]
