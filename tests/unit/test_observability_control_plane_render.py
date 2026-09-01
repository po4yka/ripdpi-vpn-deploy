"""Static receiver-contract regression tests for the observability control plane."""

from pathlib import Path
import os
import subprocess

import yaml

from scripts.template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"


def _values() -> dict:
    return {
        "observability_control_plane": {
            "ingress_port": 9443,
            "ingress_sni": "ingest.example.test",
            "control_plane_dns_san": "control.example.test",
            "prometheus_listen": "127.0.0.1:9090",
            "remote_write_path_prefix": "/remote-write/v1/nodes",
            "request_body_limit": "8m",
            "request_concurrency": 4,
            "request_rate": "20r/s",
            "request_rate_burst": 40,
            "config_root": "/etc/observability-control-plane",
            "data_dir": "/var/lib/observability-prometheus",
            "service_user": "prometheus",
            "service_group": "prometheus",
            "binary_link": "/usr/local/libexec/observability-prometheus",
            "tsdb_retention_time": "30d",
            "tsdb_retention_size": "20GB",
            "ingest_identities": [
                {"node_id": "vpn-p0"},
                {"node_id": "vpn-p2"},
            ],
        }
    }


def test_ingress_is_only_the_bounded_authenticated_write_path() -> None:
    rendered = render_template(
        ROLE / "templates/observability-remote-write.conf.j2", _values()
    )

    for required in (
        "listen 9443 ssl http2 default_server;",
        "ssl_reject_handshake on;",
        "listen 9443 ssl http2;",
        "ssl_client_certificate /etc/observability-control-plane/tls/client-ca.crt;",
        "ssl_crl /etc/observability-control-plane/tls/client.crl;",
        "ssl_verify_client on;",
        "client_max_body_size 8m;",
        "limit_conn observability_remote_write_conn 4;",
        "rate=20r/s;",
        "burst=40 nodelay;",
        "location ~ ^/remote-write/v1/nodes/",
        "if ($request_method != POST) { return 405; }",
        "if ($observability_remote_write_node != $1) { return 403; }",
        "proxy_pass http://127.0.0.1:9090/api/v1/write;",
        "X-Prometheus-Remote-Write-Version $http_x_prometheus_remote_write_version;",
        "location / { return 404; }",
    ):
        assert required in rendered

    for forbidden in ("/api/v1/query", "/-/reload", "proxy_set_header Authorization"):
        assert forbidden not in rendered


def test_ingress_binds_each_certificate_subject_to_exact_node_path() -> None:
    rendered = render_template(
        ROLE / "templates/observability-remote-write.conf.j2", _values()
    )

    assert '"CN=vpn-p0" vpn-p0;' in rendered
    assert '"CN=vpn-p2" vpn-p2;' in rendered
    assert 'default "";' in rendered


def test_prometheus_service_is_loopback_only_and_storage_is_bounded() -> None:
    rendered = render_template(
        ROLE / "templates/observability-prometheus.service.j2", _values()
    )

    for required in (
        "--web.listen-address=127.0.0.1:9090",
        "--web.enable-remote-write-receiver",
        "--storage.tsdb.retention.time=30d",
        "--storage.tsdb.retention.size=20GB",
        "ProtectSystem=strict",
        "NoNewPrivileges=true",
        "PrivateDevices=true",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "ProtectKernelLogs=yes",
        "ProtectClock=yes",
        "LockPersonality=yes",
        "RestrictNamespaces=yes",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "ReadWritePaths=/var/lib/observability-prometheus",
    ):
        assert required in rendered
    assert "0.0.0.0:9090" not in rendered


def test_role_defaults_and_tasks_fail_closed_before_host_writes() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_control_plane"
    ]
    enabled = (ROLE / "tasks/enable.yml").read_text()

    assert defaults["enabled"] is False
    assert defaults["prometheus"]["version"] == ""
    assert defaults["tls"]["server_key_pem"] == ""
    assert "requires exact bounded receiver settings" in enabled
    assert "- sslclient" in enabled
    assert "- -crl_check_all" in enabled
    assert "ingress_sni != observability_control_plane.control_plane_dns_san" in enabled


def test_enabled_role_refuses_missing_pins_and_mtls_before_mutation(
    tmp_path: Path,
) -> None:
    playbook = tmp_path / "missing-control-plane-contract.yml"
    playbook.write_text("""---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    observability_control_plane:
      enabled: true
  roles:
    - observability_control_plane
""")

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    # The failed assert is intentionally no_log because it checks credential
    # material; its recap proves the refusal happened before any host mutation.
    assert "changed=0" in result.stdout
