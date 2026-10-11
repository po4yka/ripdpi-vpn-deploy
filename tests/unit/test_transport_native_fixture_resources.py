"""Real file/descriptor ownership; namespace and ioctl faults are portable inputs."""
from contextlib import contextmanager
import ast
import errno
import importlib.util
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_fixture(name, monkeypatch):
    path = ROOT / "tests/integration" / name / "fixture.py"
    monkeypatch.setattr(sys, "argv", [str(path), str(ROOT)])
    spec = importlib.util.spec_from_file_location(name + "_resources", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("group", [None, "actor"])
def test_fixture_config_is_private_before_write_and_atomically_published(tmp_path, monkeypatch, group):
    module = load_fixture("transport_destination_boundary", monkeypatch)
    stack = object.__new__(module.NativeStack)
    stack.library, stack.gids = tmp_path, {"actor": os.getgid()}
    target = tmp_path / "owned.json"
    target.write_text("accepted authority")
    target.chmod(0o600)
    observations = []

    @contextmanager
    def observed_stream(fd, mode):
        observations.append(stat.S_IMODE(os.fstat(fd).st_mode))
        assert target.read_text() == "accepted authority"
        with os.fdopen(fd, mode) as stream:
            yield stream
        assert target.read_text() == "accepted authority"

    def assign_group(fd, uid, gid):
        assert uid == 0 and gid == os.getgid()
        assert stat.S_IMODE(os.fstat(fd).st_mode) == 0o600
        os.fchown(fd, -1, gid)

    monkeypatch.setattr(module, "os", SimpleNamespace(
        fdopen=observed_stream, fchown=assign_group,
        fchmod=os.fchmod, replace=os.replace,
    ))
    assert stack.file("owned.json", "candidate authority", group) == target
    assert observations == [0o600]
    assert target.read_text() == "candidate authority"
    assert stat.S_IMODE(target.stat().st_mode) == (0o640 if group else 0o600)
    assert set(tmp_path.iterdir()) == {target}


@pytest.mark.parametrize("fault", ["write", "publication"])
def test_fixture_config_failure_retains_accepted_file_and_cleans_candidate(tmp_path, monkeypatch, fault):
    module = load_fixture("transport_destination_boundary", monkeypatch)
    stack = object.__new__(module.NativeStack)
    stack.library = tmp_path
    target = tmp_path / "owned.json"
    target.write_text("accepted authority")
    target.chmod(0o600)
    before = target.stat()
    descriptors = []

    @contextmanager
    def faulty_stream(fd, mode):
        descriptors.append(fd)
        with os.fdopen(fd, mode) as stream:
            if fault == "write":
                stream.write("partial candidate")
                raise OSError(errno.EIO, "owned-write-fault")
            yield stream

    def publish(source, destination):
        raise OSError(errno.EIO, "owned-publication-fault")

    monkeypatch.setattr(module, "os", SimpleNamespace(
        fdopen=faulty_stream, fchmod=os.fchmod, replace=publish,
    ))
    with pytest.raises(OSError):
        stack.file("owned.json", "candidate authority")
    assert target.read_text() == "accepted authority"
    assert target.stat().st_ino == before.st_ino
    assert target.stat().st_mtime_ns == before.st_mtime_ns
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert set(tmp_path.iterdir()) == {target}
    for fd in descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(fd)
        assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize("fault", [None, "selected-open", "enter", "ioctl", "restore"])
def test_tun_descriptor_transfers_only_after_success_and_restores_namespace(tmp_path, monkeypatch, fault):
    module = load_fixture("transport_warp_tun", monkeypatch)
    descriptors, transitions = [], []

    def open_descriptor(path, flags):
        if fault == "selected-open" and path.startswith("/run/netns/"):
            raise OSError(errno.EACCES, "owned-open-fault")
        fd = os.open(tmp_path / str(len(descriptors)), os.O_CREAT | os.O_RDWR, 0o600)
        descriptors.append(fd)
        return fd

    def setns(fd, kind):
        assert kind == 0x40000000
        os.fstat(fd)
        transitions.append(fd)
        return int((fault == "enter" and fd == descriptors[1]) or
                   (fault == "restore" and fd == descriptors[0]))

    def ioctl(fd, operation, value):
        assert fd == descriptors[2] and operation == 0x400454ca
        os.fstat(fd)
        if fault == "ioctl":
            raise OSError(errno.EIO, "owned-ioctl-fault")

    monkeypatch.setattr(module, "os", SimpleNamespace(
        open=open_descriptor, close=os.close, O_RDONLY=os.O_RDONLY,
        O_RDWR=os.O_RDWR, O_NONBLOCK=os.O_NONBLOCK,
    ))
    monkeypatch.setattr(module, "ctypes", SimpleNamespace(
        CDLL=lambda *args, **kwargs: SimpleNamespace(setns=setns),
        get_errno=lambda: errno.EPERM,
    ))
    monkeypatch.setattr(module, "fcntl", SimpleNamespace(ioctl=ioctl))
    retained = None
    try:
        if fault:
            with pytest.raises(OSError):
                module.tun("owned", "owned-tun")
        else:
            retained = module.tun("owned", "owned-tun")
            assert retained == descriptors[2]
            os.fstat(retained)
        if fault != "selected-open":
            assert transitions == [descriptors[1], descriptors[0]]
        for fd in descriptors:
            if fd != retained:
                with pytest.raises(OSError) as closed:
                    os.fstat(fd)
                assert closed.value.errno == errno.EBADF
    finally:
        if retained is not None:
            os.close(retained)


@pytest.mark.parametrize("second_fails", [False, True])
def test_two_tun_caller_registers_each_transferred_descriptor_before_next_acquisition(tmp_path, second_fails):
    """Execute the actual acquisition and cleanup statements with real owned FDs."""
    source = ROOT / "tests/integration/transport_warp_tun/fixture.py"
    main = next(node for node in ast.parse(source.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    owner = next(node for node in main.body if isinstance(node, ast.Try))
    start = next(index for index, node in enumerate(owner.body) if isinstance(node, ast.Assign)
                 and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                         and call.func.id == "tun" for call in ast.walk(node)))
    end = next(index for index in range(start + 1, len(owner.body))
               if isinstance(owner.body[index], ast.For))
    cleanup = next(node for node in owner.finalbody if isinstance(node, ast.For)
                   and isinstance(node.iter, ast.Name) and node.iter.id == "descriptors")
    program = ast.fix_missing_locations(ast.Module(body=[ast.Try(
        body=owner.body[start:end], handlers=[], orelse=[], finalbody=[cleanup],
    )], type_ignores=[]))
    acquired, registered, calls = [], [], []

    def acquire(namespace, name):
        calls.append((namespace, name))
        if len(calls) == 2 and second_fails:
            raise OSError(errno.EIO, "owned-second-acquisition-fault")
        fd = os.open(tmp_path / str(len(acquired)), os.O_CREAT | os.O_RDWR, 0o600)
        acquired.append(fd)
        return fd

    values = {"tun": acquire, "os": os, "descriptors": registered,
              "gateway_ns": "owned-gateway", "peer_ns": "owned-peer"}
    try:
        if second_fails:
            with pytest.raises(OSError, match="owned-second-acquisition-fault"):
                exec(compile(program, str(source), "exec"), values)
        else:
            exec(compile(program, str(source), "exec"), values)
            assert values["gateway_fd"] == acquired[0] and values["peer_fd"] == acquired[1]
        assert len(calls) == 2
        assert registered == acquired
        for fd in acquired:
            with pytest.raises(OSError) as closed:
                os.fstat(fd)
            assert closed.value.errno == errno.EBADF
    finally:
        # A red baseline must not leak its test descriptor into another case.
        for fd in acquired:
            try:
                os.fstat(fd)
            except OSError:
                continue
            os.close(fd)
