"""Fleet status controller regressions; isolated observations are not live proof."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def modules(monkeypatch):
    loaded = []
    for name in ("fleet_inspection", "fleet_status"):
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded


def report(inspection, now):
    services = {name: {"status": "unknown"} for name in inspection.SERVICES}
    completed = inspection.timestamp(now - dt.timedelta(seconds=30))
    services["vpn-watchdog.service"] = {
        "status": "observed", "load_state": "loaded", "active_state": "inactive",
        "sub_state": "dead", "result": "success", "exec_main_status": 0,
        "exec_main_exit_timestamp": completed,
    }
    services["vpn-watchdog.timer"] = {
        "status": "observed", "load_state": "loaded", "active_state": "active",
        "sub_state": "waiting", "result": "success", "exec_main_status": None,
        "exec_main_exit_timestamp": None,
    }
    return {
        "schema_version": 1, "observed_at": inspection.timestamp(now), "services": services,
        "manifest": {"status": "observed", "schema_version": 2,
                     "source_revision": "a" * 40, "deployable_digest": "b" * 64},
        "listeners": {"status": "observed", "items": [
            {"protocol": "udp", "address": "0.0.0.0", "port": 443}]},
        "backup": {"latest_snapshot": {"status": "unknown"}, "restore": {"status": "unknown"}},
    }


def inputs(tmp_path):
    key = tmp_path / "key"
    key.write_text("synthetic-key")
    key.chmod(0o600)
    inventory = tmp_path / "inventory.ini"
    inventory.write_text(
        "[vpn]\nnode-a ansible_host=100.64.0.2 vpn_service_address=192.0.2.1 "
        "ansible_user=deploy ansible_port=2222 provider=upcloud env=prod\n"
        "node-b ansible_host=192.0.2.2 ansible_user=deploy ansible_port=22 provider=vultr env=prod\n"
        f"[vpn:vars]\nansible_ssh_private_key_file={key}\n"
    )
    known = tmp_path / "known_hosts"
    known.write_text("synthetic-pin")
    return inventory, known


def test_wrapper_resolves_default_inventory_from_checkout(tmp_path, monkeypatch):
    inventory, known = inputs(tmp_path)
    checkout = tmp_path / "checkout"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    for name in ("fleet-status.sh", "fleet_status.py", "fleet_inspection.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    default_inventory = checkout / "ansible/inventory/generated.ini"
    default_inventory.parent.mkdir(parents=True)
    inventory.rename(default_inventory)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv("FLEET_INVENTORY", raising=False)
    result = subprocess.run(
        [str(scripts / "fleet-status.sh"), "--hosts", "missing:prod", "--known-hosts", str(known)],
        cwd=elsewhere, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stderr) == {"error": "host-not-found"}


def test_recent_completed_success_is_local_only(modules):
    inspection, status = modules
    now = dt.datetime.now(dt.timezone.utc)
    observation = report(inspection, now)
    inspection.validate_report(observation, now)
    assert status.watchdog_health(observation, now) == {"status": "healthy", "reason": "recent-success"}


@pytest.mark.parametrize("change,expected", [
    ({"active_state": "failed", "sub_state": "failed", "result": "exit-code", "exec_main_status": 1}, "unhealthy"),
    ({"result": "timeout"}, "unhealthy"),
    ({"exec_main_status": 1}, "unhealthy"),
    ({"active_state": "activating", "sub_state": "start"}, "unknown"),
    ({"active_state": "activating", "sub_state": "start", "result": "exit-code", "exec_main_status": 1}, "unknown"),
    ({"active_state": "active", "sub_state": "running"}, "unknown"),
    ({"exec_main_exit_timestamp": None}, "unknown"),
    ({"exec_main_status": None}, "unknown"),
    ({"result": ""}, "unknown"),
    ({"load_state": "not-found"}, "unknown"),
])
def test_active_timer_never_masks_failed_or_uncompleted_service(modules, change, expected):
    inspection, status = modules
    now = dt.datetime.now(dt.timezone.utc)
    observation = report(inspection, now)
    observation["services"]["vpn-watchdog.service"].update(change)
    assert status.watchdog_health(observation, now)["status"] == expected


@pytest.mark.parametrize("field,seconds,expected", [
    ("exec_main_exit_timestamp", -301, "stale"),
    ("exec_main_exit_timestamp", -300, "healthy"),
    ("exec_main_exit_timestamp", 1, "unknown"),
    ("observed_at", -301, "stale"),
    ("observed_at", 1, "unknown"),
])
def test_watchdog_freshness_is_explicit(modules, field, seconds, expected):
    inspection, status = modules
    now = dt.datetime.now(dt.timezone.utc)
    observation = report(inspection, now)
    target = observation if field == "observed_at" else observation["services"]["vpn-watchdog.service"]
    target[field] = inspection.timestamp(now + dt.timedelta(seconds=seconds))
    assert status.watchdog_health(observation, now)["status"] == expected


@pytest.mark.parametrize("timer", [{"status": "unknown"}, {"active_state": "inactive"}, {"load_state": "not-found"}])
def test_success_requires_active_loaded_timer(modules, timer):
    inspection, status = modules
    now = dt.datetime.now(dt.timezone.utc)
    observation = report(inspection, now)
    observation["services"]["vpn-watchdog.timer"].update(timer)
    assert status.watchdog_health(observation, now)["status"] != "healthy"


def test_status_uses_strict_tailnet_identity_and_does_not_probe_udp_only_host(modules, tmp_path, monkeypatch, capsys):
    inspection, status = modules
    inventory, known = inputs(tmp_path)
    observation = report(inspection, dt.datetime.now(dt.timezone.utc))
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return json.dumps(observation).encode()

    monkeypatch.setattr(inspection, "bounded_command", run)
    args = ["--hosts", "upcloud:prod", "--inventory", str(inventory), "--known-hosts", str(known)]
    assert status.main([*args, "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    row = output["hosts"][0]
    assert row["name"] == "node-a"
    assert row["source_revision"] == "a" * 40
    assert row["watchdog_local"]["status"] == "healthy"
    assert row["client_path"] == "unknown"
    assert row["observation"] == observation
    command, options = calls[0]
    assert command[:3] == ["ssh", "-F", "/dev/null"]
    assert command[-2] == "100.64.0.2"
    assert command[command.index("-p") + 1] == "2222"
    assert "StrictHostKeyChecking=yes" in command
    assert "HostKeyAlias=[192.0.2.1]:2222" in command
    assert options["timeout"] == 30
    assert b"def collect" in options["input_bytes"]
    assert len(calls) == 1
    assert status.main(args) == 0
    table = capsys.readouterr().out
    assert all(value in table for value in ("SOURCE_REV", "WATCHDOG_LOCAL", "CLIENT_PATH", "healthy", "unknown"))
    assert "blocked" not in table and "reachable" not in table


@pytest.mark.parametrize("invalid", ["host", "duplicate", "known", "key", "ambiguous"])
def test_all_local_inputs_are_admitted_before_any_ssh(modules, tmp_path, monkeypatch, capsys, invalid):
    inspection, status = modules
    inventory, known = inputs(tmp_path)
    selected = "upcloud:prod,vultr:prod"
    if invalid == "host":
        selected += ",unknown:prod"
    elif invalid == "duplicate":
        selected += ",upcloud:prod"
    elif invalid == "known":
        known.chmod(0o666)
    elif invalid == "key":
        inventory.write_text(inventory.read_text().replace("provider=vultr", "ansible_ssh_private_key_file=/missing provider=vultr"))
    else:
        inventory.write_text(inventory.read_text().replace("provider=vultr", "provider=upcloud"))
    monkeypatch.setattr(inspection, "bounded_command", lambda *a, **k: pytest.fail("unexpected remote command"))
    assert status.main(["--hosts", selected, "--inventory", str(inventory), "--known-hosts", str(known)]) == 2
    assert "error" in capsys.readouterr().err


@pytest.mark.parametrize("raw", [b'{"password":"never-print-this"}', b'not-json-never-print-this'])
def test_untrusted_remote_output_is_categorical(modules, tmp_path, monkeypatch, capsys, raw):
    inspection, status = modules
    inventory, known = inputs(tmp_path)
    monkeypatch.setattr(inspection, "bounded_command", lambda *a, **k: raw)
    assert status.main(["--hosts", "upcloud:prod", "--inventory", str(inventory), "--known-hosts", str(known), "--json"]) == 1
    output = capsys.readouterr()
    assert "never-print-this" not in output.out + output.err
    row = json.loads(output.out)["hosts"][0]
    assert row["watchdog_local"]["status"] == "unknown"
    assert row["client_path"] == "unknown"


def test_hosts_environment_selection_preserves_default_pair(modules, tmp_path, monkeypatch, capsys):
    inspection, status = modules
    inventory, known = inputs(tmp_path)
    monkeypatch.setenv("FLEET_INVENTORY", str(inventory))
    monkeypatch.setenv("FLEET_KNOWN_HOSTS", str(known))
    monkeypatch.setenv("PROVIDER", "vultr")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("HOSTS", raising=False)
    observation = report(inspection, dt.datetime.now(dt.timezone.utc))
    monkeypatch.setattr(inspection, "bounded_command", lambda *a, **k: json.dumps(observation).encode())
    assert status.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["hosts"][0]["name"] == "node-b"
    monkeypatch.setenv("HOSTS", "upcloud:prod")
    assert status.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["hosts"][0]["name"] == "node-a"


@pytest.mark.parametrize("kind,expected", [("failure", "unhealthy"), ("stale", "stale"), ("future", "unknown")])
def test_cli_preserves_negative_watchdog_verdicts(modules, tmp_path, monkeypatch, capsys, kind, expected):
    inspection, status = modules
    inventory, known = inputs(tmp_path)
    now = dt.datetime.now(dt.timezone.utc)
    observation = report(inspection, now)
    service = observation["services"]["vpn-watchdog.service"]
    if kind == "failure":
        service.update(active_state="failed", sub_state="failed", result="exit-code", exec_main_status=1)
    else:
        service["exec_main_exit_timestamp"] = inspection.timestamp(now + dt.timedelta(seconds=10 if kind == "future" else -301))
    monkeypatch.setattr(inspection, "bounded_command", lambda *a, **k: json.dumps(observation).encode())
    assert status.main(["--hosts", "upcloud:prod", "--inventory", str(inventory), "--known-hosts", str(known), "--json"]) == 1
    row = json.loads(capsys.readouterr().out)["hosts"][0]
    assert row["watchdog_local"]["status"] == expected
    assert row["client_path"] == "unknown"


def test_one_timed_out_host_does_not_hide_remaining_observations(modules, tmp_path, monkeypatch, capsys):
    inspection, status = modules
    inventory, known = inputs(tmp_path)
    observation = report(inspection, dt.datetime.now(dt.timezone.utc))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise inspection.InspectionError("timeout")
        return json.dumps(observation).encode()

    monkeypatch.setattr(inspection, "bounded_command", run)
    assert status.main(["--hosts", "upcloud:prod,vultr:prod", "--inventory", str(inventory), "--known-hosts", str(known), "--json"]) == 1
    rows = json.loads(capsys.readouterr().out)["hosts"]
    assert len(calls) == 2
    assert rows[0]["error"] == "timeout"
    assert rows[0]["watchdog_local"]["status"] == "unknown"
    assert rows[1]["watchdog_local"]["status"] == "healthy"


def test_shell_wrapper_forwards_arguments_before_host_access(tmp_path):
    inventory, known = inputs(tmp_path)
    command = [str(ROOT / "scripts/fleet-status.sh"), "--hosts", "missing:prod",
               "--inventory", str(inventory), "--known-hosts", str(known), "--json"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=5, check=False)
    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"error": "host-not-found"}
