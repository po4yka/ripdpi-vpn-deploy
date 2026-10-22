"""Actual persisted activation fences; mocked PID1 is not live protocol evidence."""
import hashlib
from types import SimpleNamespace

import pytest
from test_vpn_consumer_reliability import FILES, load, put

AUTH = {'operation_id': '3fbb2baa-3a76-4f03-ae92-8ed9513fe268', 'intent_sha256': 'a' * 64}


@pytest.fixture
def barrier(private_authority_path, monkeypatch):
    core = load('transport_runtime_transaction', FILES / 'runtime-release/files/transport_runtime_transaction.py', monkeypatch)
    helper = load('device_revocation_barrier_test', FILES / 'runtime-release/files/device_revocation_barrier.py', monkeypatch)
    root = private_authority_path
    state = root / 'state'
    state.mkdir(mode=0o700)
    units = root / 'units'
    units.mkdir(mode=0o755)
    units.chmod(0o755)
    monkeypatch.setattr(helper, 'ROOT', state)
    monkeypatch.setattr(helper, 'UNIT_DIRECTORY', units)
    runtime = {'LoadState': 'loaded', 'ActiveState': 'active', 'MainPID': '123'}
    monkeypatch.setattr(helper, 'fields', lambda _unit: dict(runtime))
    monkeypatch.setattr(helper.os.path, 'samefile', lambda *_args: True)
    calls = []
    def run(argv):
        calls.append(argv)
        if argv[:2] == ['systemctl', 'stop']:
            runtime.update(ActiveState='inactive', MainPID='0')
        if argv[:2] == ['systemctl', 'restart'] or argv[:2] == ['/usr/bin/python3', '/usr/local/libexec/vpn-naive-activate.py']:
            runtime.update(ActiveState='active', MainPID='456')
        return ''
    monkeypatch.setattr(helper, 'run', run)
    return SimpleNamespace(core=core, helper=helper, root=root, units=units, state=state, runtime=runtime, calls=calls, run=run)


@pytest.mark.parametrize('unit', ['snell.service', 'caddy-naive.service'])
def test_partial_publication_and_failed_native_activation_never_restart_old_credentials(barrier, monkeypatch, unit):
    b = barrier
    config = b.root / ('config.json' if unit == 'snell.service' else 'caddy.json')
    unit_file = put(b.units / unit, 'boot-admission', 0o644)
    put(config, 'old-credential')
    wanted = {str(unit_file): hashlib.sha256(unit_file.read_bytes()).hexdigest(),
              str(config): hashlib.sha256(b'revoked-credential-absent').hexdigest()}
    activation = None
    if unit == 'caddy-naive.service':
        for name in ['server.fullchain.pem', 'server.key']:
            path = put(b.root / name, name)
            wanted[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        activation = {'server_name': 'owned.example', 'port': 443}
    payload = {'authority': AUTH, 'plan': wanted, 'activation': activation}
    assert b.helper.operate('begin', unit, payload)['changed']
    assert b.runtime['ActiveState'] == 'inactive'
    with pytest.raises(b.core.Refusal, match='revocation-resume-required'):
        b.helper.operate('guard', unit, {})
    with pytest.raises(b.core.Refusal, match='unfinished-runtime-without-publisher'):
        b.helper.operate('admit', unit, {})
    with pytest.raises(b.core.Refusal, match='revocation-service-publication-unconfirmed'):
        b.helper.operate('activate', unit, payload)
    assert b.runtime['ActiveState'] == 'inactive'
    put(config, 'revoked-credential-absent')
    before = list(b.calls)
    with pytest.raises(b.core.Refusal, match='revocation-candidate-changed'):
        b.helper.operate('begin', unit, {**payload, 'plan': {**wanted, str(config): 'b' * 64}})
    assert b.calls == before
    fail = [True]
    def reject(argv):
        # Observe real published bytes at every attempt to load the service.
        if argv[:2] == ['systemctl', 'restart'] or argv[:2] == ['/usr/bin/python3', '/usr/local/libexec/vpn-naive-activate.py']:
            assert config.read_bytes() == b'revoked-credential-absent'
            result = b.run(argv)
            if fail[0]:
                fail[0] = False
                raise b.core.Refusal('injected-readiness-failure')
            return result
        return b.run(argv)
    monkeypatch.setattr(b.helper, 'run', reject)
    with pytest.raises(b.core.Refusal, match='injected-readiness-failure'):
        b.helper.operate('activate', unit, payload)
    assert b.runtime['ActiveState'] == 'inactive'
    assert b.helper.operate('activate', unit, payload)['changed']
    assert b.runtime['ActiveState'] == 'active'
    assert b.helper.operate('admit', unit, {}) == {'changed': False}
    before = list(b.calls)
    assert not b.helper.operate('begin', unit, payload)['changed']
    assert not b.helper.operate('activate', unit, payload)['changed']
    assert before == b.calls


def test_disabled_never_installed_transport_retires_without_creating_credentials(barrier):
    b = barrier
    unit = 'snell.service'
    b.runtime.update(LoadState='not-found', ActiveState='inactive', MainPID='0')
    missing = b.root / 'never-installed' / 'config.json'
    payload = {'authority': AUTH, 'plan': {str(b.units / unit): None, str(missing): None}}
    b.helper.operate('begin', unit, payload)
    b.helper.operate('activate', unit, payload)
    assert not missing.exists() and not (b.units / unit).exists()
    assert not any(command[:2] == ['systemctl', 'restart'] for command in b.calls)


def test_barrier_check_mode_retains_current_runtime_and_creates_no_intent(barrier):
    b = barrier
    unit_file = put(b.units / 'snell.service', 'boot-admission', 0o644)
    payload = {'authority': AUTH, 'plan': {str(unit_file): hashlib.sha256(unit_file.read_bytes()).hexdigest()}, 'check': True}
    b.helper.operate('begin', 'snell.service', payload)
    assert not b.calls
    assert b.runtime['ActiveState'] == 'active'
    assert not (b.state / 'snell.service').exists()


def test_role_plan_hashes_match_actual_ansible_template_publication(tmp_path):
    """Lookup and template action must agree on whitespace and JSON text types."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    import yaml
    from template_render import merge_render_vars
    roles = Path(__file__).resolve().parents[2] / 'ansible/roles'
    values = merge_render_vars()
    tasks = []
    for index, relative in enumerate(('snell/templates/config.json.j2', 'snell/templates/snell.service.j2',
                                      'naive/templates/caddy.json.j2', 'naive/templates/caddy-naive.service.j2')):
        template = str(roles / relative)
        destination = str(tmp_path / str(index))
        tasks.extend([
            {'ansible.builtin.set_fact': {'expected': "{{ lookup('ansible.builtin.template', " + json.dumps(template) + ") | hash('sha256') }}"}},
            {'ansible.builtin.template': {'src': template, 'dest': destination, 'mode': '0600'}},
            {'ansible.builtin.stat': {'path': destination, 'checksum_algorithm': 'sha256'}, 'register': 'published'},
            {'ansible.builtin.assert': {'that': ['expected == published.stat.checksum']}},
        ])
    play = tmp_path / 'render.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
                                  'vars': {**values, 'ansible_python_interpreter': sys.executable}, 'tasks': tasks}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)], capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
