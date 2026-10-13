"""Ensure idempotent convergence does not overwrite rollback configs."""

from pathlib import Path

from jinja2 import Environment, StrictUndefined
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('filename', ['config.json', 'config.yaml'])
def test_config_restore_point_requires_changed_bytes_and_preserves_unchanged_backup(tmp_path, monkeypatch, filename):
    import base64
    import os
    import sys
    sys.path.insert(0, str(ROOT/'ansible/roles/runtime-release/files'))
    import transport_runtime_accept as accept
    import transport_runtime_transaction as core
    original_node = core.node
    monkeypatch.setattr(core, 'node', lambda path, _uid, **options: original_node(path, os.getuid(), **options))
    current, previous = tmp_path/filename, tmp_path/(filename+'.prev')
    current.write_bytes(b'accepted-a'); current.chmod(0o640)
    previous.write_bytes(b'older-distinct'); previous.chmod(0o640)
    before = (current.stat().st_ino, previous.stat().st_ino, current.read_bytes(), previous.read_bytes())
    def candidate(data):
        return {'path':str(current),'data':base64.b64encode(data).decode(),'mode':0o640,'gid':os.getgid()}
    assert accept.restore_points([candidate(b'accepted-a')]) == [candidate(b'accepted-a')]
    changed = accept.restore_points([candidate(b'candidate-b')])
    assert changed[1] == {**candidate(b'accepted-a'), 'path':str(previous)}
    assert (current.stat().st_ino, previous.stat().st_ino, current.read_bytes(), previous.read_bytes()) == before
    current.unlink()
    assert accept.restore_points([candidate(b'fresh')]) == [candidate(b'fresh')]
    assert previous.read_bytes() == b'older-distinct' and previous.stat().st_ino == before[1]


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
