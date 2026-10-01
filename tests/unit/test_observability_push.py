"""Positive acknowledgements and fail-closed direct heartbeat conditions."""

import datetime as dt
import importlib.util
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import subprocess
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('observability_push', ROOT / 'ansible/roles/observability_kuma/files/observability-push.py')
push = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(push)


@pytest.fixture
def inputs(tmp_path):
    for name, value in {'push-token': 'p' * 32, 'observer-ca': 'test-ca', 'relay-auth-token': 'r' * 32}.items():
        (tmp_path / name).write_text(value)
    return {'kind': 'node', 'node_id': 'node-a', 'origin': 'https://100.64.0.8:9444', 'prometheus_origin': 'http://127.0.0.1:9090', 'relay_origin': 'http://127.0.0.1:19095', 'services': ['xray.service'], 'expected_nodes': ['node-a']}, tmp_path


def runner(*args, **kwargs):
    return SimpleNamespace(returncode=0)


def test_node_publishes_only_minimal_acknowledged_signal(inputs):
    config, directory = inputs
    calls = []
    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return {'ok': True}
    result = push.run(config, directory, directory / 'state', now=1000, fetcher=fetch, runner=runner)
    assert result == {'last_success': 1000, 'sequence': 0}
    assert calls == [('https://100.64.0.8:9444/api/push/' + 'p' * 32, {'ca': 'test-ca'})]


@pytest.mark.parametrize('answer', [{'ok': False}, {}, {'ok': 1}, {'ok': True, 'msg': 'anything'}])
def test_wrong_application_ack_cannot_refresh_state(inputs, answer):
    config, directory = inputs
    # Boolean identity matters: {ok: 1} is not the upstream JSON contract.
    with pytest.raises(push.Refusal):
        push.run(config, directory, directory / 'state', now=1000, fetcher=lambda *a, **k: answer, runner=runner)
    assert not (directory / 'state').exists()


def test_failed_service_never_sends(inputs):
    config, directory = inputs
    with pytest.raises(push.Refusal, match='local-service'):
        push.run(config, directory, directory / 'state', now=1000, fetcher=lambda *a, **k: pytest.fail('sent'), runner=lambda *a, **k: SimpleNamespace(returncode=3))


@pytest.mark.parametrize('size', [19, 129])
def test_out_of_contract_token_never_reaches_observer(inputs, size):
    config, directory = inputs
    (directory / 'push-token').write_text('p' * size)
    with pytest.raises(push.Refusal, match='push-credential'):
        push.run(config, directory, directory / 'state', now=1000,
                 fetcher=lambda *a, **k: pytest.fail('sent'), runner=runner)
    assert not (directory / 'state').exists()


@pytest.mark.parametrize('size', [20, 128])
def test_schema_boundary_tokens_accept_application_ack_contract(inputs, size):
    config, directory = inputs
    (directory / 'push-token').write_text('p' * size)
    result = push.run(config, directory, directory / 'state', now=1000,
                      fetcher=lambda *a, **k: {'ok': True}, runner=runner)
    assert result['last_success'] == 1000


@pytest.mark.parametrize('origin', ['http://100.64.0.8', 'https://example.org', 'https://8.8.8.8', 'https://100.64.0.8/path', 'https://100.64.0.8?secret=x', 'https://user@100.64.0.8', 'https://127.0.0.1', 'https://169.254.1.1'])
def test_only_exact_private_tls_origin_allowed(inputs, origin):
    config, _ = inputs
    config['origin'] = origin
    with pytest.raises(ValueError):
        push.validate_config(config)


def test_delivery_requires_current_real_edit_and_daily_send(inputs):
    config, directory = inputs
    config['kind'] = 'delivery'
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        if url.endswith('/v1/receipts'):
            return {'edit_sequence': 1, 'edit_at': 1000, 'send_at': 999}
        if url.endswith('/v1/delivery-canary'):
            assert kwargs['timeout'] == 35
            return {'status': 'delivered'}
        return {'ok': True}
    state = directory / 'state'
    push.run(config, directory, state, now=1000, fetcher=fetch)
    assert calls[0].endswith('/v1/delivery-canary')
    assert json.loads(state.read_text())['sequence'] == 1
    with pytest.raises(push.Refusal, match='delivery-receipt'):
        push.run(config, directory, state, now=1001, fetcher=fetch)


@pytest.mark.parametrize('receipt', [
    {'edit_sequence': 2, 'edit_at': 10, 'send_at': 100000},
    {'edit_sequence': 2, 'edit_at': 100000, 'send_at': 1},
    {'edit_sequence': 2, 'edit_at': 100010, 'send_at': 100000},
    {'edit_sequence': 0, 'edit_at': 100000, 'send_at': 100000},
])
def test_delivery_stale_or_future_receipt_refused(inputs, receipt):
    config, directory = inputs
    config['kind'] = 'delivery'
    def fetch(url, **kwargs):
        assert '/api/push/' not in url
        return receipt if url.endswith('receipts') else {'status': 'delivered'}
    with pytest.raises(push.Refusal, match='delivery-receipt'):
        push.run(config, directory, directory / 'state', now=100000, fetcher=fetch)


def pipeline_fetch(url, **kwargs):
    if url.endswith('receipts'):
        return {'rule_to_relay_at': 999}
    if '/api/v1/query?' in url:
        return {'status': 'success', 'data': {'resultType': 'vector', 'result': [{'value': [1000, '1']}]}}
    if url.endswith('/api/v1/rules'):
        return {'status': 'success', 'data': {'groups': [{'lastEvaluation': dt.datetime.fromtimestamp(999, dt.timezone.utc).isoformat(), 'rules': [{'health': 'ok'}]}]}}
    return {'ok': True}


def test_pipeline_requires_fresh_nodes_rules_am_and_unconsumed_canary(inputs):
    config, directory = inputs
    config['kind'] = 'pipeline'
    state = directory / 'state'
    push.run(config, directory, state, now=1000, fetcher=pipeline_fetch)
    assert json.loads(state.read_text())['sequence'] == 999
    with pytest.raises(push.Refusal, match='pipeline-receipt'):
        push.run(config, directory, state, now=1001, fetcher=pipeline_fetch)


@pytest.mark.parametrize('missing', ['node', 'alertmanager', 'rules'])
def test_pipeline_failure_cannot_send(inputs, missing):
    config, directory = inputs
    config['kind'] = 'pipeline'
    def fetch(url, **kwargs):
        assert '/api/push/' not in url
        result = pipeline_fetch(url, **kwargs)
        if (missing == 'node' and 'node-exporter' in url) or (missing == 'alertmanager' and 'observability-alertmanager' in url):
            result['data']['result'] = []
        if missing == 'rules' and url.endswith('/api/v1/rules'):
            result['data']['groups'][0]['rules'][0]['health'] = 'err'
        return result
    with pytest.raises(push.Refusal):
        push.run(config, directory, directory / 'state', now=1000, fetcher=fetch)


def test_redirect_disabled_and_json_content_type_required():
    assert push.NoRedirect().redirect_request(None) is None
    class Response(io.BytesIO):
        status = 200
        headers = SimpleNamespace(get_content_type=lambda: 'text/html')
    with pytest.raises(push.Refusal, match='acknowledgement'):
        push.fetch('https://100.64.0.8', opener=lambda *a, **k: Response(b'{"ok": true}'))


def test_symlink_credential_refused(inputs):
    _, directory = inputs
    (directory / 'alias').symlink_to(directory / 'push-token')
    with pytest.raises(OSError):
        push.credential(directory, 'alias')


def test_real_tls_acknowledgement_and_redirect_refusal(tmp_path):
    key, certificate = tmp_path / 'key.pem', tmp_path / 'cert.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(certificate), '-days', '1', '-subj', '/CN=observer-test', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/accepted')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        def log_message(self, *_args):
            return
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = 'https://127.0.0.1:' + str(server.server_port)
        assert push.fetch(origin + '/accepted', ca=certificate.read_text()) == {'ok': True}
        with pytest.raises(Exception):
            push.fetch(origin + '/redirect', ca=certificate.read_text())
        with pytest.raises(Exception):
            push.fetch(origin + '/accepted')
        with pytest.raises(Exception):
            push.fetch('https://localhost:' + str(server.server_port) + '/accepted', ca=certificate.read_text())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
