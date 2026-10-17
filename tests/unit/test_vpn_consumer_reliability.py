"""Portable real-file transactions; lifecycle adapters do not claim native traffic."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles'


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
    monkeypatch.setattr(awg.subprocess, 'run', stop)
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


def test_actual_check_mode_policy_reader_composition_compiles_and_runs(context, monkeypatch):
    import re
    import yaml
    c = context
    tasks = yaml.safe_load((FILES / 'firewall/tasks/consumer-prepare.yml').read_text())
    task = next(row for row in tasks if row['name'] == 'Read only exact owned accepted AWG firewall claims')
    expression = task['ansible.builtin.command']['argv'][2]
    pattern = re.search(r"regex_replace\('([^']+)', ''\)", expression).group(1)
    generic = (FILES / 'runtime-release/files/transport_runtime_transaction.py').read_text()
    selected = (FILES / 'firewall/files/firewall_consumer.py').read_text()
    combined = generic + '\n' + re.sub(pattern, '', selected)
    namespace = {'__name__': 'owned_composite_fixture'}
    exec(compile(combined, '<actual-firewall-policy-reader>', 'exec'), namespace)
    # The executed source reads exact owned scratch metadata/configuration and
    # returns the old claims, without relying on an installed helper in check mode.
    namespace['AWG_RECORD'] = c.record
    assert namespace['accepted_awg']()[0]['peers'][0]['allowed_ips']['ipv4'] == '10.66.66.2/32'
