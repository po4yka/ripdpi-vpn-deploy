"""Contract checks for the observability agent sender role."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible" / "roles" / "observability_agent"


def test_private_credentials_do_not_depend_on_system_credstore_traversal() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())

    assert defaults["observability_agent"]["credential_dir"] == (
        "/etc/observability-agent/credentials"
    )


def test_sender_is_fail_closed_and_uses_runtime_release() -> None:
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "observability_agent.version" in tasks
    assert "linux_amd64_sha256" in tasks
    assert "include_role:" in tasks
    assert "name: runtime-release" in tasks
    assert "runtime_release_archive_strip_components: 1" in tasks
    assert "runtime_release_binary_name: promtool" in tasks
    assert "contract/observability-metric-manifest.example.json" in tasks
    assert "Validate candidate observability configuration" in tasks
    assert (
        "not ansible_check_mode"
        not in tasks.split("Install pinned observability agent", 1)[0]
    )
    assert "Assert observability agent owned path boundary" in tasks
    assert (
        "promtool_install_root | default('/opt/observability-agent-promtool')" in tasks
    )


def test_sender_constructs_exact_node_bound_write_path_and_sni() -> None:
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")

    assert "/remote-write/v1/nodes/{{ observability_agent.node_id }}" in template
    assert 'server_name: "{{ observability_agent.receiver_sni }}"' in template
    assert "cert_file: client.crt" in template
    assert "key_file: client.key" in template
    assert "ca_file: receiver-ca.crt" in template
    assert "/run/credentials/observability-agent.service" not in template
    assert "max_shards: 4" in template
    assert "127.0.0.1:9100" in template
    assert "{{ observability_agent.web_listen }}" in template


def test_sender_template_renders_node_path_without_credential_values() -> None:
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")
    rendered = (
        Environment(undefined=StrictUndefined, autoescape=True)
        .from_string(template)
        .render(
            observability_agent={
                "scrape_interval": "30s",
                "scrape_sample_limit": 2000,
                "scrape_label_limit": 16,
                "scrape_label_name_length_limit": 64,
                "scrape_label_value_length_limit": 128,
                "environment": "prod",
                "node_id": "edge-prod",
                "web_listen": "127.0.0.1:19090",
                "receiver_origin": "https://receiver.test",
                "receiver_sni": "ingest.internal.test",
                "queue_capacity": 5000,
                "queue_max_samples_per_send": 1000,
                "queue_batch_send_deadline": "5s",
            }
        )
    )

    document = yaml.safe_load(rendered)
    receiver = document["remote_write"][0]
    assert receiver["url"] == "https://receiver.test/remote-write/v1/nodes/edge-prod"
    assert receiver["tls_config"]["server_name"] == "ingest.internal.test"
    assert receiver["tls_config"]["key_file"] == "client.key"
    assert "BEGIN" not in rendered


def test_service_uses_systemd_credentials_and_bounded_agent_wal() -> None:
    unit = (ROLE / "templates" / "observability-agent.service.j2").read_text(
        encoding="utf-8"
    )

    assert "LoadCredential=client.crt:" in unit
    assert "LoadCredential=client.key:" in unit
    assert "LoadCredential=receiver-ca.crt:" in unit
    assert "LoadCredential=prometheus.yml:" in unit
    assert "WorkingDirectory=%d" in unit
    assert "ExecStartPre=" not in unit
    assert "--config.file=%d/prometheus.yml" in unit
    assert "--config.file=${CREDENTIALS_DIRECTORY}/prometheus.yml" not in unit
    assert (
        "--config.file={{ observability_agent.credential_dir }}/current/prometheus.yml"
        not in unit
    )
    assert "config_dir }}/prometheus.yml" not in unit
    assert " --agent " in unit
    assert " prometheus-observability-agent agent " not in unit
    assert "--storage.agent.retention.max-size=" not in unit
    assert (
        "--storage.agent.retention.max-time={{ observability_agent.wal_max_time }}"
        in unit
    )
    assert "EnvironmentFile=" not in unit
    assert "MemoryMax=" in unit
    assert "TasksMax=" in unit
    assert "CapabilityBoundingSet=" in unit


def test_scrapes_have_explicit_sample_and_label_bounds() -> None:
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")

    assert (
        template.count("sample_limit: {{ observability_agent.scrape_sample_limit }}")
        == 2
    )
    assert (
        template.count("label_limit: {{ observability_agent.scrape_label_limit }}") == 2
    )
    assert template.count("label_name_length_limit:") == 2
    assert template.count("label_value_length_limit:") == 2
    assert "node_metric_name_allowlist" not in template
    assert "node_metric_label_allowlist" not in template
    assert "node_device_allowlist" not in template
    assert "node_mountpoint_allowlist" not in template
    assert "self_metric_name_allowlist" not in template
    assert (
        "^(node_(cpu|memory|filesystem|load|time|boot|network|disk|filefd)_.*"
        in template
    )
    assert "^(__name__|job|cpu|mode|device|fstype|mountpoint)$" in template


def test_credentials_are_validated_as_a_bundle_before_atomic_generation_switch() -> (
    None
):
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    unit = (ROLE / "templates" / "observability-agent.service.j2").read_text(
        encoding="utf-8"
    )

    candidate = tasks.index("Create private observability credential candidate")
    verify_ca = tasks.index("Verify candidate sender certificate authority")
    verify_key = tasks.index("Verify candidate sender private key")
    publish = tasks.index("Atomically publish validated observability generation")
    switch = tasks.index("Switch current observability credential generation")
    validate_config = tasks.index("Validate candidate observability configuration")
    assert candidate < verify_ca < publish < switch
    assert candidate < verify_key < publish < switch
    assert candidate < validate_config < publish < switch
    assert "os.rename(candidate, generation)" in tasks[publish:switch]
    assert 'path: "{{ observability_agent.credential_dir }}/generations"' in tasks
    assert (
        'path: "{{ observability_agent.credential_dir }}/generations"'
        in tasks[:candidate]
    )
    assert "state: link" in tasks[switch:]
    assert "Create observability configuration generation directory" not in tasks
    assert (
        "Reinspect complete observability configuration generation"
        in tasks[publish:switch]
    )
    always_cleanup = tasks.index("Remove private observability credential candidate")
    assert publish < always_cleanup < switch
    assert (
        "LoadCredential=client.crt:{{ observability_agent.credential_dir }}/current/client.crt"
        in unit
    )
    assert (
        "LoadCredential=client.key:{{ observability_agent.credential_dir }}/current/client.key"
        in unit
    )
    assert (
        "LoadCredential=prometheus.yml:{{ observability_agent.credential_dir }}/current/prometheus.yml"
        in unit
    )
    assert "- -purpose\n              - sslclient" in tasks
    assert "- x509\n              - x509" not in tasks
    assert "prometheus.yml" in tasks[publish:switch]
    assert "mode: \"0711\"" in tasks
    assert "'0644' if item.item == 'prometheus.yml' else '0600'" in tasks
    assert "Wait for observability agent local readiness" in tasks[switch:]
    assert "Link observability agent configuration to the active generation" not in tasks


def test_agent_policy_bounds_and_first_activation_rollback_are_fail_closed() -> None:
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    contract = tasks[
        tasks.index(
            "Assert observability agent contract and exact runtime pins"
        ) : tasks.index("Select exact node mTLS sender authority")
    ]

    for bound in (
        "observability_agent.scrape_interval",
        "observability_agent.scrape_label_name_length_limit",
        "observability_agent.scrape_label_value_length_limit",
        "observability_agent.queue_capacity",
        "observability_agent.queue_max_samples_per_send",
        "observability_agent.queue_batch_send_deadline",
        "observability_agent.wal_max_time",
        "observability_agent.memory_max",
        "observability_agent.tasks_max",
        "observability_agent.nofile_limit",
    ):
        assert bound in contract
    assert "urlsplit('port')" in contract
    assert "[^/?#]+" not in contract
    assert "queue_highest_timestamp_seconds" in (
        ROLE / "templates" / "prometheus.yml.j2"
    ).read_text(encoding="utf-8")
    assert "queue_highest_sent_timestamp_seconds" in (
        ROLE / "templates" / "prometheus.yml.j2"
    ).read_text(encoding="utf-8")
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")
    for family in (
        "samples_failed_total",
        "samples_retried_total",
        "samples_dropped_total",
    ):
        assert family in template
    assert "failed_samples_total" not in template
    assert "retried_samples_total" not in template
    assert "dropped_samples_total" not in template

    rescue = tasks.index("Stop and disable failed first observability agent activation")
    refuse = tasks.index("Refuse failed observability generation activation")
    first_activation_rescue = tasks[rescue:refuse]
    assert (
        "Stop and disable failed first observability agent activation"
        in first_activation_rescue
    )
    assert "enabled: false" in first_activation_rescue
    assert "state: stopped" in first_activation_rescue
    assert first_activation_rescue.index(
        "state: stopped"
    ) < first_activation_rescue.index(
        "Remove failed first observability generation activation"
    )
    assert "Assert failed first observability agent activation is inactive" in (
        first_activation_rescue
    )

    switch = tasks.index("Switch current observability credential generation")
    restart = tasks.index("Restart observability agent on the complete generation")
    readiness = tasks.index("Wait for observability agent local readiness")
    assert "register: _observability_agent_generation_switch" in tasks[switch:restart]
    assert "_observability_agent_generation_switch.changed" in tasks[restart:readiness]


def test_self_scrape_follows_the_configured_loopback_listener_and_drops_endpoint_labels() -> (
    None
):
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")

    assert 'targets: ["{{ observability_agent.web_listen }}"]' in template
    assert 'regex: "^(__name__|job)$"' in template
    assert "action: labelkeep" in template
    assert "instance" not in template


def test_disable_removes_only_observability_agent_owned_state() -> None:
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "Remove observability agent owned runtime state" in tasks
    assert "/var/lib/node_exporter/textfile/observability-agent.prom" not in tasks
    assert "prometheus-node-exporter" not in tasks
    assert "watchdog" not in tasks


def test_enabled_scenario_proves_idempotence_queue_age_and_authenticated_drain() -> (
    None
):
    molecule = (ROLE / "molecule" / "enabled" / "molecule.yml").read_text(
        encoding="utf-8"
    )
    verify = (ROLE / "molecule" / "enabled" / "verify.yml").read_text(encoding="utf-8")

    scenario = yaml.safe_load(molecule)["scenario"]["test_sequence"]
    assert scenario == [
        "dependency",
        "syntax",
        "create",
        "prepare",
        "converge",
        "idempotence",
        "verify",
        "destroy",
    ]
    baseline = verify.index(
        "Capture authenticated receiver and remote-write counter baseline"
    )
    stop = verify.index("Stop receiver to exercise bounded local WAL evidence")
    outage = verify.index("Wait for a new remote-write retry and positive queue age")
    restore = verify.index("Restore receiver after bounded outage")
    drain = verify.index("Wait for queue drain and new authenticated receiver arrival")
    assert baseline < stop < outage < restore < drain
    assert "queue_highest_timestamp_seconds" in verify[outage:restore]
    assert "queue_highest_sent_timestamp_seconds" in verify[outage:restore]
    assert "retry > float(sys.argv[1])" in verify[outage:restore]
    assert "received > int(sys.argv[1])" in verify[drain:]


def test_site_uses_the_role_contract_as_the_single_enablement_flag() -> None:
    site = (ROOT / "ansible" / "playbooks" / "site.yml").read_text()
    group_vars = (ROOT / "ansible" / "group_vars" / "all.yml").read_text()

    assert "when: observability_agent.enabled | default(false)" in site
    assert "enable_observability_agent" not in group_vars


def test_molecule_scenarios_execute_the_named_role_and_seed_disable_state_once() -> None:
    default_converge = (ROLE / "molecule/default/converge.yml").read_text()
    default_prepare = (ROLE / "molecule/default/prepare.yml").read_text()
    enabled_converge = (ROLE / "molecule/enabled/converge.yml").read_text()

    assert "- role: observability_agent" in default_converge
    assert "name: observability_agent" in enabled_converge
    assert "Create synthetic agent-owned state" not in default_converge
    assert "Create synthetic agent-owned state" in default_prepare


def test_enabled_molecule_preserves_bounded_failure_diagnostics() -> None:
    converge = yaml.safe_load(
        (ROLE / "molecule" / "enabled" / "converge.yml").read_text()
    )[0]
    exercise = converge["tasks"][0]
    outer = exercise["block"]
    rescue = exercise["rescue"]

    assert outer[0]["ansible.builtin.include_role"] == {"name": "observability_agent"}
    by_name = {task["name"]: task for task in rescue}
    journal = by_name["Read bounded observability agent fixture journal"][
        "ansible.builtin.command"
    ]["argv"]
    assert journal[0] == "/usr/bin/journalctl"
    assert journal[journal.index("--lines=80")] == "--lines=80"
    assert rescue[-1]["ansible.builtin.fail"]["msg"].startswith(
        "Observability agent fixture convergence failed"
    )
