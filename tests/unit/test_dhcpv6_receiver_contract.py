"""Actual loopback UDP proves receiver timing; Linux firewall remains separate."""

import ast
import json
import os
import select
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "tests/native/transport_acceptance/test_dhcpv6.py"


def observation_source():
    tree = ast.parse(NATIVE.read_text())
    source = ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RECEIVER"
                for target in node.targets)))
    # Keep the exact observation protocol after Linux-only bind and group setup.
    # The child gets a real, already-bound IPv6 loopback UDP descriptor instead.
    multicast = next(node for node in ast.parse(source).body
                     if isinstance(node, ast.If)
                     and isinstance(node.test, ast.Compare)
                     and isinstance(node.test.left, ast.Name)
                     and node.test.left.id == "multicast")
    return "\n".join(source.splitlines()[multicast.end_lineno:])


@contextmanager
def receiver():
    with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as bound:
        bound.bind(("::1", 0))
        address = bound.getsockname()
        source = "import json,os,select,socket,sys,time\ns=socket.socket(fileno=int(sys.argv[1]))\n"
        process = subprocess.Popen(
            [sys.executable, "-c", source + observation_source(), str(bound.fileno())],
            pass_fds=(bound.fileno(),), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    try:
        assert select.select([process.stdout], [], [], 3)[0], "receiver-ready-deadline"
        assert process.stdout.readline().strip() == "ready"
        yield process, address
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=3)


@pytest.mark.parametrize("deliver", [False, True])
def test_delayed_sender_cannot_expire_positive_or_negative_observation(deliver):
    with receiver() as (process, address):
        # Deliberately exceed the complete historical 0.7-second observation.
        time.sleep(1.0)
        if deliver:
            with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as sender:
                sender.sendto(b"dhcpv6-regression", address)
        acknowledged = time.monotonic()
        output, error = process.communicate(input="send-complete\n", timeout=3)
        assert process.returncode == 0, error
        packet = json.loads(output)
        if deliver:
            assert packet is not None, "receiver-expired-before-completed-send"
            assert packet[0] == "dhcpv6-regression"
        else:
            assert packet is None
            assert time.monotonic() - acknowledged >= .7, "negative-observation-ended-before-send"


@pytest.mark.parametrize("acknowledgement", ["", "invalid\n"])
def test_missing_or_invalid_send_acknowledgement_refuses(acknowledgement):
    with receiver() as (process, _address):
        output, error = process.communicate(input=acknowledgement, timeout=3)
        assert process.returncode != 0, "unacknowledged-receiver-reported-success"
        assert "dhcpv6-receiver-send-ack" in error
        assert not output.strip()


def admission_branch_source():
    """Execute the actual route admission and guard, without Linux socket setup."""
    tree = ast.parse(NATIVE.read_text())
    source = ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RECEIVER"
                for target in node.targets)))
    receiver_tree = ast.parse(source)
    helper = next(node for node in receiver_tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "admit_multicast_input_route")
    group = next(node for node in receiver_tree.body if isinstance(node, ast.If)
                 and isinstance(node.test, ast.Compare)
                 and isinstance(node.test.left, ast.Name) and node.test.left.id == "multicast")
    admission = next(node for node in group.body if isinstance(node, ast.Expr)
                     and isinstance(node.value, ast.Call)
                     and isinstance(node.value.func, ast.Name)
                     and node.value.func.id == helper.name)
    ready = next(node for node in receiver_tree.body if isinstance(node, ast.Expr)
                 and isinstance(node.value, ast.Call) and node.value.args
                 and isinstance(node.value.args[0], ast.Constant)
                 and node.value.args[0].value == "ready")
    assert admission.lineno < ready.lineno
    branch = ast.If(test=group.test, body=[admission], orelse=[])
    helpers = [node for node in receiver_tree.body if isinstance(node, ast.FunctionDef)
               or isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                   and target.id == "readiness_reported" for target in node.targets)]
    program = ast.fix_missing_locations(ast.Module(body=[*helpers, branch, ready], type_ignores=[]))
    return "import json,os,select,sys\ninterface,multicast=sys.argv[1:]\n" + ast.unparse(program)


def input_route():
    return [{"type": "multicast", "dev": "peer0", "iif": "peer0", "table": "local",
             "dst": "ff02::1:2", "from": "fe80::10"}]


def execute_input_admission(tmp_path, body, *, multicast="yes", available=True):
    executable = tmp_path / "ip"
    pid_file, argv_file = tmp_path / "child.pid", tmp_path / "argv.json"
    executable.write_text(
        "#!" + sys.executable + "\nimport json,os,sys,time\n"
        + "open(" + repr(str(pid_file)) + ", 'w').write(str(os.getpid()))\n"
        + "open(" + repr(str(argv_file)) + ", 'w').write(json.dumps(sys.argv[1:]))\n"
        + body + "\n"
    )
    executable.chmod(0o700)
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", admission_branch_source(), "peer0", multicast],
        check=False, capture_output=True, text=True, timeout=5,
        env={**os.environ, "PATH": str(tmp_path) if available else ""},
    )
    assert time.monotonic() - started < 3, "input-route-admission-exceeded-ready-bound"
    if pid_file.exists():
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
    if result.returncode:
        assert result.stdout == ""
        assert result.stderr.splitlines()[-1] == "dhcpv6-input-fib-refused"
        assert sum(line.startswith("dhcpv6-readiness:") for line in result.stderr.splitlines()) == 1
    return result, json.loads(argv_file.read_text()) if argv_file.exists() else None


def test_input_route_admission_uses_exact_flow_before_readiness(tmp_path):
    result, arguments = execute_input_admission(tmp_path, "print(" + repr(json.dumps(input_route())) + ")")
    assert result.returncode == 0 and result.stdout == "ready\n" and result.stderr == ""
    assert arguments == ["-j", "-6", "route", "get", "ff02::1:2", "from", "fe80::10",
                         "iif", "peer0", "ipproto", "udp", "sport", "546", "dport", "547"]


@pytest.mark.parametrize("field,value", [
    ("type", "local"), ("type", "unreachable"), ("type", True),
    ("dev", "other0"), ("iif", "other0"), ("table", "main"),
    ("dst", "ff02::2"), ("from", "fe80::30"),
])
def test_input_route_wrong_authority_refuses_readiness(tmp_path, field, value):
    route = input_route()
    route[0][field] = value
    result, _ = execute_input_admission(tmp_path, "print(" + repr(json.dumps(route)) + ")")
    assert result.returncode != 0


@pytest.mark.parametrize("document", ["private-secret", "[]", "{}", "[1]", "null"])
def test_input_route_malformed_document_refuses_readiness(tmp_path, document):
    result, _ = execute_input_admission(tmp_path, "print(" + repr(document) + ")")
    assert result.returncode != 0


def test_input_route_multiple_results_refuse_readiness(tmp_path):
    result, _ = execute_input_admission(tmp_path, "print(" + repr(json.dumps(input_route() * 2)) + ")")
    assert result.returncode != 0


def test_input_route_command_failure_keeps_stderr_private(tmp_path):
    result, _ = execute_input_admission(tmp_path, "sys.stderr.write('private-secret');sys.exit(2)")
    assert result.returncode != 0


def test_input_route_missing_command_refuses_readiness(tmp_path):
    result, arguments = execute_input_admission(tmp_path, "pass", available=False)
    assert result.returncode != 0 and arguments is None


@pytest.mark.parametrize("size,accepted", [(4096, True), (4097, False)])
def test_input_route_stdout_cap_is_exact(tmp_path, size, accepted):
    document = json.dumps(input_route())
    body = document + " " * (size - len(document))
    result, _ = execute_input_admission(tmp_path, "os.write(1," + repr(body.encode()) + ")")
    assert (result.returncode == 0) is accepted


@pytest.mark.parametrize("body", [
    "time.sleep(10)", "os.write(1,b'x'*1000000);time.sleep(10)",
    "while True:os.write(1,b'x'*1024)",
])
def test_input_route_timeout_or_unbounded_writer_is_stopped_and_reaped(tmp_path, body):
    result, _ = execute_input_admission(tmp_path, body)
    assert result.returncode != 0


def test_unicast_readiness_does_not_execute_input_route_admission(tmp_path):
    result, arguments = execute_input_admission(tmp_path, "raise RuntimeError('unexpected lookup')", multicast="no")
    assert result.returncode == 0 and result.stdout == "ready\n"
    assert arguments is None
