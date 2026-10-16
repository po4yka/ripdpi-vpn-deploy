"""Bounded controller subprocess I/O; fixtures do not establish live SSH."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
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


@pytest.mark.parametrize("capture", [False, True])
def test_process_group_owner_is_not_reaped_before_cleanup(monkeypatch, capture):
    readiness = module()
    real_popen, real_killpg = readiness.subprocess.Popen, readiness.os.killpg
    children, signals = [], []

    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    def signal_group(group, sig):
        assert group == children[0].pid
        assert children[0].returncode is None, "process-group ownership was released before signalling"
        signals.append(group)
        return real_killpg(group, sig)

    monkeypatch.setattr(readiness.subprocess, "Popen", spawn)
    monkeypatch.setattr(readiness.os, "killpg", signal_group)
    try:
        status, output = readiness.run_command(
            [sys.executable, "-c", "import sys;sys.stdout.write('done');sys.exit(7)"],
            timeout=5, capture=capture,
        )
        assert status == 7 and output == (b"done" if capture else b"")
        assert signals == [children[0].pid]
        assert children[0].returncode is not None
    finally:
        for child in children:
            if child.returncode is None:
                child.kill()
            child.wait(timeout=5)
            for stream in (child.stdout, child.stderr):
                if stream is not None:
                    stream.close()


def descendant_program(marker, *, wait):
    stop = marker.with_suffix(".stop")
    release = marker.with_suffix(".release")
    loop = (f"import pathlib,time; deadline=time.monotonic()+60\n"
            f"while time.monotonic()<deadline and not pathlib.Path({str(stop)!r}).exists(): time.sleep(0.01)\n")
    command_wait = (
        "import time; deadline=time.monotonic()+60\n"
        f"while time.monotonic()<deadline and not pathlib.Path({str(stop)!r}).exists() "
        f"and not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
    )
    program = (
        "import json,os,pathlib,subprocess,sys\n"
        f"child=subprocess.Popen([sys.executable,'-c',{loop!r}], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"pathlib.Path({str(marker)!r}).write_text(json.dumps([os.getpid(),os.getppid(),child.pid]))\n"
        + (command_wait if wait else "sys.exit(0)\n")
    )
    return program, stop


def stopped(pid):
    state = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
    return not state or state.startswith("Z")


@pytest.mark.parametrize("capture", [False, True])
@pytest.mark.parametrize("outcome", ["complete", "timeout"])
def test_quiet_descendants_are_reclaimed_after_command_exit_or_timeout(tmp_path, capture, outcome):
    readiness = module()
    marker = tmp_path / "descendant.json"
    program, stop = descendant_program(marker, wait=outcome == "timeout")
    try:
        if outcome == "timeout":
            with pytest.raises(readiness.CommandTimeout):
                readiness.run_command([sys.executable, "-c", program], timeout=1, capture=capture)
        else:
            assert readiness.run_command([sys.executable, "-c", program], timeout=5, capture=capture)[0] == 0
        assert stopped(json.loads(marker.read_text())[-1]), "quiet descendant escaped cleanup"
    finally:
        stop.touch()


def test_owner_loss_reclaims_the_supervisor_and_its_descendants(tmp_path):
    marker = tmp_path / "descendant.json"
    program, stop = descendant_program(marker, wait=True)
    launch = (
        "import importlib.util,sys\n"
        f"spec=importlib.util.spec_from_file_location('readiness',{str(ROOT / 'scripts/bootstrap_readiness.py')!r})\n"
        "readiness=importlib.util.module_from_spec(spec);spec.loader.exec_module(readiness)\n"
        f"readiness.run_command([sys.executable,'-c',{program!r}],timeout=30)\n"
    )
    owner = subprocess.Popen([sys.executable, "-c", launch], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        until = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < until:
            time.sleep(0.01)
        pids = json.loads(marker.read_text())
        owner.kill()
        owner.wait(timeout=5)
        until = time.monotonic() + 5
        while not all(stopped(pid) for pid in pids) and time.monotonic() < until:
            time.sleep(0.01)
        assert all(stopped(pid) for pid in pids), "owner loss retained a live session member"
    finally:
        stop.touch()
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=5)


def test_group_signal_refusal_fails_without_retry_and_reclaims_supervisor(monkeypatch, tmp_path):
    readiness = module()
    real_popen = readiness.subprocess.Popen
    children, signals = [], []

    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    def signal_group(group, sig):
        signals.append(group)
        raise PermissionError("fixture signal refused")

    monkeypatch.setattr(readiness.subprocess, "Popen", spawn)
    monkeypatch.setattr(readiness.os, "killpg", signal_group)
    marker = tmp_path / "descendant.json"
    program, stop = descendant_program(marker, wait=False)
    try:
        with pytest.raises(readiness.ReadinessError, match="command cleanup unavailable"):
            readiness.run_command([sys.executable, "-c", program], timeout=5)
        assert signals == [children[0].pid]
        assert children[0].returncode is not None
        assert stopped(json.loads(marker.read_text())[-1])
    finally:
        stop.touch()


def test_missing_command_refuses_categorically():
    readiness = module()
    with pytest.raises(readiness.ReadinessError, match="command unavailable"):
        readiness.run_command(["/nonexistent/bootstrap-fixture-command"], timeout=5, capture=True)


def test_status_reader_loss_at_command_exit_reclaims_quiet_descendants(tmp_path):
    readiness = module()
    marker = tmp_path / "descendant.json"
    program, stop = descendant_program(marker, wait=True)
    status_read, status_write = os.pipe()
    control_read, control_write = os.pipe()
    supervisor = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", readiness._SESSION_SUPERVISOR,
         str(status_write), str(control_read), sys.executable, "-c", program],
        start_new_session=True, pass_fds=(status_write, control_read),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    os.close(status_write)
    os.close(control_read)
    try:
        until = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < until:
            time.sleep(0.01)
        pids = json.loads(marker.read_text())
        os.close(status_read)
        status_read = None
        # Keep control open and the quiet descendant running; only the command
        # exits, forcing its status report into the disappeared reader.
        marker.with_suffix(".release").touch()
        supervisor.wait(timeout=5)
        until = time.monotonic() + 5
        while not stopped(pids[-1]) and time.monotonic() < until:
            time.sleep(0.01)
        assert stopped(pids[-1]), "status-report failure retained a quiet descendant"
    finally:
        stop.touch()
        if status_read is not None:
            os.close(status_read)
        os.close(control_write)
        if supervisor.poll() is None:
            supervisor.kill()
        supervisor.wait(timeout=5)


@pytest.mark.parametrize("failure", ["kill", "wait"])
def test_uncertain_fallback_cleanup_refuses_categorically(monkeypatch, failure):
    readiness = module()
    real_popen = readiness.subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)

        def wait(*, timeout):
            raise subprocess.TimeoutExpired("private supervisor argv", timeout)

        def kill():
            if failure == "kill":
                raise PermissionError("private supervisor argv")

        monkeypatch.setattr(child, "wait", wait)
        monkeypatch.setattr(child, "kill", kill)
        return child

    monkeypatch.setattr(readiness.subprocess, "Popen", spawn)
    try:
        with pytest.raises(readiness.ReadinessError, match="^command cleanup unavailable$"):
            readiness.run_command([sys.executable, "-c", "pass"], timeout=5)
    finally:
        monkeypatch.undo()
        for child in children:
            child.wait(timeout=5)
