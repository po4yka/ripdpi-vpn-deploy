"""Bounded controller subprocess I/O; fixtures do not establish live SSH."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module():
    spec = importlib.util.spec_from_file_location("bootstrap_readiness_io", ROOT / "scripts/bootstrap_readiness.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_bounded_input_reaches_child_without_argv_or_environment():
    readiness = module()
    payload = b'{"nonce":"fixture-only"}'
    status, output = readiness.run_command(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        timeout=5, capture=True, input_data=payload,
    )
    assert status == 0 and output == payload


def test_deferred_cancellation_allows_one_cleanup_command():
    readiness = module()
    readiness._cancelled = 15
    with pytest.raises(SystemExit):
        readiness.run_command([sys.executable, "-c", "pass"], timeout=5)
    status, _ = readiness.run_command(
        [sys.executable, "-c", "import sys; sys.exit(0)"], timeout=5, defer_cancellation=True,
    )
    assert status == 0
    readiness._cancelled = 0


def test_input_size_and_type_are_rejected_before_spawn():
    readiness = module()
    for payload in ("not-bytes", b"x" * 65537):
        with pytest.raises(readiness.ReadinessError, match="command input invalid"):
            readiness.run_command([sys.executable, "-c", "pass"], timeout=5, input_data=payload)


@pytest.mark.parametrize('limit,accepted', [(65536, False), (1_049_600, True)])
def test_large_inspection_output_remains_bounded(limit, accepted):
    readiness = module()
    operation = lambda: readiness.run_command(
        [sys.executable, '-c', 'import sys;sys.stdout.write("x"*100000)'],
        timeout=5, capture=True, output_limit=limit)
    if accepted:
        status, output = operation()
        assert status == 0 and len(output) == 100000
    else:
        with pytest.raises(readiness.ReadinessError, match='command output limit'):
            operation()


@pytest.mark.parametrize('limit', [True, 0, -1, 1_049_601])
def test_invalid_output_budget_refuses_before_spawn(limit):
    readiness = module()
    with pytest.raises(readiness.ReadinessError, match='output limit invalid'):
        readiness.run_command(['missing-command'], timeout=5, output_limit=limit)


@pytest.mark.parametrize("state", ["exited", "live", "persistent-refusal"])
def test_permission_cleanup_retries_only_after_owned_child_exit(monkeypatch, state):
    readiness = module()
    real_popen = readiness.subprocess.Popen
    real_killpg = readiness.os.killpg
    children, attempts, cleanup_polls = [], [], []

    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        real_poll = child.poll

        def poll():
            result = real_poll()
            if attempts:
                cleanup_polls.append(result)
            return result

        child.poll = poll
        children.append(child)
        return child

    def signal_group(group, signal):
        child = children[0]
        assert group == child.pid and signal == readiness.signal.SIGKILL
        attempts.append(group)
        if len(attempts) == 1:
            if state != "live":
                child.wait(timeout=5)
            raise PermissionError("fixture signal refused")
        if state == "persistent-refusal":
            raise PermissionError("fixture signal refused again")
        return real_killpg(group, signal)

    monkeypatch.setattr(readiness.subprocess, "Popen", spawn)
    monkeypatch.setattr(readiness.os, "killpg", signal_group)
    program = 'import sys;sys.stdout.write("xx");sys.stdout.flush()'
    if state == "live":
        # This case must prove a denied signal to a live child is not suppressed.
        program += ';import time;time.sleep(30)'
    try:
        expected = readiness.ReadinessError if state == "exited" else PermissionError
        message = "command output limit" if state == "exited" else "fixture signal refused"
        with pytest.raises(expected, match=message):
            readiness.run_command(
                [sys.executable, "-c", program], timeout=5, capture=True,
                output_limit=1,
            )
        assert attempts == [children[0].pid] * (1 if state == "live" else 2)
        assert cleanup_polls == [None if state == "live" else 0]
    finally:
        for child in children:
            try:
                real_killpg(child.pid, readiness.signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                # A completed child's zombie-only group can refuse on Darwin.
                if child.poll() is None:
                    raise
            child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()
