"""Production refuses two unrelated TLS identities on one public address."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import yaml

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "ansible/playbooks/tasks/tls-identity-preflight.yml"
GROUP_VARS = ROOT / "ansible/group_vars"
MANIFEST = ROOT / "ansible/roles/node_manifest/templates/manifest.json.j2"
FULL = {"enable_xray_reality": True, "enable_reality_self_steal": False,
        "enable_nginx_xhttp": True, "enable_hysteria": True}
P0 = {**FULL, "enable_nginx_xhttp": False, "enable_hysteria": False}


def evaluate(tmp_path: Path, cases: dict[str, dict]) -> dict[str, str | None]:
    """Run the real preflight task once for each case; return its failure message or None."""
    (task,) = yaml.safe_load(PREFLIGHT.read_text())
    tasks = []
    for index, variables in enumerate(cases.values()):
        tasks.append({**task, "vars": {**task["vars"], **variables}, "ignore_errors": True,
                      "register": f"outcome_{index}", "tags": []})
    result_file = tmp_path / "outcomes.json"
    outcomes = "[" + ", ".join(
        f"(outcome_{index}.msg if outcome_{index} is failed else none)" for index in range(len(cases))) + "]"
    tasks.append({"name": "Record outcomes", "ansible.builtin.copy": {
        "dest": str(result_file), "mode": "0600", "content": "{{ " + outcomes + " | to_json }}"}})
    play = tmp_path / "preflight.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {"ansible_python_interpreter": sys.executable}, "tasks": tasks}]))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(play)],
                            env={**os.environ, "ANSIBLE_RETRY_FILES_ENABLED": "0"}, cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return dict(zip(cases, json.loads(result_file.read_text())))


def test_production_refuses_a_borrowed_target_beside_the_operator_certificate(tmp_path: Path) -> None:
    outcomes = evaluate(tmp_path, {
        "hysteria": {"env": "prod", "vpn": {**P0, "enable_hysteria": True}},
        # A permanent workspace has its own name as env; inventory marks it with vpn_build_environment.
        "named_workspace": {"env": "p0-workspace", "vpn_build_environment": "prod", "vpn": {**P0, "enable_hysteria": True}},
        "xhttp": {"env": "prod", "vpn": {**P0, "enable_nginx_xhttp": True}, "nginx_xhttp_public_port": 8443},
        "other_network": {"env": "prod", "vpn": P0, "reality_target_network": "different_asn"},
        "blank_exception": {"env": "prod", "vpn": FULL, "tls_identity_exception": "  "},
    })
    assert all(outcomes.values()), outcomes
    flat = {name: " ".join(message.split()) for name, message in outcomes.items()}
    for message in flat.values():
        assert "REALITY on TCP/443" in message
        assert all(way in message for way in (
            "vpn.enable_reality_self_steal", "node without those listeners", "tls_identity_exception"))
    assert "Hysteria on UDP/443 present the operator certificate" in flat["hysteria"]
    assert "nginx-xhttp" not in flat["hysteria"]
    assert "nginx-xhttp on TCP/8443 present the operator certificate" in flat["xhttp"]
    assert "different network" in flat["other_network"] and "present the operator" not in flat["other_network"]
    assert "Hysteria on UDP/443 and nginx-xhttp on TCP/8443" in flat["blank_exception"]


def test_rendered_inventory_marks_a_named_workspace_as_production(tmp_path: Path) -> None:
    """`make inventory` writes the build environment as a shell-quoted JSON string; Ansible must read it as prod."""
    (task,) = yaml.safe_load(PREFLIGHT.read_text())
    inventory = tmp_path / "hosts.ini"
    inventory.write_text("[vpn]\nnode ansible_connection=local env=p0-workspace vpn_build_environment="
                         + shlex.quote(json.dumps("prod")) + "\n")
    play = tmp_path / "preflight.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "all", "gather_facts": False, "become": False,
        "vars": {"ansible_python_interpreter": sys.executable, "vpn": {**P0, "enable_hysteria": True}},
        "tasks": [{**task, "tags": []}]}]))
    result = subprocess.run(["ansible-playbook", "-i", str(inventory), str(play)],
                            env={**os.environ, "ANSIBLE_RETRY_FILES_ENABLED": "0"}, cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode != 0
    assert "REALITY on TCP/443" in " ".join(result.stdout.split())


def test_one_identity_an_exception_or_a_non_production_host_passes(tmp_path: Path) -> None:
    outcomes = evaluate(tmp_path, {
        "self_steal": {"env": "prod", "vpn": {**FULL, "enable_reality_self_steal": True}},
        "exception": {"env": "prod", "vpn": FULL, "reality_target_network": "different_asn",
                      "tls_identity_exception": "measured 2026-11-01: path keeps both listeners"},
        "staging": {"env": "staging", "vpn": FULL, "reality_target_network": "different_asn"},
        "no_env": {"vpn": FULL},
        "p0_same_network": {"env": "prod", "vpn": P0, "reality_target_network": "same_asn"},
        "p0_not_recorded": {"env": "prod", "vpn": P0},
        "p0_unknown": {"env": "prod", "vpn": P0, "reality_target_network": "unknown"},
        "no_reality": {"env": "prod", "vpn": {**FULL, "enable_xray_reality": False}},
        "subscription_only": {"env": "prod", "vpn": FULL, "vpn_subscription_only": True},
    })
    assert outcomes == dict.fromkeys(outcomes, None)


def test_an_unknown_network_value_refuses_everywhere(tmp_path: Path) -> None:
    outcomes = evaluate(tmp_path, {"typo": {"env": "staging", "vpn": P0, "reality_target_network": "same"}})
    assert "reality_target_network accepts same_asn, different_asn or unknown" in " ".join(outcomes["typo"].split())


def test_committed_profiles_that_need_a_layout_change_or_an_exception_on_production(tmp_path: Path) -> None:
    base = yaml.safe_load((GROUP_VARS / "all.yml").read_text())
    cases = {}
    for path in sorted(GROUP_VARS.glob("*.yml")):
        profile = yaml.safe_load(path.read_text()) or {}
        # The controller replaces the canonical vpn map with the profile's map.
        cases[path.stem] = {"env": "prod", "vpn": profile.get("vpn", base["vpn"])}
    refused = {name for name, message in evaluate(tmp_path, cases).items() if message}
    assert refused == {
        "all", "vpn", "vpn-ci-p0p1", "vpn-ci-p0p1p2", "vpn-device-full", "vpn-device-full-staging",
        "vpn-device-full-tailnet", "vpn-device-full-warp-staging", "vpn-family-standard", "vpn-fullstack", "vpn-lab",
        "vpn-prod-hardened",
        "vpn-split-hop-family-egress-staging",
        "vpn-split-hop-ingress-live", "vpn-split-hop-ingress-staging",
    }


def test_manifest_records_an_active_exception_without_its_reason() -> None:
    variables = merge_render_vars()
    assert json.loads(render_template(MANIFEST, variables))["security_controls"]["tls_identity_exception"] is False
    variables["tls_identity_exception"] = "measured 2026-11-01: path keeps both listeners"
    rendered = render_template(MANIFEST, variables)
    assert json.loads(rendered)["security_controls"]["tls_identity_exception"] is True
    assert "measured" not in rendered
