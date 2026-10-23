"""Portable AWG orchestration regressions; these adapters are not native proof."""

import re
import time
from pathlib import Path
from types import SimpleNamespace

import device_lifecycle_probe_worker as worker
import pytest


class AwgHarness(worker.Runtime):
    """Model a visible TUN whose independently started UAPI is not yet ready."""

    def __init__(self, tmp_path, monkeypatch, *, replies=None, dead_after_reads=None,
                 setconf_status=0, cleanup_failure=False, fault=None,
                 moved_before_failure=False, read_seconds=0):
        super().__init__(namespace_root=tmp_path / "resolvers")
        self.directory = tmp_path / "private"
        self.directory.mkdir(mode=0o700)
        self.markers = tmp_path / "markers"
        self.markers.mkdir(mode=0o700)
        self.replies = [(0, b"59390\n")] if replies is None else list(replies)
        self.reads = 0
        self.setconf_calls = 0
        self.http_calls = 0
        self.events = []
        self.fresh = False
        self.setconf_status = setconf_status
        self.cleanup_failure = cleanup_failure
        self.fault = fault
        self.moved_before_failure = moved_before_failure
        self.read_seconds = read_seconds
        self.phases = []
        self.command_deadlines = []
        self.interface = None
        self.location = None
        self.namespace = None
        self.stopped = False
        self.elapsed = 0.0
        self.process = SimpleNamespace(poll=lambda: (
            1 if dead_after_reads is not None and self.reads >= dead_after_reads else None))
        original_path = Path
        monkeypatch.setattr(worker, "Path", lambda value: self.markers if value == "/run/netns" else original_path(value))
        monkeypatch.setattr(worker.subprocess, "Popen", self.launch)
        monkeypatch.setattr(worker, "_stop", self.stop)
        monkeypatch.setattr(worker, "time", SimpleNamespace(
            monotonic=self.monotonic, sleep=self.sleep, time=time.time))

    def monotonic(self):
        self.elapsed += 0.001
        return self.elapsed

    def sleep(self, seconds):
        assert 0 < seconds <= 0.1
        self.elapsed += seconds

    def binary(self, name):
        return name

    def launch(self, args, **kwargs):
        assert args[:2] == ["awg-go", "-f"]
        assert kwargs["start_new_session"]
        self.interface, self.location = args[2], "host"
        self.events.append("tun-visible")
        return self.process

    def stop(self, process):
        assert process is self.process if self.interface else process is None
        self.stopped = True
        self.events.append("stop")
        return True

    def outcome(self, phase, value=b""):
        self.phases.append(phase)
        return (7, b"private-output-canary") if phase == self.fault else (0, value)

    def command(self, args, *, data=None, timeout=5):
        args = [str(value) for value in args]
        self.command_deadlines.append(self.deadline)
        if self.deadline is not None and self.elapsed >= self.deadline:
            raise worker.ProbeError("probe-budget-exhausted")
        if args[:3] == ["ip", "netns", "add"]:
            self.namespace = args[3]
            (self.markers / self.namespace).touch(mode=0o600)
            return self.outcome("namespace-create")
        if args[:3] == ["ip", "netns", "delete"]:
            assert args[3] == self.namespace
            (self.markers / self.namespace).unlink()
            self.events.append("namespace-removed")
            return 0, b""
        if args[:2] == ["awg-quick", "strip"]:
            path = Path(args[2])
            assert path.stat().st_mode & 0o777 == 0o600
            return self.outcome("config-strip", path.read_bytes())
        if args[:2] == ["awg", "show"] and args[-1] == "listen-port":
            assert args[2] == self.interface and self.location == "host"
            self.reads += 1
            self.events.append("uapi-read")
            reply = self.replies[min(self.reads - 1, len(self.replies) - 1)]
            self.fresh = (reply[0] == 0 and re.fullmatch(rb"(?:0|[1-9][0-9]{0,4})\n", reply[1]) is not None
                          and int(reply[1]) <= 65535)
            self.elapsed += self.read_seconds
            if self.deadline is not None and self.elapsed >= self.deadline:
                raise worker.ProbeError("runtime-command-timeout")
            return reply
        if args[:2] == ["awg", "setconf"]:
            assert args[2:] == [self.interface, "/dev/stdin"]
            self.setconf_calls += 1
            self.events.append("setconf")
            assert data == b"[Interface]\nPrivateKey = portable-private-canary\n"
            code, output = self.outcome("configure")
            return (code or self.setconf_status if self.fresh else 1), output
        if args[:3] == ["ip", "link", "set"] and "netns" in args:
            assert self.fresh and self.setconf_calls == 1
            result = self.outcome("namespace-move")
            if not result[0] or self.moved_before_failure:
                self.location = "namespace"
            return result
        if args[-1] == "latest-handshakes":
            return self.outcome("handshake-read", f"portable-peer {int(time.time())}\n".encode())
        if args[0] == "ip":
            offset = 3 if args[1:2] == ["-n"] else 1
            operation = args[offset:]
            queried_location = "namespace" if offset == 3 else "host"
            if operation[:2] == ["link", "show"]:
                self.events.append("link-observed")
                return (0 if self.location == queried_location else 1), b""
            if operation[:2] == ["link", "delete"]:
                assert self.stopped and self.location == queried_location
                self.events.append("interface-removed")
                if self.cleanup_failure:
                    return 1, b""
                self.location = None
                return 0, b""
            if self.fresh and self.location == "namespace":
                if operation == ["link", "set", "lo", "up"]:
                    return self.outcome("loopback")
                if operation[:2] == ["address", "add"]:
                    return self.outcome("address")
                if operation[:2] == ["link", "set"] and "mtu" in operation:
                    return self.outcome("interface-up")
                if operation[:3] in (["-4", "route", "add"], ["-6", "route", "add"]):
                    return self.outcome("route")
        raise AssertionError("unexpected portable AWG command")

    def http(self, _control, _timeout, _directory, *, namespace):
        assert self.fresh and self.setconf_calls == 1 and namespace == self.namespace
        self.http_calls += 1
        return {"accepted": True, "exit": 0, "elapsed": 0.01}

    def run(self):
        profile = {"config": {
            "text": "[Interface]\nPrivateKey = portable-private-canary\n",
            "addresses": ["192.0.2.2/32", "2001:db8::2/128"],
            "dns": ["192.0.2.53"], "mtu": 1280,
        }}
        return self.awg(profile, {}, 5, self.directory)

    def assert_reclaimed(self):
        assert self.stopped
        assert not self.location
        assert not list(self.directory.iterdir())
        assert not list(self.markers.iterdir())
        assert not self.namespace_root.exists() or not list(self.namespace_root.iterdir())


@pytest.mark.parametrize("port", [b"0\n", b"59390\n", b"65535\n"])
def test_visible_tun_waits_for_fresh_uapi_before_one_configuration(tmp_path, monkeypatch, port):
    runtime = AwgHarness(tmp_path, monkeypatch, replies=[(1, b""), (1, b""), (0, port)])
    result = runtime.run()
    assert runtime.reads == 3
    assert runtime.setconf_calls == runtime.http_calls == 1
    assert runtime.events.index("tun-visible") < runtime.events.index("uapi-read")
    assert runtime.events.index("setconf") > max(i for i, event in enumerate(runtime.events) if event == "uapi-read")
    assert result["accepted"] and result["fresh_handshake"] and result["cleanup_ok"]
    runtime.assert_reclaimed()


@pytest.mark.parametrize("dead_after_reads", [0, 1])
def test_exited_owned_daemon_never_receives_configuration(tmp_path, monkeypatch, dead_after_reads):
    runtime = AwgHarness(tmp_path, monkeypatch, replies=[(1, b"")], dead_after_reads=dead_after_reads)
    with pytest.raises(worker.ProbeError, match="awg-client-exited"):
        runtime.run()
    assert runtime.setconf_calls == runtime.http_calls == 0
    runtime.assert_reclaimed()


def test_uapi_readiness_timeout_never_mutates_and_is_bounded(tmp_path, monkeypatch):
    runtime = AwgHarness(tmp_path, monkeypatch, replies=[(1, b"")])
    with pytest.raises(worker.ProbeError):
        runtime.run()
    assert runtime.reads > 1
    assert runtime.setconf_calls == runtime.http_calls == 0
    assert 5 <= runtime.elapsed < 5.2
    runtime.assert_reclaimed()


@pytest.mark.parametrize("output", [
    b"", b"0", b"65536\n", b"01\n", b"+1\n", b"-1\n", b"x\n",
    b"0\nextra\n", b"private-output-canary",
])
def test_noncanonical_fresh_uapi_response_never_mutates_or_leaks(tmp_path, monkeypatch, output):
    runtime = AwgHarness(tmp_path, monkeypatch, replies=[(0, output)])
    with pytest.raises(worker.ProbeError) as failure:
        runtime.run()
    assert runtime.reads >= 1
    assert runtime.setconf_calls == runtime.http_calls == 0
    assert "private-" not in str(failure.value)
    runtime.assert_reclaimed()


def test_configuration_failure_is_one_attempt_after_uapi_readiness(tmp_path, monkeypatch):
    runtime = AwgHarness(tmp_path, monkeypatch, setconf_status=2)
    with pytest.raises(worker.ProbeError):
        runtime.run()
    assert runtime.reads == runtime.setconf_calls == 1
    assert runtime.http_calls == 0
    runtime.assert_reclaimed()


def test_failed_owned_interface_cleanup_cannot_report_success(tmp_path, monkeypatch):
    runtime = AwgHarness(tmp_path, monkeypatch, cleanup_failure=True)
    with pytest.raises(worker.ProbeError, match="cleanup-failed"):
        runtime.run()
    assert runtime.reads == runtime.setconf_calls == runtime.http_calls == 1
    assert runtime.stopped and runtime.location == "namespace"
    assert not list(runtime.directory.iterdir())
    assert not list(runtime.markers.iterdir())
    assert not list(runtime.namespace_root.iterdir())


@pytest.mark.parametrize("phase,moved", [
    ("namespace-create", False), ("config-strip", False), ("configure", False),
    ("namespace-move", False), ("namespace-move", True), ("loopback", False),
    ("address", False), ("interface-up", False), ("route", False), ("handshake-read", False),
])
def test_setup_phase_failure_is_fixed_private_and_reclaims_resources(tmp_path, monkeypatch, phase, moved):
    runtime = AwgHarness(tmp_path, monkeypatch, fault=phase, moved_before_failure=moved)
    with pytest.raises(worker.ProbeError) as failure:
        runtime.run()
    assert str(failure.value) == "awg-" + phase + "-failed"
    assert "private-" not in str(failure.value)
    assert runtime.phases.count(phase) == 1
    assert runtime.setconf_calls == (0 if phase in {"namespace-create", "config-strip"} else 1)
    assert runtime.http_calls == (1 if phase == "handshake-read" else 0)
    runtime.assert_reclaimed()


def test_successful_uapi_reply_after_startup_deadline_never_mutates(tmp_path, monkeypatch):
    runtime = AwgHarness(tmp_path, monkeypatch, read_seconds=5.1)
    with pytest.raises(worker.ProbeError, match="awg-client-start-timeout"):
        runtime.run()
    assert runtime.reads == 1
    assert runtime.setconf_calls == runtime.http_calls == 0
    runtime.assert_reclaimed()


def test_readiness_preserves_existing_probe_deadline_and_independent_cleanup(tmp_path, monkeypatch):
    runtime = AwgHarness(tmp_path, monkeypatch, replies=[(1, b"")], read_seconds=0.1)
    runtime.deadline = 0.25
    with pytest.raises(worker.ProbeError, match="runtime-command-timeout|probe-budget-exhausted"):
        runtime.run()
    assert runtime.deadline == 0.25
    assert runtime.elapsed < 0.5
    assert runtime.setconf_calls == runtime.http_calls == 0
    assert 0.25 in runtime.command_deadlines and runtime.command_deadlines[-1] is None
    runtime.assert_reclaimed()
