"""Passive inspection contracts; fixture results are not live fleet proof."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module():
    spec = importlib.util.spec_from_file_location("fleet_inspection", ROOT / "scripts/fleet_inspection.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def inventory(tmp_path: Path, extra: str = "") -> Path:
    key = tmp_path / "key"
    key.write_text("test-only-key")
    key.chmod(0o600)
    path = tmp_path / "inventory.ini"
    path.write_text(
        "[vpn]\nnode-a ansible_host=192.0.2.1 ansible_user=deploy ansible_port=2222 "
        f"{extra}\nnode-b ansible_host=192.0.2.2 ansible_user=deploy ansible_port=22\n"
        "[vpn-test]\nnode-a\n[vpn:vars]\n"
        f"ansible_ssh_private_key_file={key}\nansible_python_interpreter=/usr/bin/python3\n"
    )
    return path


def test_inventory_requires_explicit_exact_subset(tmp_path):
    m = module()
    path = inventory(tmp_path)
    assert [h["name"] for h in m.select_hosts(path, ["node-a"])] == ["node-a"]
    for selected in ([], ["all"], ["node-*"], ["node-a", "node-a"], ["missing"]):
        with pytest.raises(m.InspectionError):
            m.select_hosts(path, selected)


def test_generated_inventory_fixture_is_supported(tmp_path):
    m = module()
    path = inventory(tmp_path)
    original = (ROOT / "tests/fixtures/inventory-sample.ini").read_text()
    path.write_text(original.replace("/tmp/test-ssh-key", str(tmp_path / "key")))
    selected = m.select_hosts(path, ["vpn-test.example.com"])
    assert selected[0]["port"] == 2222
    assert selected[0]["address"] == "198.51.100.10"


@pytest.mark.parametrize("extra", [
    "ansible_ssh_common_args='-o ProxyCommand=unsafe'",
    "ansible_connection=local", "ansible_host=192.0.2.3",
    "inspection_host_key_alias='bad name'", "inspection_transport_host=192.0.2.4",
])
def test_ambiguous_or_executable_inventory_is_rejected(tmp_path, extra):
    m = module()
    with pytest.raises(m.InspectionError):
        m.select_hosts(inventory(tmp_path, extra), ["node-a"])


def test_ssh_isolated_from_user_configuration_and_keeps_identity(tmp_path):
    m = module()
    host = m.select_hosts(inventory(tmp_path, "inspection_transport_host=100.64.0.2 inspection_host_key_alias=192.0.2.1"), ["node-a"])[0]
    known = tmp_path / "known_hosts"
    known.write_text("test-only-pin")
    command = m.ssh_command(host, known)
    assert command[:3] == ["ssh", "-F", "/dev/null"]
    for option in ("StrictHostKeyChecking=yes", "UpdateHostKeys=no", "IdentitiesOnly=yes",
                   "ControlPath=none", "ControlMaster=no", "ControlPersist=no",
                   "ProxyCommand=none", "ProxyJump=none", "ClearAllForwardings=yes",
                   "PermitLocalCommand=no", "IdentityAgent=none", "ForwardAgent=no",
                   "GlobalKnownHostsFile=/dev/null", "HostKeyAlias=[192.0.2.1]:2222"):
        assert option in command
    assert command[command.index("-p") + 1] == "2222"
    assert command[-2:] == ["100.64.0.2", "sudo -n /usr/bin/python3 -I -B -S -"]


def test_private_file_read_is_bounded_and_rejects_links_and_fifo(tmp_path):
    m = module()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    regular = root / "value"
    regular.write_text("safe")
    # A supplied root descriptor is a test fixture boundary, not a CLI override.
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert m.read_beneath(fd, "value", owner=os.getuid()) == b"safe"
        (root / "link").symlink_to(regular)
        os.mkfifo(root / "fifo")
        regular.write_bytes(b"x" * 65537)
        for path in ("link", "fifo", "value", "../outside", "/absolute"):
            with pytest.raises(m.InspectionError):
                m.read_beneath(fd, path, owner=os.getuid())
    finally:
        os.close(fd)


def test_read_rejects_writable_parent(tmp_path):
    m = module()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    child = root / "unsafe"
    child.mkdir()
    child.chmod(0o777)
    (child / "value").write_text("no")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(m.InspectionError):
            m.read_beneath(fd, "unsafe/value", owner=os.getuid())
    finally:
        os.close(fd)


def test_restore_evidence_distinguishes_snapshot_and_drill_freshness():
    m = module()
    raw = {"version": 1, "repository_source": "local", "snapshot_id": "private-id",
           "snapshot_time": "2026-01-01T00:00:00Z", "verified_at": "2026-01-02T00:00:00Z"}
    result = m.restore_evidence(raw, m.parse_time("2026-01-03T00:00:00Z"))
    assert result["status"] == "observed"
    assert result["snapshot_freshness"] == "stale"
    assert result["repository_source"] == "local"
    assert "private-id" not in json.dumps(result)
    assert m.restore_evidence(raw, m.parse_time("2026-03-03T00:00:00Z"))["status"] == "stale"
    assert m.restore_evidence(raw, m.parse_time("2025-12-31T00:00:00Z"))["status"] == "unknown"
    assert m.restore_evidence(raw, m.parse_time("2026-01-01T23:59:59Z"))["status"] == "unknown"


def test_manifest_output_does_not_copy_unapproved_fields():
    m = module()
    result = m.manifest_evidence({"schema_version": 2, "source_revision": "a" * 40,
                                  "deployable_digest": "b" * 64, "password": "do-not-emit"})
    assert result == {"status": "observed", "schema_version": 2,
                      "source_revision": "a" * 40, "deployable_digest": "b" * 64}
    assert m.manifest_evidence({"schema_version": 99})["status"] == "unknown"


def test_listener_output_contains_only_address_protocol_and_port():
    m = module()
    raw = "tcp LISTEN 0 100 127.0.0.1:22 0.0.0.0:*\nudp UNCONN 0 0 [::]:443 [::]:*\n"
    assert m.parse_listeners(raw) == [{"protocol": "tcp", "address": "127.0.0.1", "port": 22},
                                     {"protocol": "udp", "address": "::", "port": 443}]
    with pytest.raises(m.InspectionError):
        m.parse_listeners("raw-secret-output")


def test_remote_collector_never_invokes_repair_or_restic(monkeypatch):
    m = module()
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "/usr/bin/ss":
            return b"tcp LISTEN 0 100 127.0.0.1:22 0.0.0.0:*\n"
        return b"LoadState=loaded\nActiveState=failed\nSubState=failed\nResult=exit-code\nExecMainStatus=1\nExecMainExitTimestamp=\n"

    monkeypatch.setattr(m, "bounded_command", run)
    monkeypatch.setattr(m, "read_host_json", lambda path: (_ for _ in ()).throw(m.InspectionError("missing")))
    result = m.collect()
    assert result["services"]["ssh.service"]["active_state"] == "failed"
    assert result["services"]["ssh.service"]["exec_main_exit_timestamp"] is None
    assert result["manifest"] == {"status": "unknown"}
    assert result["backup"]["restore"] == {"status": "unknown"}
    assert result["backup"]["latest_snapshot"]["status"] == "unknown"
    assert all(c[:2] == ["/usr/bin/systemctl", "show"] or c == ["/usr/bin/ss", "-H", "-lntu"] for c in commands)
    assert "watchdog.sh" not in json.dumps(commands)
    assert "restic" not in json.dumps(commands)
    monkeypatch.setattr(m, "bounded_command", lambda *args, **kwargs: (_ for _ in ()).throw(m.InspectionError("unavailable")))
    assert m.collect()["listeners"] == {"status": "unknown"}


def test_command_output_limit_and_deadline_are_enforced():
    m = module()
    with pytest.raises(m.InspectionError, match="output-limit"):
        m.bounded_command(["/usr/bin/printf", "x" * 4096], timeout=2, limit=100)
    with pytest.raises(m.InspectionError, match="timeout"):
        m.bounded_command(["/bin/sleep", "2"], timeout=0.05)


def test_inspect_make_target_has_no_active_prerequisites():
    result = subprocess.run(["make", "-n", "inspect", "INSPECT_HOSTS=node-a"], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0
    assert "fleet-inspect.py" in result.stdout
    assert all(word not in result.stdout for word in ("terraform-env", "ansible-playbook", "decrypt-secrets", "wait-cloud-init", "vpn-watchdog"))


def test_local_inventory_rejects_links_and_nonregular_files(tmp_path):
    m = module()
    original = inventory(tmp_path)
    linked = tmp_path / "linked.ini"
    linked.symlink_to(original)
    for path in (linked, tmp_path):
        with pytest.raises(m.InspectionError):
            m.select_hosts(path, ["node-a"])


def test_inventory_fifo_fails_promptly(tmp_path):
    path = tmp_path / "fifo"
    os.mkfifo(path)
    code = "import fleet_inspection as m; m.select_hosts(__import__('pathlib').Path(__import__('sys').argv[1]), ['node-a'])"
    result = subprocess.run([sys.executable, "-c", code, str(path)], cwd=ROOT / "scripts", capture_output=True, timeout=2)
    assert result.returncode != 0


def test_timer_properties_do_not_require_service_exec_fields():
    m = module()
    result = m.service_evidence("LoadState=loaded\nActiveState=active\nSubState=waiting\nResult=success\n")
    assert result["status"] == "observed"
    assert result["active_state"] == "active"
    assert result["exec_main_status"] is None


def test_awg_instances_are_discovered_from_managed_target(monkeypatch):
    m = module()
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if "--property=Wants" in command:
            return b"Wants=awg-quick@awg7.service awg-quick@edge0.service\n"
        if command[0] == "/usr/bin/ss":
            return b""
        return b"LoadState=loaded\nActiveState=active\nSubState=running\nResult=success\nExecMainStatus=0\nExecMainExitTimestamp=\n"

    monkeypatch.setattr(m, "bounded_command", run)
    monkeypatch.setattr(m, "read_host_json", lambda path: {})
    result = m.collect()
    assert result["services"]["awg-quick@awg7.service"]["active_state"] == "active"
    assert "amneziawg.service" not in result["services"]
    assert "awg-quick@awg0.service" not in result["services"]


def observation(m, monkeypatch):
    monkeypatch.setattr(m, "bounded_command", lambda *a, **k: b"")
    monkeypatch.setattr(m, "read_host_json", lambda path: {})
    return m.collect()


@pytest.mark.parametrize("kind", ["secret", "unit", "listener", "timestamp", "backup", "service"])
def test_controller_rejects_unapproved_remote_fields(monkeypatch, kind):
    m = module()
    report = observation(m, monkeypatch)
    if kind == "secret":
        report["password"] = "do-not-emit"
    elif kind == "unit":
        report["services"]["injected.service"] = {"status": "unknown"}
    elif kind == "listener":
        report["listeners"] = {"status": "observed", "items": [{"protocol": "tcp", "address": "private-secret", "port": 443}]}
    elif kind == "timestamp":
        report["observed_at"] = "2099-01-01T00:00:00Z"
    elif kind == "backup":
        report["backup"]["latest_snapshot"] = {"status": "observed"}
    else:
        report["services"]["ssh.service"] = {"status": "unknown", "stderr": "do-not-emit"}
    with pytest.raises(m.InspectionError):
        m.validate_report(report, m.parse_time("2026-08-28T12:00:00Z"))


def test_controller_accepts_only_canonical_observation(monkeypatch):
    m = module()
    report = observation(m, monkeypatch)
    assert m.validate_report(report, m.parse_time(report["observed_at"])) == report


def test_command_input_stderr_and_exit_are_bounded():
    m = module()
    assert m.bounded_command(["/bin/cat"], input_bytes=b"bounded") == b"bounded"
    with pytest.raises(m.InspectionError, match="output-limit"):
        m.bounded_command([sys.executable, "-c", "import sys;sys.stderr.write('x'*1024)"], limit=100)
    with pytest.raises(m.InspectionError, match="command-failed"):
        m.bounded_command([sys.executable, "-c", "raise SystemExit(2)"])


def controller(monkeypatch):
    m = module()
    monkeypatch.setitem(sys.modules, "fleet_inspection", m)
    spec = importlib.util.spec_from_file_location("fleet_inspect_cli", ROOT / "scripts/fleet-inspect.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return m, cli


def test_controller_never_contacts_implicit_hosts_or_emits_raw_output(tmp_path, monkeypatch, capsys):
    m, cli = controller(monkeypatch)
    path = inventory(tmp_path)
    known = tmp_path / "known_hosts"
    known.write_text("fixture-only")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return b'{"password":"do-not-emit"}'

    monkeypatch.setattr(m, "bounded_command", run)
    args = ["--inventory", str(path), "--known-hosts", str(known)]
    assert cli.main(args) == 2
    assert not calls
    assert cli.main([*args, "--hosts", "node-a"]) == 1
    assert len(calls) == 1
    assert calls[0][0][-2] == "192.0.2.1"
    assert calls[0][1]["timeout"] == 30
    assert b"def collect" in calls[0][1]["input_bytes"]
    output = capsys.readouterr()
    assert "do-not-emit" not in output.out + output.err
    assert "node-b" not in output.out


def test_unknown_and_failed_collection_cannot_be_healthy(monkeypatch):
    m = module()
    report = observation(m, monkeypatch)
    now = m.parse_time(report["observed_at"])
    assert m.observation_status(report, now) == "unknown"
    report["services"]["ssh.service"] = {"status": "observed", "active_state": "failed"}
    assert m.observation_status(report, now) == "error"


def test_known_hosts_and_keys_reject_unsafe_parent_and_expansion(tmp_path):
    m = module()
    path = inventory(tmp_path)
    known = tmp_path / "known%h"
    known.write_text("fixture")
    host = m.select_hosts(path, ["node-a"])[0]
    with pytest.raises(m.InspectionError):
        m.ssh_command(host, known)
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    known = unsafe / "known_hosts"
    known.write_text("fixture")
    unsafe.chmod(0o777)
    with pytest.raises(m.InspectionError):
        m.ssh_command(host, known)


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59"])
def test_extreme_timezone_dates_are_categorical_errors(value):
    m = module()
    with pytest.raises(m.InspectionError):
        m.parse_time(value)


def test_unknown_systemd_state_cannot_be_observed():
    m = module()
    assert m.service_evidence("LoadState=garbage\nActiveState=garbage\nSubState=garbage\n")["status"] == "unknown"


def test_duplicate_transport_or_identity_is_rejected(tmp_path):
    m = module()
    path = inventory(tmp_path)
    path.write_text(path.read_text().replace("ansible_host=192.0.2.2 ansible_user=deploy ansible_port=22", "ansible_host=192.0.2.1 ansible_user=deploy ansible_port=2222"))
    with pytest.raises(m.InspectionError):
        m.select_hosts(path, ["node-a", "node-b"])
