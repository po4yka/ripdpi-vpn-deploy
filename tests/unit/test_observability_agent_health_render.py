"""Role wiring for bounded root-private producer health adaptation."""

from __future__ import annotations

import json
from pathlib import Path
import yaml
import pytest

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible" / "roles" / "observability_agent"


def test_health_adapter_service_reads_only_fixed_producer_state() -> None:
    service = (
        ROLE / "templates/observability-agent-health-adapter.service.j2"
    ).read_text()

    assert "User=root" in service
    assert "Group={{ monitoring.node_exporter_textfile_group" in service
    assert "--watchdog-state {{ observability_agent_watchdog_state_path }}" in service
    assert "--backup-stage {{ observability_agent_backup_stage_path }}" in service
    assert "--restore-drill {{ observability_agent_restore_drill_path }}" in service
    assert "LoadCredential=client.crt:" in service
    assert "--certificate %d/client.crt" in service
    assert "backup_snapshot_max_age_hours | default(36)" in service
    assert "ProtectSystem=strict" in service
    assert "RestrictAddressFamilies=AF_UNIX" in service
    assert "ReadWritePaths={{ monitoring.node_exporter_textfile_dir" in service
    for forbidden in (
        "systemctl restart",
        "restic",
        "vpn-watchdog.sh",
        "vpn-backup.sh",
    ):
        assert forbidden not in service


def test_role_installs_starts_and_convergently_removes_health_adapter() -> None:
    tasks = (ROLE / "tasks/main.yml").read_text()

    install = tasks.index("Install watchdog and backup health adapter")
    units = tasks.index(
        "Install observability agent adapter units after sender acceptance"
    )
    start = tasks.index("Enable and start observability agent health adapter timer")
    assert install < units < start
    for path in (
        "/usr/local/libexec/observability-agent-health-adapter.py",
        "/etc/systemd/system/observability-agent-health-adapter.service",
        "/etc/systemd/system/observability-agent-health-adapter.timer",
        "observability-health.prom",
    ):
        assert path in tasks
    assert "observability-agent-health-adapter.timer" in tasks[:install]


def test_defaults_pin_private_paths_and_retention_aware_freshness() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    assert (
        defaults["observability_agent_watchdog_state_path"]
        == "/var/lib/vpn-watchdog/state"
    )
    assert defaults["observability_agent_watchdog_max_age_seconds"] == 900
    assert (
        defaults["observability_agent_backup_stage_path"]
        == "/var/lib/vpn-backup/backup-stage-status.json"
    )
    assert defaults["observability_agent_backup_stage_max_age_seconds"] == 129600
    assert (
        defaults["observability_agent_restore_drill_path"]
        == "/var/lib/vpn-backup/restore-drill-last-success.json"
    )
    assert defaults["observability_agent_restore_drill_max_age_seconds"] == 3024000


def test_metric_manifest_declares_every_health_adapter_family() -> None:
    manifest = json.loads(
        (ROOT / "contract/observability-metric-manifest.example.json").read_text()
    )
    families = {family["name"]: family for family in manifest["families"]}
    expected = {
        "vpn_watchdog_collection_success",
        "vpn_watchdog_last_run_timestamp_seconds",
        "vpn_watchdog_freshness_state",
        "vpn_watchdog_result",
        "vpn_watchdog_consecutive_failures",
        "vpn_watchdog_restart_attempts",
        "vpn_watchdog_rate_limit_state",
        "vpn_watchdog_recovery_outcome",
        "vpn_backup_collection_success",
        "vpn_backup_collected_timestamp_seconds",
        "vpn_backup_freshness_state",
        "vpn_backup_result",
        "vpn_backup_attempted_timestamp_seconds",
        "vpn_backup_succeeded_timestamp_seconds",
        "vpn_backup_failed_timestamp_seconds",
        "vpn_backup_snapshot_timestamp_seconds",
        "vpn_backup_restore_source",
        "vpn_certificate_collection_success",
        "vpn_certificate_not_after_timestamp_seconds",
    }
    assert expected <= families.keys()
    for name in expected:
        assert families[name]["owner"] == "observability_agent"
        assert families[name]["max_series"] <= 256
        assert set(families[name]["labels"]) <= {"node", "role", "state"}


def test_enabled_molecule_uses_root_private_fixtures_and_proves_redaction() -> None:
    prepare = (ROLE / "molecule/enabled/prepare.yml").read_text()
    verify = (ROLE / "molecule/enabled/verify.yml").read_text()

    assert "Write root-private watchdog state fixture" in prepare
    assert "Write root-private backup stage fixture" in prepare
    assert "Write root-private restore drill fixture" in prepare
    assert prepare.count('mode: "0600"') >= 2
    assert "Run root-private producer health adapter now" in verify
    assert "observability_health_stat.stat.mode == '0640'" in verify
    assert "vpn_watchdog_recovery_outcome" in verify
    assert "vpn_backup_restore_source" in verify
    assert "vpn_certificate_collection_success" in verify
    assert "vpn_certificate_not_after_timestamp_seconds" in verify
    assert (
        "'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'" in verify
    )
    assert "not in (observability_health_output.content | b64decode)" in verify


@pytest.mark.parametrize("enabled", [True, False])
def test_rendered_watchdog_input_follows_the_effective_profile(enabled: bool) -> None:
    values = merge_render_vars()
    values["vpn"]["enable_watchdog"] = enabled
    service = render_template(
        ROLE / "templates/observability-agent-health-adapter.service.j2", values
    )
    assert ("--watchdog-state " in service) is enabled
    assert ("ReadOnlyPaths=-/var/lib/vpn-watchdog/state" in service) is enabled
    assert "--backup-stage " in service
    assert "--restore-drill " in service
    assert "--certificate " in service


@pytest.mark.parametrize(
    ("stat_result", "enabled"),
    [
        ({"exists": True, "isreg": True}, True),
        ({"exists": True, "isreg": False, "isdir": True}, False),
        ({"exists": False}, False),
    ],
)
def test_rendered_self_steal_certificate_follows_the_installed_chain(
    stat_result: dict[str, bool], enabled: bool
) -> None:
    values = merge_render_vars()
    # The profile flag no longer decides; only the host stat result does.
    values["vpn"]["enable_reality_self_steal"] = not enabled
    values["_observability_agent_self_steal_certificate"] = {"stat": stat_result}
    service = render_template(
        ROLE / "templates/observability-agent-health-adapter.service.j2", values
    )
    credential = (
        "LoadCredential=reality-self-steal.crt:"
        "/etc/nginx/reality-self-steal/current/fullchain.pem\n"
    )
    assert (credential in service) is enabled
    assert (
        "--reality-self-steal-certificate %d/reality-self-steal.crt \\\n" in service
    ) is enabled
    assert "privkey" not in service


def test_self_steal_chain_is_inspected_read_only_before_unit_render() -> None:
    def walk(tasks: list[dict]) -> list[dict]:
        found = []
        for task in tasks:
            found.append(task)
            for key in ("block", "rescue", "always"):
                found.extend(walk(task.get(key, [])))
        return found

    tasks = walk(yaml.safe_load((ROLE / "tasks/main.yml").read_text()))
    names = [task.get("name") for task in tasks]
    inspect = tasks[
        names.index("Inspect installed REALITY self-steal certificate chain")
    ]
    assert inspect["ansible.builtin.stat"]["path"] == (
        "{{ reality_self_steal_tls_dir | default('/etc/nginx/reality-self-steal') }}"
        "/current/fullchain.pem"
    )
    assert inspect["check_mode"] is False
    # A symlinked leaf must still count as an installed chain.
    assert inspect["ansible.builtin.stat"]["follow"] is True
    assert inspect["register"] == "_observability_agent_self_steal_certificate"
    assert names.index(inspect["name"]) < names.index(
        "Install observability agent adapter units after sender acceptance"
    )
