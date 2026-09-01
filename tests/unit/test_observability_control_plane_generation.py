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
    assert "observability-remote-write.conf" in " ".join(removed)
    assert "Preserve TSDB on convergent disable" in tasks


def test_capacity_preflight_and_retention_have_no_auto_deletion_path() -> None:
    source = (ROLE / "tasks/enable.yml").read_text()
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_control_plane"
    ]

    assert "Read filesystem capacity reserved for Prometheus TSDB" in source
    assert "Require TSDB capacity before activation" in source
    assert defaults["tsdb_required_bytes"] == 42949672960
    assert "state: absent" not in source


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
