"""Retirement grants only exact regular files to declared producer accounts."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def authority(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "retirement", ROOT / "ansible/roles/runtime-release/files/validate_retirement.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metric = "/owned/textfile/metric.prom"

    def metadata(mode, uid=0, links=1):
        return os.stat_result((mode, 1, 1, links, uid, 0, 0, 0, 0, 0))

    entries = {
        "/": metadata(stat.S_IFDIR | 0o755),
        "/owned": metadata(stat.S_IFDIR | 0o755),
        "/owned/textfile": metadata(stat.S_IFDIR | 0o3775),
        metric: metadata(stat.S_IFREG | 0o640, 1001),
    }

    def lstat(path):
        try:
            return entries[str(path)]
        except KeyError:
            raise FileNotFoundError(str(path)) from None

    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.Path, "lstat", lstat)
    monkeypatch.setattr(module.pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=1001))
    return module, metric, entries, metadata


def test_declared_regular_metric_owner_is_admitted(authority):
    module, metric, _, _ = authority
    assert module.validate([metric], {metric: "prometheus"}) == [metric]
    with pytest.raises(ValueError, match="retirement owner"):
        module.validate([metric])


@pytest.mark.parametrize("kind", ["foreign", "directory", "symlink", "hardlink", "writable", "ancestor"])
def test_producer_grant_does_not_relax_other_authority(authority, kind):
    module, metric, entries, metadata = authority
    if kind == "foreign":
        entries[metric] = metadata(stat.S_IFREG | 0o640, 1002)
    elif kind == "directory":
        entries[metric] = metadata(stat.S_IFDIR | 0o750, 1001)
    elif kind == "symlink":
        entries[metric] = metadata(stat.S_IFLNK | 0o777, 1001)
    elif kind == "hardlink":
        entries[metric] = metadata(stat.S_IFREG | 0o640, 1001, 2)
    elif kind == "writable":
        entries[metric] = metadata(stat.S_IFREG | 0o666, 1001)
    else:
        entries["/owned/textfile"] = metadata(stat.S_IFDIR | 0o3775, 1001)
    with pytest.raises(ValueError, match="retirement"):
        module.validate([metric], {metric: "honeypot"})


def test_absent_producer_file_needs_no_removed_account(authority, monkeypatch):
    module, metric, entries, _ = authority
    del entries[metric]
    monkeypatch.setattr(module.pwd, "getpwnam", lambda _: pytest.fail("absent file needs no account lookup"))
    assert module.validate([metric], {metric: "honeypot"}) == [metric]
    with pytest.raises(ValueError, match="retirement file owners"):
        module.validate([], {metric: "honeypot"})


@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("role,filename", [
    ("monitoring", "vpn_xray.prom"),
    ("honeypot", "vpn_honeypot.prom"),
])
def test_consumers_expand_their_actual_metric_writer(tmp_path, role, filename, custom):
    """Ansible must expand owner-map keys before the validator checks paths."""
    import yaml

    tasks = yaml.safe_load((ROOT / f"ansible/roles/{role}/tasks/disable.yml").read_text())
    retire = next(task for task in tasks if task.get("ansible.builtin.include_role", {}).get("name") == "runtime-release")
    defaults = {}
    for name in ("monitoring", "honeypot"):
        defaults.update(yaml.safe_load((ROOT / f"ansible/roles/{name}/defaults/main.yml").read_text()))
    directory = "/srv/custom-textfile" if custom else "/var/lib/node_exporter/textfile"
    account = "custom_exporter" if custom and role == "monitoring" else (
        "prometheus" if role == "monitoring" else "honeypot"
    )
    if custom:
        defaults["monitoring"].update(node_exporter_textfile_dir=directory, node_exporter_user="custom_exporter")
    preflight = next(task for task in yaml.safe_load((ROOT / "ansible/roles/runtime-release/tasks/retire.yml").read_text())
                     if task["name"] == "Validate complete declared runtime authority before stopping units")
    play = [{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {**defaults, **retire["vars"], "expected_owners": {f"{directory}/{filename}": account},
                 "ansible_python_interpreter": sys.executable},
        "tasks": [
            {"name": "Evaluate the real validator request", "ansible.builtin.set_fact": {
                "request": preflight["ansible.builtin.command"]["stdin"]}},
            {"name": "Require exact expanded owner authority", "ansible.builtin.assert": {"that": [
                "(request | from_json).owners == expected_owners",
                "(request | from_json).owners.keys() | list | difference((request | from_json).paths) | length == 0",
            ]}},
        ],
    }]
    candidate = tmp_path / "play.yml"
    candidate.write_text(yaml.safe_dump(play))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    environment.update(ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(candidate)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


def test_validator_reports_which_accepted_paths_are_present(authority, monkeypatch, capsys):
    module, metric, _, _ = authority
    absent = "/owned/textfile/absent.prom"
    monkeypatch.setattr(module.sys, "stdin", io.StringIO(json.dumps({"paths": [metric, absent],
                                                                       "owners": {metric: "prometheus"}})))
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out) == {"status": "accepted", "paths": [metric, absent],
                                                   "present": [metric]}


@pytest.mark.parametrize("check_mode", [True, False])
def test_retirement_removes_only_present_paths_of_the_mode_validation(tmp_path, check_mode):
    """Check mode reuses the first validation; a deploy uses the one after its producers stopped."""
    import yaml

    removal = next(task for task in yaml.safe_load((ROOT / "ansible/roles/runtime-release/tasks/retire.yml").read_text())
                   if task["name"] == "Remove only declared runtime authority")
    play = [{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {"ansible_python_interpreter": sys.executable,
                 "_runtime_retire_effective_paths": ["/a", "/b", "/c"],
                 "_runtime_retire_preflight": {"stdout": json.dumps({"present": ["/a", "/b"]})},
                 "_runtime_retire_postflight": {"stdout": json.dumps({"present": ["/x", "/c", "/a"]})}},
        "tasks": [
            {"name": "Evaluate the real removal selection", "ansible.builtin.set_fact": {"selected": removal["loop"]}},
            {"name": "Require the mode's present accepted paths",
             "ansible.builtin.assert": {"that": [f"selected | sort == {['/a', '/b'] if check_mode else ['/a', '/c']}"]}},
        ],
    }]
    candidate = tmp_path / "play.yml"
    candidate.write_text(yaml.safe_dump(play))
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    environment.update(ANSIBLE_CONFIG=str(tmp_path / "absent.cfg"), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", *(["--check"] if check_mode else []), str(candidate)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


def test_declared_producer_grant_preserves_root_owned_metric(authority):
    module, metric, entries, metadata = authority
    entries[metric] = metadata(stat.S_IFREG | 0o600)
    assert module.validate([metric], {metric: "prometheus"}) == [metric]
