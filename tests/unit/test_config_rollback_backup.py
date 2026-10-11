"""Ensure idempotent convergence does not overwrite rollback configs."""

from pathlib import Path

from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_xray_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/xray/tasks/enable.yml").read_text()
    assert "register: _xray_config_change" in content
    assert "- _xray_config_change.changed" in content


def test_hysteria_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/hysteria/tasks/enable.yml").read_text()
    assert "register: _hysteria_config_change" in content
    assert "- _hysteria_config_change.changed" in content


def test_xray_molecule_requests_the_pinned_image_architecture():
    molecule = yaml.safe_load(
        (ROOT / "ansible/roles/xray/molecule/default/molecule.yml").read_text()
    )
    assert molecule["platforms"][0]["platform"] == "linux/amd64"


def test_xray_molecule_uses_shared_runtime_publisher_and_idempotence():
    """The real shared publisher and Molecule idempotence own link replay."""
    converge = yaml.safe_load(
        (ROOT / "ansible/roles/xray/molecule/default/converge.yml").read_text()
    )[0]
    runtime = yaml.safe_load(
        (ROOT / "ansible/roles/xray-runtime/tasks/main.yml").read_text()
    )
    publisher = next(
        task
        for task in runtime
        if task.get("name") == "Install pinned Xray archive through runtime-release"
    )
    setup_names = {task["name"] for task in converge["pre_tasks"]}
    molecule = yaml.safe_load(
        (ROOT / "ansible/roles/xray/molecule/default/molecule.yml").read_text()
    )

    assert publisher["ansible.builtin.include_role"]["name"] == "runtime-release"
    assert publisher["when"] == "not xray_runtime_build_from_source | bool"
    archive = next(task["ansible.builtin.get_url"] for task in converge["pre_tasks"]
                   if task["name"] == "Fetch exact checksum-verified native Xray archive fixture")
    pins = converge["vars"]["xray"]
    assert pins["version"] == "v26.3.27"
    destination = f"/var/tmp/xray-molecule/xray-{pins['version']}.zip"
    assert archive["dest"] == destination
    assert archive["mode"] == "0600"
    environment = Environment(undefined=StrictUndefined)
    for architecture, filename, pin in (
        ("x86_64", "64", "linux_amd64_sha256"),
        ("aarch64", "arm64-v8a", "linux_arm64_sha256"),
    ):
        context = {"ansible_facts": {"architecture": architecture}, "xray": pins}
        assert environment.from_string(archive["url"]).render(context) == (
            f"https://github.com/XTLS/Xray-core/releases/download/{pins['version']}/Xray-linux-{filename}.zip"
        )
        assert environment.from_string(archive["checksum"]).render(context) == f"sha256:{pins[pin]}"
    assert converge["vars"]["xray_runtime_release_urls"] == {
        "amd64": f"file://{destination}", "arm64": f"file://{destination}",
    }
    assert "Pre-create release dir for runtime link idempotence coverage" not in setup_names
    assert "Seed Xray binary for runtime link idempotence coverage" not in setup_names
    assert "idempotence" in molecule["scenario"]["test_sequence"]
