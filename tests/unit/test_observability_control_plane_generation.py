"""Lifecycle boundaries for generated control-plane configuration."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"


def _tasks(name: str) -> dict[str, dict]:
    return {
        task["name"]: task
        for task in yaml.safe_load((ROLE / "tasks" / name).read_text())
    }


def test_enable_preserves_previous_generation_before_current_activation() -> None:
    tasks = _tasks("enable.yml")
    ordered = list(tasks)

    assert (
        ordered.index("Inspect current generation before activation")
        < ordered.index("Refuse an unsafe existing control-plane generation link")
        < ordered.index("Preserve ready control-plane generation before activation")
        < ordered.index(
            "Activate complete validated Prometheus generation with rollback"
        )
    )
    activation = tasks[
        "Activate complete validated Prometheus generation with rollback"
    ]
    activate = activation["block"][0]["ansible.builtin.file"]
    assert activate["dest"].endswith("/current.yml")
    assert activate["state"] == "link"
    assert activate["force"] is True
    rescue_names = [task["name"] for task in activation["rescue"]]
    assert "Restore previous ready configuration after failed candidate" in rescue_names
    assert "Fail closed when no previous ready generation exists" in rescue_names


def test_disable_removes_only_owned_runtime_and_keeps_tsdb() -> None:
    tasks = _tasks("disable.yml")
    removed = tasks["Remove control-plane units and ingress only"]["loop"]

    assert "/var/lib/observability-prometheus" not in removed
    assert "observability-prometheus.service" in " ".join(removed)
    assert "/etc/systemd/system/observability-ingress.service" in removed
    assert not any(path.startswith("/etc/nginx/") for path in removed)
    assert not any("credentials" in path or "latched" in path for path in removed)
    assert "Preserve TSDB on convergent disable" in tasks


def test_capacity_preflight_and_retention_have_no_auto_deletion_path() -> None:
    source = (ROLE / "tasks/enable.yml").read_text()
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_control_plane"
    ]

    assert (
        "Require measured capacity and private address before host mutation" in source
    )
    assert "observability-disk-guard.py" in source
    assert "--preflight" in source
    assert defaults["tsdb_required_bytes"] == 2147483648
    assert defaults["disk_reserve_bytes"] == 5368709120
    assert defaults["disk_reserve_percent"] == 20
    assert (
        'path: "{{ observability_control_plane.data_dir }}"\n    state: absent'
        not in source
    )


def test_generation_is_content_addressed_and_rollback_restores_the_original_link() -> (
    None
):
    tasks = _tasks("enable.yml")
    source = (ROLE / "tasks/enable.yml").read_text()
    ordered = list(tasks)

    assert (
        ordered.index(
            "Derive the immutable Prometheus generation from candidate content"
        )
        < ordered.index("Inspect immutable Prometheus generation before publication")
        < ordered.index("Refuse a conflicting immutable Prometheus generation")
        < ordered.index("Publish isolated immutable Prometheus generation")
    )
    assert "_observability_generation" in source
    assert "observability_control_plane.generation" not in source
    assert (
        tasks["Publish isolated immutable Prometheus generation"][
            "ansible.builtin.copy"
        ]["force"]
        is False
    )
    rescue = tasks["Activate complete validated Prometheus generation with rollback"][
        "rescue"
    ]
    restored = next(
        task
        for task in rescue
        if task["name"] == "Restore previous ready configuration after failed candidate"
    )
    assert (
        restored["ansible.builtin.file"]["src"]
        == "{{ _observability_current.stat.lnk_source }}"
    )


def test_enable_preserves_shared_nginx_and_starts_only_isolated_ingress() -> None:
    tasks = _tasks("enable.yml")
    ordered = list(tasks)

    assert "Remove the distribution default ingress site" not in tasks
    assert ordered.index("Render isolated write-only mTLS ingress") < ordered.index(
        "Start isolated ingress without changing shared VPN nginx"
    )
    nginx = tasks["Start isolated ingress without changing shared VPN nginx"][
        "ansible.builtin.systemd_service"
    ]
    assert nginx["name"] == "observability-ingress"
    assert nginx["enabled"] is True
    assert (
        tasks["Install hardened ingress package"]["ansible.builtin.apt"]["policy_rc_d"]
        == 101
    )
    assert not any(
        task.get("ansible.builtin.systemd_service", {}).get("name") == "nginx"
        for task in tasks.values()
    )


def test_playbook_keeps_the_control_plane_out_of_transport_site() -> None:
    playbook = yaml.safe_load(
        (ROOT / "ansible/playbooks/observability-control-plane.yml").read_text()
    )[0]

    assert playbook["hosts"] == "vpn-observability-control"
    assert playbook["roles"] == [{"role": "observability_control_plane"}]
    assert (
        not (ROOT / "ansible/playbooks/site.yml")
        .read_text()
        .find("observability_control_plane")
        >= 0
    )


def test_enabled_molecule_declares_receiver_and_rollback_acceptance_boundaries() -> (
    None
):
    verify = (ROLE / "molecule" / "enabled" / "verify.yml").read_text(encoding="utf-8")
    for required in (
        "missing or wrong SNI",
        "authenticated GET refusal",
        "CN path mismatch",
        "oversized request",
        "invalid protobuf reaches real Prometheus and is rejected",
        "published generation remains content-addressed",
        "TSDB free-space preflight remains enforced",
    ):
        assert required in verify
    runtime = (ROLE / "molecule/enabled/tasks/bounded-runtime.yml").read_text()
    for proof in [
        "real_agent_remote_write_missing",
        "actual_filesystem_high_water=pass",
        "wal_backlog_not_recovered",
    ]:
        assert proof in runtime
