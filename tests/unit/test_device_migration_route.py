"""Real loopback TLS and supervised route deadlines; no live publisher claim."""
from __future__ import annotations

import base64
import contextlib
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import device_migration_io as migration_io
import device_migration_route as migration_route
import pytest
from bootstrap_readiness import CommandTimeout, run_command
from test_subscription_document import service as service  # noqa: PLC0414

TOKEN = 'A' * 43
PAYLOAD = b'{"route_nonce":"' + b'b' * 64 + b'"}'
HOSTNAME = 'delivery.example.test'


@pytest.fixture
def tls_server(tmp_path, monkeypatch):
    """An independent test CA signs the exact virtual-host certificate."""
    ca, ca_key = tmp_path / 'ca.pem', tmp_path / 'ca.key'
    cert, key, csr = tmp_path / 'leaf.pem', tmp_path / 'leaf.key', tmp_path / 'leaf.csr'
    extensions = tmp_path / 'extensions.cnf'
    extensions.write_text('subjectAltName=DNS:' + HOSTNAME + '\nextendedKeyUsage=serverAuth\n')
    commands = [
        ['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
         '-nodes', '-days', '1', '-subj', '/CN=migration-route-test-ca',
         '-addext', 'basicConstraints=critical,CA:TRUE', '-keyout', str(ca_key), '-out', str(ca)],
        ['openssl', 'req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
         '-nodes', '-subj', '/CN=' + HOSTNAME, '-keyout', str(key), '-out', str(csr)],
        ['openssl', 'x509', '-req', '-in', str(csr), '-CA', str(ca), '-CAkey', str(ca_key),
         '-CAcreateserial', '-days', '1', '-extfile', str(extensions), '-out', str(cert)],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, timeout=10)
    monkeypatch.setenv('SSL_CERT_FILE', str(ca))

    @contextlib.contextmanager
    def serve(handler):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        names = []
        context.set_servername_callback(lambda _socket, name, _context: names.append(name))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port, names
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            assert not thread.is_alive()

    return serve


def route_io(port, *, hostname=HOSTNAME):
    # Only transport admission is isolated: read_route launches the real helper.
    instance = object.__new__(migration_io.LocalIO)
    instance.plan = {'publication': {'origin': f'https://{hostname}:{port}',
                                     'source_alias': 'delivery', 'target_alias': 'delivery'}}
    instance.hosts = {'delivery': {'address': '127.0.0.1'}}
    return instance


def responder(mode, requests, stop):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('Host')))
            try:
                if mode == 'slow-headers':
                    self.connection.sendall(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                    while not stop.wait(0.04):
                        self.connection.sendall(b'x')
                    return
                if mode == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', '/must-not-be-followed')
                    self.end_headers()
                    return
                body = b'wrong-namespace' if mode == 'wrong-body' else PAYLOAD
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if mode == 'slow-body':
                    for byte in body:
                        if stop.wait(0.04):
                            return
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                else:
                    self.wfile.write(body)
            except OSError:
                pass  # Expected when the owned probe session reaches its deadline.

        def log_message(self, _format, *_args):
            return

    return Handler


def short_real_deadline(monkeypatch):
    calls = []

    def bounded(argv, **kwargs):
        assert kwargs['timeout'] == 15
        assert TOKEN not in ' '.join(argv)
        assert kwargs['capture'] is True and kwargs['output_limit'] == 4096
        calls.append(argv)
        return run_command(argv, **dict(kwargs, timeout=0.8))

    monkeypatch.setattr(migration_io, 'run_command', bounded)
    return calls


def test_origin_and_route_require_verified_tls12_or_newer(tls_server, monkeypatch):
    contexts = []
    default_context = ssl.create_default_context

    def observed_context():
        context = default_context()
        contexts.append(context)
        return context

    monkeypatch.setattr(ssl, 'create_default_context', observed_context)
    requests, stop = [], threading.Event()
    with tls_server(responder('exact', requests, stop)) as (port, names):
        instance = route_io(port)
        instance.origin('delivery')
        migration_route.probe({'origin': instance.plan['publication']['origin'],
                               'address': '127.0.0.1', 'token': TOKEN,
                               'expected_b64': base64.b64encode(PAYLOAD).decode()})
        assert names == [HOSTNAME, HOSTNAME]
        assert requests == [('/sub/' + TOKEN, f'{HOSTNAME}:{port}')]
    assert len(contexts) == 2
    for context in contexts:
        assert context.minimum_version == ssl.TLSVersion.TLSv1_2
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname


@pytest.mark.parametrize('payload', [
    b'[]',
    b'[' * 2000 + b']' * 2000,
    b'\xff',
    migration_io.encoded({'origin': None, 'address': '127.0.0.1',
                          'token': TOKEN, 'expected_b64': 'eA=='}),
])
def test_route_refuses_malformed_private_input_without_diagnostics(payload):
    result = subprocess.run([sys.executable, migration_route.__file__],
                            input=payload, capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    assert result.stdout == b''
    assert result.stderr == b''


@pytest.mark.parametrize('mode', ['exact', 'wrong-body', 'redirect', 'wrong-san'])
def test_route_uses_exact_tls_virtual_host_and_never_accepts_wrong_namespace(tls_server, mode):
    requests, stop = [], threading.Event()
    with tls_server(responder(mode, requests, stop)) as (port, names):
        instance = route_io(port, hostname='wrong.example.test' if mode == 'wrong-san' else HOSTNAME)
        if mode == 'exact':
            instance.read_route('delivery', TOKEN, PAYLOAD)
        else:
            with pytest.raises(ValueError, match='route-mismatch'):
                instance.read_route('delivery', TOKEN, PAYLOAD)
        assert names == ['wrong.example.test' if mode == 'wrong-san' else HOSTNAME]
        assert requests == ([] if mode == 'wrong-san' else [('/sub/' + TOKEN, f'{HOSTNAME}:{port}')])


@pytest.mark.parametrize('mode', ['slow-headers', 'slow-body'])
def test_route_total_deadline_terminates_continuously_progressing_tls_peer(tls_server, monkeypatch, mode):
    calls = short_real_deadline(monkeypatch)
    requests, stop = [], threading.Event()
    with tls_server(responder(mode, requests, stop)) as (port, _):
        started = time.monotonic()
        try:
            with pytest.raises(CommandTimeout):
                route_io(port).read_route('delivery', TOKEN, PAYLOAD)
        finally:
            stop.set()
        assert time.monotonic() - started < 4
        assert len(calls) == 1 and len(requests) == 1


@pytest.mark.parametrize('outcome', ['exact', 'wrong-body', 'slow-body', 'lost-create-ack'])
def test_route_canary_is_removed_by_exact_cas_after_real_io_failure(service, tls_server, monkeypatch, outcome):
    requests, stop = [], threading.Event()
    handler = service.Handler if outcome == 'exact' else responder(outcome, requests, stop)
    if outcome == 'slow-body':
        short_real_deadline(monkeypatch)
    with tls_server(handler) as (port, _):
        instance = route_io(port)
        calls = []

        def publish(_alias, action, token_hash, expected, document, *, cleanup=False):
            assert action == 'publish'
            calls.append((token_hash, expected, document, cleanup))
            request = migration_io.encoded({'schema_version': 1, 'expected_document_sha256': expected,
                               'document_b64': base64.b64encode(document).decode() if document is not None else None})
            result = service._migration_publish(token_hash, request)
            if outcome == 'lost-create-ack' and not cleanup:
                raise OSError('lost synthetic acknowledgement')
            return result

        monkeypatch.setattr(instance, 'publisher', publish)
        try:
            if outcome == 'exact':
                instance.verify_routes()
            else:
                expected_error = CommandTimeout if outcome == 'slow-body' else OSError if outcome == 'lost-create-ack' else ValueError
                with pytest.raises(expected_error):
                    instance.verify_routes()
        finally:
            stop.set()
        assert len(calls) == 2
        token_hash, _, created, _ = calls[0]
        assert calls[0][1] is None and calls[0][3] is False
        assert calls[1] == (token_hash, migration_io.sha(created), None, True)
        assert service._migration_snapshot()['documents'] == []
        assert not list((service.SUBSCRIPTION_DIR / 'sub').glob('*.document'))
