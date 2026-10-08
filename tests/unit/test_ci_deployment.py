"""Exercise confirmed CI source authority and native loopback SSH ownership."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import uuid

import pytest
from ci_deployment import confirmed_sources
import tailnet_management as tailnet

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def binding():
    public = b'synthetic-ed25519-public-blob'
    host = dict(name='ci-node', address='192.0.2.10', transport='100.64.0.2', port=2222, user='deploy', alias='192.0.2.10')
    identity = dict(DEPLOY_SOURCE_REVISION='a' * 40, DEPLOYABLE_SOURCE_DIGEST='b' * 64)
    document = dict(schema_version=1, status='configured', binding=dict(
        inventory_alias=host['name'], public_address=host['address'], ssh_port=host['port'],
        public_sources=['198.51.100.20'], approved_sources=['100.64.0.1'],
        host_key_sha256=hashlib.sha256(public).hexdigest(), source_revision=identity['DEPLOY_SOURCE_REVISION'],
        deployable_digest=identity['DEPLOYABLE_SOURCE_DIGEST']))
    nonce = 'c' * 32
    document['confirmation'] = dict(status='configured', changed=False, nonce=nonce, generation=tailnet.RECOVERY_GENERATION,
        binding_sha256=hashlib.sha256(tailnet._canonical_bytes(document['binding'])).hexdigest(),
        lease=dict(boot_id=str(uuid.uuid4()), started_ms=100, deadline_ms=300100),
        node=dict(id='node-one', hostname='vpn-enroll-' + nonce, ipv4=host['transport'], ipv6='fd7a:115c:a1e0::2'))
    contexts = [dict(user='deploy', host=remote, addr=remote, laddr=local, lport=2222)
                for remote, local in [('198.51.100.20', host['address']), ('100.64.0.1', host['transport'])]]
    document['contexts'] = contexts
    return dict(document=document, host=host, metadata=dict(provider='upcloud', env='ci-staging-test'),
                memberships=['vpn-ci-p0'], identity=identity,
                pin=b'[192.0.2.10]:2222 ssh-ed25519 ' + base64.b64encode(public) + b'\n', contexts=copy.deepcopy(contexts))


def test_confirmed_sources_are_derived_only_from_exact_bound_handoff(binding):
    assert confirmed_sources(**binding) == {'approved_sources': ['100.64.0.1']}


@pytest.mark.parametrize('case', ['prod', 'provider', 'cohort', 'multi', 'revision', 'digest', 'pin', 'port',
                                  'address', 'transport', 'contexts', 'source', 'receipt', 'lease', 'node', 'user'])
def test_confirmed_sources_refuse_cross_scope_or_unproven_context(binding, case):
    if case == 'prod': binding['metadata']['env'] = 'prod'
    elif case == 'provider': binding['metadata']['provider'] = 'vultr'
    elif case == 'cohort': binding['memberships'] = ['vpn-fullstack']
    elif case == 'multi': binding['memberships'].append('vpn-ci-p0p1')
    elif case == 'revision': binding['identity']['DEPLOY_SOURCE_REVISION'] = 'f' * 40
    elif case == 'digest': binding['identity']['DEPLOYABLE_SOURCE_DIGEST'] = 'f' * 64
    elif case == 'pin': binding['pin'] = b'[192.0.2.10]:2222 ssh-ed25519 Zm9yZWlnbg==\n'
    elif case == 'port': binding['host']['port'] = 22
    elif case == 'address': binding['host']['address'] = '192.0.2.11'
    elif case == 'transport': binding['host']['transport'] = '100.64.0.99'
    elif case == 'contexts': binding['contexts'][0]['addr'] = '198.51.100.21'
    elif case == 'source': binding['document']['binding']['approved_sources'] = ['100.64.0.3']
    elif case == 'receipt': binding['document']['confirmation']['status'] = 'pending'
    elif case == 'lease': binding['document']['confirmation']['lease']['deadline_ms'] += 1
    elif case == 'node': binding['document']['confirmation']['node']['hostname'] = 'other-node'
    else: binding['host']['user'] = 'other'
    with pytest.raises((ValueError, tailnet.Refusal)):
        confirmed_sources(**binding)


@pytest.mark.native_runtime
def test_ci_sentinel_real_loopback_sshd_pinned_key_and_owned_stop():
    """Real Linux/systemd/SSH paths; this does not claim VPN data-plane proof."""
    assert sys.platform == 'linux' and os.getuid() == 0
    user = os.environ.get('SUDO_USER', '')
    assert user and user != 'root', 'native runner must retain its invoking non-root user'
    account = pwd.getpwnam(user)
    root = Path(tempfile.mkdtemp(prefix='ci-sentinel-native-', dir=account.pw_dir))
    os.chown(root, account.pw_uid, account.pw_gid)
    command = ['sudo', '-u', user, 'env', 'HOME=' + account.pw_dir, sys.executable,
               str(ROOT / 'scripts/ci-liveness-sentinel.py')]
    try:
        result = subprocess.run([*command, 'prepare', '--root', str(root)], capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stdout + result.stderr
        owner = json.loads((root / 'owner.json').read_bytes())
        probe = subprocess.run(['sudo', '-u', user, 'ssh', 'ci-liveness', 'printf', 'native-ssh-ok'],
                               capture_output=True, timeout=10)
        assert probe.returncode == 0 and probe.stdout == b'native-ssh-ok'
        pin = root / 'known-hosts'
        original = pin.read_bytes()
        pin.write_text('ci-liveness ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINAfMmSQkvhoZSXRBZ+PGHiHP14AlvXMh13PRirPQyxG\n')
        rejected = subprocess.run(['sudo', '-u', user, 'ssh', 'ci-liveness', 'true'], capture_output=True, timeout=10)
        assert rejected.returncode != 0
        pin.write_bytes(original)
        assert owner['unit'].startswith('vpn-ci-liveness-')
    finally:
        if (root / 'owner.json').exists():
            stopped = subprocess.run([*command, 'stop', '--root', str(root)], capture_output=True, timeout=30)
            assert stopped.returncode == 0, stopped.stdout
        __import__('shutil').rmtree(root)
