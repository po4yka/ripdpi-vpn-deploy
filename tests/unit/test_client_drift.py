"""Real SOPS and shared materializer drift, privacy and transaction regressions."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import client_payload as payload
import client_delivery_identity as identities
import encrypted_client_document as encrypted
import issue_sub_token as issuer

ROOT = Path(__file__).resolve().parents[2]
MARKER = 'synthetic-sensitive-payload-marker-7F3A'


@pytest.fixture
def lab(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    key = tmp_path / 'age.key'
    subprocess.run(['age-keygen', '-o', str(key)], capture_output=True, check=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip()
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(key))
    monkeypatch.setenv('AGE_KEY', str(key))
    monkeypatch.setenv('AUDIT_ACTOR', 'fixture')
    monkeypatch.setenv('AUDIT_LOG_FILE', str(tmp_path / 'audit.age'))
    path = tmp_path / 'devices.sops.yaml'
    monkeypatch.setenv('SOPS_FILE', str(path))
    for name in ('SOPS_FILES', 'VPN_SECRETS_FILE', 'HOSTS', 'COHORTS', 'AWG_HOST', 'UTLS_FINGERPRINT'):
        monkeypatch.delenv(name, raising=False)
    document = yaml.safe_load((ROOT / 'tests/fixtures/secrets-sample.yml').read_text())
    document['hysteria']['clients'][0]['password'] = MARKER
    document['hysteria']['masquerade_url'] = 'https://vpn.example.com'
    ciphertext = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json', '--output-type', 'yaml', '/dev/stdin'],
                                input=json.dumps(document).encode(), capture_output=True, check=True).stdout
    path.write_bytes(ciphertext)
    path.chmod(0o600)
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    # Real SOPS, real renderer and crypto; only provider lookup and SSH delivery
    # are isolated. No fixture is claimed as live fleet acceptance.
    (bin_dir / 'terraform').write_text('''#!/usr/bin/env python3
import sys
key = sys.argv[-1]
print({'server_ipv4':'192.0.2.10','server_hostname':'vpn.example.com','admin_user':'admin'}.get(key, ''))
''')
    (bin_dir / 'ssh').write_text('''#!/usr/bin/env python3
import os, pathlib, sys
if '.vpn-sub-mirror' in sys.argv[-1]:
    raise SystemExit(0)
data = sys.stdin.buffer.read()
pathlib.Path(os.environ['PAYLOAD_CAPTURE'] + ('.meta' if sys.argv[-1].endswith(".meta'") else '')).write_bytes(data)
''')
    for file in bin_dir.iterdir():
        file.chmod(0o700)
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    capture = tmp_path / 'delivered.json'
    monkeypatch.setenv('PAYLOAD_CAPTURE', str(capture))
    spec = importlib.util.spec_from_file_location('client_drift', ROOT / 'scripts/client-drift.py')
    drift = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift)
    return path, capture, drift


def deliver(*args):
    return issuer.issue(issuer.argparse.Namespace(client='phone', format='ripdpi', expires=None, refresh_token=None, print_token_only=True, qr=False, **dict(args)))


def change(path, transform):
    # Deliberately corrupt/rotate synthetic authority using real SOPS, including
    # top-level deletion and bool-vs-int changes refused by ordinary writers.
    doc = payload.read_document(path)
    transform(doc)
    recipient = subprocess.check_output(['age-keygen', '-y', os.environ['SOPS_AGE_KEY_FILE']], text=True).strip()
    data = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json', '--output-type', 'yaml', '/dev/stdin'],
                          input=json.dumps(doc).encode(), capture_output=True, check=True).stdout
    path.write_bytes(data)


def test_current_real_delivery_matches_private_artifact_and_ciphertext_rewrap(lab, capsys):
    path, capture, drift = lab
    deliver()
    capsys.readouterr()
    document = payload.read_document(path)
    entry = document['client_registry']['phone']
    import jsonschema
    jsonschema.validate(document, json.loads((ROOT / 'secrets/schema.json').read_text()))
    actual = json.loads(capture.read_bytes())
    rendered, bindings = payload.materialize('phone', entry['delivery_options'], extended=True)
    assert actual == rendered
    assert entry['last_payload_identity'] == identities.digest('phone', entry['delivery_options'], actual, bindings, identities.authority(document))
    assert drift._verdict('phone')[0] == 'current'
    original = path.read_bytes()
    # A change to an unconsumed field forces actual SOPS ciphertext publication.
    change(path, lambda d: d.update(unconsumed_note='rewrapped'))
    assert path.read_bytes() != original
    assert drift._verdict('phone')[0] == 'current'
    change(path, lambda d: None)
    assert drift._verdict('phone')[0] == 'current'
    assert MARKER.encode() not in path.read_bytes()
    audit = subprocess.run(['age', '--decrypt', '-i', os.environ['AGE_KEY'], str(path.parent / 'audit.age')], capture_output=True, check=True).stdout
    record = json.loads(audit)
    assert record['action'] == 'issue-sub-token' and record['client'] == 'phone'
    for value in (MARKER, document['client_delivery_identity']['key'], entry['last_payload_identity']['digest']):
        assert value.encode() not in audit


@pytest.mark.parametrize('field', ['password', 'uuid', 'sni', 'path', 'peer', 'instance', 'parameter', 'expiry'])
def test_consumed_private_change_is_stale(lab, field, capsys):
    path, _, drift = lab
    deliver()
    capsys.readouterr()
    def mutate(d):
        if field == 'password':
            d['hysteria']['clients'][0]['password'] += '-rotated'
        elif field == 'uuid':
            d['xray']['clients'][0]['uuid'] = '11111111-1111-4111-8111-111111111111'
        elif field == 'sni':
            d['xray']['server_names'][0] = 'changed.example.com'
        elif field == 'path':
            d['xray']['xhttp_path'] = '/changed-path'
        elif field == 'peer':
            d['amneziawg_secrets']['instances'][0]['peers'][0]['preshared_key'] = 'CwsLCwsLCwsLCwsLCwsLCwsLCwsLCwsLCwsLCwsLCws='
        elif field == 'instance':
            d['amneziawg_secrets']['instances'][0]['name'] = 'awg-renamed'
            d['client_registry']['phone']['awg_binding']['instance'] = 'awg-renamed'
        elif field == 'parameter':
            d['amneziawg_secrets']['instances'][0]['jc'] += 1
        else:
            d['client_registry']['phone']['token_expires'] = '2028-01-01'
    change(path, mutate)
    assert drift._verdict('phone')[0] == 'stale'
    assert MARKER not in repr(drift._verdict('phone'))


def test_unconsumed_other_device_and_metadata_stay_current(lab, capsys):
    path, _, drift = lab
    deliver()
    capsys.readouterr()
    def mutate(d):
        d['xray']['clients'][1]['uuid'] = '22222222-2222-4222-8222-222222222222'
        d['client_registry']['phone']['issued_at'] = '2026-10-15T12:00:00Z'
    change(path, mutate)
    assert drift._verdict('phone')[0] == 'current'


@pytest.mark.parametrize('fault', ['missing', 'rotation', 'generation', 'key', 'malformed', 'version', 'legacy', 'absent', 'sources', 'permissions', 'symlink', 'hardlink', 'fifo', 'invalid-json'])
def test_authority_or_reader_failure_is_unknown_without_mutation(lab, fault, capsys):
    path, _, drift = lab
    deliver()
    capsys.readouterr()
    def mutate(d):
        if fault == 'missing':
            del d['client_delivery_identity']
        elif fault == 'rotation':
            del d['client_delivery_identity']
            identities.authority(d, create=True)
        elif fault in ('generation', 'key'):
            d['client_delivery_identity'][fault] = 'a' * (32 if fault == 'generation' else 64)
            if fault == 'key':
                # Real rotation always changes the generation with the key.
                d['client_delivery_identity']['generation'] = 'b' * 32
        elif fault == 'malformed':
            d['client_delivery_identity']['key'] = MARKER
        elif fault == 'version':
            d['client_delivery_identity']['version'] = True
        elif fault == 'legacy':
            d['client_registry']['phone']['last_payload_identity'] = dict(source='a' * 64, outputs='b' * 64)
        elif fault == 'absent':
            del d['client_registry']['phone']
        elif fault == 'sources':
            del d['client_registry']['phone']['delivery_sources']
    change(path, mutate)
    if fault == 'permissions':
        path.chmod(0o644)
    elif fault in ('symlink', 'hardlink', 'fifo'):
        moved = path.with_name('original.yaml')
        path.rename(moved)
        if fault == 'symlink':
            path.symlink_to(moved)
        elif fault == 'hardlink':
            os.link(moved, path)
        else:
            os.mkfifo(path, 0o600)
    elif fault == 'invalid-json':
        path.write_bytes(MARKER.encode())
    before = path.lstat()
    assert drift._verdict('phone')[0] == 'unknown'
    after = path.lstat()
    assert (before.st_ino, before.st_mtime_ns, before.st_size) == (after.st_ino, after.st_mtime_ns, after.st_size)
    assert MARKER not in repr(drift._verdict('phone'))


def test_registry_encryption_failure_preserves_original_authority_and_remote(lab, monkeypatch, capsys):
    path, capture, _ = lab
    deliver()
    capsys.readouterr()
    before = path.read_bytes()
    before_payload = capture.read_bytes()
    original = encrypted.run_sops
    def fail(args, **kwargs):
        if args[0] == 'set':
            raise ValueError(MARKER)
        return original(args, **kwargs)
    monkeypatch.setattr(encrypted, 'run_sops', fail)
    # operate's runner is bound at definition time; inject at the integration seam.
    operate = issuer.operate
    monkeypatch.setattr(issuer, 'operate', lambda p, t, **kw: operate(p, t, runner=fail, **kw))
    with pytest.raises(ValueError):
        deliver()
    assert path.read_bytes() == before
    assert capture.read_bytes() == before_payload
    assert not list(path.parent.glob('.devices.sops.yaml.client.*'))
    assert MARKER not in repr(capsys.readouterr())


def test_no_secret_arguments_or_diagnostic_output(lab, monkeypatch, capsys):
    path, _, drift = lab
    run = subprocess.Popen
    calls = []
    def observe(argv, *args, **kwargs):
        calls.append((argv, kwargs.get('env')))
        return run(argv, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', observe)
    deliver()
    capsys.readouterr()  # authorized bearer output
    document = payload.read_document(path)
    assert drift._verdict('phone')[0] == 'current'
    surfaces = repr(calls) + repr(capsys.readouterr())
    for secret in (MARKER, document['client_delivery_identity']['key'], document['client_registry']['phone']['last_payload_identity']['digest']):
        assert secret not in surfaces


def test_endpoint_and_renderer_failure_have_categorical_verdict(lab, monkeypatch, capsys):
    path, _, drift = lab
    deliver()
    capsys.readouterr()
    original = payload.command
    def changed(argv, **kw):
        if argv[-1] == 'server_ipv4':
            return b'192.0.2.44'
        return original(argv, **kw)
    monkeypatch.setattr(payload, 'command', changed)
    assert drift._verdict('phone')[0] == 'stale'
    monkeypatch.setattr(payload, 'command', lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(MARKER, 1)))
    assert drift._verdict('phone') == ('unknown', 'private input or materialization unavailable')


def test_refresh_keeps_expiry_and_canonical_private_choices(lab, capsys):
    path, capture, drift = lab
    args = issuer.argparse.Namespace(client='phone', format='ripdpi', expires='2027-12-31', refresh_token=None, print_token_only=True, qr=False)
    issuer.issue(args)
    token = capsys.readouterr().out.strip()
    before = json.loads(capture.read_bytes())
    auth = payload.read_document(path)['client_delivery_identity']
    args.refresh_token, args.format, args.expires = token, None, None
    issuer.issue(args)
    capsys.readouterr()
    assert json.loads(capture.read_bytes()) == before
    assert payload.read_document(path)['client_delivery_identity'] == auth
    assert drift._verdict('phone')[0] == 'current'


def test_real_command_deadline_and_private_stderr(monkeypatch):
    import time
    monkeypatch.setattr(payload, 'DEADLINE', time.monotonic() + 0.2)
    start = time.monotonic()
    with pytest.raises(ValueError, match='payload-input-unavailable'):
        payload.command([sys.executable, '-c', 'import time; time.sleep(30)'])
    assert time.monotonic() - start < 3
    monkeypatch.setattr(payload, 'DEADLINE', None)
    with pytest.raises(ValueError) as error:
        payload.command([sys.executable, '-c', 'import sys; sys.stderr.buffer.write(sys.stdin.buffer.read()); sys.exit(2)'], data=MARKER.encode())
    assert MARKER not in str(error.value)


def test_real_multi_host_delivery_preserves_exact_awg_and_private_sources(lab, monkeypatch, capsys):
    import base64
    import hashlib
    from awg_device_binding import public_key
    path, capture, drift = lab
    other = path.with_name('other.sops.yaml')
    other.write_bytes(path.read_bytes())
    other.chmod(0o600)
    def rebind(d):
        private = base64.b64encode(bytes([9]) * 32).decode()
        public = public_key(private)
        d['amneziawg_secrets']['instances'][0]['peers'][0]['public_key'] = public
        d['amneziawg_secrets']['instances'][0]['listen_port'] = 51821
        d['client_registry']['phone'].update(awg_binding=dict(provider='vultr', environment='prod', instance='awg0'), awg_private_key=private,
                                          awg_public_key_fingerprint='sha256:' + hashlib.sha256(public.encode()).hexdigest()[:16])
    change(other, rebind)
    monkeypatch.setenv('HOSTS', 'upcloud:prod,vultr:prod')
    monkeypatch.setenv('COHORTS', 'p2-udp,p2-udp')
    monkeypatch.setenv('SOPS_FILES', str(path) + ',' + str(other))
    monkeypatch.setenv('AWG_HOST', 'vultr:prod')
    deliver()
    token = capsys.readouterr().out.strip()
    before = capture.read_bytes()
    assert json.loads(before)['ripdpi']['amneziawg'][0]['peer']['endpoint'].endswith(':51821')
    assert drift._verdict('phone')[0] == 'current'
    monkeypatch.setenv('SOPS_FILES', '/unavailable,/unavailable')
    monkeypatch.setenv('UTLS_FINGERPRINT', 'firefox')
    monkeypatch.setenv('AWG_HOST', 'upcloud:prod')
    assert drift._verdict('phone')[0] == 'current'
    args = issuer.argparse.Namespace(client='phone', format=None, expires=None, refresh_token=token, print_token_only=True, qr=False)
    issuer.issue(args)
    capsys.readouterr()
    assert capture.read_bytes() == before
    assert drift._verdict('phone')[0] == 'current'


def test_same_second_refresh_republishes_with_unchanged_encrypted_registry(lab, monkeypatch, capsys):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    path, capture, drift = lab
    fixed = datetime(2026, 10, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(issuer, 'datetime', SimpleNamespace(now=lambda tz: fixed))
    deliver()
    token = capsys.readouterr().out.strip()
    before, delivered = path.read_bytes(), capture.read_bytes()
    capture.unlink()
    args = issuer.argparse.Namespace(client='phone', format=None, expires=None, refresh_token=token, print_token_only=True, qr=False)
    issuer.issue(args)
    capsys.readouterr()
    assert path.read_bytes() == before
    assert capture.read_bytes() == delivered
    assert drift._verdict('phone')[0] == 'current'


@pytest.mark.parametrize('device', ['-phone', '--device'])
def test_dispatchers_keep_leading_dash_device_names_literal(lab, device):
    path, capture, _drift = lab
    def rename(value):
        if isinstance(value, dict):
            return {device if key == 'phone' else key: rename(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rename(item) for item in value]
        return device if value == 'phone' else value
    def replace(doc):
        new = rename(doc)
        doc.clear()
        doc.update(new)
    change(path, replace)
    result = subprocess.run(['bash', str(ROOT / 'scripts/issue-sub-token.sh'), device, '--format', 'ripdpi', '--print-token-only'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    delivered = json.loads(capture.read_bytes())
    for script in ('emit-singbox.sh', 'emit-bundle.sh'):
        emitted = subprocess.run(['bash', str(ROOT / 'scripts' / script), device], capture_output=True, text=True, timeout=30)
        assert emitted.returncode == 0, emitted.stderr
        assert json.loads(emitted.stdout)['outbounds']
        assert MARKER not in emitted.stderr
        if script == 'emit-bundle.sh':
            assert json.loads(emitted.stdout) == delivered
    checked = subprocess.run(['make', '--silent', '--no-print-directory', 'client-drift', 'CLIENT=' + device, 'SOPS_FILE=' + str(path)], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert checked.returncode == 0, checked.stderr
    assert checked.stdout.startswith('current:')


def test_refresh_bearer_with_leading_dash_remains_a_literal_value(lab, monkeypatch, capsys):
    _path, capture, _drift = lab
    token = '-' + 'A' * 42
    monkeypatch.setattr(issuer.secrets, 'token_urlsafe', lambda size: token)
    deliver()
    assert capsys.readouterr().out.strip() == token
    before = capture.read_bytes()
    result = subprocess.run(['bash', str(ROOT / 'scripts/issue-sub-token.sh'), 'phone', '--refresh-token', token, '--print-token-only'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == token
    assert capture.read_bytes() == before


@pytest.mark.parametrize('invalid', ['empty-sni', 'scalar-sni', 'missing-key'])
def test_invalid_consumed_reality_authority_is_categorical_unknown(lab, invalid, capsys):
    path, _capture, drift = lab
    deliver()
    capsys.readouterr()
    def mutate(doc):
        if invalid == 'empty-sni':
            doc['xray']['server_names'] = []
        elif invalid == 'scalar-sni':
            doc['xray']['server_names'] = MARKER
        else:
            doc['xray']['reality_public_key'] = ''
    change(path, mutate)
    before = path.read_bytes()
    assert drift._verdict('phone') == ('unknown', 'private input or materialization unavailable')
    checked = subprocess.run([sys.executable, str(ROOT / 'scripts/client-drift.py'), 'phone'], capture_output=True, text=True, timeout=30)
    assert checked.returncode == 2
    assert checked.stdout.startswith('unknown:') and not checked.stderr
    assert MARKER not in checked.stdout
    assert path.read_bytes() == before


@pytest.mark.parametrize('field,format', [('xhttp-host', 'ripdpi'), ('hysteria-password', 'singbox'), ('hysteria-host', 'singbox')])
def test_empty_consumed_transport_authority_refuses(lab, field, format, capsys):
    path, _capture, drift = lab
    args = issuer.argparse.Namespace(client='phone', format=format, expires=None, refresh_token=None, print_token_only=True, qr=False)
    issuer.issue(args)
    capsys.readouterr()
    def mutate(doc):
        if field == 'hysteria-password':
            doc['hysteria']['clients'][0]['password'] = ''
        else:
            doc['nginx_xhttp']['server_name'] = ''
            if field == 'hysteria-host':
                doc['hysteria']['server_name'] = ''
    change(path, mutate)
    before = path.read_bytes()
    assert drift._verdict('phone')[0] == 'unknown'
    assert path.read_bytes() == before


def test_machine_token_mode_retains_early_exit_without_qr_side_effects(lab, monkeypatch, capsys):
    path, capture, drift = lab
    command = issuer.command
    def observe(argv, **kwargs):
        assert argv[0] != 'qrencode'
        return command(argv, **kwargs)
    monkeypatch.setattr(issuer, 'command', observe)
    args = issuer.argparse.Namespace(client='phone', format='ripdpi', expires=None, refresh_token=None, print_token_only=True, qr=True)
    assert issuer.issue(args) == 0
    out = capsys.readouterr()
    assert len(out.out.strip()) == 43 and not out.err
    assert capture.exists() and drift._verdict('phone')[0] == 'current'


def test_missing_optional_qr_encoder_retains_committed_delivery(lab, monkeypatch, capsys):
    _path, capture, drift = lab
    monkeypatch.setattr(issuer.shutil, 'which', lambda name: None)
    args = issuer.argparse.Namespace(client='phone', format='ripdpi', expires=None, refresh_token=None, print_token_only=False, qr=True)
    assert issuer.issue(args) == 0
    out = capsys.readouterr()
    assert 'skip --qr' in out.err and MARKER not in out.out + out.err
    assert capture.exists() and drift._verdict('phone')[0] == 'current'


def test_peer_public_key_rotation_is_stale_even_with_identical_export(lab, capsys):
    import base64
    import hashlib
    from awg_device_binding import public_key
    path, capture, drift = lab
    deliver()
    capsys.readouterr()
    delivered = json.loads(capture.read_bytes())
    def rotate(doc):
        private = base64.b64encode(bytes([9]) * 32).decode()
        public = public_key(private)
        doc['amneziawg_secrets']['instances'][0]['peers'][0]['public_key'] = public
        doc['client_registry']['phone']['awg_private_key'] = private
        doc['client_registry']['phone']['awg_public_key_fingerprint'] = 'sha256:' + hashlib.sha256(public.encode()).hexdigest()[:16]
    change(path, rotate)
    entry = payload.read_document(path)['client_registry']['phone']
    current, _binding = payload.materialize('phone', entry['delivery_options'], extended=True)
    assert current == delivered
    assert drift._verdict('phone')[0] == 'stale'
