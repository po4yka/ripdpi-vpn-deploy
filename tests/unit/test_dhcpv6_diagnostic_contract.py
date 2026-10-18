"""Public native diagnostics admit fixed synthetic values, never raw log text."""

import ast
import importlib.util
import json
import os
from pathlib import Path
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "dhcpv6_diagnostic_runner", ROOT / "tests/native/transport_acceptance/runner.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def record():
    return {
        "probe_id": "multicast-request", "phase": "packet", "ready_ms": 1,
        "send_ms": 2, "elapsed_ms": 703, "receiver_member": True,
        "packet_received": False, "output_before": 1, "output_after": 1,
        "input_before": 0, "input_after": 0, "udp_errors": 0, "udp_checksum_errors": 0,
        "udp_no_ports": 0, "udp_ignored_multicast": 0,
    }


def extract(tmp_path, body):
    log = tmp_path / "private.log"
    log.write_bytes(body)
    return runner.dhcpv6_diagnostics(log)


def encoded(value):
    return (runner.DHCPV6_DIAGNOSTIC_PREFIX + json.dumps(value) + "\n").encode()


def test_fixed_record_survives_private_surrounding_output(tmp_path):
    body = b"private credential must stay private\n" + encoded(record()) + b"private namespace\n"
    assert extract(tmp_path, body) == [record()]
    assert "private" not in json.dumps(extract(tmp_path, body))


@pytest.mark.parametrize("field,value", [
    ("credential", "private-secret"), ("path", "/private/operator"),
    ("address", "2001:db8::1"), ("namespace", "private-node"),
    ("probe_id", "private-secret"), ("phase", "private-secret"),
    ("phase", []), ("phase", {}), ("phase", "send"), ("probe_id", []),
    ("output_before", "private-secret"), ("output_before", -1),
    ("output_before", 65536), ("output_before", 1.5), ("output_before", True),
    ("ready_ms", 30001), ("ready_ms", -1), ("ready_ms", "100"),
    ("receiver_member", 1), ("packet_received", None),
    ("udp_errors", "private-secret"), ("udp_checksum_errors", -1),
    ("udp_no_ports", "private-secret"), ("udp_ignored_multicast", True),
])
def test_untrusted_field_or_value_refuses_whole_record(tmp_path, field, value):
    value_record = record()
    value_record[field] = value
    assert extract(tmp_path, encoded(value_record)) == []


@pytest.mark.parametrize("body", [
    b"dhcpv6-observation:broken\n", b"dhcpv6-observation:[]\n",
    b"dhcpv6-observation:\xff\n", b"dhcpv6-observation:" + b"x" * 4096 + b"\n",
    b"untrusted-log-line" * 70000,
])
def test_malformed_or_oversized_input_refuses(tmp_path, body):
    assert extract(tmp_path, body) == []


def test_duplicate_probe_or_json_field_refuses(tmp_path):
    assert extract(tmp_path, encoded(record()) * 2) == []
    duplicate = encoded(record()).replace(b'"phase": "packet"', b'"phase": "private-secret", "phase": "packet"')
    assert extract(tmp_path, duplicate) == []


@pytest.mark.parametrize("field,limit", [
    ("ready_ms", 30000), ("send_ms", 30000), ("elapsed_ms", 30000),
    ("output_before", 65535), ("output_after", 65535), ("input_before", 65535),
    ("input_after", 65535), ("udp_errors", 65535), ("udp_checksum_errors", 65535),
    ("udp_no_ports", 65535), ("udp_ignored_multicast", 65535),
])
def test_each_numeric_bound_is_exact(tmp_path, field, limit):
    value = record()
    value[field] = limit
    assert extract(tmp_path, encoded(value)) == [value]
    value[field] += 1
    assert extract(tmp_path, encoded(value)) == []


def test_observer_is_counter_only_and_keeps_native_packet_matrix():
    tree = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    observer = ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
        and target.id == "MULTICAST_OBSERVER" for target in node.targets)))
    assert all(line.endswith(" counter") for line in observer.splitlines() if line.startswith("add rule"))
    assert not any(word in observer.split() for word in ("accept", "drop", "reject", "policy"))
    native_cases = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name.startswith("test_")]
    assert len(native_cases) == 1
    probes = [node for node in ast.walk(native_cases[0]) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "packet"]
    assert len(probes) == 12
    assert sum(any(key.arg == "observe_multicast" and ast.literal_eval(key.value) is True
                   for key in call.keywords) for call in probes) == 1


def test_failed_suite_publishes_only_validated_observation(tmp_path, monkeypatch):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(runner.sys, "platform", "linux")
    monkeypatch.setattr(runner.os, "geteuid", lambda: 0)
    monkeypatch.setenv("TRANSPORT_NATIVE_ISOLATED", "1")
    monkeypatch.setenv("TRANSPORT_NATIVE_EVIDENCE", str(output))
    monkeypatch.setattr(runner, "preflight", lambda evidence: {})
    monkeypatch.setattr(runner, "suite_commands", lambda plan: [("hopping", [], [])])
    original_temporary = runner.tempfile.TemporaryDirectory
    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", lambda **kwargs: original_temporary(dir=tmp_path))

    def execute(argv, **kwargs):
        kwargs["stdout"].write(b"private credential\n" + encoded(record()))
        report = Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--junitxml=")))
        report.write_text('<testsuite><testcase classname="native" name="probe"><failure>synthetic failure</failure></testcase></testsuite>')
        return types.SimpleNamespace(returncode=1)

    monkeypatch.setattr(runner.subprocess, "run", execute)

    def finish(evidence, before, destination):
        evidence["cleanup"] = True
        runner.publish(evidence, destination)

    monkeypatch.setattr(runner, "finish", finish)
    previous_umask = os.umask(0o077)
    try:
        with pytest.raises(RuntimeError, match="native-suite-failed:hopping"):
            runner.main()
    finally:
        os.umask(previous_umask)
    evidence = json.loads(output.read_text())
    assert evidence["dhcpv6_diagnostics"] == [record()]
    assert evidence["success"] is False
    assert "private" not in output.read_text()


@pytest.mark.parametrize("stage", ["install", "stats", "membership", "counters", "cleanup"])
@pytest.mark.parametrize("outcome", ["absent", "received", "send-error"])
def test_observation_failure_preserves_actual_packet_outcome(stage, outcome, capsys):
    """Execute the actual controller with injected observer failures; no native claim."""
    import io
    import subprocess
    import sys
    import time

    source = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    selected = [node for node in source.body
                if (isinstance(node, ast.FunctionDef) and node.name in {
                    "packet", "multicast_counters", "multicast_udp_errors"})
                or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                    and target.id in {"MULTICAST_OBSERVER", "RECEIVER", "SENDER"}
                    for target in node.targets))]
    namespace = {"json": json, "sys": sys, "time": time}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "retained-native-controller", "exec"), namespace)

    events = []

    class Ready(io.StringIO):
        def readline(self):
            events.append("ready")
            return super().readline()

    class Listener:
        stdout = Ready("ready\n")
        returncode = 0

        def poll(self):
            return 0

        def communicate(self, input, timeout):
            assert input == "send-complete\n" and timeout == 3
            received = ["dhcpv6-regression", "::1", 547] if outcome == "received" else None
            marker = "dhcpv6-membership:unknown" if stage == "membership" else "dhcpv6-membership:yes"
            return json.dumps(received), marker

    namespace["subprocess"] = types.SimpleNamespace(
        Popen=lambda *args, **kwargs: events.append("listener") or Listener(), PIPE=subprocess.PIPE,
        SubprocessError=subprocess.SubprocessError,
    )
    namespace["select"] = types.SimpleNamespace(select=lambda *args: ([Listener.stdout], [], []))

    def run(*args, **kwargs):
        events.append("send" if "-c" in args else "udp-baseline" if "/proc/net/snmp6" in args else "observer")
        if "-c" in args and outcome == "send-error":
            raise subprocess.CalledProcessError(1, ["synthetic-sender"])
        if (stage == "install" and kwargs.get("data")) or (stage == "cleanup" and "delete" in args):
            raise RuntimeError("private-observer-error")
        return ""

    def counters(_namespace):
        if stage == "counters":
            raise RuntimeError("private-observer-error")
        return {"before": 1, "after": 1}

    def errors(_namespace):
        events.append("udp-baseline")
        if stage == "stats":
            raise RuntimeError("private-observer-error")
        return {"Udp6InErrors": 0, "Udp6InCsumErrors": 0, "Udp6NoPorts": 0, "Udp6IgnoredMulti": 0}

    metric_getter = namespace["multicast_udp_errors"]
    namespace.update(run=run, multicast_counters=counters,
                     multicast_udp_errors=metric_getter if stage == "stats" else errors)
    if outcome == "send-error":
        with pytest.raises(AssertionError, match="dhcpv6-send-result-refused"):
            namespace["packet"]("sender", "receiver", observe_multicast=True)
    else:
        received = namespace["packet"]("sender", "receiver", observe_multicast=True)
        assert (received is not None) is (outcome == "received")
    assert events[events.index("ready") + 1] == "send", "observer-command-between-ready-and-send"
    if stage != "install":
        assert events.index("udp-baseline") < events.index("listener")
    output = capsys.readouterr().out
    assert "private-observer-error" not in output
    if (stage, outcome) not in {("counters", "send-error"), ("membership", "send-error"), ("membership", "absent"), ("membership", "received")}:
        assert "dhcpv6-observation-unavailable" in output or "dhcpv6-observation-cleanup-unavailable" in output
    if stage != "cleanup" or outcome == "send-error":
        assert "dhcpv6-observation:" not in output


def test_unavailable_private_log_does_not_replace_native_failure():
    class Unreadable:
        def open(self, mode):
            raise PermissionError("private-log-path")

    assert runner.dhcpv6_diagnostics(Unreadable()) == []


@pytest.mark.parametrize("missing", [None, "Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti"])
def test_missing_udp_metric_cannot_be_published_as_zero(missing):
    metrics = {"Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti"}
    body = "" if missing is None else "".join(key + " 0\n" for key in metrics - {missing})
    tree = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    getter = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "multicast_udp_errors")
    namespace = {"run": lambda *args: body}
    exec(compile(ast.Module(body=[getter], type_ignores=[]), "retained-metric-getter", "exec"), namespace)
    with pytest.raises(ValueError, match="dhcpv6-observation-metric-unavailable"):
        namespace["multicast_udp_errors"]("owned")


def test_all_measured_zero_udp_metrics_remain_valid():
    metrics = {"Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti"}
    tree = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    getter = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "multicast_udp_errors")
    namespace = {"run": lambda *args: "".join(key + " 0\n" for key in metrics) + "Ip6InMcastPkts 3\n"}
    exec(compile(ast.Module(body=[getter], type_ignores=[]), "retained-metric-getter", "exec"), namespace)
    assert namespace["multicast_udp_errors"]("owned") == dict.fromkeys(metrics, 0)
