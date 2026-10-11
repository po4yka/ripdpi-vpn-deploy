"""Real localhost reporting/cleanup proof, separate from native engine admission."""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys

import yaml

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLES = ROOT / "ansible/roles"


def _tasks(role):
    return yaml.safe_load((ROLES / role / "tasks/enable.yml").read_text())


def _named(role, name):
    return copy.deepcopy(next(task for task in _tasks(role) if task["name"] == name))


def _snapshot(directory):
    result = {}
    for path in sorted(directory.iterdir()):
        metadata = path.lstat()
        result[path.name] = (
            stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid,
            metadata.st_ino, metadata.st_mtime_ns,
            os.readlink(path) if path.is_symlink() else hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return result


def _fixture(tmp_path):
    accepted = tmp_path / "accepted"
    accepted.mkdir(mode=0o700)
    temporary = tmp_path / "temporary"
    temporary.mkdir(mode=0o700)
    variables = merge_render_vars()
    # Standalone snapshot rendering supplies item; real Ansible loops own it.
    variables.pop("item", None)
    variables["hysteria_config_dir"] = str(accepted)
    marker = "reporting-fixture-" + secrets.token_hex(24)
    variables["transport_egress_secrets"]["direct_xray_password"] = marker + "-xray"
    variables["transport_egress_secrets"]["direct_hysteria_password"] = marker + "-hys"
    variables["p0_reality_shape_template"] = str(ROOT / "ansible/templates/p0-reality-shape.json.j2")
    for name, source, mode in (
        ("xray.json", ROLES / "xray/templates/config.json.j2", 0o640),
        ("hysteria.yaml", ROLES / "hysteria/templates/config.yaml.j2", 0o640),
        ("hysteria.service", ROLES / "hysteria/templates/hysteria-server.service.j2", 0o644),
    ):
        path = accepted / name
        path.write_text(render_template(source, variables))
        path.chmod(mode)
    helper = accepted / "validate_yaml_mapping.py"
    helper.write_bytes((ROLES / "runtime-release/files/validate_yaml_mapping.py").read_bytes())
    helper.chmod(0o600)
    # These are retained authority bytes, not certificates used in a TLS handshake.
    for name in ("server.fullchain.pem", "server.key"):
        path = accepted / name
        path.write_text("reporting fixture retained TLS authority\n")
        path.chmod(0o640)
    (accepted / "current").symlink_to("xray.json")
    return accepted, temporary, variables, marker


def _temporary_block(role, temporary):
    name = f"Validate {'Xray' if role == 'xray' else 'Hysteria'} candidate before quiescing the accepted route"
    block = _named(role, name)
    block["vars"] = {"role_path": str(ROLES / role)}
    for task in [*block["block"], *block["always"]]:
        if "ansible.builtin.tempfile" in task:
            task["ansible.builtin.tempfile"]["path"] = str(temporary)
        for module in ("ansible.builtin.template", "ansible.builtin.copy"):
            if module in task:
                # Host fixture authority only; production remains root-owned.
                task[module]["owner"] = str(os.getuid())
                task[module]["group"] = str(os.getgid())
        if "ansible.builtin.template" in task:
            options = task["ansible.builtin.template"]
            options["src"] = str(ROLES / role / "templates" / options["src"])
            if role == "xray":
                # Genuine semantic admission; this test never substitutes a fake
                # native binary or claims Xray parser/forwarding acceptance.
                code = (
                    "import json,runpy,sys;runpy.run_path("
                    + repr(str(ROLES / "xray/files/xray_validate.py"))
                    + ")[\"admitted_frontend\"](json.load(open(sys.argv[1])))"
                )
                options["validate"] = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)} %s"
            else:
                options["validate"] = options["validate"].replace("/usr/bin/python3", shlex.quote(sys.executable), 1)
    return block


def _run(tmp_path, tasks, variables, marker):
    executable = shutil.which("ansible-playbook")
    assert executable, "the pinned genuine Ansible toolchain is required"
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\ncallback_result_format=json\n")
    variables_file = tmp_path / "variables.yml"
    variables_file.write_text(yaml.safe_dump(variables))
    variables_file.chmod(0o600)
    playbook = tmp_path / "reporting.yml"
    playbook.write_text(yaml.safe_dump([{
        "name": "Observe owned local validation reporting",
        "hosts": "localhost", "connection": "local", "become": False,
        "gather_facts": False, "vars_files": [str(variables_file)], "tasks": tasks,
    }], sort_keys=False))
    playbook.chmod(0o600)
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
    environment.update({
        "ANSIBLE_CONFIG": str(config), "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
        "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
        "ANSIBLE_ROLES_PATH": str(ROLES), "ANSIBLE_NOCOLOR": "1",
        "ANSIBLE_BECOME": "false", "ANSIBLE_STDOUT_CALLBACK": "default",
        "ANSIBLE_LOAD_CALLBACK_PLUGINS": "false",
        "ANSIBLE_PYTHON_INTERPRETER": sys.executable,
    })
    result = subprocess.run(
        [executable, "-i", "localhost,", str(playbook)], cwd=tmp_path,
        env=environment, text=True, capture_output=True, timeout=90,
    )
    output = result.stdout + result.stderr
    assert marker not in output, "synthetic private authority reached Ansible output"
    return result, output


def test_only_temporary_validation_tasks_suppress_changed_reporting():
    for role, label, count in (("xray", "Xray", 3), ("hysteria", "Hysteria", 4)):
        block = _named(role, f"Validate {label} candidate before quiescing the accepted route")
        transient = [*block["block"], *block["always"]]
        assert len(transient) == count
        assert all(task["changed_when"] is False for task in transient)
        candidate = next(task for task in transient if "ansible.builtin.template" in task)
        assert candidate["no_log"] is True and candidate["diff"] is False
        assert "validate" in candidate["ansible.builtin.template"]
        cleanup = block["always"][0]
        assert cleanup["ansible.builtin.file"]["state"] == "absent"
        for task in _tasks(role):
            if task.get("check_mode") is True:
                assert task.get("changed_when") is not False
    assert "--binary" in _named("xray", "Validate Xray candidate before quiescing the accepted route")["block"][1]["ansible.builtin.template"]["validate"]
    for role, name in (("xray", "Render and validate Xray config"), ("hysteria", "Render Hysteria config")):
        assert _named(role, name).get("changed_when") is not False


def test_actual_ansible_temporary_validation_twice_preserves_accepted_authority(tmp_path):
    from molecule.command.idempotence import Idempotence
    parser = object.__new__(Idempotence)
    accepted, temporary, variables, marker = _fixture(tmp_path)
    before = _snapshot(accepted)
    tasks = [_temporary_block(role, temporary) for role in ("xray", "hysteria")]
    for _ in range(2):
        result, output = _run(tmp_path, tasks, variables, marker)
        assert result.returncode == 0, output
        assert re.search(r"localhost\s+: ok=\d+\s+changed=0\s+unreachable=0\s+failed=0", output), output
        assert parser._is_idempotent(output) is True
        assert parser._non_idempotent_tasks(output) == []
        assert _snapshot(accepted) == before
        assert list(temporary.iterdir()) == []


def test_actual_hysteria_semantic_refusal_always_cleans_without_publication(tmp_path):
    accepted, temporary, variables, marker = _fixture(tmp_path)
    before = _snapshot(accepted)
    variables["hysteria"]["clients"] = []
    result, output = _run(tmp_path, [_temporary_block("hysteria", temporary)], variables, marker)
    assert result.returncode != 0
    assert "Prove guarded Hysteria candidate admission" in output
    assert "Remove only the owned Hysteria validation candidate" in output
    assert re.search(r"localhost\s+: ok=\d+\s+changed=0\s+unreachable=0\s+failed=1", output), output
    assert _snapshot(accepted) == before
    assert list(temporary.iterdir()) == []


def test_actual_predictive_and_persistent_changes_remain_non_idempotent(tmp_path):
    from molecule.command.idempotence import Idempotence
    parser = object.__new__(Idempotence)
    accepted, temporary, variables, marker = _fixture(tmp_path)
    variables["role_path"] = str(ROLES / "hysteria")
    variables["hysteria_config_dir"] = str(accepted)
    # The production detector executes in real Ansible check mode. Its changed
    # result must survive, while neither config nor unit is published.
    task = _named("hysteria", "Detect Hysteria frontend authority change before publication")
    task["ansible.builtin.template"].update(owner=str(os.getuid()), group=str(os.getgid()))
    task["loop"] = [{"source": str(ROLES / "hysteria/templates/config.yaml.j2"),
                     "destination": str(accepted / "hysteria.yaml"), "mode": "0640"}]
    # Seed accepted bytes with the genuine Ansible producer, not the portable
    # Jinja snapshot polyfills, before observing an unchanged repeat detector.
    seed = copy.deepcopy(task)
    seed["name"] = "Seed owned accepted config with actual Ansible and semantic validation"
    seed.pop("check_mode")
    seed.pop("register")
    seed["ansible.builtin.template"]["validate"] = (
        f"{shlex.quote(sys.executable)} "
        f"{shlex.quote(str(ROLES / 'runtime-release/files/validate_yaml_mapping.py'))} "
        "--profile hysteria %s"
    )
    result, output = _run(tmp_path, [seed], variables, marker)
    assert result.returncode == 0, output
    before = _snapshot(accepted)
    unchanged = [task, {"name": "Require unchanged accepted authority", "ansible.builtin.assert": {
        "that": ["not _hysteria_frontend_change.changed"]}}]
    result, output = _run(tmp_path, unchanged, variables, marker)
    assert result.returncode == 0 and parser._is_idempotent(output) is True, output
    assert _snapshot(accepted) == before
    variables["hysteria_port"] += 1
    tasks = [task, {"name": "Require genuine predictive change", "ansible.builtin.assert": {
        "that": ["_hysteria_frontend_change.changed"]}}]
    result, output = _run(tmp_path, tasks, variables, marker)
    assert result.returncode == 0, output
    assert re.search(r"changed=1\s+unreachable=0\s+failed=0", output), output
    assert parser._is_idempotent(output) is False
    assert any("Detect Hysteria frontend authority change" in item for item in parser._non_idempotent_tasks(output))
    assert _snapshot(accepted) == before
    assert list(temporary.iterdir()) == []
    published = tmp_path / "owned-persistent-control"
    control = {"name": "Publish genuine owned persistent change", "ansible.builtin.copy": {
        "content": "persistent reporting control\n", "dest": str(published), "mode": "0600"}}
    result, output = _run(tmp_path, [control], variables, marker)
    assert result.returncode == 0 and published.read_text() == "persistent reporting control\n", output
    assert parser._is_idempotent(output) is False
    assert parser._non_idempotent_tasks(output) == ["* [localhost] => Publish genuine owned persistent change"]
    assert _snapshot(accepted) == before
