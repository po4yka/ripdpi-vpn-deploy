"""P0 REALITY self-steal behavior at the Ansible role boundary."""

import base64
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess

import pytest
import yaml

from tests.site_role_graph import site_roles

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
    assert "reality-self-steal" in [role["role"] for role in site_roles(yaml.safe_load(site)[0])]


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
    # An ordinary site accepts TLS 1.2 and the common groups; REALITY needs TLS 1.3 and X25519.
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in rendered
    assert "ssl_ecdh_curve X25519:prime256v1:secp384r1;" in rendered
    assert re.search(r"ssl_ciphers ECDHE-[A-Z0-9:-]+;", rendered)
    assert "root /var/www/reality-self-steal;" in rendered
    assert "listen 80" not in rendered
    assert "0.0.0.0" not in rendered
    assert "[::]" not in rendered


@pytest.mark.parametrize("xhttp,expected", [
    (None, {"edge.example.test": "301", "_": "404"}),
    ("other.example.test", {"edge.example.test": "301"}),
    ("EDGE.example.test", {}),
], ids=["alone", "beside-another-name", "shared-name"])
def test_opt_in_port_80_redirects_the_owned_name_and_leaves_one_default_server(xhttp, expected) -> None:
    rendered = renderer.render_template(NGINX_TEMPLATE, {
        "reality_self_steal_listen_address": "127.0.0.1", "reality_self_steal_port": 8443,
        "reality_self_steal": {"server_name": "edge.example.test"}, "reality_self_steal_http_redirect": True,
        "vpn": {"enable_nginx_xhttp": xhttp is not None}, "nginx_xhttp": {"server_name": xhttp or ""},
    })
    servers = {}
    for block in rendered.split("\nserver {")[1:]:
        if re.search(r"^\s*listen 80\b", block, re.M):
            (name,) = re.findall(r"server_name (\S+);", block)
            assert "access_log off;" in block and "listen [::]:80" in block
            servers[name] = "301" if "return 301 https://$host$request_uri;" in block else "404"
            assert ("default_server" in block) == (name == "_")
    assert servers == expected


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
        if item["port"] == 443 and item["streamSettings"].get("security") == "reality"
    )
    reality = inbound["streamSettings"]["realitySettings"]

    assert inbound["listen"] == "::"
    assert inbound["port"] == 443
    assert inbound["streamSettings"]["network"] == "raw"
    assert reality["target"] == "127.0.0.1:8443"
    assert reality["serverNames"] == ["edge.example.test"]


def test_enabled_role_rejects_a_non_loopback_xray_target(tmp_path: Path) -> None:
    playbook = tmp_path / "self-steal-invalid.yml"
    playbook.write_text("""---
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
""")
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
    playbook.write_text("""---
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
""")
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
    example = yaml.safe_load(
        (ROOT / "secrets" / "prod.secrets.example.yaml").read_text()
    )
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
    assert '$(echo "$self_steal_cert_pem")' in ci


def test_enabled_role_rejects_server_names_not_bound_to_owned_identity(
    tmp_path: Path,
) -> None:
    playbook = tmp_path / "self-steal-sni-mismatch.yml"
    playbook.write_text("""---
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
""")
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
    playbook.write_text("""---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    xray_port: 443
    xray_fallback_port: 2053
    nginx_xhttp_port: 10085
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
""")
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
    configure = yaml.safe_load(
        (
            ANSIBLE / "roles" / "reality-self-steal" / "tasks" / "configure.yml"
        ).read_text()
    )[0]["vars"]["reality_self_steal_public_tcp_ports"]

    assert "selectattr('enabled', 'equalto', true)" in configure
    assert "public_listener_manifest | default([])" in configure


def test_first_install_check_mode_skips_the_absent_nginx_service() -> None:
    tasks = yaml.safe_load(
        (
            ANSIBLE / "roles" / "reality-self-steal" / "tasks" / "configure.yml"
        ).read_text()
    )
    transaction = next(task for task in tasks if "shared nginx lock" in task["name"])
    assert transaction["ansible.builtin.include_role"] == {
        "name": "nginx-xhttp",
        "tasks_from": "transaction",
    }
    assert transaction["vars"]["nginx_transaction_unit"] == "nginx.service"
    assert transaction["vars"]["nginx_transaction_desired_enabled"] is True
    memory = next(task for task in tasks if "seven-day" in task["name"])
    assert memory["check_mode"] is False
    assert (
        memory["when"]
        == "not ansible_check_mode or (_self_steal_tls_validator.stat.executable | default(false))"
    )
    assert not any("systemd_service" in key for task in tasks for key in task)


def test_enabled_role_rejects_an_unsafe_server_name(tmp_path: Path) -> None:
    playbook = tmp_path / "self-steal-unsafe-server-name.yml"
    playbook.write_text("""---
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
""")
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
    verify_path = (
        ANSIBLE / "roles" / "reality-self-steal" / "molecule" / "default" / "verify.yml"
    )
    verify = verify_path.read_text()
    tasks = yaml.safe_load(verify)[0]["tasks"]
    root_probe = next(
        task
        for task in tasks
        if task["name"] == "HTTPS root returns the ordinary landing site"
    )
    root_probe_lines = {
        line.strip() for line in root_probe["ansible.builtin.shell"]["cmd"].splitlines()
    }

    assert "nginx -t" in verify
    assert (
        "https://edge.example.test:8443/ | grep -q 'LLM Model Notes'"
        in root_probe_lines
    )
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


def test_enabled_role_requires_one_certificate_for_a_hostname_shared_with_nginx_xhttp(
    tmp_path: Path,
) -> None:
    playbook = tmp_path / "self-steal-shared-name.yml"
    playbook.write_text("""---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    vpn:
      enable_xray_reality: true
      enable_nginx_xhttp: true
      enable_reality_self_steal: true
    xray:
      target: 127.0.0.1:8443
      server_names: [edge.example.test]
    nginx_xhttp:
      server_name: Edge.example.test
      cert_pem: direct-frontend-certificate
    reality_self_steal:
      server_name: edge.example.test
      cert_pem: loopback-target-certificate
      key_pem: placeholder
  roles:
    - reality-self-steal
""")
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
    assert "one hostname must present one certificate" in result.stdout
    assert "loopback-target-certificate" not in result.stdout


def test_self_steal_access_log_retains_no_client_address_or_user_agent() -> None:
    rendered = renderer.render_template(
        NGINX_TEMPLATE,
        {
            "reality_self_steal_listen_address": "127.0.0.1",
            "reality_self_steal_port": 8443,
            "reality_self_steal": {"server_name": "edge.example.test"},
        },
    )
    assert not any(field in rendered for field in ("$remote_addr", "$http_referer", "$http_user_agent"))
    assert "access_log /var/log/nginx/reality-self-steal.access.log vpn_self_steal;" in rendered
    assert "log_format vpn_self_steal" in rendered


SELF_STEAL_TASKS = ANSIBLE / "roles" / "reality-self-steal" / "tasks"
SITE_STAGING_TASKS = (
    ("main.yml", "Require an operator-owned self-steal site on production hosts"),
    ("operator-site.yml", "Enumerate the operator-owned self-steal site on the controller"),
    ("operator-site.yml", "Resolve the published self-steal site layout"),
    ("configure.yml", "Require the operator-owned tree to carry the index and the ordinary error page"),
    ("configure.yml", "Refuse repository-bundled bytes in the operator-owned tree"),
    ("configure.yml", "Inspect owned candidate roots without following links"),
    ("configure.yml", "Add the bundled landing assets to the same publication"),
    ("configure.yml", "Add the operator-owned site to the same publication"),
    ("configure.yml", "Retire the bundled pages that the operator-owned tree does not provide"),
)


def _stage_self_steal_site(tmp_path: Path, variables: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
    """Run the role's own site-staging tasks in place of the nginx publication transaction."""
    selected = []
    for name, task_name in SITE_STAGING_TASKS:
        selected.append(next(task for task in yaml.safe_load((SELF_STEAL_TASKS / name).read_text())
                             if task["name"] == task_name))
    result_file = tmp_path / "staged.json"
    play = tmp_path / "site-staging.yml"
    defaults = yaml.safe_load((SELF_STEAL_TASKS.parent / "defaults" / "main.yml").read_text())
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {**defaults, "nginx_transaction_files": [], "role_path": str(SELF_STEAL_TASKS.parent),
                 "reality_self_steal_role_enabled": True, "reality_self_steal_site_root": "/srv/site",
                 "reality_self_steal_tls_dir": "/srv/tls", **variables},
        "tasks": selected + [{"name": "Record staged rows", "ansible.builtin.copy": {
            "dest": str(result_file), "mode": "0600",
            "content": "{{ {'files': nginx_transaction_files, 'roots': _self_steal_candidate_roots.results"
                       " | map(attribute='item') | list} | to_json }}"}}],
    }]))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(play)],
                            env={**os.environ, "ANSIBLE_RETRY_FILES_ENABLED": "0"}, cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    return result, json.loads(result_file.read_text()) if result_file.exists() else None


@pytest.mark.parametrize("production", [{"env": "prod"}, {"env": "p0-workspace", "vpn_build_environment": "prod"}], ids=["env", "named-workspace"])
def test_production_refuses_the_bundled_self_steal_site_before_staging(tmp_path: Path, production) -> None:
    result, staged = _stage_self_steal_site(tmp_path, production)
    assert result.returncode != 0
    assert staged is None
    assert "reality_self_steal_public_site_dir" in result.stdout


def test_non_production_publishes_the_bundled_self_steal_site(tmp_path: Path) -> None:
    result, staged = _stage_self_steal_site(tmp_path, {"env": "staging"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert {row["path"]: row["kind"] for row in staged["files"]} == {
        "/srv/site/index.html": "file", "/srv/site/404.html": "file", "/srv/site/site.css": "file"}
    assert staged["roots"] == [{"path": "/srv/site", "mode": "0755"}, {"path": "/srv/tls", "mode": "0750"}]


def test_operator_tree_replaces_the_bundled_self_steal_site(tmp_path: Path) -> None:
    site = tmp_path / "site"
    (site / "img" / "deep").mkdir(parents=True)
    (site / "index.html").write_text("<h1>owned</h1>")
    (site / "404.html").write_text("missing")
    binary = bytes(range(256)) * 3
    (site / "img" / "deep" / "logo.png").write_bytes(binary)
    result, staged = _stage_self_steal_site(tmp_path, {"env": "prod", "reality_self_steal_public_site_dir": str(site)})
    assert result.returncode == 0, result.stdout + result.stderr
    rows = {row["path"]: row for row in staged["files"]}
    assert {path: row["kind"] for path, row in rows.items()} == {
        "/srv/site/index.html": "file", "/srv/site/404.html": "file", "/srv/site/img/deep/logo.png": "file",
        "/srv/site/site.css": "absent"}
    assert base64.b64decode(rows["/srv/site/index.html"]["content_b64"], validate=True) == b"<h1>owned</h1>"
    assert base64.b64decode(rows["/srv/site/img/deep/logo.png"]["content_b64"], validate=True) == binary
    assert staged["roots"][2:] == [{"path": "/srv/site/img", "mode": "0755"},
                                   {"path": "/srv/site/img/deep", "mode": "0755"}]
    assert "<h1>owned</h1>" not in result.stdout


@pytest.mark.parametrize("missing", ["index.html", "404.html"])
def test_operator_tree_without_a_required_page_refuses(tmp_path: Path, missing: str) -> None:
    site = tmp_path / "site"
    site.mkdir()
    for name in {"index.html", "404.html"} - {missing}:
        (site / name).write_text("page")
    result, staged = _stage_self_steal_site(tmp_path, {"env": "staging", "reality_self_steal_public_site_dir": str(site)})
    assert result.returncode != 0
    assert staged is None
    assert "must contain index.html and 404.html" in result.stdout.replace("\n", " ").replace("  ", " ")


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_operator_tree_that_repeats_a_bundled_page_refuses_under_any_label(tmp_path: Path, env: str) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>owned</h1>")
    bundled = ANSIBLE / "roles" / "nginx-xhttp" / "files" / "public-site" / "404.html"
    (site / "404.html").write_bytes(bundled.read_bytes())
    result, staged = _stage_self_steal_site(tmp_path, {"env": env, "reality_self_steal_public_site_dir": str(site)})
    assert result.returncode != 0
    assert staged is None
    assert "404.html" in result.stdout and "reality_self_steal_public_site_dir" in result.stdout


def test_operator_tree_publishes_no_dot_path_except_well_known(tmp_path: Path) -> None:
    site = tmp_path / "site"
    for directory in (".git", ".well-known"):
        (site / directory).mkdir(parents=True)
    for name in ("index.html", "404.html", ".git/config", ".well-known/security.txt", ".htpasswd"):
        (site / name).write_text(name)
    # Unpublished paths are outside the content and file-type checks.
    (site / ".git" / "packed").write_bytes((ANSIBLE / "roles" / "nginx-xhttp" / "files" / "public-site" / "404.html").read_bytes())
    (site / ".git" / "link").symlink_to("config")
    result, staged = _stage_self_steal_site(tmp_path, {"env": "prod", "reality_self_steal_public_site_dir": str(site)})
    assert result.returncode == 0, result.stdout + result.stderr
    published = {row["path"] for row in staged["files"] if row["kind"] == "file"}
    assert published == {"/srv/site/index.html", "/srv/site/404.html", "/srv/site/.well-known/security.txt"}
    assert {"path": "/srv/site/.well-known", "mode": "0755"} in staged["roots"]
    assert not any(".git" in root["path"] for root in staged["roots"])


@pytest.mark.parametrize("days,accepted", [(20, False), (45, True)])
def test_certificate_needs_thirty_days_of_remaining_lifetime(tmp_path: Path, days: int, accepted: bool) -> None:
    certificate = tmp_path / "cert.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                    "-subj", "/CN=edge.example.test", "-days", str(days), "-keyout", str(tmp_path / "key.pem"),
                    "-out", str(certificate)], check=True, capture_output=True)
    tasks = yaml.safe_load((SELF_STEAL_TASKS / "configure.yml").read_text())
    (floor,) = [task for task in tasks if task["name"] == "Require the minimum remaining certificate lifetime"]
    play = tmp_path / "lifetime.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {**yaml.safe_load((SELF_STEAL_TASKS.parent / "defaults" / "main.yml").read_text()),
                 "reality_self_steal": {"cert_pem": certificate.read_text()}},
        "tasks": [floor],
    }]))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(play)],
                            env={**os.environ, "ANSIBLE_RETRY_FILES_ENABLED": "0"}, cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
