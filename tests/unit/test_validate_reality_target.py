"""Real local certificates, sockets and subprocess cleanup; no fleet inputs."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

import reality_target_validation as validator

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/validate-reality-target.sh'


@pytest.fixture
def tls_site(tmp_path, request):
    variant = getattr(request, "param", "normal")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'cn-only.example')])
    now = dt.datetime.now(dt.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=2))
            .not_valid_after(now + dt.timedelta(days=-1 if variant == 'expired' else 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            )
    if variant != 'no-san':
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName('exact.example'),
                                                    x509.DNSName('*.wild.example')]), critical=False)
    if variant == 'large-certificate':
        builder = builder.add_extension(x509.UnrecognizedExtension(
            x509.ObjectIdentifier('1.3.6.1.4.1.55555.1'), b'x' * 80 * 1024), critical=False)
    cert = builder.sign(key, hashes.SHA256())
    ca = tmp_path / 'ca.pem'; private = tmp_path / 'key.pem'
    ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, private)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.set_alpn_protocols(['http/1.1'] if variant == 'no-h2' else ['h2', 'http/1.1'])
    # UDP connect selects a local ingress address without sending a packet.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        route.connect(('192.0.2.1', 9))
        ingress = os.environ.get('REALITY_TEST_PUBLIC_IP', route.getsockname()[0])
    listener = socket.socket(); listener.bind((os.environ.get('REALITY_TEST_BIND', ingress), 0)); listener.listen(); listener.settimeout(.1)
    port = listener.getsockname()[1]
    stopped = threading.Event()
    seen = []

    def serve():
        while not stopped.is_set():
            try:
                raw, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            raw.settimeout(1)
            if variant == 'client-no-h2' and len(seen) >= 2:
                context.set_alpn_protocols(['http/1.1'])
            try:
                with context.wrap_socket(raw, server_side=True) as conn:
                    seen.append((conn.version(), conn.selected_alpn_protocol()))
                    data = conn.recv(4096)
                    if data:
                        if conn.selected_alpn_protocol() == 'h2':
                            # SETTINGS, then HPACK indexed :status=200 with END_HEADERS/END_STREAM.
                            conn.sendall(bytes.fromhex('00000004000000000000000101050000000188'))
                            conn.recv(4096)
                        else:
                            conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok')
            except (OSError, ssl.SSLError):
                raw.close()
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    yield port, ca, seen, ingress
    stopped.set(); listener.close(); thread.join(2)
    assert not thread.is_alive()


def run_site(tls_site, **extra):
    port, ca, _, ingress = tls_site
    env = {**os.environ, 'TARGET': f'{ingress}:{port}', 'SERVER_NAMES': 'exact.example',
           'REALITY_CA_FILE': str(ca), 'TARGET_MODE': 'borrowed',
           'PROBE_TIMEOUT': '5', 'VALIDATION_TIMEOUT': '10'}
    env.pop('REALITY_CLIENT_DIR', None); env.pop('REALITY_VALIDATION_END', None)
    env.update(extra)
    env = {key: value for key, value in env.items() if value is not None}
    result = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True, timeout=15)
    report = json.loads(result.stdout)
    assert 'exact.example' not in result.stdout + result.stderr
    evidence_dir = os.environ.get('REALITY_TEST_EVIDENCE_DIR')
    if evidence_dir:
        payload = dict(source_revision=os.environ['REALITY_TEST_SOURCE_SHA'],
                       tested_revision=os.environ['REALITY_TEST_TESTED_SHA'], observation=report)
        encoded = json.dumps(payload, sort_keys=True).encode()
        destination = Path(evidence_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / (hashlib.sha256(encoded).hexdigest() + '.json')).write_bytes(encoded)
    return result, report


def test_real_trusted_exact_wildcard_and_normalization(tls_site):
    result, report = run_site(tls_site, SERVER_NAMES='Exact.Example.,a.wild.example exact.example\ta.wild.example')
    assert result.returncode == 0, (report, result.stderr)
    assert report['checked_pairs'] == 2
    assert report['hygiene'] == 'passed'
    assert report['client_compatibility'] == 'unavailable'
    assert report['filtered_survival'] == 'unverified'
    assert len(tls_site[2]) == 4  # actual TLS + HTTPS for each normalized name


@pytest.mark.parametrize('name', ['a.b.wild.example', 'wild.example', 'wrong.example', 'cn-only.example'])
def test_real_certificate_rejects_wrong_identity(tls_site, name):
    result, report = run_site(tls_site, SERVER_NAMES=name)
    assert result.returncode != 0
    assert 'certificate_validation_failed' in report['reason_codes']


def test_real_untrusted_certificate_refuses(tls_site, tmp_path):
    result, report = run_site(tls_site, REALITY_CA_FILE=None)
    assert result.returncode != 0
    assert report['hygiene'] == 'failed'
    assert 'certificate_validation_failed' in report['reason_codes']


@pytest.mark.parametrize('value', ['', ', ', 'bad..example', '*.example', 'a.example/secret', '-a.example',
                                   'a.example:443', '127.0.0.1', 'é.example', 'a.example,,', 'a' * 254])
def test_invalid_names_refuse_before_network(value, monkeypatch):
    monkeypatch.setenv('TARGET', 'private.example:443'); monkeypatch.setenv('SERVER_NAMES', value)
    with pytest.raises(validator.Refused, match='invalid_names'):
        validator.load_inputs(validator.Budget())


def test_name_count_and_address_endpoint_bounds():
    with pytest.raises(validator.Refused):
        validator.names(' '.join(f'a{i}.example' for i in range(17)))
    for endpoint in ['a.example:0', 'a.example:65536', 'a.example:abc', 'a.example,b.example:443', '[a.example:443', 'a.example]:443', '::1:443']:
        with pytest.raises(validator.Refused):
            validator.endpoint(endpoint)
    assert validator.endpoint('[::1]:443') == ('::1', 443)


@pytest.mark.parametrize('stage', ['dns', 'tls', 'http', 'metadata'])
def test_stalled_stage_reclaims_real_child_group(stage, tmp_path, monkeypatch):
    child = tmp_path / 'child.pid'
    monkeypatch.setenv('PROBE_TIMEOUT', '2')
    monkeypatch.setenv('VALIDATION_TIMEOUT', '5')
    command = ["/bin/sh", "-c", 'sleep 30 & echo "$!" > "$1"; wait', "fixture", str(child)]
    start = time.monotonic()
    with pytest.raises(validator.Refused, match=stage + '_timeout'):
        validator.Budget().run(stage, command)
    assert time.monotonic() - start < 4
    pid = int(child.read_text())
    # Killed descendants can briefly remain zombies until their platform reaper runs.
    for _ in range(30):
        status = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
        if not status.stdout.strip() or status.stdout.strip().startswith('Z'):
            break
        time.sleep(.05)
    else:
        # A recorded child PID may already have been reused; assert without signalling it.
        pytest.fail('owned child survived timeout')


def test_aggregate_budget_does_not_reset_for_names(monkeypatch):
    monkeypatch.setenv('PROBE_TIMEOUT', '1'); monkeypatch.setenv('VALIDATION_TIMEOUT', '.35')
    budget = validator.Budget(); completed = 0
    start = time.monotonic()
    with pytest.raises(validator.Refused, match='aggregate_timeout'):
        for _name in validator.names('a.example,b.example,c.example'):
            budget.run('tls', [sys.executable, '-c', 'import time;time.sleep(.15)'])
            completed += 1
    assert completed < 3
    assert time.monotonic() - start < 1.5


def test_actual_stalled_tls_is_failed_and_bounded(monkeypatch):
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen()
    monkeypatch.setenv('PROBE_TIMEOUT', '.25'); monkeypatch.setenv('VALIDATION_TIMEOUT', '1')
    try:
        with pytest.raises(validator.Refused, match='tls_timeout'):
            validator.call_worker(validator.Budget(), 'tls',
                                  dict(ip='127.0.0.1', port=listener.getsockname()[1], sni='a.example'))
    finally:
        listener.close()


def test_owned_public_endpoint_and_sni_admission(tls_site, monkeypatch):
    port, _, _, _ = tls_site
    result, report = run_site(tls_site, TARGET_MODE='owned-public',
                              TARGET='127.0.0.1:8443', PUBLIC_ENDPOINT=f'127.0.0.1:{port}', OWNED_SNI='exact.example')
    assert result.returncode != 0
    assert report['reason_codes'] == ['public_endpoint_loopback']
    monkeypatch.setenv('TARGET_MODE', 'owned-public'); monkeypatch.setenv('TARGET', '127.0.0.1:8443')
    monkeypatch.setenv('SERVER_NAMES', 'owned.example'); monkeypatch.setenv('OWNED_SNI', 'owned.example')
    monkeypatch.setenv('PUBLIC_ENDPOINT', '192.0.2.7:443')
    assert validator.load_inputs(validator.Budget()) == ('owned-public', '192.0.2.7', 443, ['owned.example'])
    monkeypatch.setenv('OWNED_SNI', 'foreign.example')
    with pytest.raises(validator.Refused, match='owned_sni_mismatch'):
        validator.load_inputs(validator.Budget())


def test_invalid_client_pin_never_claims_success(tls_site, tmp_path):
    (tmp_path / 'curl-impersonate-chrome').write_text('not the supported client')
    result, report = run_site(tls_site, REALITY_CLIENT_DIR=str(tmp_path))
    assert result.returncode != 0
    assert report['client_compatibility'] == 'unavailable'
    assert report['reason_codes'] == ['client_pin_mismatch']


def test_private_input_preserved_on_failure(tls_site, tmp_path):
    authority = tmp_path / 'accepted.json'; authority.write_text('{"accepted":"unchanged-private-value"}')
    before = authority.read_bytes()
    result, report = run_site(tls_site, SERVER_NAMES='wrong.example', SOPS_FILE=str(authority))
    assert result.returncode != 0
    assert authority.read_bytes() == before
    assert 'unchanged-private-value' not in result.stdout + result.stderr
    assert report['promotion'] == 'not_authorized'



def test_real_monitor_collects_shared_tls_and_preserves_private_source(tls_site, tmp_path):
    port, _, _, ingress = tls_site
    fixture = tmp_path / 'source.json'
    fixture.write_text(json.dumps({'xray': {'target': f'{ingress}:{port}', 'server_names': ['exact.example']},
                                   'watchdog_secrets': {}}))
    fixture.chmod(0o600)
    before = fixture.read_bytes()
    bin_dir = tmp_path / 'bin'; bin_dir.mkdir()
    whois = bin_dir / 'whois'
    whois.write_text('#!/bin/sh\necho "64500 | 192.0.2.7 | 192.0.2.0/24 | XX | fixture | 2026-01-01 | fixture"\n')
    whois.chmod(0o755)
    env = {**os.environ, 'VPN_SECRETS_FILE': str(fixture), 'SOPS_FILE': str(tmp_path / 'unused'),
           'VANTAGE': 'fixture-cohort', 'TARGET_MODE': 'borrowed', 'REALITY_CA_FILE': str(tls_site[1]),
           'XDG_STATE_HOME': str(tmp_path / 'state'), 'NTFY_TOPIC': '', 'NTFY_TOKEN': '',
           'PROBE_TIMEOUT': '5', 'VALIDATION_TIMEOUT': '20', 'PATH': f"{bin_dir}:{os.environ['PATH']}"}
    for name in ('REALITY_VALIDATION_END', 'REALITY_CLIENT_DIR'):
        env.pop(name, None)
    script = ROOT / 'scripts/monitor-reality-target.sh'
    result = subprocess.run(['bash', str(script)], env=env, text=True, capture_output=True, timeout=25)
    report = json.loads(result.stdout)
    assert result.returncode == 0, (report, result.stderr)
    assert report['verdict'] == 'ok'
    assert report['baseline_created']
    assert report['observations'][0]['checks'] == 1
    assert fixture.read_bytes() == before
    assert 'exact.example' not in result.stdout + result.stderr
    # A real failed observation cannot replace accepted health with a new pass.
    listener_port = port + 1
    data = json.loads(fixture.read_text()); data['xray']['target'] = f'{ingress}:{listener_port}'
    fixture.write_text(json.dumps(data))
    failed = subprocess.run(['bash', str(script)], env=env, text=True, capture_output=True, timeout=25)
    report = json.loads(failed.stdout)
    assert report['verdict'] != 'ok'
    assert not report['baseline_created']


def test_client_fifo_refuses_without_blocking(tmp_path, monkeypatch):
    os.mkfifo(tmp_path / 'curl-impersonate-chrome')
    monkeypatch.setenv('REALITY_CLIENT_DIR', str(tmp_path))
    start = time.monotonic()
    with pytest.raises(validator.Refused, match='client_pin_mismatch'):
        validator.pinned_client()
    assert time.monotonic() - start < 1


def test_successful_command_also_reclaims_detached_child(tmp_path):
    child = tmp_path / 'pid'
    code = ("import subprocess,pathlib,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
            "pathlib.Path(%r).write_text(str(p.pid)); print('done')") % str(child)
    result = validator.Budget().run('metadata', [sys.executable, '-c', code])
    assert result.strip() == 'done'
    pid = int(child.read_text())
    status = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
    assert not status.stdout.strip() or status.stdout.strip().startswith('Z')


def test_output_flood_is_bounded(monkeypatch):
    monkeypatch.setenv('PROBE_TIMEOUT', '3')
    with pytest.raises(validator.Refused, match='metadata_unavailable'):
        validator.Budget().run('metadata', [sys.executable, '-c', "print('x'*100000)"])


def test_cancellation_reclaims_owned_stage(tmp_path):
    child = tmp_path / 'pid'
    code = "import os,time,pathlib;pathlib.Path(%r).write_text(str(os.getpid()));time.sleep(30)" % str(child)
    proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/reality_target_validation.py'),
                             'bounded', 'tls', sys.executable, '-c', code],
                            env={**os.environ, 'PROBE_TIMEOUT': '10', 'VALIDATION_TIMEOUT': '10'})
    try:
        until = time.monotonic() + 5
        while not child.exists() and time.monotonic() < until:
            time.sleep(.02)
        assert child.exists()
        proc.terminate()
        assert proc.wait(timeout=3) != 0
        pid = int(child.read_text())
        status = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
        assert not status.stdout.strip() or status.stdout.strip().startswith('Z')
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()


def test_ipv6_metadata_uses_numeric_address_without_resolving(tmp_path):
    whois = tmp_path / 'whois'
    whois.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$PROBE_ARGS"\necho "64500 | 2001:db8::7 | 2001:db8::/48 | XX | fixture | 2026-01-01 | fixture"\n')
    whois.chmod(0o755)
    env = {**os.environ, 'PATH': f"{tmp_path}:{os.environ['PATH']}", 'PROBE_ARGS': str(tmp_path / 'args')}
    result = subprocess.run(['bash', str(ROOT / 'scripts/probe-asn.sh'), '2001:db8::7'],
                            capture_output=True, text=True, env=env, timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split('\t')[:3] == ['2001:db8::7', '64500', '2001:db8::/48']
    assert '2001:db8::7' in (tmp_path / 'args').read_text()


@pytest.mark.parametrize('tls_site', ['no-san', 'expired', 'no-h2'], indirect=True)
def test_actual_missing_san_expiry_and_alpn_refuse(tls_site, request):
    variant = request.node.callspec.params['tls_site']
    result, report = run_site(tls_site, SERVER_NAMES='cn-only.example' if variant == 'no-san' else 'exact.example')
    assert result.returncode != 0
    assert ('h2_unavailable' if variant == 'no-h2' else 'certificate_validation_failed') in report['reason_codes']


@pytest.mark.parametrize('tls_site', ['large-certificate'], indirect=True)
def test_large_certificate_retains_healthy_transport_classification(tls_site):
    # Exceeds ordinary pipe buffers; TLS evidence must not depend on shell readers.
    assert tls_site[1].stat().st_size > 64 * 1024
    result, report = run_site(tls_site)
    assert result.returncode == 0, (report, result.stderr)
    assert report['hygiene'] == 'passed'
    assert report['reason_codes'] == []


@pytest.mark.parametrize("explicit", [{"TARGET": ""}, {"SERVER_NAMES": ""}, {"SERVER_NAMES": "bad/name"}])
def test_invalid_partial_input_refuses_before_private_defaults(monkeypatch, explicit):
    monkeypatch.delenv("TARGET", raising=False)
    monkeypatch.delenv("SERVER_NAMES", raising=False)
    for key, value in explicit.items():
        monkeypatch.setenv(key, value)
    budget = validator.Budget()
    monkeypatch.setattr(budget, "run", lambda *a, **kw: pytest.fail("invalid input loaded private defaults"))
    with pytest.raises(validator.Refused):
        validator.load_inputs(budget)


@pytest.mark.parametrize("public", [None, "", "bad/path"])
def test_invalid_public_endpoint_refuses_before_private_defaults(monkeypatch, public):
    monkeypatch.delenv("TARGET", raising=False)
    monkeypatch.delenv("SERVER_NAMES", raising=False)
    monkeypatch.setenv("TARGET_MODE", "owned-public")
    monkeypatch.setenv("OWNED_SNI", "owned.example")
    if public is None:
        monkeypatch.delenv("PUBLIC_ENDPOINT", raising=False)
    else:
        monkeypatch.setenv("PUBLIC_ENDPOINT", public)
    budget = validator.Budget()
    monkeypatch.setattr(budget, "run", lambda *a, **kw: pytest.fail("invalid input loaded private defaults"))
    with pytest.raises(validator.Refused, match="invalid_endpoint"):
        validator.load_inputs(budget)
