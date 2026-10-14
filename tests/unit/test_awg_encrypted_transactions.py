"""Real SOPS/age enrollment, revocation, isolation and failure preservation."""
import copy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from awg_client import enroll, export, config, public_key, revoke
from encrypted_client_document import operate, run_sops
from test_awg_device_binding import document


@pytest.fixture
def encrypted(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    identity = tmp_path / 'age.key'
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(identity))
    original = document()
    original.update(unrelated={'private': 'must-stay-encrypted'}, xray={'clients': [{'name': 'keep', 'uuid': 'other'}]}, client_registry={})
    ciphertext = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json', '--output-type', 'yaml', '/dev/stdin'],
                                input=json.dumps(original).encode(), check=True, capture_output=True).stdout
    path = tmp_path / 'devices.sops.yaml'
    path.write_bytes(ciphertext)
    path.chmod(0o600)
    return path, original


def decrypt(path):
    return json.loads(run_sops(['--decrypt', '--output-type', 'json', str(path)]))


def issue(path, name, instance):
    return operate(path, lambda doc: enroll(doc, {}, name, 'upcloud:fixture', instance))


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
    operate(path, lambda doc: revoke(doc, {}, 'first', 'upcloud:fixture', 'awg0'))
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
    runner = run_sops
    transform = lambda doc: enroll(doc, {}, 'first', 'upcloud:fixture', 'awg0')
    descriptor = None
    if failure == 'encryption':
        def runner(args, *, data=None):
            if args[0] == 'set':
                raise ValueError('encryption-refused')
            return run_sops(args, data=data)
    elif failure == 'verification':
        count = 0
        def runner(args, *, data=None):
            nonlocal count
            if '--decrypt' in args:
                count += 1
                if count == 2:
                    return b'{}'
            return run_sops(args, data=data)
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
            operate(path, transform, runner=runner)
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
    operate(path, lambda doc: revoke(doc, {}, 'first', 'upcloud:fixture', 'awg0'))
    doc = decrypt(path)
    doc['xray'] = {'clients': [{'name': 'first'}], 'cohorts': []}
    doc['hysteria'] = {'clients': [{'name': 'first'}]}
    paths = executor_module()._client_secret_paths(doc, 'first')
    assert all('amneziawg_secrets' not in item for item in paths)
    paths, final = retirement_module()._secret_plan(doc, 'first', 'upcloud:fixture')
    assert final['xray']['clients'] == [] and final['hysteria']['clients'] == []
    assert final['amneziawg_secrets'] == doc['amneziawg_secrets']
    assert all('amneziawg_secrets' not in item for item in paths)
