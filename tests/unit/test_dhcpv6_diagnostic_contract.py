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
        "postrouting_after": 11, "prerouting_before": 13,
        "prerouting_after": 17, "ingress_expected": True,
        "ipv6_no_routes": 19, "ipv6_multicast": 23, "ipv6_discards": 29,
        "ipv6_address_errors": 31, "ipv6_delivers": 37, "local_multicast_routes": None,
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
    *[(field, value) for field in ("postrouting_after", "prerouting_before", "prerouting_after",
                                  "ipv6_no_routes", "ipv6_multicast", "ipv6_discards",
                                  "ipv6_address_errors", "ipv6_delivers")
      for value in (None, True, 1.5, "private-secret", -1, 65536)],
    ("ingress_expected", 1), ("ingress_expected", None), ("ingress_expected", "private-canary"),
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


@pytest.mark.parametrize("field", ["postrouting_after", "prerouting_before", "prerouting_after",
                                 "ingress_expected", "ipv6_no_routes", "ipv6_multicast", "ipv6_discards",
                                 "ipv6_address_errors", "ipv6_delivers", "local_multicast_routes"])
def test_missing_or_duplicate_transit_counter_refuses(tmp_path, field):
    missing = record()
    del missing[field]
    assert extract(tmp_path, encoded(missing)) == []
    duplicate = encoded(record()).replace(b'{', ('{"' + field + '": 0,').encode(), 1)
    assert extract(tmp_path, duplicate) == []


@pytest.mark.parametrize("field,limit", [
    ("ready_ms", 30000), ("send_ms", 30000), ("elapsed_ms", 30000),
    ("output_before", 65535), ("output_after", 65535), ("input_before", 65535),
    ("input_after", 65535), ("udp_errors", 65535), ("udp_checksum_errors", 65535),
    ("udp_no_ports", 65535), ("udp_ignored_multicast", 65535),
    ("postrouting_after", 65535), ("prerouting_before", 65535),
    ("prerouting_after", 65535), ("ipv6_no_routes", 65535), ("ipv6_multicast", 65535),
    ("ipv6_discards", 65535), ("ipv6_address_errors", 65535), ("ipv6_delivers", 65535),
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
    receiver_observer = ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
        and target.id == "MULTICAST_RECEIVER_OBSERVER" for target in node.targets)))
    assert "transit_after { type filter hook prerouting priority 301; }" in receiver_observer
    assert "expected_iif { type filter hook prerouting priority -301; }" in receiver_observer
    assert 'expected_iif iifname "peer0" ip6 saddr fe80::10 ip6 daddr ff02::1:2 udp sport 546 udp dport 547 counter' in receiver_observer
    assert not any(word in receiver_observer.split() for word in ("accept", "drop", "reject", "policy"))
    assert all(line.endswith(" counter") for line in receiver_observer.splitlines() if line.startswith("add rule"))
    for hook, transit, priority in (("output", "postrouting", 301), ("input", "prerouting", -301)):
        installed = observer % (hook, hook, transit, priority)
        assert "add chain inet dhcpv6_probe transit { type filter hook " + transit + " priority " + str(priority) + "; }" in installed
        rules = [line for line in installed.splitlines() if line.startswith("add rule")]
        assert len(rules) == 3
        assert all(line.endswith("ip6 saddr fe80::10 ip6 daddr ff02::1:2 udp sport 546 udp dport 547 counter") for line in rules)
    native_cases = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name.startswith("test_")]
    assert {node.name for node in native_cases} == {
        "test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server",
        "test_native_established_dhcpv6_tuple_cannot_cross_uplink_scope",
    }
    original = next(node for node in native_cases if node.name == "test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server")
    probes = [node for node in ast.walk(original) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "packet"]
    assert len(probes) == 12
    assert sum(any(key.arg == "observe_multicast" and ast.literal_eval(key.value) is True
                   for key in call.keywords) for call in probes) == 1
    established = next(node for node in native_cases if node.name == "test_native_established_dhcpv6_tuple_cannot_cross_uplink_scope")
    warm_probes = [node for node in ast.walk(established) if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name) and node.func.id == "packet"]
    assert len(warm_probes) == 6
    assert sum(any(key.arg == "expected_output_deny" and ast.literal_eval(key.value) is True
                   for key in call.keywords) for call in warm_probes) == 2


def test_failed_suite_publishes_only_validated_observation(tmp_path, monkeypatch):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(runner.sys, "platform", "linux")
    monkeypatch.setattr(runner.os, "geteuid", lambda: 0)
    monkeypatch.setenv("TRANSPORT_NATIVE_ISOLATED", "1")
    monkeypatch.setenv("TRANSPORT_NATIVE_EVIDENCE", str(output))
    # This isolated controller fixture tests hopping observation publication;
    # the core's separate early DHCP gate has its own complete regressions.
    monkeypatch.setenv("TRANSPORT_NATIVE_PLAN", "recovery-1")
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
    assert "route_diagnostic" not in evidence
    assert "private" not in output.read_text()


@pytest.mark.parametrize("stage", [
    "measured", "install", "stats", "membership", "counters", "postrouting", "prerouting",
    "prerouting-late", "expected-iif", "other-iif", "bad-iif", "iif-bool", "iif-float",
    "metric-reset", "route-error", "cleanup",
])
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
                    and target.id in {"MULTICAST_OBSERVER", "MULTICAST_RECEIVER_OBSERVER", "RECEIVER", "SENDER"}
                    for target in node.targets))]
    namespace = {"json": json, "sys": sys, "time": time}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "retained-native-controller", "exec"), namespace)

    events = []
    queries = []
    installs = []
    route_reads = []
    metrics = {"Udp6InErrors": "udp_errors", "Udp6InCsumErrors": "udp_checksum_errors",
               "Udp6NoPorts": "udp_no_ports", "Udp6IgnoredMulti": "udp_ignored_multicast",
               "Ip6InNoRoutes": "ipv6_no_routes", "Ip6InMcastPkts": "ipv6_multicast",
               "Ip6InDiscards": "ipv6_discards", "Ip6InAddrErrors": "ipv6_address_errors",
               "Ip6InDelivers": "ipv6_delivers"}
    metric_reads = []

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
        if kwargs.get("data"):
            installs.append(kwargs["data"])
        if "/proc/net/snmp6" in args:
            metric_reads.append(args)
            if stage == "stats":
                return ""
            return "".join(key + " " + str(99 if stage == "metric-reset" and len(metric_reads) == 2 else
                                           100 + (record()[field] if len(metric_reads) == 2 else 0)) + "\n"
                           for key, field in metrics.items())
        if "list" in args:
            assert "send" in events, "counter-query-before-original-send"
            queries.append(args)
            if stage == "counters":
                raise RuntimeError("private-observer-error")
            counts = ({"before": 2, "after": 3, "transit": 11} if args[3] == "sender"
                      else {"before": 5, "after": 7, "transit": 13, "transit_after": 17, "expected_iif": 1})
            if ((stage == "postrouting" and args[3] == "sender")
                    or (stage == "prerouting" and args[3] == "receiver")):
                del counts["transit"]
            if args[3] == "receiver" and stage in {"prerouting-late", "expected-iif"}:
                del counts["transit_after" if stage == "prerouting-late" else "expected_iif"]
            if args[3] == "receiver" and stage in {"other-iif", "bad-iif"}:
                counts["expected_iif"] = 0 if stage == "other-iif" else 14
            if args[3] == "receiver" and stage in {"iif-bool", "iif-float"}:
                counts["expected_iif"] = True if stage == "iif-bool" else 0.5
            return json.dumps({"nftables": [{"rule": {"chain": chain,
                "expr": [{"counter": {"packets": count}}]}} for chain, count in counts.items()]})
        return ""

    route_projection = dict(peer_present=True, peer_multicast=True, peer_linkdown=False,
                            other_present=True, other_multicast=True, other_linkdown=False)

    def routes(_namespace):
        route_reads.append(_namespace)
        assert events.count("send") == 1 and len(queries) == len(metric_reads) == 2
        if stage == "route-error":
            raise RuntimeError("private-route-error")
        return route_projection

    namespace.update(run=run, multicast_local_routes=routes)
    if outcome == "send-error":
        with pytest.raises(AssertionError, match="dhcpv6-send-result-refused"):
            namespace["packet"]("sender", "receiver", observe_multicast=True)
    else:
        received = namespace["packet"]("sender", "receiver", observe_multicast=True)
        assert (received is not None) is (outcome == "received")
    assert events[events.index("ready") + 1] == "send", "observer-command-between-ready-and-send"
    assert events.count("send") == 1
    if stage != "install":
        assert events.index("udp-baseline") < events.index("listener")
    output = capsys.readouterr().out
    assert "private-observer-error" not in output
    if stage not in {"measured", "route-error", "other-iif"} and (stage, outcome) not in {
        ("counters", "send-error"), ("postrouting", "send-error"), ("prerouting", "send-error"),
        ("prerouting-late", "send-error"), ("expected-iif", "send-error"),
        ("bad-iif", "send-error"), ("metric-reset", "send-error"),
        ("iif-bool", "send-error"), ("iif-float", "send-error"),
        ("membership", "send-error"), ("membership", "absent"), ("membership", "received"),
    }:
        assert "dhcpv6-observation-unavailable" in output or "dhcpv6-observation-cleanup-unavailable" in output
    if stage not in {"measured", "cleanup", "route-error", "other-iif"} or outcome == "send-error":
        assert "dhcpv6-observation:" not in output
    else:
        observation, = [json.loads(line.split(":", 1)[1]) for line in output.splitlines()
                        if line.startswith(runner.DHCPV6_DIAGNOSTIC_PREFIX)]
        assert {field: observation[field] for field in (
            "output_before", "output_after", "postrouting_after", "prerouting_before", "input_before", "input_after"
        )} == {"output_before": 2, "output_after": 3, "postrouting_after": 11,
              "prerouting_before": 13, "input_before": 5, "input_after": 7}
        assert observation["packet_received"] is (outcome == "received")
        assert observation["prerouting_after"] == 17 and observation["ingress_expected"] is (stage != "other-iif")
        assert all(observation[field] == record()[field] for field in metrics.values())
        assert route_reads == (["receiver"] if outcome == "absent" else [])
        assert observation["local_multicast_routes"] == (route_projection if outcome == "absent" and stage != "route-error" else None)
        assert len(installs) == len(queries) == 2
        log = types.SimpleNamespace(open=lambda _mode: io.BytesIO(output.encode()))
        assert runner.dhcpv6_diagnostics(log) == [observation]


def test_unavailable_private_log_does_not_replace_native_failure():
    class Unreadable:
        def open(self, mode):
            raise PermissionError("private-log-path")

    assert runner.dhcpv6_diagnostics(Unreadable()) == []


@pytest.mark.parametrize("missing", [None, "Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti",
                                    "Ip6InNoRoutes", "Ip6InMcastPkts", "Ip6InDiscards", "Ip6InAddrErrors", "Ip6InDelivers"])
def test_missing_udp_metric_cannot_be_published_as_zero(missing):
    metrics = {"Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti",
               "Ip6InNoRoutes", "Ip6InMcastPkts", "Ip6InDiscards", "Ip6InAddrErrors", "Ip6InDelivers"}
    body = "" if missing is None else "".join(key + " 0\n" for key in metrics - {missing})
    tree = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    getter = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "multicast_udp_errors")
    namespace = {"run": lambda *args: body}
    exec(compile(ast.Module(body=[getter], type_ignores=[]), "retained-metric-getter", "exec"), namespace)
    with pytest.raises(ValueError, match="dhcpv6-observation-metric-unavailable"):
        namespace["multicast_udp_errors"]("owned")


def test_all_measured_zero_udp_metrics_remain_valid():
    metrics = {"Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti",
               "Ip6InNoRoutes", "Ip6InMcastPkts", "Ip6InDiscards", "Ip6InAddrErrors", "Ip6InDelivers"}
    tree = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    getter = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "multicast_udp_errors")
    namespace = {"run": lambda *args: "".join(key + " 0\n" for key in metrics) + "Ip6InReceives 3\n"}
    exec(compile(ast.Module(body=[getter], type_ignores=[]), "retained-metric-getter", "exec"), namespace)
    assert namespace["multicast_udp_errors"]("owned") == dict.fromkeys(metrics, 0)


@pytest.mark.parametrize("metric", ["Ip6InNoRoutes", "Ip6InMcastPkts", "Ip6InDiscards", "Ip6InAddrErrors", "Ip6InDelivers"])
@pytest.mark.parametrize("invalid", ["duplicate", "negative", "malformed"])
def test_ipv6_metric_is_explicit_and_unique(metric, invalid):
    tree = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    getter = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "multicast_udp_errors")
    keys = {"Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti",
            "Ip6InNoRoutes", "Ip6InMcastPkts", "Ip6InDiscards", "Ip6InAddrErrors", "Ip6InDelivers"}
    body = "".join(key + " 0\n" for key in keys - {metric})
    body += (metric + " 0\n") * 2 if invalid == "duplicate" else metric + (" -1\n" if invalid == "negative" else " canary\n")
    namespace = {"run": lambda *args: body}
    exec(compile(ast.Module(body=[getter], type_ignores=[]), "actual-metric-getter", "exec"), namespace)
    with pytest.raises(ValueError):
        namespace["multicast_udp_errors"]("owned")


def route_row(dev="peer0", **changes):
    return dict(dst="ff00::/8", dev=dev, type="multicast", flags=[], **changes)


@pytest.mark.parametrize("routes,received,valid", [
    (None, False, True), (None, True, True),
    ({key: False for key in ("peer_present", "peer_multicast", "peer_linkdown",
                            "other_present", "other_multicast", "other_linkdown")}, False, True),
    ({}, False, False), ({"private": "canary"}, False, False), ([], False, False),
    ({"peer_present": False, "peer_multicast": True, "peer_linkdown": False,
      "other_present": False, "other_multicast": False, "other_linkdown": False}, False, False),
    ({"peer_present": True, "peer_multicast": True, "peer_linkdown": False,
      "other_present": False, "other_multicast": False, "other_linkdown": False}, True, False),
    ({"peer_present": 1, "peer_multicast": True, "peer_linkdown": False,
      "other_present": False, "other_multicast": False, "other_linkdown": False}, False, False),
])
def test_closed_route_supplement_cannot_invent_a_measurement(tmp_path, routes, received, valid):
    value = dict(record(), packet_received=received, local_multicast_routes=routes)
    assert extract(tmp_path, encoded(value)) == ([value] if valid else [])


def test_duplicate_route_projection_key_refuses(tmp_path):
    routes = {prefix + "_" + field: False for prefix in ("peer", "other")
              for field in ("present", "multicast", "linkdown")}
    body = encoded(dict(record(), local_multicast_routes=routes))
    body = body.replace(b'"peer_present": false', b'"peer_present": false, "peer_present": false')
    assert extract(tmp_path, body) == []


@pytest.mark.parametrize("payload,expected", [
    (b'[]', (False, False, False, False, False, False)),
    (b'[]' + b' ' * 4094, (False, False, False, False, False, False)),
    (json.dumps([route_row()]).encode(), (True, True, False, False, False, False)),
    (json.dumps([dict(route_row(), flags=["linkdown"]), route_row("other0")]).encode(),
     (True, True, True, True, True, False)),
    (json.dumps([dict(route_row(), type="unicast")]).encode(), (True, False, False, False, False, False)),
    (json.dumps([dict(route_row(), protocol="private-canary")]).encode(), (True, True, False, False, False, False)),
    *[(json.dumps([dict((key, value) for key, value in route_row().items() if key != missing)]).encode(), None)
      for missing in ("dst", "dev", "type", "flags")],
    *[(json.dumps([dict(route_row(), **{key: value})]).encode(), None)
      for key, value in (("dst", "::/0"), ("dev", "private-canary"), ("type", "private-canary"),
                         ("flags", None), ("flags", ["private-canary"]), ("flags", ["dead", "dead"]),
                         ("flags", [True]), ("flags", {}))],
    (json.dumps([route_row(), route_row()]).encode(), None),
    (json.dumps([route_row()] * 3).encode(), None),
    (b'[{"dst":"ff00::/8","dst":"ff00::/8","dev":"peer0","type":"multicast","flags":[]}]', None),
    (b'{}', None), (b'null', None), (b'[true]', None), (b'\xff', None),
    (b' ' * 4097, None),
], ids=lambda value: "bytes-" + str(len(value)) if isinstance(value, bytes) else None)
def test_route_show_real_child_has_closed_projection(payload, expected, capsys):
    result, children, _elapsed = run_route_child("import os;os.write(1," + repr(payload) + ")")
    if expected is None:
        assert result is None
    else:
        assert set(result) == {prefix + "_" + field for prefix in ("peer", "other")
                               for field in ("present", "multicast", "linkdown")}
        assert tuple(result[key] for key in ("peer_present", "peer_multicast", "peer_linkdown",
                                            "other_present", "other_multicast", "other_linkdown")) == expected
    assert all(child.poll() is not None for child in children)
    assert capsys.readouterr().out == ""


def run_route_child(program, cleanup_error=None):
    """Run the actual bounded accessor against a real portable child, not a network."""
    import select
    import subprocess
    import sys
    import time

    tree = ast.parse((ROOT / "tests/native/transport_acceptance/test_dhcpv6.py").read_text())
    accessor = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "multicast_local_routes")
    children = []

    def spawn(argv, **kwargs):
        assert argv == ["ip", "-n", "owned", "-j", "-6", "route", "show", "table", "local", "exact", "ff00::/8"]
        assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL}
        child = subprocess.Popen([sys.executable, "-c", program], **kwargs)
        children.append(child)
        if cleanup_error:
            def cleanup_refusal():
                assert child.returncode is not None, "cleanup-fixture-child-not-reaped"
                raise (OSError if cleanup_error == "OSError" else subprocess.SubprocessError)("private-cleanup-canary")

            return types.SimpleNamespace(stdout=child.stdout, wait=child.wait, poll=cleanup_refusal,
                                         kill=child.kill, returncode=0)
        return child

    namespace = {"json": json, "os": os, "select": select, "time": time,
                 "subprocess": types.SimpleNamespace(Popen=spawn, PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL,
                                                     SubprocessError=subprocess.SubprocessError)}
    exec(compile(ast.Module(body=[accessor], type_ignores=[]), "actual-route-accessor", "exec"), namespace)
    started = time.monotonic()
    result = namespace["multicast_local_routes"]("owned")
    return result, children, time.monotonic() - started


@pytest.mark.parametrize("program", [
    "import time;time.sleep(3)",
    "import os,time;os.write(1,b' '*4097);time.sleep(3)",
    "import sys;print('[]');print('private-canary',file=sys.stderr);sys.exit(2)",
], ids=["deadline", "overrun", "nonzero"])
def test_route_show_deadline_overrun_and_nonzero_are_reaped(program, capsys):
    result, children, elapsed = run_route_child(program)
    assert result is None and elapsed < 2
    assert len(children) == 1 and children[0].poll() is not None
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("cleanup_error", ["OSError", "SubprocessError"])
@pytest.mark.parametrize("payload,measured", [(b'[]', True), (b'broken', False)])
def test_route_cleanup_failure_keeps_projection_and_closed_marker(cleanup_error, payload, measured, capsys):
    result, children, _elapsed = run_route_child("import os;os.write(1," + repr(payload) + ")", cleanup_error)
    assert result == ({prefix + "_" + field: False for prefix in ("peer", "other")
                       for field in ("present", "multicast", "linkdown")} if measured else None)
    assert len(children) == 1 and children[0].poll() is not None
    captured = capsys.readouterr()
    assert captured.out == "dhcpv6-route-cleanup-unavailable\n" and captured.err == ""
