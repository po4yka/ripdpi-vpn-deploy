"""Real localhost SOCKS negotiation; only the namespace boundary is relocated."""

import importlib.util
import json
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def readiness(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        'native_readiness', ROOT / 'tests/native/transport_acceptance/native_common.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = subprocess.run

    def local_namespace(argv, *args, **kwargs):
        if argv[:4] == ['ip', 'netns', 'exec', 'owned-readiness-test']:
            argv = argv[4:]
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', local_namespace)
    return module


@contextmanager
def socks_peer(mode):
    stop = threading.Event()
    workers = []
    with socket.socket() as listener, ThreadPoolExecutor(max_workers=32) as replies:
        listener.bind(('127.0.0.1', 0))
        listener.listen(32)
        listener.settimeout(.05)

        def reply(stream):
            try:
                with stream:
                    stream.settimeout(2)
                    greeting = b''
                    while len(greeting) < 3:
                        chunk = stream.recv(3 - len(greeting))
                        assert chunk, 'owned greeting ended early'
                        greeting += chunk
                    assert greeting == b'\x05\x01\x00'
                    if mode == 'fragmented':
                        stream.sendall(b'\x05')
                        stop.wait(.1)
                        stream.sendall(b'\x00')
                    elif mode in {'stall', 'wrong-prefix-stall'}:
                        stream.sendall(b'\x05' if mode == 'stall' else b'\x04')
                        stop.wait(13)
                    elif mode != 'eof':
                        stream.sendall({'ready': b'\x05\x00', 'wrong-version': b'\x04\x00',
                                        'wrong-method': b'\x05\xff'}[mode])
            except (BrokenPipeError, ConnectionResetError):
                pass  # A refused client can close before the peer's last write.

        def accept():
            while not stop.is_set():
                try:
                    stream, _peer = listener.accept()
                except TimeoutError:
                    continue
                workers.append(replies.submit(reply, stream))

        thread = threading.Thread(target=accept)
        thread.start()
        try:
            yield listener.getsockname()[1]
        finally:
            stop.set()
            thread.join(timeout=2)
            assert not thread.is_alive()
            for worker in workers:
                worker.result(timeout=2)


@pytest.mark.parametrize('mode', ['ready', 'fragmented'])
def test_complete_valid_socks_response_is_admitted(readiness, mode):
    with socks_peer(mode) as port:
        readiness.wait_client('owned-readiness-test', port)


@pytest.mark.parametrize('mode,reason', [
    ('eof', 'eof'), ('wrong-version', 'wrong-version'),
    ('wrong-method', 'wrong-method'), ('wrong-prefix-stall', 'wrong-version'),
])
def test_incomplete_or_wrong_socks_response_refuses(readiness, mode, reason):
    with socks_peer(mode) as port:
        started = time.monotonic()
        with pytest.raises(RuntimeError, match='native-SOCKS-readiness-' + reason):
            readiness.wait_client('owned-readiness-test', port)
        assert time.monotonic() - started < 2


def test_stalled_partial_response_keeps_original_deadline(readiness):
    with socks_peer('stall') as port:
        started = time.monotonic()
        with pytest.raises(RuntimeError):
            readiness.wait_client('owned-readiness-test', port)
        elapsed = time.monotonic() - started
    assert 9.5 <= elapsed <= 12, 'the existing ten-second deadline must stay bounded'


@pytest.mark.parametrize('state,expected', [
    ('active\n', 'active'), ('failed\n', 'failed'),
    ('private-unit-state\n', 'unknown'), ('active\nprivate-metadata\n', 'unknown'),
])
def test_failed_real_probe_records_only_closed_context(readiness, monkeypatch, state, expected):
    original = subprocess.run
    queries = []

    def metadata(argv, *args, **kwargs):
        if argv[:2] == ['systemctl', 'show']:
            queries.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, state, 'private-journal')
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', metadata)
    properties = []
    with (
        socks_peer('wrong-method') as port,
        pytest.raises(RuntimeError, match='native-SOCKS-readiness-wrong-method'),
    ):
        readiness.wait_client(
            'owned-readiness-test', port, unit='private-unit-name',
            record_property=lambda name, value: properties.append((name, json.loads(value))),
            family=6, phase='retirement', cycle=1)
    assert properties == [('native-socks-readiness', {
        'family': 'ipv6', 'phase': 'retirement', 'cycle': 1,
        'reason': 'wrong-method', 'unit_state': expected})]
    assert len(queries) == 1 and queries[0][1]['timeout'] == 2
    assert 'private' not in json.dumps(properties)


@pytest.mark.parametrize('failure', [OSError('private-command'),
    subprocess.TimeoutExpired(['private-unit-query'], 2)])
def test_missing_unit_diagnostic_stays_unknown_after_actual_probe_failure(readiness, monkeypatch, failure):
    original = subprocess.run

    def metadata(argv, *args, **kwargs):
        if argv[:2] == ['systemctl', 'show']:
            raise failure
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', metadata)
    properties = []
    with (
        socks_peer('eof') as port,
        pytest.raises(RuntimeError, match='native-SOCKS-readiness-eof'),
    ):
        readiness.wait_client(
            'owned-readiness-test', port, unit='private-unit-name',
            record_property=lambda name, value: properties.append(json.loads(value)),
            family=4, phase='hopping')
    assert properties == [{'family': 'ipv4', 'phase': 'hopping', 'cycle': None,
                           'reason': 'eof', 'unit_state': 'unknown'}]
    assert 'private' not in json.dumps(properties)


def test_ready_probe_does_not_query_state_or_record_failure(readiness, monkeypatch):
    original = subprocess.run

    def no_metadata(argv, *args, **kwargs):
        assert argv[:2] != ['systemctl', 'show']
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', no_metadata)
    properties = []
    with socks_peer('fragmented') as port:
        readiness.wait_client(
            'owned-readiness-test', port, unit='private-unit-name',
            record_property=lambda *value: properties.append(value),
            family=6, phase='retirement', cycle=0)
    assert properties == []
