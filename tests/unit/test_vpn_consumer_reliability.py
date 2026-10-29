"""Portable real-file transactions; lifecycle adapters do not claim native traffic."""
from __future__ import annotations

import base64
import copy
import importlib.util
import ipaddress
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles'
RUN = subprocess.run


def load(name, path, monkeypatch):
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def put(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
    path.chmod(mode)
    os.chown(path, -1, os.getgid())
    return path


def data(path, raw, mode=0o600):
    return {'path': str(path), 'data': base64.b64encode(raw).decode(), 'mode': mode, 'gid': os.getgid()}


@pytest.fixture
def context(private_authority_path, monkeypatch):
    root = private_authority_path
    tx = load('transport_runtime_transaction', FILES / 'runtime-release/files/transport_runtime_transaction.py', monkeypatch)
    fw = load('firewall_consumer', FILES / 'firewall/files/firewall_consumer.py', monkeypatch)
    awg = load('amneziawg_consumer', FILES / 'amneziawg/files/consumer.py', monkeypatch)
    owned = root / 'awg'
    owned.mkdir(mode=0o700)
    os.chown(owned, -1, os.getgid())
    record = owned / 'instances.json'
    configs = owned / 'configs'
    configs.mkdir(mode=0o700)
    os.chown(configs, -1, os.getgid())
    membership = {'schema': 1, 'config_dir': str(configs), 'instances': ['a0']}
    put(record, json.dumps(membership))
    cfg = put(configs / 'a0.conf', '[Interface]\nListenPort=51820\n[Peer]\nAllowedIPs=10.66.66.2/32, fd42::2/128\n')
    binaries = {str(put(root / 'bin' / name, 'old-runtime', 0o755)) for name in ('amneziawg-go', 'awg', 'awg-quick')}
    shared = {str(put(root / 'units' / name, 'old-unit', 0o644)) for name in ('awg-quick@.service', 'awg-quick.target')}
    for key, value in [('STATE', owned / 'runtime'), ('RECORD', record), ('BINARIES', binaries), ('SHARED', shared)]:
        monkeypatch.setattr(awg, key, value)
    monkeypatch.setattr(fw, 'STATE', root / 'firewall-runtime')
    monkeypatch.setattr(fw, 'CONFIG', root / 'nftables.conf')
    monkeypatch.setattr(fw, 'AWG_RECORD', record)
    put(fw.CONFIG, fw.HEADER + b'table inet filter {}\n', 0o644)
    monkeypatch.setattr(tx.Transaction, 'executable', lambda self, path: str(path) in binaries or Path(path).parent == root / 'acquired')
    states = {'awg-quick@a0.service': {'LoadState': 'loaded', 'ActiveState': 'active', 'UnitFileState': 'enabled', 'MainPID': '0'},
              'awg-quick.target': {'LoadState': 'loaded', 'ActiveState': 'inactive', 'UnitFileState': 'disabled', 'MainPID': '0'}}
    absent = {'LoadState': 'not-found', 'ActiveState': 'inactive', 'UnitFileState': '', 'MainPID': '0'}
    monkeypatch.setattr(awg, 'fields', lambda selected: dict(states.get(selected, absent)))
    kernel = {'bytes': fw.CONFIG.read_bytes()}
    def firewall_command(argv, *, data=None):
        if argv[:3] == ['nft', '-f', str(fw.CONFIG)]:
            kernel['bytes'] = fw.CONFIG.read_bytes()
        return b''
    monkeypatch.setattr(fw, 'command', firewall_command)
    control = {'stop_failed': False, 'still_active': False, 'restore_checks': 0, 'adoption_failed': 0, 'repair_failed': False}
    def stop(argv, **kwargs):
        if argv[:2] == ['systemctl', 'stop']:
            if not control['still_active']:
                states[argv[2]]['ActiveState'] = 'inactive'
            return SimpleNamespace(returncode=int(control['stop_failed']), stdout=b'', stderr=b'')
        raise AssertionError(argv)
    monkeypatch.setattr(awg, 'subprocess', SimpleNamespace(run=stop, PIPE=subprocess.PIPE, SubprocessError=subprocess.SubprocessError))
    before = {raw: (Path(raw).read_bytes(), Path(raw).stat().st_ino) for raw in binaries | shared | {str(cfg), str(record)}}
    def run(argv):
        if argv[:2] == ['systemctl', 'show']:
            return ''
        if argv[:2] == ['systemctl', 'enable']:
            states.setdefault(argv[2], dict(absent)).update(LoadState='loaded', UnitFileState='enabled')
        elif argv[:2] == ['systemctl', 'disable']:
            states[argv[2]]['UnitFileState'] = 'disabled'
        elif argv[:2] == ['systemctl', 'start']:
            if control['repair_failed']:
                raise tx.Refusal('injected-repair-failure')
            if any(Path(raw).read_bytes().startswith(b'bad') for raw in binaries | shared):
                control['adoption_failed'] += 1
                raise tx.Refusal('injected-adoption-failure')
            # Actual old bytes and inodes must be back before recovery starts.
            for raw, (content, inode) in before.items():
                if control['adoption_failed'] and raw in binaries | shared:
                    assert Path(raw).read_bytes() == content and Path(raw).stat().st_ino == inode
            control['restore_checks'] += 1
            states.setdefault(argv[2], dict(absent)).update(LoadState='loaded', ActiveState='active')
        return ''
    monkeypatch.setattr(awg, 'run', run)
    with tx.Transaction(awg.STATE, uid=os.geteuid(), awg=True) as active:
        active.record('accepted.json', {'schema': 1, 'nodes': {raw: active._node(Path(raw)) for raw in before}, 'previous': None, 'units': awg.Adapter().inspect()})
    return SimpleNamespace(root=root, tx=tx, fw=fw, awg=awg, before=before, binaries=binaries, shared=shared,
                           record=record, cfg=cfg, membership=membership, kernel=kernel, states=states, control=control)


@pytest.mark.parametrize('rejected', ['binary', 'unit'])
def test_rejected_complete_generation_restores_old_binary_unit_config_and_firewall(context, rejected):
    c = context
    plan = []
    for raw in c.binaries:
        source = put(c.root / 'acquired' / Path(raw).name, 'bad-runtime' if rejected == 'binary' else 'old-runtime', 0o755)
        plan.append({'path': raw, 'source': str(source), 'sha256': c.tx.node(source, os.geteuid())['sha256'], 'mode': 0o755, 'gid': os.getgid()})
    for raw in c.shared:
        plan.append(data(raw, b'bad-unit' if rejected == 'unit' else b'old-unit', 0o644))
    plan += [data(c.cfg, b'candidate-config'), data(c.record, json.dumps(c.membership).encode())]
    old_firewall = c.fw.CONFIG.read_bytes()
    with pytest.raises(c.tx.Refusal, match='candidate-refused'):
        c.awg.operate('apply', {'candidates': plan, 'firewall': base64.b64encode(c.fw.HEADER + b'table inet filter { # candidate\n}\n').decode()})
    assert c.control['adoption_failed'] == 1
    assert c.control['restore_checks'] > 0
    for raw, (content, inode) in c.before.items():
        assert Path(raw).read_bytes() == content
        assert Path(raw).stat().st_ino == inode
    assert c.fw.CONFIG.read_bytes() == old_firewall == c.kernel['bytes']
    assert c.awg.operate('recover', {})['changed'] is False


def test_failed_stop_ack_can_compensate_only_after_proven_quiescence(context):
    c = context
    c.control['stop_failed'] = True
    c.awg.Adapter().stop()
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'inactive'
    c.states['awg-quick@a0.service']['ActiveState'] = 'active'
    c.control['still_active'] = True
    with pytest.raises(c.tx.Refusal, match='awg-stop-unconfirmed'):
        c.awg.Adapter().stop()


def test_accepted_policy_reader_never_uses_changed_desired_peer_authority(context):
    assert context.fw.accepted_awg() == [{'name': 'a0', 'listen_port': 51820, 'peers': [
        {'allowed_ips': {'ipv4': '10.66.66.2/32', 'ipv6': 'fd42::2/128'}}]}]
    # A tagged request can have any new desired peer material; publication reads
    # only the private exact membership/config authority above.
    context.membership['instances'] = ['different-desired-instance']
    assert context.fw.accepted_awg()[0]['name'] == 'a0'


def test_unselected_protected_port_change_refuses_before_firewall_publication(context):
    c = context
    old = c.fw.HEADER + b'    # Public listener contract: xray (tcp/443)\n'
    put(c.fw.CONFIG, old, 0o644)
    desired = c.fw.HEADER + b'    # Public listener contract: xray (tcp/8443)\n'
    with pytest.raises(c.tx.Refusal, match='firewall-protected-consumer-required'):
        c.fw.operate('apply', {'data': base64.b64encode(desired).decode(), 'allow_listener_change': False})
    assert c.fw.CONFIG.read_bytes() == old
    assert not (c.fw.STATE / 'consumer.json').exists()


def test_initial_firewall_restores_accepted_policy_on_failure_before_awg(context):
    c = context
    old = c.fw.CONFIG.read_bytes()
    candidate = c.fw.HEADER + b'table inet filter { # changed protected port\n}\n'
    assert c.fw.operate('apply', {'data': base64.b64encode(candidate).decode()})['changed']
    assert c.kernel['bytes'] == candidate
    assert c.fw.operate('restore', {'owner': 'site'})['changed']
    assert c.fw.CONFIG.read_bytes() == c.kernel['bytes'] == old
    assert c.cfg.read_bytes().startswith(b'[Interface]')

class FileLifecycle:
    """No process evidence; exercise the actual bounded inode/WAL publisher."""
    def retained(self, receipt): pass
    def validate(self): pass
    def validate_units(self, value): assert value == {}
    def inspect(self): return {}
    def stop(self): pass
    def start(self): pass
    def restore(self, values): pass
    def ready(self): pass
    def ensure(self): return False


def test_repeated_32_instance_renames_prune_only_retired_owned_authority(context):
    c = context
    state = c.root / 'prune-runtime'
    previous = []
    foreign = put(c.root / 'foreign.conf', b'foreign')
    with c.tx.Transaction(state, uid=os.geteuid(), awg=True) as active:
        for generation in range(7):
            selected = [c.root / f'g{generation}-{index}.conf' for index in range(32)]
            candidates = [data(path, b'private fixture') for path in selected]
            candidates += [{'path': str(path), 'absent': True} for path in previous]
            assert active.apply(candidates, FileLifecycle())['status'] == 'accepted'
            c.awg.prune_retired(active)
            receipt = active.accepted()
            assert set(receipt['nodes']) == set(map(str, selected))
            assert len(active.backups()['nodes']) <= 32
            assert not any(path.exists() for path in previous)
            previous = selected
    assert foreign.read_bytes() == b'foreign'


def test_retired_claim_cleanup_resumes_after_receipt_write_failure(context, monkeypatch):
    c = context
    first, second = c.root / 'first.conf', c.root / 'second.conf'
    with c.tx.Transaction(c.root / 'prune-runtime', uid=os.geteuid(), awg=True) as active:
        active.apply([data(first, b'old')], FileLifecycle())
        active.apply([data(second, b'new'), {'path': str(first), 'absent': True}], FileLifecycle())
        original = active.record
        def interrupted(name, value):
            if name == 'accepted.json':
                raise SystemExit('injected process death')
            return original(name, value)
        monkeypatch.setattr(active, 'record', interrupted)
        with pytest.raises(SystemExit):
            c.awg.prune_retired(active)
        assert (active.root / 'retirement.json').exists()
        monkeypatch.setattr(active, 'record', original)
        c.awg.prune_retired(active)
        assert set(active.accepted()['nodes']) == {str(second)}
        assert not (active.root / 'retirement.json').exists()


def unchanged_plan(c):
    result = []
    for raw in c.binaries:
        source = put(c.root / 'acquired' / Path(raw).name, Path(raw).read_bytes(), 0o755)
        result.append({'path': raw, 'source': str(source), 'sha256': c.tx.node(source, os.geteuid())['sha256'], 'mode': 0o755, 'gid': os.getgid()})
    result += [data(raw, Path(raw).read_bytes(), 0o644) for raw in c.shared]
    result += [data(c.cfg, c.cfg.read_bytes()), data(c.record, c.record.read_bytes())]
    return result


def test_firewall_only_failed_runtime_repair_restores_uncommitted_policy(context):
    c = context
    c.states['awg-quick@a0.service']['ActiveState'] = 'inactive'
    c.control['repair_failed'] = True
    old = c.fw.CONFIG.read_bytes()
    candidate = c.fw.HEADER + b'table inet filter { # unaccepted policy\n}\n'
    with pytest.raises(c.tx.Refusal, match='injected-repair-failure'):
        c.awg.operate('apply', {'candidates': unchanged_plan(c), 'firewall': base64.b64encode(candidate).decode()})
    assert c.fw.CONFIG.read_bytes() == c.kernel['bytes'] == old
    assert not (c.awg.STATE / 'firewall.json').exists()
    assert not (c.fw.STATE / 'consumer.json').exists()
    c.awg.operate('recover', {})
    assert c.fw.CONFIG.read_bytes() == old


def test_complete_check_mode_changes_no_runtime_or_policy_authority(context):
    c = context
    original = {raw: (Path(raw).read_bytes(), Path(raw).stat().st_ino) for raw in c.before}
    plan = unchanged_plan(c)
    plan[-2] = data(c.cfg, b'predicted-private-config')
    result = c.awg.operate('apply', {'check': True, 'candidates': plan,
                                  'firewall': base64.b64encode(c.fw.CONFIG.read_bytes()).decode()})
    assert result['status'] == 'predicted' and result['changed']
    assert {raw: (Path(raw).read_bytes(), Path(raw).stat().st_ino) for raw in original} == original
    assert not (c.awg.STATE / 'firewall.json').exists()
    assert not c.fw.STATE.exists()


def test_complete_disable_then_reenable_and_retry_keep_receipts_coherent(context):
    c = context
    reenabling = unchanged_plan(c)
    retiring = [{'path': raw, 'absent': True} for raw in c.shared | {str(c.cfg), str(c.record)}]
    assert c.awg.operate('apply', {'candidates': retiring})['changed']
    assert not c.record.exists() and not c.cfg.exists()
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'inactive'
    assert c.states['awg-quick@a0.service']['UnitFileState'] == 'disabled'
    assert c.awg.operate('apply', {'candidates': reenabling})['changed']
    assert c.record.exists() and c.cfg.exists()
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'active'
    assert not c.awg.operate('apply', {'candidates': reenabling})['changed']


def test_fresh_refusal_disables_candidate_before_shared_unit_removal(context):
    c = context
    adapter = c.awg.Adapter()
    adapter.transaction = SimpleNamespace(journal=lambda: {'units': {'awg-quick@a0.service': {'LoadState': 'not-found'}}})
    adapter.stop()
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'inactive'
    assert c.states['awg-quick@a0.service']['UnitFileState'] == 'disabled'


@pytest.mark.parametrize('directory', ['/etc/x%y', '/etc/x y', '/etc/a/../b', '/etc/x"y', '/etc/x\ny'])
def test_configuration_directory_cannot_change_systemd_or_shell_interpretation(context, directory):
    with pytest.raises(context.tx.Refusal, match='awg-membership-invalid'):
        context.awg.names({'schema': 1, 'config_dir': directory, 'instances': ['a0']})


def test_actual_check_mode_policy_reader_composition_compiles_and_runs(context, tmp_path):
    import sys
    import yaml
    c = context
    tasks = yaml.safe_load((FILES / 'firewall/tasks/consumer-prepare.yml').read_text())
    task = next(row for row in tasks if row['name'] == 'Read only exact owned accepted AWG firewall claims')
    expression = task['ansible.builtin.command']['argv'][2]
    rendered = tmp_path / 'reader.py'
    play = [{'hosts': 'localhost', 'connection': 'local', 'become': False, 'gather_facts': False,
             'vars': {'role_path': str(FILES / 'firewall'), 'ansible_python_interpreter': sys.executable},
             'tasks': [{'name': 'Render actual policy reader expression', 'ansible.builtin.copy': {
                 'content': expression, 'dest': str(rendered), 'mode': '0600'}, 'no_log': True}]}]
    playbook = tmp_path / 'render.yml'
    playbook.write_text(yaml.safe_dump(play))
    result = RUN(['ansible-playbook', '-i', 'localhost,', str(playbook)], capture_output=True,
        text=True, timeout=30, env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    assert result.returncode == 0, result.stdout + result.stderr
    combined = rendered.read_text()
    namespace = {'__name__': 'owned_composite_fixture'}
    exec(compile(combined, '<actual-firewall-policy-reader>', 'exec'), namespace)
    # The executed source reads exact owned scratch metadata/configuration and
    # returns the old claims, without relying on an installed helper in check mode.
    namespace['AWG_RECORD'] = c.record
    assert namespace['accepted_awg']()[0]['peers'][0]['allowed_ips']['ipv4'] == '10.66.66.2/32'



def test_awg_check_mode_predicts_changes_without_lifecycle_or_file_mutation(context, monkeypatch):
    c = context
    before = {str(path): (path.read_bytes(), path.stat().st_ino)
              for path in c.root.rglob('*') if path.is_file()}
    old_firewall = c.kernel['bytes']
    def forbidden(*args, **kwargs):
        raise AssertionError('check mode must not activate, repair, compensate or probe runtime')
    for callback in ['stop', 'start', 'restore', 'ensure', 'ready', 'inspect']:
        monkeypatch.setattr(c.awg.Adapter, callback, forbidden)
    firewall = c.awg.firewall
    def predictive_firewall(action, payload):
        assert action == 'apply' and payload['check'] is True
        return firewall(action, payload)
    monkeypatch.setattr(c.awg, 'firewall', predictive_firewall)
    result = c.awg.operate('apply', {'check': True, 'candidates': [data(c.cfg, b'changed-config')],
        'firewall': base64.b64encode(c.fw.HEADER + b'table inet filter { # predicted\n}\n').decode()})
    assert result == {'status': 'predicted', 'changed': True, 'published': False}
    after = {str(path): (path.read_bytes(), path.stat().st_ino)
             for path in c.root.rglob('*') if path.is_file()}
    assert after == before
    assert c.fw.CONFIG.read_bytes() == c.kernel['bytes'] == old_firewall
    for name in ['pending.json', 'preparation.json', 'compensating.json', 'firewall.json', 'retirement.json']:
        assert not (c.awg.STATE / name).exists()
    assert not (c.fw.STATE / 'consumer.json').exists()


@pytest.mark.parametrize('layout', ['fresh', 'existing', 'symlink', 'check'])
def test_actual_firewall_preparation_owns_fresh_runtime_parent(context, monkeypatch, layout):
    import copy
    import stat
    import sys
    import yaml
    c = context
    parent = c.root / 'ripdpi'
    target = c.root / 'foreign-parent'
    monkeypatch.setattr(c.fw, 'STATE', parent / 'firewall-runtime')
    if layout == 'existing':
        parent.mkdir(mode=0o700)
    elif layout == 'symlink':
        target.mkdir(mode=0o700)
        parent.symlink_to(target, target_is_directory=True)
    prepare = yaml.safe_load((FILES / 'firewall/tasks/consumer-prepare.yml').read_text())
    boundary = next(i for i, task in enumerate(prepare) if task['name'] == 'Ensure the shared retained consumer helper directory')
    guard = copy.deepcopy(yaml.safe_load((FILES / 'runtime-release/tasks/consumer-authority.yml').read_text())[0])
    authority = (FILES / 'runtime-release/files/consumer_authority.py').read_text()
    # Confine only ownership/path observations to this fixture. Keep the actual
    # no-follow, type, mode and private-leaf admission code unchanged.
    authority = authority.replace("Path('/usr/local/libexec/ripdpi-consumer')",
        "Path(" + repr(str(c.root / 'helpers')) + ")")
    authority = authority.replace('[*reversed(path.parents), path]',
        f"[current for current in [*reversed(path.parents), path] if current == Path({str(c.root)!r}) or Path({str(c.root)!r}) in current.parents]")
    authority = authority.replace('info.st_uid != 0', f'info.st_uid != {os.geteuid()}')
    guard['ansible.builtin.command']['argv'] = [sys.executable, '-c', authority]
    guard['vars'] = copy.deepcopy(prepare[0].get('vars', {}))
    for key in ['consumer_private_directories', 'consumer_guard_directories']:
        if key in guard['vars']:
            guard['vars'][key] = [value.replace('/var/lib/ripdpi', str(parent)) for value in guard['vars'][key]]
    selected = [guard, *copy.deepcopy(prepare[1:boundary])]
    for task in selected[1:]:
        for module in ['ansible.builtin.stat', 'ansible.builtin.file']:
            if module in task:
                args = task[module]
                args['path'] = args['path'].replace('/var/lib/ripdpi', str(parent))
                args.pop('owner', None)
                args.pop('group', None)
    path = c.root / 'prepare-firewall.yml'
    path.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'become': False, 'vars': {'ansible_python_interpreter': sys.executable}, 'tasks': selected}]))
    argv = ['ansible-playbook', '-i', 'localhost,', str(path)] + (['--check'] if layout == 'check' else [])
    result = RUN(argv, capture_output=True, text=True, timeout=30,
        env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    if layout == 'symlink':
        assert result.returncode != 0
        assert parent.is_symlink() and stat.S_IMODE(target.stat().st_mode) == 0o700
        assert not c.fw.STATE.exists()
        return
    assert result.returncode == 0, result.stdout + result.stderr
    raw = base64.b64encode(c.fw.HEADER + b'table inet filter { # retained candidate\n}\n').decode()
    publication = c.fw.operate('apply', {'check': layout == 'check', 'data': raw, 'owner': 'site'})
    assert publication['changed'] is True
    if layout == 'check':
        assert not parent.exists()
    else:
        assert stat.S_IMODE(parent.stat().st_mode) == (0o700 if layout == 'existing' else 0o755)
        assert (c.fw.STATE / 'consumer.json').exists()
        assert c.fw.CONFIG.read_bytes() == c.kernel['bytes'] == base64.b64decode(raw)


def test_repeated_retirement_accepts_firewall_without_runtime_republication(context, monkeypatch):
    c = context
    plan = [{'path': raw, 'absent': True} for raw in c.shared | {str(c.cfg), str(c.record)}]
    policy = base64.b64encode(c.fw.CONFIG.read_bytes()).decode()
    assert c.awg.operate('apply', {'candidates': plan, 'firewall': policy})['changed']
    with c.tx.Transaction(c.awg.STATE, uid=os.geteuid(), awg=True) as active:
        assert {raw for raw, claim in active.accepted()['nodes'].items() if claim is None} == c.shared | {str(c.record)}
    paths = c.binaries | c.shared | {str(c.cfg), str(c.record), str(c.awg.STATE / 'accepted.json')}
    def observed():
        return {raw: (Path(raw).read_bytes(), Path(raw).stat().st_ino) if Path(raw).exists() else None for raw in paths}
    before = observed()
    calls = []
    for name in ['ensure', 'ready']:
        original = getattr(c.awg.Adapter, name)
        def checked(self, _name=name, _original=original):
            calls.append(_name)
            return _original(self)
        monkeypatch.setattr(c.awg.Adapter, name, checked)
    def forbidden(*args, **kwargs):
        raise AssertionError('accepted retirement must not republish runtime or change lifecycle')
    for name in ['stop', 'start', 'restore']:
        monkeypatch.setattr(c.awg.Adapter, name, forbidden)
    monkeypatch.setattr(c.tx.Transaction, 'replace', forbidden)
    record = c.tx.Transaction.record
    def checked_record(self, name, value):
        if self.root == c.awg.STATE and name in {'pending.json', 'preparation.json', 'compensating.json', 'retirement.json'}:
            forbidden()
        return record(self, name, value)
    monkeypatch.setattr(c.tx.Transaction, 'record', checked_record)
    firewall = c.awg.firewall
    def checked_firewall(action, payload):
        calls.append('firewall-' + action)
        return firewall(action, payload)
    monkeypatch.setattr(c.awg, 'firewall', checked_firewall)
    repeated = [{'path': raw, 'absent': True} for raw in c.shared | {str(c.record)}]
    result = c.awg.operate('apply', {'candidates': repeated, 'firewall': policy})
    assert result == {'status': 'accepted', 'changed': False, 'published': False}
    assert calls == ['ensure', 'firewall-apply', 'ready', 'firewall-finish']
    assert observed() == before
    assert c.fw.CONFIG.read_bytes() == c.kernel['bytes'] == base64.b64decode(policy)
    assert not (c.awg.STATE / 'firewall.json').exists()
    assert not (c.fw.STATE / 'consumer.json').exists()


@pytest.mark.parametrize('tampered', [False, True])
def test_legacy_retirement_cleanup_resumes_only_exact_old_authority(context, monkeypatch, tampered):
    c = context
    fixed, dynamic = str(c.root / 'fixed.service'), str(c.root / 'retired.conf')
    monkeypatch.setattr(c.awg, 'SHARED', {fixed})
    with c.tx.Transaction(c.root / 'legacy-prune', uid=os.geteuid(), awg=True) as active:
        before = {'schema': 1, 'nodes': {fixed: None, dynamic: None}, 'previous': None, 'units': {}}
        after = {**before, 'nodes': {}}
        active.record('accepted.json', before)
        active.record('retirement.json', {'schema': 1, 'before': before, 'after': after,
            'backups': None, 'next_backups': None, 'retired': [dynamic] if tampered else [fixed, dynamic], 'last': None})
        if tampered:
            with pytest.raises(c.tx.Refusal, match='awg-retirement-invalid'):
                c.awg.prune_retired(active)
            assert active.accepted() == before
            assert (active.root / 'retirement.json').exists()
        else:
            c.awg.prune_retired(active)
            assert active.accepted() == after
            assert not (active.root / 'retirement.json').exists()


@pytest.mark.parametrize('failure', ['native-ready', 'firewall-apply'])
def test_revocation_keeps_new_peers_and_policy_stopped_until_exact_forward_resume(context, monkeypatch, failure):
    c = context
    authority = {'operation_id': '3fbb2baa-3a76-4f03-ae92-8ed9513fe268', 'intent_sha256': 'a' * 64}
    candidate = b'[Interface]\nListenPort=51820\n# revoked peer removed\n'
    policy = c.fw.HEADER + b'table inet filter { # revoked claim removed\n}\n'
    payload = {'candidates': [data(c.cfg, candidate)], 'firewall': base64.b64encode(policy).decode(), 'revocation': authority}
    starts = []
    native_run = c.awg.run
    def run(argv):
        if argv[:2] == ['systemctl', 'start']:
            starts.append((c.cfg.read_bytes(), c.kernel['bytes']))
        return native_run(argv)
    monkeypatch.setattr(c.awg, 'run', run)
    attempts = []
    if failure == 'native-ready':
        ready = c.awg.Adapter.ready
        def reject(self):
            if not attempts:
                attempts.append('failed')
                raise c.tx.Refusal('injected-native-ready-failure')
            return ready(self)
        monkeypatch.setattr(c.awg.Adapter, 'ready', reject)
    else:
        command = c.fw.command
        def reject(argv, **kwargs):
            result = command(argv, **kwargs)
            if argv[:2] == ['nft', '-f'] and not attempts:
                attempts.append('failed')
                raise c.tx.Refusal('injected-firewall-apply-failure')
            return result
        monkeypatch.setattr(c.fw, 'command', reject)
    with pytest.raises(c.tx.Refusal, match='candidate-refused'):
        c.awg.operate('apply', payload)
    assert c.cfg.read_bytes() == candidate
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'inactive'
    assert (c.awg.STATE / 'pending.json').exists()
    assert (c.awg.STATE / 'firewall.json').exists()
    assert all(config == candidate and kernel == policy for config, kernel in starts)
    with pytest.raises(c.tx.Refusal, match='revocation-resume-required'):
        c.awg.operate('recover', {})
    with pytest.raises(c.tx.Refusal, match='unfinished-runtime-without-publisher'):
        c.tx.admission(c.awg.STATE, uid=os.geteuid())
    before_check = {str(path): (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
                    for path in c.root.rglob('*') if path.is_file()}
    starts_before = list(starts)
    assert c.awg.operate('recover', {'check': True, 'revocation': authority})['forward_pending']
    assert c.awg.operate('apply', {**payload, 'check': True})['status'] == 'predicted'
    wrong = {**authority, 'intent_sha256': 'b' * 64}
    with pytest.raises(c.tx.Refusal, match='revocation-resume-required'):
        c.awg.operate('recover', {'check': True, 'revocation': wrong})
    with pytest.raises(c.tx.Refusal, match='revocation-candidate-changed'):
        c.awg.operate('apply', {**payload, 'check': True, 'candidates': [data(c.cfg, candidate + b'# changed\n')]})
    with pytest.raises(c.tx.Refusal, match='revocation-candidate-changed'):
        c.awg.operate('apply', {**payload, 'check': True, 'firewall': base64.b64encode(policy + b'# changed\n').decode()})
    assert starts == starts_before
    assert before_check == {str(path): (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
                            for path in c.root.rglob('*') if path.is_file()}
    marker = c.fw.STATE / 'consumer.json'
    original = marker.read_bytes()
    foreign = json.loads(original) | {'owner': 'site'}
    put(marker, json.dumps(foreign))
    with pytest.raises(c.tx.Refusal, match='awg-firewall-recovery-required'):
        c.awg.operate('recover', {'check': True, 'revocation': authority})
    assert marker.read_bytes() == json.dumps(foreign).encode()
    put(marker, original)
    assert c.awg.operate('recover', {'revocation': authority})['forward_pending']
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'inactive'
    result = c.awg.operate('apply', payload)
    assert result['status'] == 'accepted'
    assert starts and all(config == candidate and kernel == policy for config, kernel in starts)
    assert c.cfg.read_bytes() == candidate and c.kernel['bytes'] == policy
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'active'
    assert not (c.awg.STATE / 'pending.json').exists()
    assert not (c.awg.STATE / 'firewall.json').exists()
    assert not (c.fw.STATE / 'consumer.json').exists()
    assert not c.awg.operate('apply', payload)['changed']


@pytest.mark.parametrize('boundary', ['retirement.json', 'backups.json', 'accepted.json'])
def test_revocation_retirement_cleanup_check_is_readonly_and_resume_is_exact(context, monkeypatch, boundary):
    c = context
    authority = {'operation_id': '3fbb2baa-3a76-4f03-ae92-8ed9513fe268', 'intent_sha256': 'a' * 64}
    policy = base64.b64encode(c.fw.HEADER + b'table inet filter {}\n').decode()
    payload = {'candidates': [{'path': raw, 'absent': True} for raw in sorted(c.shared | {str(c.record), str(c.cfg)})],
               'firewall': policy, 'revocation': authority}
    record = c.tx.Transaction.record
    interrupted = []
    def interrupt(self, name, value):
        record(self, name, value)
        if self.root == c.awg.STATE and name == boundary and (self.root / 'retirement.json').exists() and not interrupted:
            interrupted.append(True)
            raise RuntimeError('interrupted-retirement-cleanup')
    monkeypatch.setattr(c.tx.Transaction, 'record', interrupt)
    with pytest.raises(RuntimeError, match='interrupted-retirement-cleanup'):
        c.awg.operate('apply', payload)
    assert interrupted and (c.awg.STATE / 'retirement.json').exists()
    resumed = {**payload, 'candidates': [item for item in payload['candidates'] if item['path'] != str(c.cfg)]}
    def snapshot():
        return {str(path): (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
                for path in c.root.rglob('*') if path.is_file()}
    before = snapshot()
    assert c.awg.operate('recover', {'check': True, 'revocation': authority}) == {'changed': False}
    assert c.awg.operate('apply', {**resumed, 'check': True})['status'] == 'predicted'
    for wrong in (None, {**authority, 'intent_sha256': 'b' * 64}):
        for check in (True, False):
            with pytest.raises(c.tx.Refusal, match='revocation-resume-required'):
                c.awg.operate('recover', {'check': check, 'revocation': wrong})
    assert snapshot() == before
    marker = c.awg.STATE / 'retirement.json'
    original = marker.read_bytes()
    tampered = json.loads(original)
    tampered['retired'] = []
    put(marker, json.dumps(tampered))
    with pytest.raises(c.tx.Refusal, match='awg-retirement-invalid'):
        c.awg.operate('recover', {'check': True, 'revocation': authority})
    assert marker.read_bytes() == json.dumps(tampered).encode()
    put(marker, original)
    c.awg.operate('recover', {'revocation': authority})
    assert c.awg.operate('apply', resumed)['status'] == 'accepted'
    assert not marker.exists() and not c.cfg.exists() and not c.record.exists()


@pytest.fixture
def ssh_rotation(context, monkeypatch):
    c = context
    before = c.fw.HEADER + b'table inet filter {\n chain input {\n  tcp dport 22 ip saddr { 1.1.1.1/32, 9.9.9.9/32 } accept\n }\n}\n'
    put(c.fw.CONFIG, before, 0o644)
    c.fw.STATE.mkdir(mode=0o700)
    with c.tx.Transaction(c.fw.STATE, uid=os.geteuid()) as active:
        active.record('accepted.json', {'schema': 1, 'nodes': {str(c.fw.CONFIG): c.tx.node(c.fw.CONFIG, os.geteuid())}, 'previous': None, 'units': {}})
    rule = {'family': 'inet', 'table': 'filter', 'chain': 'input', 'handle': 7, 'expr': [
        {'match': {'op': '==', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}}, 'right': 22}},
        {'match': {'op': '==', 'left': {'payload': {'protocol': 'ip', 'field': 'saddr'}}, 'right': {'set': ['1.1.1.1', '9.9.9.9']}}},
        {'accept': None}]}
    c.kernel['nftables'] = [
        {'set': {'family': 'inet', 'table': 'filter', 'name': 'f2b_sshd4', 'type': 'ipv4_addr', 'flags': ['timeout'], 'elem': ['8.8.4.4']}},
        {'rule': rule},
        {'rule': {'family': 'inet', 'table': 'foreign', 'chain': 'input', 'handle': 12, 'expr': [{'drop': None}]}}]
    c.kernel['calls'] = []
    def nft(argv, *, data=None):
        c.kernel['calls'].append(argv)
        if argv == ['nft', '-j', 'list', 'ruleset']:
            return json.dumps({'nftables': c.kernel['nftables']}).encode()
        if argv == ['nft', '-c', '-f', '-']:
            return b''
        if argv == ['nft', '-j', '-f', '-']:
            replacement = json.loads(data)['nftables'][0]['replace']['rule']
            selected = [row for row in c.kernel['nftables'] if row.get('rule', {}).get('handle') == replacement['handle']]
            assert len(selected) == 1
            selected[0]['rule'] = replacement
            for item in replacement['expr']:
                right = item.get('match', {}).get('right')
                if isinstance(right, dict) and set(right) == {'set'}:
                    right['set'].sort(key=lambda address: int(ipaddress.IPv4Address(address)))
            return b''
        raise AssertionError('rotation must never reload a complete table: ' + repr(argv))
    monkeypatch.setattr(c.fw, 'command', nft)
    c.rotation_request = {'old_source': '1.1.1.1', 'new_source': '8.8.8.8', 'port': 22}
    c.rotation_before = before
    c.policy_before = copy.deepcopy(c.kernel['nftables'])
    return c


def begin_ssh_rotation(c):
    checked = c.fw.operate('rotate-ssh', {**c.rotation_request, 'check': True})
    assert checked['changed'] is True
    result = c.fw.operate('rotate-ssh', {**c.rotation_request, 'plan': checked['plan']})
    assert result['status'] == 'accepted'
    return checked


@pytest.mark.parametrize('new_source', ['8.8.8.8', '208.67.222.222'])
def test_ssh_rotation_preserves_live_timed_sets_and_foreign_tables_on_apply_and_restore(ssh_rotation, new_source):
    c = ssh_rotation
    c.rotation_request['new_source'] = new_source
    checked = c.fw.operate('rotate-ssh', {**c.rotation_request, 'check': True})
    assert c.fw.CONFIG.read_bytes() == c.rotation_before
    assert not (c.fw.STATE / 'ssh-rotation.json').exists()
    begin_ssh_rotation(c)
    assert c.fw.CONFIG.read_bytes() == c.rotation_before.replace(b'1.1.1.1', new_source.encode())
    assert c.kernel['nftables'][0] == c.policy_before[0]
    assert c.kernel['nftables'][2] == c.policy_before[2]
    with pytest.raises(c.tx.Refusal, match='firewall-ssh-recovery-required'):
        c.fw.operate('apply', {'data': base64.b64encode(c.rotation_before).decode()})
    assert c.fw.operate('restore', {'owner': 'site'})['changed'] is True
    assert c.fw.CONFIG.read_bytes() == c.rotation_before
    assert c.kernel['nftables'] == c.policy_before
    assert not (c.fw.STATE / 'ssh-rotation.json').exists()
    with c.tx.Transaction(c.fw.STATE, uid=os.geteuid(), check=True) as active:
        assert active.accepted()['nodes'][str(c.fw.CONFIG)] == c.tx.node(c.fw.CONFIG, os.geteuid())
    assert checked['plan']


@pytest.mark.parametrize('changed', ['rule', 'set', 'file', 'owner'])
def test_ssh_rotation_refuses_foreign_drift_before_restore(ssh_rotation, changed):
    c = ssh_rotation
    begin_ssh_rotation(c)
    if changed == 'rule':
        c.kernel['nftables'].append({'rule': {'family': 'inet', 'table': 'filter', 'chain': 'input', 'handle': 90, 'expr': [{'accept': None}]}})
    elif changed == 'set':
        c.kernel['nftables'][0]['set']['elem'].append('8.8.8.8')
    elif changed == 'file':
        put(c.fw.CONFIG, c.fw.CONFIG.read_bytes() + b'# foreign\n', 0o644)
    else:
        path = c.fw.STATE / 'consumer.json'
        value = json.loads(path.read_bytes())
        value['before'] = None
        put(path, json.dumps(value))
    before = c.fw.CONFIG.read_bytes(), copy.deepcopy(c.kernel['nftables'])
    calls = len(c.kernel['calls'])
    with pytest.raises(c.tx.Refusal, match='firewall-ssh-'):
        c.fw.operate('restore', {'owner': 'site'})
    assert (c.fw.CONFIG.read_bytes(), c.kernel['nftables']) == before
    assert ['nft', '-j', '-f', '-'] not in c.kernel['calls'][calls:]
    assert (c.fw.STATE / 'ssh-rotation.json').exists()


def test_ssh_rotation_finish_resumes_lost_marker_removal_ack(ssh_rotation, monkeypatch):
    c = ssh_rotation
    begin_ssh_rotation(c)
    original = Path.unlink
    def interrupted(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path == c.fw.STATE / 'consumer.json':
            raise SystemExit('lost finish acknowledgement')
    with monkeypatch.context() as scoped:
        scoped.setattr(Path, 'unlink', interrupted)
        with pytest.raises(SystemExit):
            c.fw.operate('finish', {'owner': 'site'})
    assert not (c.fw.STATE / 'consumer.json').exists()
    with pytest.raises(c.tx.Refusal, match='firewall-commit-recovery-required'):
        c.fw.operate('restore', {'owner': 'site'})
    assert c.fw.operate('finish', {'owner': 'site'})['changed'] is False
    assert not (c.fw.STATE / 'ssh-rotation.json').exists()
    assert c.kernel['nftables'][0] == c.policy_before[0]
    assert c.fw.CONFIG.read_bytes() == c.rotation_before.replace(b'1.1.1.1', b'8.8.8.8')


@pytest.mark.parametrize('after_effect', [False, True])
def test_ssh_rotation_reconciles_interrupted_rule_publication(ssh_rotation, monkeypatch, after_effect):
    c = ssh_rotation
    checked = c.fw.operate('rotate-ssh', {**c.rotation_request, 'check': True})
    original = c.fw.command
    def interrupted(argv, *, data=None):
        if argv == ['nft', '-j', '-f', '-']:
            if after_effect:
                original(argv, data=data)
            raise SystemExit('lost nft acknowledgement')
        return original(argv, data=data)
    with monkeypatch.context() as scoped:
        scoped.setattr(c.fw, 'command', interrupted)
        with pytest.raises(SystemExit):
            c.fw.operate('rotate-ssh', {**c.rotation_request, 'plan': checked['plan']})
    c.fw.operate('restore', {'owner': 'site'})
    assert c.fw.CONFIG.read_bytes() == c.rotation_before
    assert c.kernel['nftables'] == c.policy_before
    assert not (c.fw.STATE / 'ssh-rotation.json').exists()


@pytest.mark.parametrize('change', ['source-op', 'port', 'extra-predicate', 'foreign-rule-after-check'])
def test_ssh_rotation_rejects_wrong_rule_or_changed_reviewed_plan(ssh_rotation, change):
    c = ssh_rotation
    checked = c.fw.operate('rotate-ssh', {**c.rotation_request, 'check': True})
    rule = c.kernel['nftables'][1]['rule']
    if change == 'source-op':
        rule['expr'][1]['match']['op'] = '!='
    elif change == 'port':
        rule['expr'][0]['match']['right'] = 2222
    elif change == 'extra-predicate':
        rule['expr'].insert(0, {'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'eth0'}})
    else:
        c.kernel['nftables'].append({'rule': {'family': 'inet', 'table': 'foreign', 'chain': 'input', 'handle': 13, 'expr': [{'drop': None}]}})
    with pytest.raises(c.tx.Refusal, match='firewall-ssh-'):
        c.fw.operate('rotate-ssh', {**c.rotation_request, 'plan': checked['plan']})
    assert c.fw.CONFIG.read_bytes() == c.rotation_before
    assert not (c.fw.STATE / 'ssh-rotation.json').exists()


@pytest.mark.parametrize('field', ['phase', 'after', 'policy_after'])
def test_ssh_rotation_corrupt_intent_refuses_without_mutation(ssh_rotation, field):
    c = ssh_rotation
    begin_ssh_rotation(c)
    path = c.fw.STATE / 'ssh-rotation.json'
    value = json.loads(path.read_bytes())
    value[field] = {'phase': 'committing', 'after': base64.b64encode(b'foreign').decode(), 'policy_after': {}}[field]
    put(path, json.dumps(value))
    before = c.fw.CONFIG.read_bytes(), copy.deepcopy(c.kernel['nftables'])
    calls = len(c.kernel['calls'])
    with pytest.raises(c.tx.Refusal, match='firewall-ssh-rotation-invalid'):
        c.fw.operate('restore', {'owner': 'site'})
    assert (c.fw.CONFIG.read_bytes(), c.kernel['nftables']) == before
    assert len(c.kernel['calls']) == calls


def test_ssh_rotation_binds_durable_source_membership_and_rule_order(ssh_rotation):
    c = ssh_rotation
    changed = c.rotation_before.replace(b'9.9.9.9/32', b'9.9.9.8/32')
    put(c.fw.CONFIG, changed, 0o644)
    with c.tx.Transaction(c.fw.STATE, uid=os.geteuid()) as active:
        active.record('accepted.json', {'schema': 1, 'nodes': {str(c.fw.CONFIG): c.tx.node(c.fw.CONFIG, os.geteuid())}, 'previous': None, 'units': {}})
    with pytest.raises(c.tx.Refusal, match='firewall-ssh-durable-runtime-mismatch'):
        c.fw.operate('rotate-ssh', {**c.rotation_request, 'check': True})
    assert not (c.fw.STATE / 'ssh-rotation.json').exists()
