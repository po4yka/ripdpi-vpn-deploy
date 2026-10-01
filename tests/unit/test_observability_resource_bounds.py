"""Executable reserve-guard decisions and aggregate resource contracts."""

import argparse
import errno
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
AGENT = ROOT / "ansible/roles/observability_agent"


def guard():
    spec = importlib.util.spec_from_file_location(
        "disk_guard", ROLE / "files/observability-disk-guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arguments(tmp_path, **changes):
    values = dict(
        data_dir=str(tmp_path),
        high_water_bytes=2 * 1024**3,
        reserve_bytes=5 * 1024**3,
        reserve_percent=20,
        headroom_bytes=128 * 1024**2,
        peak_bytes_per_second=1024**2,
        stop_seconds=30,
        interval_seconds=5,
    )
    values.update(changes)
    return argparse.Namespace(**values)


@pytest.mark.parametrize(
    "address", ["10.1.2.3", "172.16.2.3", "192.168.2.3", "100.64.2.3"]
)
def test_guard_accepts_only_documented_private_addresses(address):
    assert guard().private_address(address) == address


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "0.0.0.0", "8.8.8.8", "::1", "ingress.test", "10.1.2.999"]
)
def test_guard_refuses_public_loopback_and_nonliteral_addresses(address):
    with pytest.raises(ValueError):
        guard().private_address(address)


def test_guard_accepts_measured_headroom_and_refuses_unmeasured_or_unbounded(tmp_path):
    module = guard()
    module.validate_measurement(arguments(tmp_path))
    for changes in [
        dict(peak_bytes_per_second=0),
        dict(stop_seconds=0),
        dict(stop_seconds=31),
        dict(interval_seconds=6),
        dict(headroom_bytes=79 * 1024**2),
        dict(reserve_percent=19),
        dict(high_water_bytes=3 * 1024**3),
    ]:
        with pytest.raises(ValueError):
            module.validate_measurement(arguments(tmp_path, **changes))


def test_guard_protects_total_filesystem_reserve_and_wal_head_highwater(
    tmp_path, monkeypatch
):
    module = guard()
    fs = SimpleNamespace(f_blocks=40 * 1024**3, f_bavail=10 * 1024**3, f_frsize=1)
    monkeypatch.setattr(module.os, "statvfs", lambda _path: fs)
    assert module.inspect(arguments(tmp_path)) == (10 * 1024**3, 8 * 1024**3, 0)
    fs.f_bavail = 8 * 1024**3 + 128 * 1024**2
    with pytest.raises(ValueError, match="filesystem_reserve"):
        module.inspect(arguments(tmp_path))
    fs.f_bavail = 10 * 1024**3
    monkeypatch.setattr(
        module, "allocated_bytes", lambda _path, **_kwargs: 2 * 1024**3 - 128 * 1024**2
    )
    with pytest.raises(ValueError, match="data_high_water"):
        module.inspect(arguments(tmp_path))


def test_guard_counts_allocated_wal_blocks_and_rejects_links(tmp_path):
    module = guard()
    wal = tmp_path / "wal"
    wal.mkdir()
    chunk = wal / "000001"
    chunk.write_bytes(b"a" * 8192)
    assert module.allocated_bytes(tmp_path) >= chunk.stat().st_blocks * 512
    (wal / "foreign").symlink_to(chunk)
    with pytest.raises(ValueError, match="unsafe_data_tree"):
        module.allocated_bytes(tmp_path)


def test_missing_data_root_is_allowed_only_during_preflight(tmp_path):
    module = guard()
    missing = tmp_path / "not-created-yet"
    assert module.allocated_bytes(missing, allow_missing=True) == 0
    with pytest.raises(FileNotFoundError):
        module.allocated_bytes(missing)


def test_guard_tolerates_only_child_disappearance_during_compaction(
    tmp_path, monkeypatch
):
    module = guard()
    child = tmp_path / "old-block"
    child.write_bytes(b"a" * 8192)
    original = Path.lstat

    def vanished(path, *args, **kwargs):
        if path == child:
            raise FileNotFoundError(errno.ENOENT, "removed by compaction", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", vanished)
    assert module.allocated_bytes(tmp_path) == 0

    def denied(path, *args, **kwargs):
        if path == child:
            raise PermissionError(errno.EACCES, "denied", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(PermissionError):
        module.allocated_bytes(tmp_path)


def test_guard_does_not_silently_ignore_walk_errors_or_replaced_root(
    tmp_path, monkeypatch
):
    module = guard()

    def inaccessible(root, **kwargs):
        kwargs["onerror"](PermissionError(errno.EACCES, "denied", str(root / "child")))
        return iter([])

    monkeypatch.setattr(module.os, "walk", inaccessible)
    with pytest.raises(PermissionError):
        module.allocated_bytes(tmp_path)

    def vanished_root(root, **kwargs):
        kwargs["onerror"](FileNotFoundError(errno.ENOENT, "gone", str(root)))
        return iter([])

    monkeypatch.setattr(module.os, "walk", vanished_root)
    with pytest.raises(FileNotFoundError):
        module.allocated_bytes(tmp_path)


def test_latch_is_persistent_exclusive_and_not_removed_by_recovery(tmp_path):
    module = guard()
    module.latch(tmp_path)
    assert (tmp_path / "latched").read_text() == "disk_guard_latched\n"
    with pytest.raises(FileExistsError):
        module.latch(tmp_path)
    assert (tmp_path / "latched").exists()


def test_all_runtime_units_share_fixed_aggregate_slices_and_receiver_requires_guard():
    for role, slice_name, memory, cpu in [
        (ROLE, "observability-collector", "512M", "20%"),
        (AGENT, "observability-agent", "192M", "10%"),
    ]:
        for unit in (role / "templates").glob("*.service.j2"):
            assert f"Slice={slice_name}.slice" in unit.read_text(), unit.name
        limits = (role / f"templates/{slice_name}.slice.j2").read_text()
        for limit in [
            f"MemoryMax={memory}",
            f"CPUQuota={cpu}",
            "MemorySwapMax=0",
            "IOWeight=10",
        ]:
            assert limit in limits
    receiver = (ROLE / "templates/observability-prometheus.service.j2").read_text()
    assert "BindsTo=observability-disk-guard.service" in receiver
    assert "ConditionPathExists=!/var/lib/observability-disk-guard/latched" in receiver
    watchdog = (ROLE / "templates/observability-disk-guard.service.j2").read_text()
    assert "Type=notify" in watchdog
    assert "WatchdogSec=10s" in watchdog
    assert "Restart=no" in watchdog


def test_capacity_preflight_precedes_all_mutations_and_disable_retains_data_and_latch():
    tasks = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    names = [task["name"] for task in tasks]
    assert names.index(
        "Require measured capacity and private address before host mutation"
    ) < names.index("Create dedicated control-plane account")
    disable = (ROLE / "tasks/disable.yml").read_text()
    assert "disk_guard_state_dir" not in disable
    assert '"{{ observability_control_plane.config_root }}"' not in disable
    agent = yaml.safe_load((AGENT / "defaults/main.yml").read_text())[
        "observability_agent"
    ]
    assert agent["scrape_interval"] == "60s"
    assert agent["scrape_sample_limit"] == 2000
    assert agent["wal_max_time"] == "1h"


def test_collector_does_not_bypass_the_cohosted_agent_privacy_allowlist():
    config = (ROLE / "templates/prometheus.yml.j2").read_text()
    assert "127.0.0.1:9100" not in config
    assert 'regex: "^alertmanager_notifications_(total|failed_total)$"' in config
    assert 'regex: "^(__name__|job|integration)$"' in config
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_control_plane"
    ]
    assert defaults["service_user"] == "observability-prometheus"
    assert defaults["service_group"] == "observability-prometheus"


def test_disable_stops_existing_adapter_timers_and_services_before_removal():
    for role, relative in [
        (ROLE, "tasks/disable.yml"),
        (AGENT, "tasks/main.yml"),
        (ROLE, "tasks/expected-targets-disable.yml"),
        (ROLE, "tasks/protocol-liveness-disable.yml"),
    ]:
        text = (role / relative).read_text()
        if role == AGENT:
            text = text.split("- name: Configure observability agent")[0]
        assert "ansible.builtin.stat:" in text
        assert "item.stat.exists" in text
        assert "failed_when: false" not in text
        assert "-adapter.timer" in text
        assert "-adapter.service" in text


def test_agent_boundary_entrypoint_precedes_binary_and_account_mutation():
    tasks = (AGENT / "tasks/main.yml").read_text()
    assert tasks.index(
        "ansible.builtin.include_tasks: resource-boundary.yml"
    ) < tasks.index("Create observability agent runtime account")
    boundary = yaml.safe_load((AGENT / "tasks/resource-boundary.yml").read_text())
    assert (
        boundary[0]["ansible.builtin.template"]["dest"]
        == "/etc/systemd/system/observability-agent.slice"
    )
    assert boundary[1]["ansible.builtin.systemd_service"]["state"] == "started"
    producers = (
        ROOT / "ansible/roles/observability_kuma/tasks/producers.yml"
    ).read_text()
    assert producers.index("tasks_from: resource-boundary") < producers.index(
        "Create dedicated heartbeat user"
    )
