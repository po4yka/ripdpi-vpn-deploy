"""Contract checks for the observability agent sender role."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible" / "roles" / "observability_agent"


def test_sender_is_fail_closed_and_uses_runtime_release() -> None:
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "observability_agent.version" in tasks
    assert "linux_amd64_sha256" in tasks
    assert "include_role:" in tasks
    assert "name: runtime-release" in tasks
    assert "runtime_release_archive_strip_components: 1" in tasks
    assert "not ansible_check_mode" not in tasks.split("Install pinned observability agent", 1)[0]


def test_sender_constructs_exact_node_bound_write_path_and_sni() -> None:
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")

    assert "/remote-write/v1/nodes/{{ observability_agent.node_id }}" in template
    assert "server_name: \"{{ observability_agent.receiver_sni }}\"" in template
    assert "cert_file: ${CREDENTIALS_DIRECTORY}/client.crt" in template
    assert "key_file: ${CREDENTIALS_DIRECTORY}/client.key" in template
    assert "ca_file: ${CREDENTIALS_DIRECTORY}/receiver-ca.crt" in template
    assert "max_shards: 4" in template
    assert "127.0.0.1:9100" in template
    assert "127.0.0.1:19090" in template


def test_sender_template_renders_node_path_without_credential_values() -> None:
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")
    rendered = Environment(undefined=StrictUndefined).from_string(template).render(
        observability_agent={
            "scrape_interval": "30s",
            "environment": "prod",
            "node_id": "edge-prod",
            "metric_name_allowlist": "^vpn_observability_.*$",
            "receiver_origin": "https://receiver.test",
            "receiver_sni": "ingest.internal.test",
            "queue_capacity": 5000,
            "queue_max_samples_per_send": 1000,
            "queue_batch_send_deadline": "5s",
        }
    )

    document = yaml.safe_load(rendered)
    receiver = document["remote_write"][0]
    assert receiver["url"] == "https://receiver.test/remote-write/v1/nodes/edge-prod"
    assert receiver["tls_config"]["server_name"] == "ingest.internal.test"
    assert receiver["tls_config"]["key_file"] == "${CREDENTIALS_DIRECTORY}/client.key"
    assert "BEGIN" not in rendered


def test_service_uses_systemd_credentials_and_bounded_agent_wal() -> None:
    unit = (ROLE / "templates" / "observability-agent.service.j2").read_text(encoding="utf-8")

    assert "LoadCredential=client.crt:" in unit
    assert "LoadCredential=client.key:" in unit
    assert "LoadCredential=receiver-ca.crt:" in unit
    assert "--storage.agent.retention.max-size={{ observability_agent.wal_max_size }}" in unit
    assert "--storage.agent.retention.max-time={{ observability_agent.wal_max_time }}" in unit
    assert "EnvironmentFile=" not in unit


def test_disable_removes_only_observability_agent_owned_state() -> None:
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "Remove observability agent owned runtime state" in tasks
    assert "/var/lib/node_exporter/textfile/observability-agent.prom" not in tasks
    assert "prometheus-node-exporter" not in tasks
    assert "watchdog" not in tasks
