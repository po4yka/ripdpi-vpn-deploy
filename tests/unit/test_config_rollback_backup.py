"""Ensure idempotent convergence does not overwrite rollback configs."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_xray_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/xray/tasks/main.yml").read_text()
    assert "register: _xray_config_change" in content
    assert "- _xray_config_change.changed" in content


def test_hysteria_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/hysteria/tasks/main.yml").read_text()
    assert "register: _hysteria_config_change" in content
    assert "- _hysteria_config_change.changed" in content


def test_xray_molecule_requests_the_pinned_image_architecture():
    molecule = yaml.safe_load(
        (ROOT / "ansible/roles/xray/molecule/default/molecule.yml").read_text()
    )
    assert molecule["platforms"][0]["platform"] == "linux/amd64"


def test_xray_molecule_uses_shared_runtime_publisher_and_idempotence():
    """The real shared publisher and Molecule idempotence own link replay."""
    converge = yaml.safe_load((ROOT / "ansible/roles/xray/molecule/default/converge.yml").read_text())[0]
    runtime = yaml.safe_load((ROOT / "ansible/roles/xray-runtime/tasks/main.yml").read_text())
    publisher = next(
        task for task in runtime
        if task.get("name") == "Install pinned Xray archive through runtime-release"
    )
    setup_names = {task["name"] for task in converge["pre_tasks"]}
    molecule = yaml.safe_load(
        (ROOT / "ansible/roles/xray/molecule/default/molecule.yml").read_text()
    )

    assert publisher["ansible.builtin.include_role"]["name"] == "runtime-release"
    assert publisher["when"] == "not xray_runtime_build_from_source | bool"
    assert "Create hash-pinned Xray runtime archive fixture" in setup_names
    assert "idempotence" in molecule["scenario"]["test_sequence"]
