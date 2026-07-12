"""P0 REALITY self-steal behavior at the Ansible role boundary."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"
RENDERER = ROOT / "scripts" / "check-templates-render.py"
NGINX_TEMPLATE = ANSIBLE / "roles" / "reality-self-steal" / "templates" / "site.conf.j2"
XRAY_TEMPLATE = ANSIBLE / "roles" / "xray" / "templates" / "config.json.j2"

spec = importlib.util.spec_from_file_location("reality_self_steal_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_self_steal_mode_is_default_off_and_wired_as_a_tactical_role() -> None:
    defaults = yaml.safe_load((ANSIBLE / "group_vars" / "all.yml").read_text())
    tiers = yaml.safe_load((ANSIBLE / "role-tiers.yml").read_text())
    site = (ANSIBLE / "playbooks" / "site.yml").read_text()

    assert defaults["vpn"]["enable_reality_self_steal"] is False
    assert tiers["tiers"]["reality-self-steal"] == "tactical"
    assert tiers["toggle_role_map"]["enable_reality_self_steal"] == "reality-self-steal"
    assert "- role: reality-self-steal" in site


def test_self_steal_tls_site_is_loopback_only() -> None:
    rendered = renderer.render_template(
        NGINX_TEMPLATE,
        {
            "reality_self_steal_listen_address": "127.0.0.1",
            "reality_self_steal_port": 8443,
            "reality_self_steal": {"server_name": "edge.example.test"},
        },
    )

    assert "listen 127.0.0.1:8443 ssl http2;" in rendered
    assert "server_name edge.example.test;" in rendered
    assert "ssl_protocols TLSv1.3;" in rendered
    assert "root /var/www/reality-self-steal;" in rendered
    assert "listen 80" not in rendered
    assert "0.0.0.0" not in rendered
    assert "[::]" not in rendered


def test_self_steal_unknown_paths_use_the_ordinary_site_404() -> None:
    rendered = renderer.render_template(
        NGINX_TEMPLATE,
        {
            "reality_self_steal_listen_address": "127.0.0.1",
            "reality_self_steal_port": 8443,
            "reality_self_steal": {"server_name": "edge.example.test"},
        },
    )

    assert "error_page 404 /404.html;" in rendered
    assert "location = /404.html" in rendered
    assert "internal;" in rendered
    for forbidden in ("/health", "/metrics", "/admin"):
        assert forbidden not in rendered


def test_xray_public_reality_inbound_targets_the_owned_loopback_site() -> None:
    variables = renderer.merge_render_vars()
    variables["vpn"] = {
        **variables["vpn"],
        "enable_xray_reality": True,
        "enable_nginx_xhttp": False,
    }
    variables["xray"] = {
        **variables["xray"],
        "target": "127.0.0.1:8443",
        "server_names": ["edge.example.test"],
        "reality_private_key": "TEST_PLACEHOLDER",
        "clients": [
            {
                "name": "test-device",
                "uuid": "11111111-1111-1111-1111-111111111111",
                "short_id": "deadbeef",
            }
        ],
    }
    rendered = json.loads(renderer.render_template(XRAY_TEMPLATE, variables))
    inbound = next(
        item
        for item in rendered["inbounds"]
        if item["port"] == 443
        and item["streamSettings"].get("security") == "reality"
    )
    reality = inbound["streamSettings"]["realitySettings"]

    assert inbound["listen"] == "0.0.0.0"
    assert inbound["port"] == 443
    assert inbound["streamSettings"]["network"] == "raw"
    assert reality["target"] == "127.0.0.1:8443"
    assert reality["serverNames"] == ["edge.example.test"]


def test_enabled_role_rejects_a_non_loopback_xray_target(tmp_path: Path) -> None:
    playbook = tmp_path / "self-steal-invalid.yml"
    playbook.write_text(
        """---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    vpn:
      enable_xray_reality: true
      enable_reality_self_steal: true
    xray:
      target: remote.example.test:443
      server_names: [edge.example.test]
    reality_self_steal:
      server_name: edge.example.test
      cert_pem: placeholder
      key_pem: placeholder
  roles:
    - reality-self-steal
"""
    )
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles")}

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must equal the loopback TLS endpoint" in result.stdout


def test_enabled_role_rejects_missing_self_steal_secrets(tmp_path: Path) -> None:
    playbook = tmp_path / "self-steal-missing-secrets.yml"
    playbook.write_text(
        """---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    vpn:
      enable_xray_reality: true
      enable_reality_self_steal: true
    xray:
      target: 127.0.0.1:8443
      server_names: [edge.example.test]
  roles:
    - reality-self-steal
"""
    )
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles")}

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "requires reality_self_steal.server_name" in result.stdout


def test_self_steal_has_a_dedicated_certificate_secret_contract() -> None:
    example = yaml.safe_load((ROOT / "secrets" / "prod.secrets.example.yaml").read_text())
    schema = yaml.safe_load((ROOT / "secrets" / "schema.json").read_text())

    assert set(example["reality_self_steal"]) == {"server_name", "cert_pem", "key_pem"}
    contract = schema["properties"]["reality_self_steal"]
    assert set(contract["required"]) == {"server_name", "cert_pem", "key_pem"}
    assert contract["additionalProperties"] is False


def test_secret_bootstraps_seed_self_steal_from_the_owned_tls_identity() -> None:
    operator = (ROOT / "scripts" / "bootstrap-secrets.sh").read_text()
    ci = (ROOT / "scripts" / "ci-bootstrap-secrets.sh").read_text()

    assert "reality_self_steal:" in operator
    assert "server_name: ${SERVER_NAME_YAML}" in operator
    assert "reality_self_steal:" in ci
    assert 'server_name: "${REALITY_SERVER_NAME}"' in ci
    assert "$(echo \"$self_steal_cert_pem\")" in ci


def test_enabled_role_rejects_server_names_not_bound_to_owned_identity(tmp_path: Path) -> None:
    playbook = tmp_path / "self-steal-sni-mismatch.yml"
    playbook.write_text(
        """---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    vpn:
      enable_xray_reality: true
      enable_reality_self_steal: true
    xray:
      target: 127.0.0.1:8443
      server_names: [borrowed.example.test]
    reality_self_steal:
      server_name: edge.example.test
      cert_pem: placeholder
      key_pem: placeholder
  roles:
    - reality-self-steal
"""
    )
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles")}

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must contain only the owned certificate hostname" in result.stdout


def test_enabled_role_rejects_a_public_listener_port_collision(tmp_path: Path) -> None:
    playbook = tmp_path / "self-steal-public-port-collision.yml"
    playbook.write_text(
        """---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    vpn:
      enable_xray_reality: true
      enable_reality_self_steal: true
    xray:
      target: 127.0.0.1:8443
      server_names: [edge.example.test]
    reality_self_steal:
      server_name: edge.example.test
      cert_pem: placeholder
      key_pem: placeholder
    public_listener_manifest:
      - {name: nginx-xhttp, protocol: tcp, port: 8443, enabled: true}
  roles:
    - reality-self-steal
"""
    )
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles")}

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "private, non-conflicting TCP port" in result.stdout


def test_collision_guard_ignores_disabled_public_manifest_entries() -> None:
    configure = (
        ANSIBLE / "roles" / "reality-self-steal" / "tasks" / "configure.yml"
    ).read_text()

    assert "selectattr('enabled', 'equalto', true)" in configure
    assert "public_listener_manifest | default([])" in configure


def test_first_install_check_mode_skips_the_absent_nginx_service() -> None:
    tasks = yaml.safe_load(
        (
            ANSIBLE / "roles" / "reality-self-steal" / "tasks" / "configure.yml"
        ).read_text()
    )
    ensure_nginx = next(
        task for task in tasks if task["name"] == "Ensure nginx is enabled and started"
    )
    condition = " ".join(ensure_nginx["when"])

    assert "not ansible_check_mode" in condition
    assert "'nginx.service' in" in condition
    assert "ansible_facts.services | default({})" in condition


def test_enabled_role_rejects_an_unsafe_server_name(tmp_path: Path) -> None:
    playbook = tmp_path / "self-steal-unsafe-server-name.yml"
    playbook.write_text(
        """---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    vpn:
      enable_xray_reality: true
      enable_reality_self_steal: true
    reality_self_steal:
      server_name: "edge.example.test; listen 0.0.0.0:8443"
      cert_pem: placeholder
      key_pem: placeholder
  roles:
    - reality-self-steal
"""
    )
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles")}

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "requires reality_self_steal.server_name" in result.stdout


def test_molecule_verifies_live_tls_site_and_private_binding() -> None:
    verify = (
        ANSIBLE
        / "roles"
        / "reality-self-steal"
        / "molecule"
        / "default"
        / "verify.yml"
    ).read_text()

    assert "nginx -t" in verify
    assert "https://edge.example.test:8443/" in verify
    assert "LLM Model Notes" in verify
    assert "ALPN protocol: h2" in verify
    assert "/current/privkey.pem" in verify
    assert "127.0.0.1:8443" in verify
    assert "0.0.0.0:8443" in verify
    assert "must not expose" in verify


def test_molecule_verifies_disabling_mode_removes_the_private_listener() -> None:
    verify = (
        ANSIBLE
        / "roles"
        / "reality-self-steal"
        / "molecule"
        / "disabled"
        / "verify.yml"
    ).read_text()

    assert "/etc/nginx/sites-enabled/reality-self-steal.conf" in verify
    assert "/etc/nginx/reality-self-steal" in verify
    assert "/var/www/reality-self-steal" in verify
    assert "127.0.0.1:8443" in verify
    assert "must be absent" in verify
    assert "Default-off steady state is a no-op" in verify
    converge = (
        ANSIBLE
        / "roles"
        / "reality-self-steal"
        / "molecule"
        / "disabled"
        / "converge.yml"
    ).read_text()
    assert "Simulate interrupted cleanup" in converge
    assert "stale in-memory listener" in converge
