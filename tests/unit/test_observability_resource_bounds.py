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


def queue_boundary():
    spec = importlib.util.spec_from_file_location(
        "queue_boundary", AGENT / "files/observability-queue-boundary.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_queue_binding_refuses_unknown_backlog_and_receiver_changes(tmp_path):
    import os

    module = queue_boundary()
    queue = tmp_path / "queue"
    queue.mkdir(mode=0o700)
    binding = tmp_path / "receiver"
    receiver = "https://10.1.2.3:9443/remote-write/v1/nodes/vpn-p0"
    arguments = dict(agent_uid=os.getuid(), root_uid=os.getuid())
    module.inspect(queue, binding, receiver, **arguments)
    (queue / "chunk").write_bytes(b"persisted-telemetry")
    with pytest.raises(ValueError, match="unbound_retained_queue"):
        module.inspect(queue, binding, receiver, **arguments)
    binding.write_text(receiver + "\n")
    binding.chmod(0o600)
    module.inspect(queue, binding, receiver, **arguments)
    with pytest.raises(ValueError, match="retained_queue_receiver_changed"):
        module.inspect(
            queue, binding, receiver.replace("10.1.2.3", "10.1.2.4"), **arguments
        )
    binding.chmod(0o644)
    with pytest.raises(ValueError, match="unsafe_queue_binding"):
        module.inspect(queue, binding, receiver, **arguments)


def test_queue_capacity_adds_remaining_collector_budget(tmp_path, monkeypatch):
    module = queue_boundary()
    queue = tmp_path / "queue"
    queue.mkdir()
    fs = SimpleNamespace(f_blocks=40 * 1024**3, f_bavail=11 * 1024**3, f_frsize=1)
    monkeypatch.setattr(module.os, "statvfs", lambda _path: fs)
    monkeypatch.setattr(module, "allocated_bytes", lambda _path: 0)
    monkeypatch.setattr(
        module, "collector_allowance", lambda _device: 2 * 1024**3 + 128 * 1024**2
    )
    with pytest.raises(ValueError, match="queue_filesystem_reserve"):
        module.capacity(queue)
    fs.f_bavail = 13 * 1024**3
    module.capacity(queue)
    # A binary/candidate publication can consume the previously admitted margin.
    fs.f_bavail = 11 * 1024**3
    with pytest.raises(ValueError, match="queue_filesystem_reserve"):
        module.capacity(queue)
    fs.f_bavail = 13 * 1024**3
    monkeypatch.setattr(module, "allocated_bytes", lambda _path: 2 * 1024**3 + 1)
    with pytest.raises(ValueError, match="queue_allocation_exceeds_admission"):
        module.capacity(queue)


def test_collector_allowance_requires_new_guard_and_exact_owned_namespace(
    tmp_path, monkeypatch
):
    module = queue_boundary()
    unit = tmp_path / "guard.service"
    collector = tmp_path / "collector"
    collector.mkdir()
    monkeypatch.setattr(module, "GUARD_UNIT", unit)
    monkeypatch.setattr(module, "COLLECTOR", collector)
    original = module.os.fstat

    def owned(fd):
        value = original(fd)
        return SimpleNamespace(st_mode=value.st_mode, st_nlink=value.st_nlink, st_uid=0)

    monkeypatch.setattr(module.os, "fstat", owned)
    unit.write_text(
        "ExecStart=/usr/local/libexec/observability-disk-guard.py --data-dir "
        + str(collector)
        + " --headroom-bytes 134217728\n"
    )
    unit.chmod(0o644)
    with pytest.raises(ValueError, match="collector_shared_reserve_unproven"):
        module.collector_allowance(collector.stat().st_dev)
    unit.write_text(
        unit.read_text().strip() + " --agent-queue-allowance-bytes 2147483648\n"
    )
    used = module.allocated_bytes(collector)
    assert (
        module.collector_allowance(collector.stat().st_dev)
        == 2 * 1024**3 + 128 * 1024**2 - used
    )
    assert module.collector_allowance(collector.stat().st_dev + 1) == 0


def test_shared_guard_reserve_tracks_remaining_queue_and_rejects_overflow(
    tmp_path, monkeypatch
):
    module = guard()
    queue = tmp_path / "queue"
    queue.mkdir()
    monkeypatch.setattr(module, "AGENT_QUEUE", queue)
    fs = SimpleNamespace(f_blocks=40 * 1024**3, f_bavail=13 * 1024**3, f_frsize=1)
    monkeypatch.setattr(module.os, "statvfs", lambda _path: fs)
    monkeypatch.setattr(
        module,
        "allocated_bytes",
        lambda path, **_kw: 512 * 1024**2 if path == queue else 0,
    )
    assert module.inspect(arguments(tmp_path))[1] == 8 * 1024**3 + 1536 * 1024**2
    monkeypatch.setattr(
        module,
        "allocated_bytes",
        lambda path, **_kw: 2 * 1024**3 + 1 if path == queue else 0,
    )
    with pytest.raises(ValueError, match="agent_queue_allocation_exceeded"):
        module.inspect(arguments(tmp_path))


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
        agent_queue_allowance_bytes=2 * 1024**3,
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
    fs = SimpleNamespace(f_blocks=40 * 1024**3, f_bavail=12 * 1024**3, f_frsize=1)
    monkeypatch.setattr(module, "AGENT_QUEUE", tmp_path / "future-queue")
    monkeypatch.setattr(module.os, "statvfs", lambda _path: fs)
    assert module.inspect(arguments(tmp_path)) == (12 * 1024**3, 10 * 1024**3, 0)
    fs.f_bavail = 10 * 1024**3 + 128 * 1024**2
    with pytest.raises(ValueError, match="filesystem_reserve"):
        module.inspect(arguments(tmp_path))
    fs.f_bavail = 12 * 1024**3
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
    assert (tmp_path / "latched").stat().st_mode & 0o777 == 0o600
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
    assert agent["queue_max_disk_bytes"] == 536870912
    assert agent["queue_dir"] == "/var/lib/observability-agent/queue"
    assert "wal_max_time" not in agent


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
