"""Retirement grants only exact regular files to declared producer accounts."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
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


def test_consumers_declare_their_actual_metric_writer():
    import yaml

    for role, account, filename in (
        ("monitoring", "{{ monitoring.node_exporter_user | default('prometheus') }}", "vpn_xray.prom"),
        ("honeypot", "honeypot", "vpn_honeypot.prom"),
    ):
        tasks = yaml.safe_load((ROOT / f"ansible/roles/{role}/tasks/disable.yml").read_text())
        retire = next(task for task in tasks if task.get("ansible.builtin.include_role", {}).get("name") == "runtime-release")
        owners = retire["vars"]["runtime_retire_file_owners"]
        assert len(owners) == 1
        assert next(iter(owners)).endswith(filename)
        assert next(iter(owners.values())) == account
        assert set(owners) <= set(retire["vars"]["runtime_retire_paths"])


def test_declared_producer_grant_preserves_root_owned_metric(authority):
    module, metric, entries, metadata = authority
    entries[metric] = metadata(stat.S_IFREG | 0o600)
    assert module.validate([metric], {metric: "prometheus"}) == [metric]
