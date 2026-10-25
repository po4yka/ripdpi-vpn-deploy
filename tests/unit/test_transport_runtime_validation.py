"""Exact native validation leases refuse foreign state before cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys

import pytest


@pytest.fixture
def tmp_path(private_authority_path):
    return private_authority_path

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / 'ansible/roles/runtime-release/files'
sys.path.insert(0, str(LIBRARY))
spec = importlib.util.spec_from_file_location('transport_validation_test', LIBRARY / 'transport_runtime_validate.py')
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
from transport_runtime_transaction import Transaction, identity, node, Refusal
import transport_runtime_probe as probe
from test_public_tls_activation import tls
from test_backup_restore_profile_completeness import empty_repository


@pytest.fixture
def leased(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    root.chmod(0o755)
    for name in ('units', 'namespaces', 'staging'):
        (root / name).mkdir()
        (root / name).chmod(0o755)
    monkeypatch.setattr(validation, 'UNIT_ROOT', root / 'units')
    monkeypatch.setattr(validation, 'NAMESPACE_ROOT', root / 'namespaces')
    monkeypatch.setattr(validation, 'STAGING_ROOT', root / 'staging')
    token = 'ripdpi-candidate-' + 'a' * 16
    unit = root / 'units' / (token + '.service')
    unit.write_text('ExecStart=/owned/synthetic-runtime\n')
    unit.chmod(0o600)
    namespace = root / 'namespaces' / token
    namespace.write_text('synthetic-namespace-inode')
    namespace.chmod(0o444)
    directory = root / 'staging' / (token + '-owned')
    directory.mkdir()
    directory.chmod(0o750)
    for name in validation.FILES:
        (directory / name).write_text('synthetic-' + name)
        (directory / name).chmod(0o640)
    state = root / 'state'
    uid = os.getuid()
    monkeypatch.setattr(validation, 'boot_id', lambda: '00000000-0000-0000-0000-000000000001')
    claim = {'schema': 1, 'boot_id': validation.boot_id(), 'phase': 'prepared',
             'unit': {'name': unit.name, **node(unit, uid)},
             'namespace': {'name': namespace.name, 'identity': identity(namespace.lstat())},
             'directory': {'name': directory.name, 'identity': identity(directory.lstat())},
             'files': {name: node(directory / name, uid) for name in validation.FILES}}
    with Transaction(state, uid=uid) as tx:
        tx.record('validation.json', claim)
    calls = []
    active = [True]
    def run(argv, _timeout):
        calls.append(argv)
        if argv[1] == 'show':
            return ('LoadState=loaded\nFragmentPath=' + str(unit) + '\nActiveState='
                    + ('active' if active[0] else 'inactive') + '\nMainPID='
                    + ('42' if active[0] else '0') + '\n').encode()
        if argv[1] == 'stop':
            active[0] = False
        if argv[1:3] == ['netns', 'delete']:
            namespace.unlink()
        return b''
    monkeypatch.setattr(validation, 'run', run)
    return root, state, unit, namespace, directory, claim, calls


def test_validation_lease_stops_exact_unit_and_retires_claimed_resources(leased):
    _root, state, unit, namespace, directory, _claim, calls = leased
    with Transaction(state, uid=os.getuid()) as tx:
        assert validation.recover_validation(tx)
        assert not validation.recover_validation(tx)
    assert any(argv[1] == 'stop' for argv in calls)
    assert not unit.exists() and not namespace.exists() and not directory.exists()
    assert not (state / 'validation.json').exists()


def test_public_validation_unit_refuses_even_when_its_exact_claim_matches(leased):
    _root, state, unit, _namespace, _directory, claim, calls = leased
    unit.chmod(0o644)
    claim['unit'] = {'name': unit.name, **node(unit, os.getuid())}
    original = unit.stat().st_ino
    with Transaction(state, uid=os.getuid()) as tx:
        tx.record('validation.json', claim)
        with pytest.raises(Refusal, match='validation-lease-invalid'):
            validation.recover_validation(tx)
    assert not calls
    assert unit.stat().st_ino == original and unit.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize('kind', ['unit-bytes', 'unit-inode', 'namespace-inode',
                                   'directory-inode', 'file-inode', 'extra-file', 'malformed-lease'])
def test_foreign_validation_authority_refuses_before_stop_or_deletion(leased, kind):
    root, state, unit, namespace, directory, _claim, calls = leased
    if kind == 'unit-bytes':
        unit.write_text('ExecStart=/foreign/runtime\n')
    elif kind in {'unit-inode', 'namespace-inode', 'file-inode'}:
        selected = unit if kind == 'unit-inode' else namespace if kind == 'namespace-inode' else directory / 'server.key'
        foreign = root / 'foreign'
        foreign.write_bytes(selected.read_bytes())
        foreign.chmod(selected.stat().st_mode & 0o777)
        os.replace(foreign, selected)
    elif kind == 'directory-inode':
        os.rename(directory, root / 'retained-original')
        directory.mkdir()
        directory.chmod(0o750)
    elif kind == 'extra-file':
        (directory / 'foreign').write_text('foreign')
    else:
        (state / 'validation.json').write_text('{"schema":1,"foreign":true}')
    before = (state / 'validation.json').read_bytes()
    identities = {str(path): identity(path.lstat()) for path in (unit, namespace, directory)}
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(Refusal):
            validation.recover_validation(tx)
    assert calls == []
    assert (state / 'validation.json').read_bytes() == before
    assert {str(path): identity(path.lstat()) for path in (unit, namespace, directory)} == identities


def test_interrupted_validation_cleanup_recognizes_recorded_absence(leased, monkeypatch):
    _root, state, unit, namespace, directory, _claim, _calls = leased
    original = validation.run
    def interrupted(argv, timeout):
        if argv[1:3] == ['netns', 'delete']:
            raise SystemExit(99)
        return original(argv, timeout)
    monkeypatch.setattr(validation, 'run', interrupted)
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(SystemExit):
            validation.recover_validation(tx)
    assert not unit.exists() and namespace.exists() and directory.exists()
    assert json.loads((state / 'validation.json').read_text())['phase'] == 'cleaning'
    monkeypatch.setattr(validation, 'run', original)
    with Transaction(state, uid=os.getuid()) as tx:
        assert validation.recover_validation(tx)
    assert not namespace.exists() and not directory.exists()


def test_loaded_foreign_fragment_is_never_stopped(leased, monkeypatch):
    _root, state, unit, namespace, directory, _claim, calls = leased
    original = validation.run
    def foreign(argv, timeout):
        result = original(argv, timeout)
        return result.replace(str(unit).encode(), b'/foreign/unit.service') if argv[1] == 'show' else result
    monkeypatch.setattr(validation, 'run', foreign)
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(Refusal, match='validation-foreign-unit'):
            validation.recover_validation(tx)
    assert not any(argv[1] == 'stop' for argv in calls)
    assert unit.exists() and namespace.exists() and directory.exists()


def test_foreground_parent_death_signal_and_start_race_are_explicit(monkeypatch):
    calls = []
    class Libc:
        def prctl(self, *args):
            calls.append(args)
            return 0
    monkeypatch.setattr(probe.ctypes, 'CDLL', lambda *_args, **_kwargs: Libc())
    monkeypatch.setattr(probe.os, 'getppid', lambda: 123)
    monkeypatch.setattr(probe.os, 'kill', lambda pid, sig: calls.append(('kill', pid, sig)))
    probe.parent_death(123)
    assert calls == [(1, signal.SIGKILL, 0, 0, 0)]
    probe.parent_death(122)
    assert calls[-1] == ('kill', os.getpid(), signal.SIGKILL)


def test_unknown_namespace_process_is_not_killed_or_deleted(leased, monkeypatch):
    _root, state, unit, namespace, directory, _claim, calls = leased
    original = validation.run
    def joined(argv, timeout):
        if argv[1:3] == ['netns', 'pids']:
            calls.append(argv)
            return b'99999\n'
        return original(argv, timeout)
    monkeypatch.setattr(validation, 'run', joined)
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(Refusal, match='validation-namespace-not-empty'):
            validation.recover_validation(tx)
    assert unit.exists() and namespace.exists() and directory.exists()
    assert not any(argv[1:3] == ['netns', 'delete'] for argv in calls)
    assert json.loads((state / 'validation.json').read_text())['phase'] == 'prepared'


@pytest.mark.parametrize('foreign_manager', [False, True])
def test_proven_reboot_recovers_volatile_absence_without_adopting_new_unit(leased, monkeypatch, foreign_manager):
    _root, state, unit, namespace, directory, _claim, calls = leased
    unit.unlink()
    namespace.unlink()
    namespace.parent.rmdir()
    monkeypatch.setattr(validation, 'boot_id', lambda: '00000000-0000-0000-0000-000000000002')
    def manager(argv, _timeout):
        calls.append(argv)
        if argv[1] == 'show':
            return (b'LoadState=loaded\nFragmentPath=/foreign/new.service\nActiveState=active\nMainPID=43\n'
                    if foreign_manager else b'LoadState=not-found\nFragmentPath=\nActiveState=inactive\nMainPID=0\n')
        return b''
    monkeypatch.setattr(validation, 'run', manager)
    before = (state / 'validation.json').read_bytes()
    with Transaction(state, uid=os.getuid()) as tx:
        if foreign_manager:
            with pytest.raises(Refusal, match='validation-foreign-unit'):
                validation.recover_validation(tx)
            assert directory.exists() and (state / 'validation.json').read_bytes() == before
        else:
            assert validation.recover_validation(tx)
            assert not directory.exists() and not (state / 'validation.json').exists()
    assert all(argv[1] == 'show' for argv in calls)


def test_proven_reboot_preserves_dangling_volatile_root(leased, monkeypatch):
    root, state, unit, namespace, directory, _claim, calls = leased
    unit.unlink()
    namespace.unlink()
    namespace.parent.rmdir()
    namespace.parent.symlink_to(root/'foreign-missing-root', target_is_directory=True)
    monkeypatch.setattr(validation, 'boot_id', lambda: '00000000-0000-0000-0000-000000000002')
    before = (state/'validation.json').read_bytes()
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises((OSError, Refusal)):
            validation.recover_validation(tx)
    assert namespace.parent.is_symlink() and directory.exists()
    assert (state/'validation.json').read_bytes() == before
    assert calls == []


@pytest.mark.parametrize('binary', [None, '', 'relative/xray', '/opt/../xray', '/opt//xray'])
def test_hysteria_gateway_executable_requires_selected_absolute_authority(binary):
    with pytest.raises(Refusal, match='gateway-runtime-unavailable'):
        validation.validate_hysteria('/owned/hysteria', b'', b'', b'', '', 10, 'probe', gateway_binary=binary)


def test_native_acme_projection_uses_only_the_owned_lease_and_expected_identity(tmp_path):
    import copy
    from cryptography import x509
    policy = {'domains': ['h2.example.test'], 'email': 'operator@example.test',
              'ca': 'letsencrypt', 'dir': '/var/lib/hysteria/acme', 'type': 'http', 'http': {'altPort': 80}}
    document = {'acme': copy.deepcopy(policy), 'auth': {'type': 'userpass', 'userpass': {'probe': 'private-test-password'}},
                'listen': ':443', 'masquerade': {'proxy': {'url': 'https://site.example.test'}}}
    auth_before = copy.deepcopy(document['auth'])
    name = validation.project_hysteria_tls(document, tmp_path, None, None)
    assert name == 'h2.example.test' and 'acme' not in document
    assert document['auth'] == auth_before
    assert document['tls'] == {'cert': str(tmp_path / 'server.fullchain.pem'), 'key': str(tmp_path / 'server.key')}
    certificate = x509.load_pem_x509_certificate((tmp_path / 'server.fullchain.pem').read_bytes())
    assert certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == [name]
    client = probe.hysteria_client(document, 1080, document['tls']['cert'], 'probe', tls_server_name=name)
    assert client['tls'] == {'sni': name, 'ca': document['tls']['cert'], 'insecure': False}
    live = {'acme': policy, **{key: value for key, value in document.items() if key != 'tls'}}
    live_client = probe.hysteria_client(live, 1080, None, 'probe')
    assert live_client['tls'] == {'sni': name, 'insecure': False}


@pytest.mark.parametrize('case', ['both', 'neither', 'ca', 'cache', 'type', 'domains', 'bytes'])
def test_native_acme_projection_rejects_other_authorities(tmp_path, case):
    policy = {'domains': ['h2.example.test'], 'email': 'operator@example.test',
              'ca': 'letsencrypt', 'dir': '/var/lib/hysteria/acme', 'type': 'http', 'http': {'altPort': 80}}
    document = {'acme': policy}
    if case == 'both': document['tls'] = {'cert': 'foreign', 'key': 'foreign'}
    elif case == 'neither': document.clear()
    elif case == 'domains': policy['domains'] *= 2
    elif case == 'cache': policy['dir'] = str(tmp_path / 'foreign')
    elif case in ('ca', 'type'): policy[case] = 'foreign'
    with pytest.raises(Refusal, match='candidate-(tls|acme)-authority'):
        validation.project_hysteria_tls(document, tmp_path, b'foreign' if case == 'bytes' else None, None)


@pytest.fixture
def acme_cache(tls, tmp_path, monkeypatch):
    import shutil
    import yaml

    actual_run = validation.run
    openssl = shutil.which('openssl')
    def crypto_run(argv, timeout, **kwargs):
        if argv[0] == 'openssl':
            return actual_run([openssl, *argv[1:]], timeout, env={
                'PATH': os.environ['PATH'], 'LANG': 'C',
                'SSL_CERT_FILE': os.environ['SSL_CERT_FILE'], 'SSL_CERT_DIR': os.environ['SSL_CERT_DIR']}, **kwargs)
        return actual_run(argv, timeout, **kwargs)
    monkeypatch.setattr(validation, 'run', crypto_run)
    _module, config, issue = tls
    public, private = issue(names=[config['name']])
    root = tmp_path/'restored'
    root.mkdir(mode=0o700)
    policy = {'domains': [config['name']], 'email': config['email'], 'ca': 'letsencrypt',
              'dir': '/var/lib/hysteria/acme', 'type': 'http', 'http': {'altPort': 80}}
    document = {'acme': policy}
    cert = 'certificates/acme-v02.api.letsencrypt.org-directory/'+config['name']+'/'+config['name']
    account = 'acme/acme-v02.api.letsencrypt.org-directory/users/operator@example.test/operator'
    registration = {'status': 'valid', 'contact': ['mailto:Operator@example.test'],
                    'location': 'https://acme-v02.api.letsencrypt.org/acme/acct/123'}
    issuer = {'url': 'https://acme-v02.api.letsencrypt.org/acme/cert/test-certificate',
              'ca': 'https://acme-v02.api.letsencrypt.org/directory', 'account': registration['location']}
    files = {cert+'.crt': public.read_bytes(), cert+'.key': private.read_bytes(),
             cert+'.json': json.dumps({'sans': [config['name']], 'issuer_data': issuer}).encode(),
             account+'.json': json.dumps(registration).encode(), account+'.key': private.read_bytes()}
    for name, data in files.items():
        path = root/'var/lib/hysteria/acme'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data); path.chmod(0o600)
    configuration = root/'etc/hysteria/config.yaml'
    configuration.parent.mkdir(parents=True)
    configuration.write_text(yaml.safe_dump(document)); configuration.chmod(0o640)
    return root, document, files, cert, account


@pytest.mark.parametrize('zero_ari', [False, True])
def test_complete_cache_has_exact_domain_and_account_authority(acme_cache, zero_ari):
    root, document, files, cert, _account = acme_cache
    if zero_ari:
        value = json.loads(files[cert+'.json'])
        value['issuer_data']['renewal_info'] = {'suggestedWindow': {'start': '0001-01-01T00:00:00Z', 'end': '0001-01-01T00:00:00Z'},
            '_selectedTime': '0001-01-01T00:00:00Z'}
        files[cert+'.json'] = json.dumps(value).encode()
        (root/'var/lib/hysteria/acme'/(cert+'.json')).write_bytes(files[cert+'.json'])
    assert validation.restored_cache(root, 'etc/hysteria/config.yaml') == (document, files)


@pytest.mark.parametrize('case', ['missing-cert', 'missing-key', 'missing-meta', 'missing-account', 'missing-account-key',
    'ca', 'account', 'url', 'sans', 'symlink', 'parent-link', 'hardlink', 'oversize', 'wrong-key', 'ari-identity', 'ari-zero-explanation', 'ari-zero-identifier-type', 'ari-zero-time', 'ari-zero-id'])
def test_incomplete_or_mixed_cache_is_refused(acme_cache, case, tls):
    root, document, files, cert, account = acme_cache
    cache = root/'var/lib/hysteria/acme'
    missing = {'missing-cert': cert+'.crt', 'missing-key': cert+'.key', 'missing-meta': cert+'.json',
               'missing-account': account+'.json', 'missing-account-key': account+'.key'}
    if case in missing:
        (cache/missing[case]).unlink()
    elif case in {'ca', 'account', 'url', 'sans'} or case.startswith('ari-'):
        path = cache/(cert+'.json')
        value = json.loads(path.read_bytes())
        if case == 'sans': value['sans'] = ['foreign.example.test']
        elif case == 'ari-identity':
            value['issuer_data']['renewal_info'] = {'suggestedWindow': {'start': '2027-01-01T00:00:00Z', 'end': '2027-01-02T00:00:00Z'},
                '_selectedTime': '2027-01-01T12:00:00Z', '_uniqueIdentifier': 'foreign'}
        elif case.startswith('ari-zero'):
            ari = {'suggestedWindow': {'start': '0001-01-01T00:00:00Z', 'end': '0001-01-01T00:00:00Z'},
                   '_selectedTime': '0001-01-01T00:00:00Z'}
            if case == 'ari-zero-explanation': ari['explanationURL'] = []
            elif case == 'ari-zero-identifier-type': ari['_uniqueIdentifier'] = {'foreign': True}
            elif case == 'ari-zero-id': ari['_uniqueIdentifier'] = 'foreign'
            else: ari['_selectedTime'] = '0001-01-01 00:00:00+00:00'
            value['issuer_data']['renewal_info'] = ari
        else: value['issuer_data'][case] = 'https://foreign.example.test/'
        path.write_text(json.dumps(value))
    elif case == 'parent-link':
        directory = cache/'certificates'
        directory.rename(cache/'foreign')
        directory.symlink_to(cache/'foreign', target_is_directory=True)
    elif case == 'hardlink':
        os.link(cache/(cert+'.key'), cache/'extra.key')
    else:
        path = cache/(cert+'.key')
        if case == 'symlink':
            path.unlink(); path.symlink_to(cache/(account+'.key'))
        elif case == 'oversize': path.write_bytes(b'x'*(1024*1024+1))
        else:
            _module, _config, issue = tls
            _public, private = issue()
            path.write_bytes(private.read_bytes())
    with pytest.raises((Refusal, probe.ProbeRefused, OSError, ValueError)):
        validation.restored_cache(root, 'etc/hysteria/config.yaml')


@pytest.fixture
def cache_recovery(acme_cache, tmp_path, monkeypatch):
    import pwd
    from types import SimpleNamespace
    import yaml

    root, document, files, _cert, _account = acme_cache
    destination = tmp_path/'data/acme'
    destination.parent.mkdir(mode=0o750)
    destination.parent.chmod(0o750)
    destination.mkdir(mode=0o700)
    monkeypatch.setattr(validation, 'ACME_CACHE', destination)
    monkeypatch.setattr(validation, 'STATE', tmp_path/'state')
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()))
    monkeypatch.setattr(validation, 'unit_state', lambda name: {'LoadState': 'not-found', 'ActiveState': 'inactive', 'MainPID': '0'})
    monkeypatch.setattr(validation, 'recovery_runtime', lambda tx, binary, product: None)
    calls = []
    def native(binary, raw, certificate, key, unit, timeout, client_name, **kwargs):
        # The external Linux/systemd boundary is covered by native acceptance.
        assert yaml.safe_load(raw) == document
        assert kwargs['cache'] == files and certificate is None and key is None
        calls.append('native')
    monkeypatch.setattr(validation, 'validate_hysteria', native)
    request = {'binary': '/opt/hysteria/releases/v2.13.0/hysteria', 'gateway_binary': '/opt/xray/releases/v26.3.27/xray',
               'config': yaml.safe_dump(document), 'unit': '[Service]\nUser=hysteria\nGroup=hysteria\n',
               'client_name': 'probe', 'snapshot_id': 'a'*64}
    return root, destination, request, files, calls


@pytest.mark.parametrize('phase', ['prepared', 'validated', 'publishing', 'renamed', 'complete'])
def test_cache_recovery_retries_exact_commit_after_each_interruption(cache_recovery, monkeypatch, phase):
    root, destination, request, files, calls = cache_recovery
    before = destination.stat().st_ino
    class Interrupted(BaseException): pass
    original_record, original_rename = Transaction.record, os.rename
    def record(tx, name, value):
        original_record(tx, name, value)
        if name == 'hysteria-acme-restore.json' and value['phase'] == phase:
            raise Interrupted()
    def rename(source, target):
        original_rename(source, target)
        if target == destination: raise Interrupted()
    with monkeypatch.context() as change:
        change.setattr(Transaction, 'record', record)
        if phase == 'renamed': change.setattr(os, 'rename', rename)
        with pytest.raises(Interrupted):
            validation.recover_cache(root, 'etc/hysteria/config.yaml', request)
    journal = json.loads((validation.STATE/'hysteria-acme-restore.json').read_text())
    if phase in {'renamed', 'complete'}:
        assert destination.stat().st_ino != before
    else:
        assert not list(destination.iterdir()) and destination.stat().st_ino == before
    result = validation.recover_cache(root, 'etc/hysteria/config.yaml', request)
    assert result is (phase != 'complete')
    assert json.loads((validation.STATE/'hysteria-acme-restore.json').read_text())['phase'] == 'complete'
    assert not list(destination.parent.glob('.acme-restore-*'))
    assert {str(path.relative_to(destination)) for path in destination.rglob('*') if path.is_file()} == set(files)
    assert all(path.stat().st_uid == os.getuid() and path.stat().st_gid == os.getgid() for path in destination.rglob('*'))
    assert validation.recover_cache(root, 'etc/hysteria/config.yaml', request) is False
    assert calls


def test_failed_native_cache_admission_retains_empty_destination(cache_recovery, monkeypatch):
    root, destination, request, _files, _calls = cache_recovery
    def reject(*args, **kwargs): raise probe.ProbeRefused('client-authentication')
    monkeypatch.setattr(validation, 'validate_hysteria', reject)
    with pytest.raises(probe.ProbeRefused):
        validation.recover_cache(root, 'etc/hysteria/config.yaml', request)
    assert not list(destination.iterdir())
    assert json.loads((validation.STATE/'hysteria-acme-restore.json').read_text())['phase'] == 'prepared'


def test_real_encrypted_snapshot_retains_selected_cache_despite_newer_mixed_snapshot(acme_cache, empty_repository, tls, tmp_path):
    import shutil
    import subprocess
    from test_backup_restore_profile_completeness import PASSWORD

    root, _document, files, cert, _account = acme_cache
    repository = tmp_path/'repository'
    shutil.copytree(empty_repository, repository)
    password = tmp_path/'password'
    password.write_text(PASSWORD); password.chmod(0o600)
    environment = {**os.environ, 'RESTIC_PASSWORD_FILE': str(password), 'RESTIC_CACHE_DIR': str(tmp_path/'restic-cache')}
    restic = shutil.which('restic')
    snapshots = []
    for mixed in (False, True):
        if mixed:
            _module, _config, issue = tls
            _public, private = issue()
            (root/'var/lib/hysteria/acme'/(cert+'.key')).write_bytes(private.read_bytes())
        result = subprocess.run([restic, '-r', str(repository), 'backup', '--json', str(root)], env=environment,
                                capture_output=True, text=True, check=True, timeout=45)
        summaries = [row for line in result.stdout.splitlines() if (row := json.loads(line)).get('message_type') == 'summary']
        assert len(summaries) == 1
        snapshots.append(summaries[0]['snapshot_id'])
    assert snapshots[0] != snapshots[1]
    for index, snapshot in enumerate(snapshots):
        target = tmp_path/('snapshot-'+str(index))
        target.mkdir(mode=0o700)
        subprocess.run([restic, '-r', str(repository), 'restore', snapshot, '--target', str(target)],
                       env=environment, capture_output=True, check=True, timeout=45)
        restored = target/str(root).lstrip('/')
        if index == 0:
            assert validation.restored_cache(restored, 'etc/hysteria/config.yaml')[1] == files
        else:
            with pytest.raises(Refusal, match='acme-cache-key-mismatch'):
                validation.restored_cache(restored, 'etc/hysteria/config.yaml')
