"""Ensure idempotent convergence does not overwrite rollback configs."""

import os
from pathlib import Path
import re
import shutil
import subprocess

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


def test_xray_molecule_repeat_preserves_runtime_links(tmp_path):
    """Replay actual filesystem tasks; full Molecule still owns service proof."""
    executable = shutil.which("ansible-playbook")
    assert executable, "Ansible is required for the repeat-converge regression"
    converge = yaml.safe_load((ROOT / "ansible/roles/xray/molecule/default/converge.yml").read_text())[0]
    runtime = yaml.safe_load((ROOT / "ansible/roles/xray-runtime/tasks/main.yml").read_text())
    setup = [task for task in converge["pre_tasks"]
             if task["name"] in {
                 "Pre-create release dir for runtime link idempotence coverage",
                 "Seed Xray binary for runtime link idempotence coverage",
             }]
    links = [task for task in runtime if task["name"] in (
        "Point current Xray runtime at pinned release", "Expose pinned Xray runtime")]
    assert setup and len(links) == 2
    install = tmp_path / "xray"
    public = tmp_path / "bin/xray"
    public.parent.mkdir()
    # Change only fixture destinations and ownership. Keep source module
    # options, payloads and change detection; do not run apt/user/service tasks.
    for task in [*setup, *links]:
        module = next(task[key] for key in ("ansible.builtin.copy", "ansible.builtin.file") if key in task)
        for key in ("path", "src", "dest"):
            if key in module:
                module[key] = module[key].replace("/usr/local/bin/xray", str(public)).replace("/opt/xray", str(install))
        if "owner" in module:
            module["owner"] = str(os.getuid())
        if "group" in module:
            module["group"] = str(os.getgid())
    playbook = tmp_path / "repeat.yml"
    playbook.write_text(yaml.safe_dump([{
        "name": "Replay Xray scenario filesystem convergence",
        "hosts": "localhost", "gather_facts": False, "become": False,
        "vars": {
            "xray": converge["vars"]["xray"],
            "xray_install_dir": str(install),
            "xray_runtime_build_from_source": True,
        },
        "tasks": [*setup, *links],
    }], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
    environment.update(ANSIBLE_CONFIG=str(config), ANSIBLE_BECOME="false",
                       ANSIBLE_DEBUG="false", ANSIBLE_NOCOLOR="1")
    release = install / "releases" / converge["vars"]["xray"]["version"] / "xray"
    first_bytes = None
    for iteration in range(2):
        result = subprocess.run([executable, "-i", "localhost,", "-c", "local", str(playbook)],
                                cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        recap = re.search(r"localhost\s+:\s+ok=\d+\s+changed=(\d+)", result.stdout)
        assert recap, result.stdout
        assert public.is_symlink() and (install / "current").is_symlink()
        assert public.resolve() == release.resolve()
        if iteration == 0:
            assert int(recap.group(1)) > 0, "first converge must create the fixture runtime"
            first_bytes = release.read_bytes()
        else:
            assert release.read_bytes() == first_bytes
            assert int(recap.group(1)) == 0, "repeat converge rewrote role-owned runtime state:\n" + result.stdout
