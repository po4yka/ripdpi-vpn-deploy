"""Contract checks for the observability agent sender role."""

from __future__ import annotations

import builtins
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, StrictUndefined
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible" / "roles" / "observability_agent"


def _run_embedded_verification_script(
    script: str,
    *,
    metrics: str,
    receiver_rows: list[dict[str, str]],
    args: list[str],
) -> tuple[int, dict[str, int | float]]:
    class Response:
        def read(self) -> bytes:
            import pathlib

            assert pathlib.Path is Path
            return metrics.encode("utf-8")

    class ReceiverLog:
        def exists(self) -> bool:
            return bool(receiver_rows)

        def read_text(self) -> str:
            return "\n".join(json.dumps(row) for row in receiver_rows)

    fixture_modules = {
        "sys": SimpleNamespace(argv=["verification-script", *args]),
        "pathlib": SimpleNamespace(Path=lambda _path: ReceiverLog()),
        "urllib.request": SimpleNamespace(
            request=SimpleNamespace(urlopen=lambda *_args, **_kwargs: Response())
        ),
    }

    def fixture_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name in fixture_modules:
            return fixture_modules[name]
        return builtins.__import__(name, globals, locals, fromlist, level)

    # Only this execution sees the fixtures; never mutate shared stdlib modules.
    namespace = {
        "__name__": "__main__",
        "__builtins__": {**vars(builtins), "__import__": fixture_import},
    }
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), pytest.raises(SystemExit) as result:
        exec(script, namespace)
    return_code = int(result.value.code)

    return return_code, json.loads(stdout.getvalue())


def test_private_credentials_do_not_depend_on_system_credstore_traversal() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())

    assert defaults["observability_agent"]["credential_dir"] == (
        "/etc/observability-agent/credentials"
    )


def test_required_systemd_allowlist_matches_control_plane_policy() -> None:
    group_vars = yaml.safe_load((ROOT / "ansible/group_vars/all.yml").read_text())
    required = group_vars["observability_alert_policy"]["required_systemd_units"]
    assert required == sorted(set(required))
    assert (
        "observability_alert_policy.required_systemd_units"
        in (ROLE / "templates/prometheus.yml.j2").read_text()
    )
    assert (
        "{% set policy = observability_alert_policy -%}"
        in (
            ROOT
            / "ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2"
        ).read_text()
    )
    for caller in (
        ROLE / "molecule/enabled/converge.yml",
        ROOT
        / "ansible/roles/observability_control_plane/molecule/enabled/tasks/fixture-contract.yml",
    ):
        source = caller.read_text()
        assert "group_vars/all.yml" in source
        assert ").observability_alert_policy" in source
        assert "required_systemd_units:" not in source


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
            observability_alert_policy={
                "required_systemd_units": ["nginx.service", "xray.service"]
            },
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
            },
        )
    )

    document = yaml.safe_load(rendered)
    assert document["global"]["external_labels"] == {
        "environment": "prod",
        "node": "edge-prod",
    }
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
    assert unit.index("WorkingDirectory=%d") < unit.index("ExecStart=")
    assert "ExecStartPre=" not in unit
    assert (
        "/generations/{{ _observability_agent_service_generation }}/prometheus.yml"
        in unit
    )
    assert "/current/" not in unit
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
        == 3
    )
    assert (
        template.count("label_limit: {{ observability_agent.scrape_label_limit }}") == 3
    )
    assert template.count("label_name_length_limit:") == 3
    assert template.count("label_value_length_limit:") == 3
    assert "node_metric_name_allowlist" not in template
    assert "node_metric_label_allowlist" not in template
    assert "node_device_allowlist" not in template
    assert "node_mountpoint_allowlist" not in template
    assert "self_metric_name_allowlist" not in template
    assert "^(node_(cpu|memory|filesystem|time|boot|network|disk|filefd)_.*" in template
    assert "node_load(1|5|15)" in template
    assert (
        "^(__name__|job|cpu|mode|device|fstype|mountpoint|node|role|state)$" in template
    )
    assert 'node: "{{ observability_agent.node_id }}"' in template
    for family_prefix in (
        "watchdog_",
        "backup_",
        "certificate_",
        "honeypot_",
        "policy_ratelimit_",
        "burn_",
    ):
        assert family_prefix in template


def test_required_systemd_scrape_is_exactly_allowlisted() -> None:
    template = (ROLE / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")
    rendered = (
        Environment(undefined=StrictUndefined, autoescape=True)
        .from_string(template)
        .render(
            observability_alert_policy={
                "required_systemd_units": ["nginx.service", "xray.service"]
            },
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
            },
        )
    )
    document = yaml.safe_load(rendered)
    service_scrape = next(
        job
        for job in document["scrape_configs"]
        if job["job_name"] == "node-exporter-required-services"
    )

    assert service_scrape["static_configs"] == [{"targets": ["127.0.0.1:9100"]}]
    assert service_scrape["metric_relabel_configs"][0] == {
        "source_labels": ["__name__", "name", "state"],
        "regex": (
            "^node_systemd_unit_state;(nginx[.]service|xray[.]service);"
            "(active|failed)$"
        ),
        "action": "keep",
    }
    assert service_scrape["metric_relabel_configs"][1]["regex"] == (
        "^(__name__|job|name|state)$"
    )
    assert "ssh.service" not in service_scrape["metric_relabel_configs"][0]["regex"]


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
    assert tasks.index(
        "Bind observability service to the candidate credential generation"
    ) < tasks.index("Install observability agent units")
    assert "WorkingDirectory=%d" in unit
    for name in ("client.crt", "client.key", "receiver-ca.crt", "prometheus.yml"):
        assert (
            f"LoadCredential={name}:{{{{ observability_agent.credential_dir }}}}/"
            "generations/{{ _observability_agent_service_generation }}/"
            f"{name}"
        ) in unit
    assert "Assert active observability generation target is role-owned" in tasks
    assert "^generations/[a-f0-9]{64}$" in tasks
    assert "observability_agent.credential_dir ~ '/generations/'" in tasks
    assert "Normalize active observability credential generation" in tasks
    active_target = tasks.index(
        "Assert active observability generation target is role-owned"
    )
    service_activity = tasks.index("Inspect observability agent service activity")
    assert "stat.lnk_target" in tasks[active_target:service_activity]
    assert "stat.lnk_source" not in tasks[active_target:service_activity]
    restore = tasks.index("Restore previous observability generation")
    bind_previous = tasks.index(
        "Bind restored service to the previous credential generation"
    )
    restore_unit = tasks.index("Restore previous observability agent service unit")
    restart_previous = tasks.index("Restart restored observability generation")
    assert restore < bind_previous < restore_unit < restart_previous
    normalize = tasks.index("Normalize active observability credential generation")
    rollback = tasks[restore:restart_previous]
    assert "stat.lnk_target | basename" in tasks[active_target:service_activity]
    assert normalize < service_activity
    assert (
        'src: "generations/{{ _observability_agent_previous_generation_id }}"'
        in rollback
    )
    assert "{{ _observability_agent_previous_generation_id }}" in rollback
    assert "stat.lnk_source" not in rollback
    assert "- -purpose\n              - sslclient" in tasks
    assert "- x509\n              - x509" not in tasks
    assert "prometheus.yml" in tasks[publish:switch]
    assert 'mode: "0711"' in tasks
    assert "'0644' if item.item == 'prometheus.yml' else '0600'" in tasks
    assert "Wait for observability agent local readiness" in tasks[switch:]
    assert (
        "Link observability agent configuration to the active generation" not in tasks
    )


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
    disable = tasks[
        tasks.index(
            "Disable observability agent when feature is disabled"
        ) : tasks.index("Configure observability agent when feature is enabled")
    ]

    assert "Remove observability agent owned runtime state" in tasks
    assert "/var/lib/node_exporter/textfile/observability-agent.prom" not in tasks
    assert "prometheus-node-exporter" not in tasks
    assert "/var/lib/vpn-watchdog/state" not in disable
    assert "/var/lib/vpn-backup" not in disable


def test_adapter_explicitly_joins_the_textfile_writer_group() -> None:
    unit = (ROLE / "templates" / "observability-agent-adapter.service.j2").read_text(
        encoding="utf-8"
    )

    assert (
        "SupplementaryGroups={{ monitoring.node_exporter_textfile_group "
        "| default('node_exporter_textfile') }}"
    ) in unit
    assert unit.index("SupplementaryGroups=") < unit.index("ExecStart=")


def test_enabled_scenario_proves_idempotence_queue_age_and_authenticated_drain() -> (
    None
):
    molecule = (ROLE / "molecule" / "enabled" / "molecule.yml").read_text(
        encoding="utf-8"
    )
    verify = (ROLE / "molecule" / "enabled" / "verify.yml").read_text(encoding="utf-8")

    scenario = yaml.safe_load(molecule)["scenario"]["test_sequence"]
    platform = yaml.safe_load(molecule)["platforms"][0]
    assert platform["tmpfs"] == ["/run:rw,rshared"]
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
    drain = verify.index(
        "Wait for outage watermark recovery and new authenticated receiver arrival"
    )
    assert baseline < stop < outage < restore < drain
    assert "queue_highest_timestamp_seconds" in verify[outage:restore]
    assert "queue_highest_sent_timestamp_seconds" in verify[outage:restore]
    assert "retry > float(sys.argv[1])" in verify[outage:restore]
    assert "received > int(sys.argv[1])" in verify[drain:]
    arrival = verify[:baseline]
    for field in (
        "'arrived': arrived",
        "'received': len(rows)",
        "'failed': maximum('prometheus_remote_storage_samples_failed_total')",
        "'retried': maximum('prometheus_remote_storage_samples_retried_total')",
        "'pending': maximum('prometheus_remote_storage_samples_pending')",
        "'highest': maximum('prometheus_remote_storage_queue_highest_timestamp_seconds')",
        "'highest_sent': maximum('prometheus_remote_storage_queue_highest_sent_timestamp_seconds')",
        "'request_headers': events.count('headers')",
        "'length_rejected': events.count('length_rejected')",
        "'short_body': events.count('short_body')",
        "'handler_error': events.count('handler_error')",
        "'tls_handshake_rejected': events.count('tls_handshake_rejected')",
        "'tls_unknown_ca': events.count('tls_handshake_unknown_ca')",
        "'tls_missing_client_cert': events.count(",
        "'tls_bad_cert': events.count('tls_handshake_bad_cert')",
        "'tls_other': events.count('tls_handshake_other')",
    ):
        assert field in arrival
    assert "failed_when: false" in arrival
    assert "Classify bounded remote-write transport failure" in verify
    assert "Report bounded remote-write transport category" in verify
    assert "Refuse missing authenticated remote-write arrival" in verify
    assert "failed to send batch|non-recoverable error" in verify
    assert "observability_remote_write_arrival.stdout" in verify
    assert "observability_remote_write_failure_category.stdout" in verify
    assert "'sender_path_signal': bool(" in verify
    assert "Diagnose systemd credential transport only after missing arrival" in verify
    assert "observability-agent-credential-probe.service" in verify
    assert "observability_credential_transport_probe.stdout" in verify
    assert "when: observability_remote_write_arrival.rc != 0" in verify


def test_enabled_recovery_proves_outage_watermark_without_global_quiescence() -> None:
    tasks = yaml.safe_load(
        (ROLE / "molecule" / "enabled" / "verify.yml").read_text(encoding="utf-8")
    )[0]["tasks"]
    by_name = {task["name"]: task for task in tasks}
    outage_script = by_name["Wait for a new remote-write retry and positive queue age"][
        "ansible.builtin.command"
    ]["argv"][2]
    recovery_script = by_name[
        "Wait for outage watermark recovery and new authenticated receiver arrival"
    ]["ansible.builtin.command"]["argv"][2]
    outage_metrics = "\n".join(
        (
            "prometheus_remote_storage_queue_highest_timestamp_seconds 42",
            "prometheus_remote_storage_queue_highest_sent_timestamp_seconds 35",
            "prometheus_remote_storage_samples_failed_total 2",
            "prometheus_remote_storage_samples_retried_total 2",
        )
    )
    outage_code, outage = _run_embedded_verification_script(
        outage_script,
        metrics=outage_metrics,
        receiver_rows=[],
        args=["1"],
    )

    assert outage_code == 0
    assert outage == {"highest": 42.0, "highest_sent": 35.0, "retry": 2.0}

    recovered_metrics = "\n".join(
        (
            "prometheus_remote_storage_samples_pending 7",
            "prometheus_remote_storage_queue_highest_sent_timestamp_seconds 42",
        )
    )
    authenticated_rows = [
        {"path": "/remote-write/v1/nodes/node-fixture", "cn": "node-fixture"}
        for _ in range(55)
    ]
    recovered_code, recovered = _run_embedded_verification_script(
        recovery_script,
        metrics=recovered_metrics,
        receiver_rows=authenticated_rows,
        args=["54", str(outage["highest"])],
    )

    assert recovered_code == 0
    assert recovered == {
        "outage_highest": 42.0,
        "pending": 7.0,
        "received": 55,
        "sent": 42.0,
    }

    below_watermark_code, _ = _run_embedded_verification_script(
        recovery_script,
        metrics=recovered_metrics.replace(" 42", " 41"),
        receiver_rows=authenticated_rows,
        args=["54", str(outage["highest"])],
    )
    unchanged_receiver_code, _ = _run_embedded_verification_script(
        recovery_script,
        metrics=recovered_metrics,
        receiver_rows=authenticated_rows[:54],
        args=["54", str(outage["highest"])],
    )

    assert below_watermark_code == 1
    assert unchanged_receiver_code == 1


def test_enabled_molecule_uses_exact_systemd_credentials_for_fail_only_probe() -> None:
    prepare = (ROLE / "molecule" / "enabled" / "prepare.yml").read_text(
        encoding="utf-8"
    )
    verify = (ROLE / "molecule" / "enabled" / "verify.yml").read_text(encoding="utf-8")

    assert "observability-agent-credential-probe.py" in prepare
    assert "/run/observability-agent-fixture/credential-probe.json" in prepare
    assert "os.O_WRONLY | os.O_CREAT | os.O_EXCL" in prepare
    assert "0o600" in prepare
    assert "os.fsync(descriptor)" in prepare
    assert "if count < 1:" in prepare
    for field in (
        '"ca_cert_key_loaded": False',
        '"cert_key_match": False',
        '"sslclient_verify": False',
        '"tls_handshake": False',
    ):
        assert field in prepare
    assert "str(error)" not in prepare
    assert "stderr=subprocess.DEVNULL" in prepare
    assert "LoadCredential=" in verify
    for name in ("client.crt", "client.key", "receiver-ca.crt", "prometheus.yml"):
        assert f"'{name}'" in verify
    assert "User=observability-agent" in verify
    assert "Group=observability-agent" in verify
    assert "WorkingDirectory=%d" in verify
    assert "observability-agent-credential-probe.py" in verify
    assert "all(type(value) is bool for value in candidate.values())" in verify
    assert "/run/observability-agent-fixture/credential-probe.json" in verify
    assert "os.O_RDONLY | os.O_NOFOLLOW" in verify
    assert "stat.S_IMODE(metadata.st_mode) != 0o600" in verify
    assert "Remove credential diagnostic unit" in verify
    assert "Remove credential diagnostic runtime artifacts" in verify
    assert "credential-probe.json{{ item }}" in verify


def test_enabled_fixture_certificates_are_explicitly_valid_for_strict_mtls() -> None:
    prepare = (ROLE / "molecule" / "enabled" / "prepare.yml").read_text(
        encoding="utf-8"
    )

    assert "basicConstraints=critical,CA:TRUE" in prepare
    assert "keyUsage=critical,keyCertSign,cRLSign" in prepare
    assert prepare.count("basicConstraints=critical,CA:FALSE") == 2
    assert "keyUsage=critical,digitalSignature,keyEncipherment" in prepare
    assert "keyUsage=critical,digitalSignature" in prepare
    assert "extendedKeyUsage=serverAuth" in prepare
    assert "extendedKeyUsage=clientAuth" in prepare
    assert "subjectAltName=DNS:ingest.fixture.test" in prepare


def test_enabled_fixture_creates_diagnostic_account_before_runtime_ownership() -> None:
    prepare = yaml.safe_load(
        (ROLE / "molecule" / "enabled" / "prepare.yml").read_text(encoding="utf-8")
    )[0]["tasks"]
    by_name = {task["name"]: task for task in prepare}
    names = [task["name"] for task in prepare]

    assert by_name["Create observability agent fixture group"][
        "ansible.builtin.group"
    ] == {"name": "observability-agent", "system": True}
    assert by_name["Create observability agent fixture account"][
        "ansible.builtin.user"
    ] == {
        "name": "observability-agent",
        "group": "observability-agent",
        "system": True,
        "shell": "/usr/sbin/nologin",
    }
    assert (
        names.index("Create observability agent fixture group")
        < names.index("Create observability agent fixture account")
        < names.index("Set credential diagnostic runtime directory authority")
    )


def test_enabled_fixture_keeps_textfile_ancestors_private() -> None:
    tasks = yaml.safe_load(
        (ROLE / "molecule" / "enabled" / "prepare.yml").read_text(encoding="utf-8")
    )[0]["tasks"]
    directories = tasks[0]["loop"]
    by_path = {item["path"]: item["mode"] for item in directories}
    paths = [item["path"] for item in directories]

    assert by_path["/var/lib/node_exporter"] == "0755"
    assert by_path["/var/lib/node_exporter/textfile"] == "3775"
    assert paths.index("/var/lib/node_exporter") < paths.index(
        "/var/lib/node_exporter/textfile"
    )


def test_enabled_receiver_records_only_categorical_failure_phases() -> None:
    prepare = (ROLE / "molecule" / "enabled" / "prepare.yml").read_text(
        encoding="utf-8"
    )

    assert 'record_event("headers")' in prepare
    assert 'record_event("length_rejected")' in prepare
    assert 'record_event("short_body")' in prepare
    assert 'record_event("accepted")' in prepare
    assert 'record_event("handler_error")' in prepare
    assert 'record_event("tls_handshake_rejected")' in prepare
    assert 'record_event("tls_handshake_" + category)' in prepare
    assert "class Server(http.server.ThreadingHTTPServer)" in prepare
    assert "except ssl.SSLError as error:" in prepare
    for reason in (
        "TLSV1_ALERT_UNKNOWN_CA",
        "SSLV3_ALERT_UNKNOWN_CA",
        "PEER_DID_NOT_RETURN_A_CERTIFICATE",
        "CERTIFICATE_VERIFY_FAILED",
        "SSLV3_ALERT_BAD_CERTIFICATE",
        "TLSV1_ALERT_BAD_CERTIFICATE",
        "SSLV3_ALERT_CERTIFICATE_EXPIRED",
    ):
        assert f'"{reason}"' in prepare
    assert "str(error)" not in prepare
    assert "verify_message" not in prepare
    assert 'json.dumps({"phase": phase})' in prepare
    assert "if len(body) != length" in prepare


def test_site_uses_the_role_contract_as_the_single_enablement_flag() -> None:
    site = (ROOT / "ansible" / "playbooks" / "site.yml").read_text()
    group_vars = (ROOT / "ansible" / "group_vars" / "all.yml").read_text()

    assert "when: observability_agent.enabled | default(false)" in site
    assert "enable_observability_agent" not in group_vars


def test_molecule_scenarios_execute_the_named_role_and_seed_disable_state_once() -> (
    None
):
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
