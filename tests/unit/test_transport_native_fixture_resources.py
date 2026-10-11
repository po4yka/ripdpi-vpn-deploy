"""Real file/descriptor ownership; namespace and ioctl faults are portable inputs."""
from contextlib import contextmanager
import ast
import copy
import errno
import importlib.util
import json
import os
from pathlib import Path
import stat
import socket
import sys
import threading
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


@pytest.mark.parametrize("fault", [None, "selected-open", "enter", "ioctl", "restore", "body"])
def test_tun_scope_closes_all_descriptors_after_restore_and_body(tmp_path, monkeypatch, fault):
    module = load_fixture("transport_warp_tun", monkeypatch)
    descriptors, transitions = [], []

    def acquire():
        fd = os.open(tmp_path / str(len(descriptors)), os.O_CREAT | os.O_RDWR, 0o600)
        descriptors.append(fd)
        return fd

    def namespace_file(path, mode):
        assert mode == "rb"
        if fault == "selected-open" and path.startswith("/run/netns/"):
            raise OSError(errno.EACCES, "owned-open-fault")
        return os.fdopen(acquire(), mode)

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

    monkeypatch.setattr(module, "open", namespace_file, raising=False)
    monkeypatch.setattr(module, "os", SimpleNamespace(
        open=lambda path, flags: acquire(), close=os.close,
        O_RDWR=os.O_RDWR, O_NONBLOCK=os.O_NONBLOCK,
    ))
    monkeypatch.setattr(module, "ctypes", SimpleNamespace(
        CDLL=lambda *args, **kwargs: SimpleNamespace(setns=setns),
        get_errno=lambda: errno.EPERM,
    ))
    monkeypatch.setattr(module, "fcntl", SimpleNamespace(ioctl=ioctl))

    def enter():
        with module.tun("owned", "owned-tun") as fd:
            assert fd == descriptors[2]
            os.fstat(fd)
            for namespace in descriptors[:2]:
                with pytest.raises(OSError) as closed:
                    os.fstat(namespace)
                assert closed.value.errno == errno.EBADF
            if fault == "body":
                raise OSError(errno.EIO, "owned-body-fault")

    try:
        if fault:
            with pytest.raises(OSError):
                enter()
        else:
            enter()
        if fault != "selected-open":
            assert transitions == [descriptors[1], descriptors[0]]
        for fd in descriptors:
            with pytest.raises(OSError) as closed:
                os.fstat(fd)
            assert closed.value.errno == errno.EBADF
    finally:
        for fd in descriptors:
            try:
                os.fstat(fd)
            except OSError:
                continue
            os.close(fd)


def resource_scopes():
    """Keep main's actual lexical owners, replacing native actions with fault sites."""
    source = ROOT / "tests/integration/transport_warp_tun/fixture.py"
    main = next(node for node in ast.parse(source.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    owner = next(node for node in main.body if isinstance(node, ast.Try))
    outer = next(node for node in owner.body if isinstance(node, ast.With))
    phase = 0

    def scopes(node):
        nonlocal phase
        node = copy.deepcopy(node)
        expression = node.items[0].context_expr
        if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name) and expression.func.id == "worker":
            if isinstance(expression.args[0], ast.Name) and expression.args[0].id == "pump":
                phase += 1
                node.body = [ast.Expr(value=ast.Call(func=ast.Name(id="exercise", ctx=ast.Load()),
                    args=[ast.Constant(phase), ast.Name(id="gateway_fd", ctx=ast.Load()),
                          ast.Name(id="peer_fd", ctx=ast.Load())], keywords=[]))]
                return node
        body = []
        for child in node.body:
            if isinstance(child, ast.With):
                body.append(scopes(child))
            elif isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                target = child.value.func
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "capture":
                    body.append(child)
        node.body = body
        return node

    program = ast.fix_missing_locations(ast.Module(body=[scopes(outer)], type_ignores=[]))
    assert phase == 2
    return compile(program, str(source), "exec")


@pytest.mark.parametrize("fault", [None, "second-acquisition", "replacement-acquisition", "capture-bind",
                                   "initial-body", "replacement-body", "initial-pump", "replacement-pump",
                                   "monitor-start", "initial-pump-start", "replacement-pump-start"])
def test_actual_main_scopes_close_fds_socket_and_workers_on_every_phase(tmp_path, monkeypatch, fault):
    module = load_fixture("transport_warp_tun", monkeypatch)
    descriptors, workers, acquisitions, created_threads = [], [], [], []
    ready = {1: threading.Event(), 2: threading.Event()}
    captures = []

    def acquire():
        fd = os.open(tmp_path / str(len(descriptors)), os.O_CREAT | os.O_RDWR, 0o600)
        descriptors.append(fd)
        return fd

    def namespace_file(path, mode):
        return os.fdopen(acquire(), mode)

    def open_tun(path, flags):
        assert path == "/dev/net/tun"
        acquisitions.append(path)
        if (fault == "second-acquisition" and len(acquisitions) == 2 or
                fault == "replacement-acquisition" and len(acquisitions) == 3):
            raise OSError(errno.EIO, "owned-acquisition-fault")
        return acquire()

    class Capture(socket.socket):
        def __init__(self):
            super().__init__(socket.AF_INET, socket.SOCK_DGRAM)
            captures.append(self)

        def bind(self, address):
            assert address == ("rpd-warp-host", 0)
            if fault == "capture-bind":
                raise OSError(errno.EIO, "owned-capture-bind-fault")
            super().bind(("127.0.0.1", 0))

    class Thread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created_threads.append(self)

        def start(self):
            failure = {1: "monitor-start", 2: "initial-pump-start", 3: "replacement-pump-start"}
            if fault == failure[len(created_threads)]:
                raise OSError(errno.EAGAIN, "owned-worker-start-fault")
            super().start()

    def monitor_target(stop, capture, counts):
        workers.append(threading.current_thread())
        module.monitor(stop, capture, counts)

    def pump_target(stop, gateway, peer, counts):
        phase = len(acquisitions) - 1
        workers.append(threading.current_thread())
        ready[phase].set()
        if fault == ("initial-pump" if phase == 1 else "replacement-pump"):
            raise OSError(errno.EIO, "owned-pump-fault")
        stop.wait()

    def exercise(phase, gateway, peer):
        assert ready[phase].wait(1)
        os.fstat(gateway); os.fstat(peer)
        if fault == ("initial-body" if phase == 1 else "replacement-body"):
            raise OSError(errno.EIO, "owned-phase-fault")

    monkeypatch.setattr(module, "open", namespace_file, raising=False)
    monkeypatch.setattr(module, "os", SimpleNamespace(
        open=open_tun, close=os.close, O_RDWR=os.O_RDWR, O_NONBLOCK=os.O_NONBLOCK,
    ))
    monkeypatch.setattr(module, "ctypes", SimpleNamespace(
        CDLL=lambda *args, **kwargs: SimpleNamespace(setns=lambda fd, kind: 0),
        get_errno=lambda: errno.EPERM,
    ))
    monkeypatch.setattr(module, "fcntl", SimpleNamespace(ioctl=lambda *args: None))
    monkeypatch.setattr(module, "socket", SimpleNamespace(
        AF_PACKET=0, SOCK_RAW=0, htons=lambda value: value, socket=lambda *args: Capture(), timeout=socket.timeout,
    ))
    monkeypatch.setattr(module, "threading", SimpleNamespace(Event=threading.Event, Thread=Thread))
    values = {"tun": module.tun, "worker": module.worker, "pump": pump_target, "monitor": monitor_target,
              "socket": module.socket, "gateway_ns": "owned-gateway", "peer_ns": "owned-peer",
              "counts": {"underlay_recipient_frames": 0}, "exercise": exercise}
    try:
        if fault:
            with pytest.raises((OSError, RuntimeError)):
                exec(resource_scopes(), values)
        else:
            exec(resource_scopes(), values)
            assert len(acquisitions) == 3 and len(workers) == 3
        assert all(not thread.is_alive() for thread in created_threads)
        assert len(captures) == 1 and captures[0].fileno() == -1
        for fd in descriptors:
            with pytest.raises(OSError) as closed:
                os.fstat(fd)
            assert closed.value.errno == errno.EBADF
    finally:
        for capture in captures:
            capture.close()
        for fd in descriptors:
            try:
                os.fstat(fd)
            except OSError:
                continue
            os.close(fd)


@pytest.mark.parametrize("fault", [None, "write", "ownership", "mode"])
def test_gateway_config_is_private_before_write_and_closes_failed_candidate(tmp_path, monkeypatch, fault):
    module = load_fixture("transport_warp_tun", monkeypatch)
    descriptors = []

    def dump(document, stream):
        descriptors.append(stream.fileno())
        assert stat.S_IMODE(os.fstat(stream.fileno()).st_mode) == 0o600
        json.dump(document, stream)
        if fault == "write":
            raise OSError(errno.EIO, "owned-config-write-fault")

    def ownership(fd, uid, gid):
        assert uid == 0 and gid == os.getgid()
        assert stat.S_IMODE(os.fstat(fd).st_mode) == 0o600
        if fault == "ownership":
            raise OSError(errno.EPERM, "owned-config-ownership-fault")
        os.fchown(fd, -1, gid)

    def mode(fd, value):
        assert value == 0o640
        if fault == "mode":
            raise OSError(errno.EPERM, "owned-config-mode-fault")
        os.fchmod(fd, value)

    monkeypatch.setattr(module, "json", SimpleNamespace(dump=dump))
    monkeypatch.setattr(module, "os", SimpleNamespace(fchown=ownership, fchmod=mode))
    if fault:
        with pytest.raises(OSError):
            module.gateway_config(tmp_path, {"authority": "owned-fixture"}, os.getgid())
        assert list(tmp_path.iterdir()) == []
    else:
        path = module.gateway_config(tmp_path, {"authority": "owned-fixture"}, os.getgid())
        assert path.suffix == ".json"
        assert json.loads(path.read_text()) == {"authority": "owned-fixture"}
        assert stat.S_IMODE(path.stat().st_mode) == 0o640
        assert path.stat().st_gid == os.getgid()
    for fd in descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(fd)
        assert closed.value.errno == errno.EBADF


def test_real_pump_forwards_frames_and_stops_before_socket_scope_closes(monkeypatch):
    module = load_fixture("transport_warp_tun", monkeypatch)
    counts = {"tun_frames": 0, "recipient_tun_frames": 0}
    frame = bytes([0x45]) + bytes(15) + socket.inet_aton("192.0.2.80") + b"owned-frame"
    left, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    with left, sender:
        right, receiver = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        with right, receiver:
            receiver.settimeout(1)
            sender.settimeout(1)
            with module.worker(module.pump, left.fileno(), right.fileno(), counts):
                sender.send(frame)
                assert receiver.recv(4096) == frame
                receiver.send(b"owned-reply")
                assert sender.recv(4096) == b"owned-reply"
            assert counts["tun_frames"] == 2 and counts["recipient_tun_frames"] == 1


@pytest.mark.parametrize('error', [OSError, RuntimeError, SystemExit])
@pytest.mark.parametrize('parent_failure', [False, True])
def test_worker_abnormal_exit_surfaces_without_masking_parent_failure(monkeypatch, error, parent_failure):
    module = load_fixture('transport_warp_tun', monkeypatch)
    started = threading.Event()
    uncaught = []
    monkeypatch.setattr(threading, 'excepthook', lambda args: uncaught.append(args.exc_type))

    def target(stop):
        started.set()
        raise error('owned-child-failure')

    expected = ValueError if parent_failure else RuntimeError
    message = '^owned-parent-failure$' if parent_failure else '^owned-worker-failed$'
    with pytest.raises(expected, match=message):
        with module.worker(target):
            assert started.wait(1)
            if parent_failure:
                raise ValueError('owned-parent-failure')
    assert uncaught == ([SystemExit] if error is SystemExit else [])
