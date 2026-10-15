"""Real SOPS/age enrollment, revocation, isolation and failure preservation."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from awg_client import enroll, export, config, public_key, revoke, main
import encrypted_client_document as publisher
from test_awg_device_binding import document


@pytest.fixture
def encrypted(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    identity = tmp_path / 'age.key'
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(identity))
    monkeypatch.setenv('AGE_KEY', str(identity))
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('AUDIT_LOG_FILE', str(tmp_path / 'audit.log.age'))
    monkeypatch.setenv('AUDIT_ACTOR', 'fixture')
    original = document()
    original.update(unrelated={'private': 'must-stay-encrypted'}, xray={'clients': [{'name': 'keep', 'uuid': 'other'}]})
    ciphertext = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json', '--output-type', 'yaml', '/dev/stdin'],
                                input=json.dumps(original).encode(), check=True, capture_output=True).stdout
    path = tmp_path / 'devices.sops.yaml'
    path.write_bytes(ciphertext)
    path.chmod(0o600)
    return path, original


def decrypt(path):
    return json.loads(publisher.run_sops(['--decrypt', '--output-type', 'json', str(path)]))


def issue(path, name, instance):
    return publisher.operate(path, lambda doc: enroll(doc, {}, name, 'upcloud:fixture', instance))


def test_distinct_enrollment_export_and_selected_revocation(encrypted):
    path, original = encrypted
    issue(path, 'first', 'awg0')
    issue(path, 'second', 'awg1')
    issued = decrypt(path)
    one, two = [issued['client_registry'][name] for name in ('first', 'second')]
    assert one['awg_private_key'] != two['awg_private_key']
    for index, name in enumerate(('first', 'second')):
        peer = issued['amneziawg_secrets']['instances'][index]['peers'][-1]
        assert peer['allowed_ips'] == f'10.{70 + index}.0.3/32'
        assert public_key(issued['client_registry'][name]['awg_private_key']) == peer['public_key']
        block = export(issued, {}, name, 'upcloud:fixture', f'awg{index}', '192.0.2.1')
        assert block['peer']['endpoint'] == f'192.0.2.1:{51820 + index}'
        assert config(block).count('PresharedKey = ') == 1
        assert one['awg_private_key'] not in json.dumps(block)
        assert all(item['server_private_key'] not in config(block) for item in issued['amneziawg_secrets']['instances'])
    publisher.operate(path, lambda doc: revoke(doc, {}, 'first', 'upcloud:fixture', 'awg0'))
    final = decrypt(path)
    assert final['amneziawg_secrets']['instances'][1] == issued['amneziawg_secrets']['instances'][1]
    assert final['client_registry']['second'] == two
    assert final['client_registry']['first']['awg_private_key'] == ''
    assert final['client_registry']['first']['awg_binding'] is None
    assert final['client_registry']['first']['status'] == 'issued'
    assert final['xray'] == original['xray'] and final['unrelated'] == original['unrelated']
    assert path.stat().st_mode & 0o777 == 0o600
    assert b'must-stay-encrypted' not in path.read_bytes()


@pytest.mark.parametrize('failure', ['encryption', 'verification', 'exhaustion', 'lock', 'symlink', 'hardlink', 'permissions'])
def test_refused_transaction_retains_original_ciphertext(encrypted, failure):
    path, original = encrypted
    before = path.read_bytes()
    runner = publisher.run_sops
    transform = lambda doc: enroll(doc, {}, 'first', 'upcloud:fixture', 'awg0')
    descriptor = None
    if failure == 'encryption':
        def runner(args, *, data=None):
            if args[0] == 'set':
                raise ValueError('encryption-refused')
            return publisher.run_sops(args, data=data)
    elif failure == 'verification':
        count = 0
        def runner(args, *, data=None):
            nonlocal count
            if '--decrypt' in args:
                count += 1
                if count == 2:
                    return b'{}'
            return publisher.run_sops(args, data=data)
    elif failure == 'exhaustion':
        def transform(doc):
            doc['amneziawg_secrets']['instances'][0].update(address_v4='10.70.0.1/30')
            return enroll(doc, {}, 'first', 'upcloud:fixture', 'awg0')
    elif failure == 'lock':
        descriptor = os.open(str(path) + '.new-client.lock', os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif failure == 'symlink':
        target = path.with_name('original.yaml')
        path.rename(target)
        path.symlink_to(target)
    elif failure == 'hardlink':
        os.link(path, path.with_name('alias.yaml'))
    else:
        path.chmod(0o640)
    try:
        with pytest.raises((ValueError, OSError)):
            publisher.operate(path, transform, runner=runner)
        assert path.read_bytes() == before
        assert not list(path.parent.glob('.devices.sops.yaml.client.*'))
    finally:
        if descriptor is not None:
            os.close(descriptor)


def test_ambiguous_enrollment_does_not_modify_encrypted_source(encrypted):
    path, _ = encrypted
    before = path.read_bytes()
    with pytest.raises(ValueError, match='ambiguous-device-binding'):
        issue(path, 'first', None)
    assert path.read_bytes() == before

@pytest.mark.parametrize('fault', ['existing', 'symlink', 'hardlink', 'public-directory'])
def test_cli_export_retains_existing_or_unsafe_output(encrypted, fault):
    path, _ = encrypted
    issue(path, 'first', 'awg0')
    source = decrypt(path)
    directory = path.parent / 'recipient'
    directory.mkdir(mode=0o700)
    output = directory / 'device.conf'
    prior = b'existing-recipient-artifact'
    if fault == 'existing':
        output.write_bytes(prior)
    elif fault == 'symlink':
        target = directory / 'target'
        target.write_bytes(prior); output.symlink_to(target)
    elif fault == 'hardlink':
        target = directory / 'target'
        target.write_bytes(prior); os.link(target, output)
    else:
        directory.chmod(0o755)
    script = Path(__file__).resolve().parents[2] / 'scripts/awg_client.py'
    before = path.read_bytes()
    result = subprocess.run([sys.executable, str(script), 'config', 'first', '--host', 'upcloud:fixture',
                             '--instance', 'awg0', '--endpoint', '192.0.2.1', '--output', str(output)],
                            input=json.dumps(source).encode(), capture_output=True, timeout=20)
    assert result.returncode != 0 and result.stdout == b''
    assert path.read_bytes() == before
    assert output.read_bytes() == prior if fault != 'public-directory' else not output.exists()
    assert all(item['server_private_key'].encode() not in result.stderr for item in source['amneziawg_secrets']['instances'])


def test_cli_publishes_only_a_new_private_selected_recipient(encrypted):
    path, _ = encrypted
    issue(path, 'first', 'awg0')
    source = decrypt(path)
    directory = path.parent / 'recipient'; directory.mkdir(mode=0o700)
    output = directory / 'device.conf'
    script = Path(__file__).resolve().parents[2] / 'scripts/awg_client.py'
    result = subprocess.run([sys.executable, str(script), 'config', 'first', '--host', 'upcloud:fixture',
                             '--instance', 'awg0', '--endpoint', '192.0.2.1', '--output', str(output)],
                            input=json.dumps(source).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.read_text() == config(export(source, {}, 'first', 'upcloud:fixture', 'awg0', '192.0.2.1'))
    assert source['client_registry']['first']['awg_private_key'].encode() not in result.stdout


def test_full_cleanup_handles_a_device_with_legitimately_revoked_awg(encrypted):
    from test_disposable_liveness_executor import load_module as executor_module
    from test_retire_unbound_staging_client import _load as retirement_module
    path, _ = encrypted
    issue(path, 'first', 'awg0')
    publisher.operate(path, lambda doc: revoke(doc, {}, 'first', 'upcloud:fixture', 'awg0'))
    doc = decrypt(path)
    doc['xray'] = {'clients': [{'name': 'first'}], 'cohorts': []}
    doc['hysteria'] = {'clients': [{'name': 'first'}]}
    paths = executor_module()._client_secret_paths(doc, 'first')
    assert all('amneziawg_secrets' not in item for item in paths)
    paths, final = retirement_module()._secret_plan(doc, 'first', 'upcloud:fixture')
    assert final['xray']['clients'] == [] and final['hysteria']['clients'] == []
    assert final['amneziawg_secrets'] == doc['amneziawg_secrets']
    assert all('amneziawg_secrets' not in item for item in paths)


def test_uri_issuance_publishes_private_templates_and_only_metadata(encrypted):
    path, _ = encrypted
    publisher.operate(path, lambda doc: ({**doc, 'hysteria': {'clients': [], 'masquerade_type': 'proxy', 'masquerade_url': 'https://owned.example'}}, {}))
    directory = path.parent / 'recipient'; directory.mkdir(mode=0o700)
    output = directory / 'uris.txt'
    script = Path(__file__).resolve().parents[2] / 'scripts/new-client.sh'
    result = subprocess.run(['bash', str(script), '--emit-uri', 'uri-device'],
                            env={**os.environ, 'SOPS_FILE': str(path), 'AWG_INSTANCE': 'awg0', 'OUTPUT': str(output),
                                 'HOME': str(path.parent), 'PROVIDER': 'upcloud', 'ENV': 'fixture'},
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    doc = decrypt(path)
    password = doc['hysteria']['clients'][0]['password']
    assert password in output.read_text() and password.encode() not in result.stdout + result.stderr
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(result.stdout)['output'] == str(output)


def test_unsafe_uri_destination_refuses_before_enrollment(encrypted):
    path, _ = encrypted
    directory = path.parent / 'recipient'; directory.mkdir(mode=0o700)
    output = directory / 'uris.txt'; output.write_text('prior recipient'); output.chmod(0o600)
    before = path.read_bytes()
    script = Path(__file__).resolve().parents[2] / 'scripts/new-client.sh'
    result = subprocess.run(['bash', str(script), '--emit-uri', 'uri-device'],
                            env={**os.environ, 'SOPS_FILE': str(path), 'AWG_INSTANCE': 'awg0', 'OUTPUT': str(output)},
                            capture_output=True, timeout=30)
    assert result.returncode != 0 and result.stdout == b''
    assert path.read_bytes() == before and output.read_text() == 'prior recipient'


def test_recipient_failure_rolls_back_output_and_encrypted_authority(encrypted):
    from private_client_artifact import new_output
    path, _ = encrypted
    before = path.read_bytes()
    directory = path.parent / 'recipient'; directory.mkdir(mode=0o700)
    output = directory / 'uris.txt'
    def failure(args, *, data=None):
        if args[0] == 'set':
            raise ValueError('encryption-refused')
        return publisher.run_sops(args, data=data)
    with pytest.raises(ValueError, match='encryption-refused'):
        with new_output(output) as (write, validate):
            def transaction(doc):
                changed, metadata = enroll(doc, {}, 'uri-device', 'upcloud:fixture', 'awg0')
                write('synthetic-selected-recipient-material')
                return changed, metadata
            publisher.operate(path, transaction, runner=failure, before_publish=validate)
    assert not output.exists() and path.read_bytes() == before


@pytest.mark.parametrize('fault', ['directory-sync', 'descriptor-close'])
def test_post_commit_failure_retains_enrolled_device_and_recipient(encrypted, monkeypatch, fault):
    from private_client_artifact import new_output
    path, _ = encrypted
    directory = path.parent / 'recipient'; directory.mkdir(mode=0o700)
    output = directory / 'uris.txt'
    real_replace, real_sync, real_close = os.replace, os.fsync, os.close
    committed = False
    failed = False

    def replace(source, destination):
        nonlocal committed
        real_replace(source, destination)
        committed = True

    def sync(descriptor):
        nonlocal failed
        if committed and fault == 'directory-sync' and not failed:
            failed = True
            raise OSError('injected-directory-sync')
        return real_sync(descriptor)

    def close(descriptor):
        nonlocal failed
        real_close(descriptor)
        if committed and fault == 'descriptor-close' and not failed:
            failed = True
            raise OSError('injected-descriptor-close')

    monkeypatch.setattr(publisher.os, 'replace', replace)
    monkeypatch.setattr(publisher.os, 'fsync', sync)
    monkeypatch.setattr(publisher.os, 'close', close)
    with pytest.raises(publisher.CommittedPublication) as observed:
        with new_output(output) as (write, validate):
            def transaction(doc):
                changed, metadata = enroll(doc, {}, 'uri-device', 'upcloud:fixture', 'awg0')
                write('synthetic-selected-recipient-material')
                return changed, metadata
            publisher.operate(path, transaction, before_publish=validate)
    assert observed.value.metadata['client'] == 'uri-device'
    assert output.read_text() == 'synthetic-selected-recipient-material'
    assert 'uri-device' in decrypt(path)['client_registry']
    assert not list(path.parent.glob('.devices.sops.yaml.client.*'))


def test_cli_recipient_close_failure_reports_committed_state(encrypted, monkeypatch, capsys):
    path, _ = encrypted
    publisher.operate(path, lambda doc: ({**doc, 'hysteria': {'clients': [], 'masquerade_type': 'proxy', 'masquerade_url': 'https://owned.example'}}, {}))
    directory = path.parent / 'recipient'; directory.mkdir(mode=0o700)
    output = directory / 'uris.txt'
    real_close = os.close
    failed = False

    def close(descriptor):
        nonlocal failed
        recipient = os.fstat(descriptor).st_ino == output.stat().st_ino
        real_close(descriptor)
        if recipient and not failed:
            failed = True
            raise OSError('injected-recipient-close')

    monkeypatch.setattr(os, 'close', close)
    monkeypatch.setattr(sys, 'argv', ['awg_client.py', 'enroll', 'uri-device', '--host', 'upcloud:fixture',
                                     '--instance', 'awg0', '--file', str(path), '--all-profiles', '--emit-uri', '--output', str(output)])
    assert main() == 3
    observed = capsys.readouterr()
    assert json.loads(observed.out)['publication'] == 'committed-durability-uncertain'
    doc = decrypt(path)
    password = doc['hysteria']['clients'][0]['password']
    assert password in output.read_text() and password not in observed.out + observed.err


@pytest.mark.parametrize('name', ['-phone', '--help'])
@pytest.mark.parametrize('surface', ['wrapper', 'make'])
def test_dash_prefixed_names_are_real_enrollments(encrypted, name, surface):
    path, _ = encrypted
    publisher.operate(path, lambda doc: ({**doc, 'hysteria': {'clients': [], 'masquerade_type': 'proxy', 'masquerade_url': 'https://owned.example'}}, {}))
    root = Path(__file__).resolve().parents[2]
    environment = {**os.environ, 'SOPS_FILE': str(path), 'AWG_INSTANCE': 'awg0', 'COHORT': '',
                   'HOME': str(path.parent), 'PROVIDER': 'upcloud', 'ENV': 'fixture'}
    command = (['bash', str(root / 'scripts/new-client.sh'), name] if surface == 'wrapper' else
               ['make', 'awg-issue', f'CLIENT={name}', f'SOPS_FILE={path}', 'AWG_INSTANCE=awg0', 'PROVIDER=upcloud', 'ENV=fixture'])
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert name in decrypt(path)['client_registry']
    if surface == 'make':
        result = subprocess.run(['make', 'awg-revoke', f'CLIENT={name}', f'SOPS_FILE={path}',
                                 'AWG_INSTANCE=awg0', 'PROVIDER=upcloud', 'ENV=fixture'],
                                cwd=root, env=environment, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert decrypt(path)['client_registry'][name]['awg_binding'] is None


@pytest.mark.parametrize('fault', ['none', 'encoder', 'authority'])
@pytest.mark.parametrize('surface', ['script', 'make'])
def test_uri_qr_uses_private_uri_and_preserves_committed_failure(encrypted, fault, surface):
    path, _ = encrypted
    publisher.operate(path, lambda doc: ({**doc, 'hysteria': {'clients': [], 'masquerade_type': 'proxy', 'masquerade_url': 'https://owned.example'}}, {}))
    root = Path(__file__).resolve().parents[2]
    binaries = path.parent / 'bin'; binaries.mkdir(mode=0o700)
    encoder = binaries / 'qrencode'
    # This boundary probe records exactly what the existing QR codec receives.
    encoder.write_text('#!' + sys.executable + '\nimport os,pathlib,sys\npayload=sys.stdin.buffer.read()\nif os.environ.get("QR_FAILURE"): raise SystemExit(7)\nassert payload.startswith(b"vless://") and b"hysteria2://" not in payload\npathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_bytes(payload)\n')
    encoder.chmod(0o700)
    output = path.parent / 'recipient.png'
    environment = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
                   'SOPS_FILE': str(path), 'AWG_INSTANCE': 'awg0', 'COHORT': '',
                   'HOME': str(path.parent), 'TMPDIR': str(path.parent), 'PROVIDER': 'upcloud', 'ENV': 'fixture'}
    before = path.read_bytes()
    if fault == 'authority':
        path.chmod(0o640)
    if fault == 'encoder':
        environment['QR_FAILURE'] = '1'
    command = (['bash', str(root / 'scripts/emit-qr.sh'), 'qr-device', '--type', 'uri', '--out', str(output)]
               if surface == 'script' else ['make', 'emit-qr', 'CLIENT=qr-device', 'TYPE=uri', f'OUT={output}', f'SOPS_FILE={path}'])
    result = subprocess.run(command, cwd=root,
                            env=environment, capture_output=True, timeout=30)
    assert (result.returncode == 0) == (fault == 'none'), result.stderr
    stages = list(path.parent.glob('vpn-qr.*'))
    if fault == 'authority':
        assert path.read_bytes() == before and not stages
        return
    source = decrypt(path)
    selected = next(item for item in source['xray']['clients'] if item['name'] == 'qr-device')
    assert selected['uuid'].encode() not in result.stdout + result.stderr
    if fault == 'encoder':
        assert len(stages) == 1
        recipient = stages[0] / 'recipient.uris'
        assert selected['uuid'] in recipient.read_text()
        assert recipient.stat().st_mode & 0o777 == 0o600
        assert stages[0].stat().st_mode & 0o777 == 0o700
        assert b'private URI recipient retained' in result.stderr
    else:
        assert selected['uuid'] in output.read_text()
        assert output.stat().st_mode & 0o777 == 0o600
        assert not stages


@pytest.mark.parametrize('target', ['awg1', '0awg', 'awg.0'])
def test_awg_only_reissuance_preserves_other_device_state(encrypted, target):
    path, _ = encrypted
    def rename(doc):
        doc['amneziawg_secrets']['instances'][1]['name'] = target
        return doc, {}
    publisher.operate(path, rename)
    issue(path, 'first', 'awg0')
    def metadata(doc):
        doc['client_registry']['first'].update(status='active', formats=['ripdpi'],
            token_hash_prefix='9f86d081', token_expires='2026-12-31',
            last_payload_identity={'source': 'a' * 64, 'outputs': 'b' * 64})
        return doc, {}
    publisher.operate(path, metadata)
    issued = decrypt(path)
    old_private = issued['client_registry']['first']['awg_private_key']
    publisher.operate(path, lambda doc: revoke(doc, {}, 'first', 'upcloud:fixture', 'awg0'))
    revoked = decrypt(path)
    issue(path, 'first', target)
    final = decrypt(path)
    entry = final['client_registry']['first']
    assert entry['awg_private_key'] != old_private
    assert public_key(entry['awg_private_key']) == final['amneziawg_secrets']['instances'][1]['peers'][-1]['public_key']
    assert entry['awg_binding']['instance'] == target
    retained = {k: v for k, v in revoked['client_registry']['first'].items() if not k.startswith('awg_')}
    assert {k: v for k, v in entry.items() if not k.startswith('awg_')} == retained
    assert final['xray'] == issued['xray'] and final['unrelated'] == issued['unrelated']
    assert final['amneziawg_secrets']['instances'][0] == revoked['amneziawg_secrets']['instances'][0]
    assert export(final, {}, 'first', 'upcloud:fixture', target, '192.0.2.1')['peer']['endpoint'].endswith(':51821')


def test_make_awg_defaults_are_real_enrollment_and_revocation(encrypted):
    path, _ = encrypted
    root = Path(__file__).resolve().parents[2]
    environment = {k: v for k, v in os.environ.items() if k not in ('PROVIDER', 'ENV', 'MAKEFILES', 'MAKEFLAGS', 'GNUMAKEFLAGS', 'MFLAGS')}
    for action in ('awg-issue', 'awg-revoke'):
        result = subprocess.run(['make', action, 'CLIENT=default-device', f'SOPS_FILE={path}', 'AWG_INSTANCE=awg0'],
                                cwd=root, env=environment, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        entry = decrypt(path)['client_registry']['default-device']
        assert entry['awg_binding'] == ({'provider': 'upcloud', 'environment': 'prod', 'instance': 'awg0'} if action == 'awg-issue' else None)


@pytest.mark.parametrize('fault', ['private', 'fingerprint', 'binding-missing', 'global-revoked', 'all-profiles'])
def test_invalid_reissuance_preserves_encrypted_authority(encrypted, fault):
    path, _ = encrypted
    issue(path, 'first', 'awg0')
    publisher.operate(path, lambda doc: revoke(doc, {}, 'first', 'upcloud:fixture', 'awg0'))
    def corrupt(doc):
        entry = doc['client_registry']['first']
        if fault == 'private':
            entry['awg_private_key'] = 'retained-private-material'
        elif fault == 'fingerprint':
            entry['awg_public_key_fingerprint'] = 'retained-fingerprint'
        elif fault == 'binding-missing':
            del entry['awg_binding']
        elif fault == 'global-revoked':
            entry['status'] = 'revoked'
        return doc, {}
    publisher.operate(path, corrupt)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='device-already-enrolled'):
        publisher.operate(path, lambda doc: enroll(doc, {}, 'first', 'upcloud:fixture', 'awg1', all_profiles=fault == 'all-profiles'))
    assert path.read_bytes() == before


@pytest.mark.parametrize('variable', ['CLIENT', 'SOPS_FILE', 'PROVIDER', 'ENV', 'AWG_INSTANCE', 'COHORT'])
def test_awg_make_inputs_cannot_expand_make_functions(encrypted, variable):
    path, _ = encrypted
    marker = path.parent / 'make-function-expanded'
    values = {'CLIENT': 'literal-device', 'SOPS_FILE': str(path), 'PROVIDER': 'upcloud',
              'ENV': 'fixture', 'AWG_INSTANCE': 'awg0', 'COHORT': ''}
    values[variable] = '$(shell touch ' + str(marker) + ')'
    before = path.read_bytes()
    result = subprocess.run(['make', 'awg-issue', *[key + '=' + value for key, value in values.items()]],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True, timeout=30)
    assert result.returncode != 0
    assert not marker.exists() and path.read_bytes() == before


@pytest.mark.parametrize('environment', ['Prod', '-staging', '_staging', 'prod\n'])
def test_noncanonical_host_refuses_before_encrypted_publication(encrypted, environment):
    path, _ = encrypted
    before = path.read_bytes()
    with pytest.raises(ValueError, match='invalid-host-binding'):
        publisher.operate(path, lambda doc: enroll(doc, {}, 'first', 'upcloud:' + environment, 'awg0'))
    assert path.read_bytes() == before


@pytest.mark.parametrize('position', ['source', 'lock'])
def test_fifo_authority_refuses_promptly_and_releases_writer_lock(encrypted, position):
    path, _ = encrypted
    if position == 'source':
        path.unlink()
        os.mkfifo(path, mode=0o600)
    else:
        os.mkfifo(str(path) + '.new-client.lock', mode=0o600)
    script = Path(__file__).resolve().parents[2] / 'scripts/awg_client.py'
    result = subprocess.run([sys.executable, str(script), 'enroll', 'first', '--host', 'upcloud:fixture',
                             '--instance', 'awg0', '--file', str(path)], capture_output=True, timeout=3)
    assert result.returncode == 2 and b'awg-device-operation-refused' in result.stderr
    if position == 'source':
        with open(str(path) + '.new-client.lock', 'r+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_make_audits_successful_awg_transactions_only(encrypted):
    path, _ = encrypted
    log = path.parent / 'audit.log.age'
    environment = {**os.environ, 'HOME': str(path.parent), 'AGE_KEY': str(path.parent / 'age.key'),
                   'AUDIT_LOG_FILE': str(log), 'AUDIT_ACTOR': 'fixture'}
    root = Path(__file__).resolve().parents[2]
    def invoke(action):
        return subprocess.run(['make', action, 'CLIENT=audited', f'SOPS_FILE={path}', 'AWG_INSTANCE=awg0',
                               'PROVIDER=upcloud', 'ENV=fixture'], cwd=root, env=environment, capture_output=True, timeout=30)
    for action in ('awg-issue', 'awg-revoke'):
        result = invoke(action)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['client'] == 'audited'
    assert log.exists()
    records = subprocess.run(['bash', str(root / 'scripts/audit-log.sh'), 'read'], cwd=root,
                             env=environment, capture_output=True, check=True).stdout.splitlines()
    events = [json.loads(record) for record in records]
    assert [event['action'] for event in events] == ['awg-issue', 'awg-revoke']
    assert all(event['client'] == 'audited' and event['env'] == 'fixture' and event['provider'] == 'upcloud' for event in events)
    before = log.read_bytes()
    assert invoke('awg-revoke').returncode != 0
    assert log.read_bytes() == before
