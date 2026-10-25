"""Exact certificate authority and guarded renewal publication boundaries."""
import base64
import importlib.util
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from test_nginx_site_transaction import fixture

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tls(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('public_tls', ROOT / 'ansible/roles/nginx-xhttp/files/activate_public_tls.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ('LIVE', 'ARCHIVE', 'TLS', 'RENEWAL'):
        path = tmp_path / name.lower()
        path.mkdir(mode=0o700)
        monkeypatch.setattr(module, name, path)
    monkeypatch.setattr(module, 'HTTP', tmp_path / 'http.conf')
    monkeypatch.setattr(module, 'CONFIG', tmp_path / 'config.json')
    monkeypatch.setattr(module, 'APPLICATION_RECEIPT', tmp_path / 'application.json')
    monkeypatch.setattr(module, 'PUBLIC_RECEIPT', tmp_path / 'public.json')
    ca_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test CA')])
    now = datetime.now(UTC)
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
          .not_valid_after(now + timedelta(days=60)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
          .sign(ca_key, hashes.SHA256()))
    trust = tmp_path / 'ca.pem'
    trust.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    monkeypatch.setenv('SSL_CERT_FILE', str(trust))
    monkeypatch.setenv('SSL_CERT_DIR', str(tmp_path / 'no-ca-directory'))
    config = {'name': 'site.example.test', 'domains': ['site.example.test', 'www.example.test'],
              'http_vhost': 'server { listen 80; }', 'email': 'operator@example.test'}

    def issue(*, names=None, days=30, mismatch=False):
        key = ec.generate_private_key(ec.SECP256R1())
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, config['name'])]))
                .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=2)).not_valid_after(now + timedelta(days=days))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(value) for value in (names or config['domains'])]), False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False).sign(ca_key, hashes.SHA256()))
        directory = module.ARCHIVE / config['name']
        directory.mkdir(mode=0o700, exist_ok=True)
        public = directory / 'fullchain1.pem'
        private = directory / 'privkey1.pem'
        public.write_bytes(leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
        if mismatch:
            key = ec.generate_private_key(ec.SECP256R1())
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        private.chmod(0o600)
        live = module.LIVE / config['name']
        live.mkdir(mode=0o700, exist_ok=True)
        for path, target in ((live / 'fullchain.pem', public), (live / 'privkey.pem', private)):
            path.unlink(missing_ok=True)
            path.symlink_to(target)
        return public, private
    return module, config, issue


def test_fresh_http_then_exact_trusted_certificate_candidate(tls):
    module, config, issue = tls
    fresh = module.request(config, prepare=True)
    assert [row['kind'] for row in fresh['files']] == ['file', 'absent', 'absent', 'absent']
    public, private = issue()
    candidate = module.request(config)
    assert candidate['owner'] == 'public-tls' and candidate['desired_enabled'] is True
    assert [base64.b64decode(row['content_b64']) for row in candidate['files'][1:3]] == [public.read_bytes(), private.read_bytes()]
    assert [row['mode'] for row in candidate['files'][1:3]] == [0o644, 0o600]
    assert not list(module.TLS.iterdir())


@pytest.mark.parametrize('case', ['san', 'expiry', 'key', 'trust', 'mode', 'outside', 'partial', 'manual'])
def test_invalid_authority_refuses_without_writing_tls(tls, monkeypatch, case):
    module, config, issue = tls
    public, private = issue(names=['other.example.test'] if case == 'san' else None,
                            days=0 if case == 'expiry' else 30, mismatch=case == 'key')
    if case == 'trust':
        monkeypatch.setenv('SSL_CERT_FILE', '/nonexistent-test-ca')
    elif case == 'mode':
        private.chmod(0o644)
    elif case == 'outside':
        link = module.LIVE / config['name'] / 'privkey.pem'
        link.unlink()
        link.symlink_to(module.ARCHIVE.parent / 'foreign.key')
        link.resolve().write_bytes(private.read_bytes())
    elif case == 'partial':
        (module.TLS / (config['name'] + '.key')).write_bytes(private.read_bytes())
    elif case == 'manual':
        module.APPLICATION_RECEIPT.write_text(json.dumps({'files': {str(module.TLS / (config['name'] + '.key')): {}}}))
        module.APPLICATION_RECEIPT.chmod(0o600)
    before = {path.name: path.read_bytes() for path in module.TLS.iterdir()}
    with pytest.raises((module.Refusal, OSError)):
        module.request(config, prepare=case == 'partial')
    assert {path.name: path.read_bytes() for path in module.TLS.iterdir()} == before


@pytest.mark.parametrize('domains', [[], ['192.0.2.1'], ['wrong.example.test'], ['site.example.test'] * 2, ['site.example.test', 'BAD.example.test']])
def test_invalid_domain_contract_refuses_before_certificate_read(tls, domains):
    module, config, _ = tls
    config['domains'] = domains
    with pytest.raises(module.Refusal, match='invalid-certificate-contract'):
        module.request(config)


def test_preparation_retains_accepted_timer_contract_until_activation(tls):
    module, config, _ = tls
    old = {**config, 'http_vhost': 'server { listen 80; # accepted\n }'}
    module.CONFIG.write_text(json.dumps(old)); module.CONFIG.chmod(0o600)
    prepared = module.request(config, prepare=True)
    assert json.loads(base64.b64decode(prepared['files'][-1]['content_b64'])) == old
    assert json.loads(module.CONFIG.read_bytes()) == old


def test_preparation_refuses_an_unclaimed_existing_active_certificate(tls):
    module, config, issue = tls
    public, private = issue()
    for source, suffix in ((public, '.fullchain.pem'), (private, '.key')):
        path = module.TLS / (config['name'] + suffix)
        path.write_bytes(source.read_bytes()); path.chmod(0o600)
    with pytest.raises(module.Refusal, match='unclaimed-active-certificate'):
        module.request(config, prepare=True)


@pytest.mark.parametrize('missing', [None, 'config', 'claim', 'receipt', 'account-key', 'account-meta', 'account-registration', 'active-key', 'live-cert', 'bad-json'])
def test_backup_requires_complete_accepted_managed_tls_authority(tls, fixture, monkeypatch, missing):
    module, config, issue = tls
    tx, _context, _commands = fixture
    state = tx.STATE_ROOT / 'nginx.service'
    with tx.unit_lock(state):
        pass
    tx.persist(state / ('public-tls-lineage-'+config['name']+'.json'), module.lineage_claim(config))
    public, private = issue()
    document = module.request(config)
    for row in document['files']:
        row.update(uid=os.geteuid(), gid=os.getegid())
        tx.apply(Path(row['path']), {key: value for key, value in row.items() if key != 'path'}, [])
    tx.persist(module.PUBLIC_RECEIPT, tx.owned_receipt(document))
    account = module.LIVE.parent / 'accounts/acme-v02.api.letsencrypt.org/directory/test-account'
    account.mkdir(parents=True)
    for name in ('private_key.json', 'meta.json', 'regr.json'):
        path = account/name; path.write_text('{"test_account_metadata":true}'); path.chmod(0o600)
    paths = {'config': module.CONFIG, 'claim': state / ('public-tls-lineage-'+config['name']+'.json'),
             'receipt': module.PUBLIC_RECEIPT, 'account-key': account/'private_key.json',
             'account-meta': account/'meta.json', 'account-registration': account/'regr.json',
             'active-key': module.TLS/(config['name']+'.key'), 'live-cert': public}
    if missing == 'bad-json': module.CONFIG.write_text('{')
    elif missing: paths[missing].unlink()
    if missing is None:
        assert module.check_backup(tx) == {'status': 'validated', 'changed': False}
    else:
        with pytest.raises((module.Refusal, tx.TransactionError, OSError, ValueError)):
            module.check_backup(tx)
