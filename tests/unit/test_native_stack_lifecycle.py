"""Portable controller regressions; these stubs are not native traffic evidence."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_transport_frontend_boundary_native import fixture


def test_failed_start_acknowledgement_retains_unit_ownership(tmp_path, monkeypatch):
    stack = object.__new__(fixture.NativeStack)
    stack.token = stack.namespace = "owned-fixture"
    stack.assets = tmp_path
    stack.xray = "/synthetic/xray"
    stack.units, stack.unit_files = [], []
    monkeypatch.setattr(fixture, "Path", lambda path: tmp_path if path == "/etc/systemd/system" else Path(path))

    def command(argv):
        if argv[1] == "start":
            assert stack.units == ["owned-fixture-client"]
            raise RuntimeError("start-acknowledgement-lost")
        return ""

    monkeypatch.setattr(fixture, "command", command)
    with pytest.raises(RuntimeError, match="start-acknowledgement-lost"):
        stack.unit("client", ["/synthetic/client"])
    assert stack.unit_files == [tmp_path / "owned-fixture-client.service"]
    assert stack.unit_files[0].is_file()


@pytest.mark.parametrize("stop_status,state,pid", [(1, "inactive", 0), (0, "active", 42), (0, "failed", 42)])
def test_unconfirmed_stop_retains_runtime_authority(tmp_path, monkeypatch, stop_status, state, pid):
    stack = object.__new__(fixture.NativeStack)
    stack.processes, stack.units = [], ["owned-fixture-client"]
    unit = tmp_path / "owned-fixture-client.service"
    unit.write_text("synthetic unit authority")
    stack.unit_files = [unit]
    stack.library, stack.state = tmp_path / "library", tmp_path / "state"
    stack.library.mkdir()
    stack.state.mkdir()
    stack.created_namespace, stack.created_users = False, []
    monkeypatch.setattr(fixture.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=stop_status))
    monkeypatch.setattr(fixture, "command", lambda _argv: f"ActiveState={state}\nMainPID={pid}\n")
    with pytest.raises(RuntimeError, match="owned-native-unit-cleanup-unconfirmed"):
        stack.close()
    assert unit.is_file() and stack.library.is_dir() and stack.state.is_dir()


def test_log_rotation_deadline_reaches_driver_wire_contract(tmp_path, monkeypatch):
    stack = object.__new__(fixture.NativeStack)
    stack.values = {"watchdog": {"reality_probe_timeout": 15}}
    stack.driver_state, stack.namespace, stack.processes = tmp_path, "owned-fixture", []
    messages = []

    def complete(timeout):
        Path(messages[0]["result"]).write_text('{"tcp":true}')
        return 0

    process = SimpleNamespace(stdin=SimpleNamespace(
        write=lambda payload: messages.append(fixture.json.loads(payload)), close=lambda: None), wait=complete)
    monkeypatch.setattr(fixture.subprocess, "Popen", lambda *_args, **_kwargs: process)
    assert stack.run_driver(31081, socket_timeout=15) == {"tcp": True}
    assert messages[0]["socket_timeout"] == 15
    assert messages[0]["port"] == 31081 and messages[0]["negative_auth"] is False
