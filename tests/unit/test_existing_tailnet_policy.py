"""Legacy conversion and bridge-free recovery; fixtures are not live proof."""
from __future__ import annotations

import base64
from contextlib import nullcontext
import importlib.util
import json
import os
from pathlib import Path
import sys
import shutil
import tempfile
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAIN = b'''#!/usr/sbin/nft -f
# Managed by Ansible role `firewall`. Hand edits will be overwritten.
destroy table inet filter
table inet filter {
  chain input {
    type filter hook input priority 0;
    policy drop;
    tcp dport {443,2053} accept
    udp dport {8443,51820} accept
    counter drop
  }
  chain forward { type filter hook forward priority 0; policy drop; }
  chain output { type filter hook output priority 0; policy accept; }
}
'''
FRAGMENT = b'''set vpn_tailnet_ssh_v4 { type ipv4_addr; flags interval; elements = {100.64.0.20}; }
set vpn_tailnet_ssh_v6 { type ipv6_addr; flags interval; elements = {fd7a:115c:a1e0::20}; }
'''
BINDING = {'inventory_alias': 'node-one', 'public_address': '192.0.2.10', 'ssh_port': 22,
           'public_sources': ['198.51.100.20'], 'approved_sources': ['100.64.0.20', 'fd7a:115c:a1e0::20'],
           'host_key_sha256': 'a'*64, 'source_revision': 'b'*40, 'deployable_digest': 'c'*64}


@pytest.fixture
def planner(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    spec = importlib.util.spec_from_file_location('legacy_probe', ROOT/'scripts/tailnet_bootstrap_probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_preserves_all_existing_bytes_and_listeners(planner):
    value = planner.legacy_candidate(MAIN, BINDING)
    original = [line for line in value.splitlines(keepends=True)
                if b'vpn-bootstrap-' not in line and b'include ' not in line]
    assert b''.join(original) == MAIN
    assert b'tcp dport {443,2053} accept' in value
    assert b'udp dport {8443,51820} accept' in value
    assert value.count(b'include ') == 1
    assert value.index(b'vpn-bootstrap-overlay-drop') < value.index(b'vpn-bootstrap-public-0')


@pytest.mark.parametrize('addition', [b'include "foreign.nft"\n', b'# tailscale0\n', b'# vpn-bootstrap-collision\n'])
def test_foreign_or_ambiguous_legacy_layout_refuses(planner, addition):
    with pytest.raises(planner.ProbeError, match='layout-unsupported'):
        planner.legacy_candidate(MAIN+addition, BINDING)


@pytest.mark.parametrize('row', [
    {'counter': {'family': 'inet', 'table': 'filter', 'name': 'foreign'}},
    {'set': {'family': 'inet', 'table': 'filter', 'name': 'foreign'}},
    {'rule': {'family': 'inet', 'table': 'filter', 'chain': 'foreign', 'expr': []}},
    {'chain': {'family': 'inet', 'table': 'nat', 'name': 'foreign'}},
    {'flowtable': {'family': 'inet', 'table': 'filter', 'name': 'foreign'}},
])
def test_graph_validation_covers_every_object(planner, row):
    with pytest.raises(planner.ProbeError, match='foreign-firewall'):
        planner.validate_owned_rules([row])


@pytest.mark.parametrize('changes', [
    {'boot_id': 'changed'}, {'wall': 1601}, {'monotonic': 701},
    {'wall': 999}, {'monotonic': 99},
])
def test_lease_never_survives_expiry_reboot_or_clock_reversal(planner, changes):
    lease = {'boot_id': 'original', 'wall_started': 1000, 'monotonic_started': 100,
             'monotonic_deadline': 700, 'request': {'expires_at': 1600}}
    arguments = {'boot_id': 'original', 'wall': 1100, 'monotonic': 200}
    assert planner.lease_active(lease, **arguments)
    with_changes = {**arguments, **changes}
    assert not planner.lease_active(lease, **with_changes)


def test_review_digest_preserves_effective_objects_and_ignores_only_inert_quartet(planner):
    base = [{'table': {'family': 'inet', 'name': 'filter'}}]
    inert = [{'table': {'family': family, 'name': name}} for family in ('ip', 'ip6') for name in ('filter', 'nat')]
    plan = {'base_rules': base, 'observed_rules': base, 'candidate_rules': base, 'base_text_b64': 'original', 'service': 'unchanged'}
    equivalent = {**plan, **{key: inert+base for key in ('base_rules', 'observed_rules', 'candidate_rules')}, 'base_text_b64': 'inert-added'}
    assert planner.review_digest(plan) == planner.review_digest(equivalent)
    equivalent['candidate_rules'].append({'rule': {'family': 'ip', 'table': 'filter', 'chain': 'foreign', 'expr': []}})
    assert planner.review_digest(plan) != planner.review_digest(equivalent)


@pytest.mark.parametrize('early_boot', [False, True])
def test_restore_never_replays_console_rule(planner, monkeypatch, tmp_path, early_boot):
    import tailnet_firewall
    adapter = tailnet_firewall.Firewall(root=tmp_path)
    adapter.fragment.parent.mkdir(parents=True)
    snapshot = {'console_lease': {'request': {'expires_at': int(time.time())+900}},
                'main': None, 'fragment': None, 'fragment_directory_existed': True,
                'base_rules': ['base'], 'before_rules': ['base', 'bridge'],
                'base_rules_text': tailnet_firewall._record(b'base-only'),
                'rules_text': tailnet_firewall._record(b'base-and-console-bridge'),
                'service': {'ActiveState': 'active', 'UnitFileState': 'enabled'}}
    loaded = []
    monkeypatch.setattr(adapter, 'validate_snapshot', lambda _: None)
    monkeypatch.setattr(adapter, '_graph', lambda _: None)
    monkeypatch.setattr(adapter, '_console_lock', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(adapter, '_write', lambda *a: None)
    monkeypatch.setattr(adapter, '_load', loaded.append)
    monkeypatch.setattr(adapter, 'command', lambda _: b'')
    monkeypatch.setattr(adapter, '_service', lambda: snapshot['service'])
    monkeypatch.setattr(adapter, '_rules', lambda: ['base'])
    adapter.restore(snapshot, BINDING, early_boot=early_boot)
    assert loaded
    assert all(value == b'flush ruleset\nbase-only' for value in loaded)


@pytest.mark.native_runtime
def test_native_nft_conversion_preserves_listener_policy(planner):
    assert sys.platform == 'linux' and os.geteuid() == 0
    before = planner.parse_policy(MAIN)
    after = planner.parse_policy(planner.legacy_candidate(MAIN, BINDING).replace(
        b'include "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"', FRAGMENT))
    planner.validate_owned_rules(after)
    restored = [row for row in after if not (
        row.get('set', {}).get('name') in {'vpn_tailnet_ssh_v4', 'vpn_tailnet_ssh_v6'}
        or row.get('rule', {}).get('comment', '').startswith('vpn-bootstrap-'))]
    assert restored == before
    assert len(after) == len(before)+6


@pytest.mark.parametrize('control', [b'    ip saddr @f2b_sshd4 drop\n', b'    ip saddr 203.0.113.0/24 counter drop comment "exposure-ingress"\n'])
def test_management_allowance_stays_after_existing_security_controls(planner, control):
    original = MAIN.replace(b'    tcp dport {443,2053} accept', control+b'    tcp dport 22 ip saddr { 198.51.100.10 } accept\n    tcp dport {443,2053} accept')
    candidate = planner.legacy_candidate(original, BINDING)
    assert candidate.index(control) < candidate.index(b'vpn-bootstrap-overlay-v4')
    assert candidate.index(b'vpn-bootstrap-public-0') < candidate.index(b'tcp dport 22 ip saddr {')


@pytest.fixture
def isolated_kernel():
    assert sys.platform == 'linux' and os.geteuid() == 0
    descriptor = os.open('/proc/self/ns/net', os.O_RDONLY | os.O_CLOEXEC)
    os.unshare(os.CLONE_NEWNET)
    try:
        yield
    finally:
        os.setns(descriptor, os.CLONE_NEWNET)
        os.close(descriptor)


@pytest.fixture
def native_root(isolated_kernel):
    assert sys.platform == 'linux' and os.geteuid() == 0
    root = Path(tempfile.mkdtemp(prefix='vpn-policy-native-', dir='/var/lib'))
    try:
        yield root
    finally:
        shutil.rmtree(root)


@pytest.mark.native_runtime
def test_native_plan_approval_apply_and_bridge_free_restore(planner, monkeypatch, native_root):
    """Real kernel/files in a private netns; service fixture is not PID1 proof."""
    import tailnet_firewall
    import tailnet_management
    assert sys.platform == 'linux' and os.geteuid() == 0
    adapter = tailnet_firewall.Firewall(root=native_root)
    adapter.main.parent.mkdir()
    adapter.main.write_bytes(MAIN)
    adapter.main.chmod(0o644)
    adapter.state.mkdir(parents=True, mode=0o700)
    real_command = planner.command
    def isolated_command(argv, *, input_data=None):
        if argv[0] == 'systemctl':
            if argv[1] == 'show' and argv[2] == 'nftables.service':
                return b'ActiveState=active\nUnitFileState=enabled\n'
            if argv[1] == 'show':
                return b'inactive\n'
            return b''
        return real_command(argv, input_data=input_data)
    monkeypatch.setattr(planner, 'command', isolated_command)
    # The adapter imports planner functions into its module namespace.
    monkeypatch.setattr(tailnet_firewall, 'inspect_legacy_policy', planner.inspect_legacy_policy)
    adapter.command = isolated_command
    real_command(['nft', '-f', '-'], input_data=MAIN)
    original = adapter._rules()
    fragment = tailnet_management.canonical_sources_fragment(BINDING['approved_sources']).encode()
    plan = planner.inspect_legacy_policy(BINDING, fragment, root=native_root)
    approval = {'schema_version': 1, 'decision': 'approve-managed-legacy-v1', 'plan_sha256': plan['plan_sha256']}
    snapshot = adapter.snapshot(BINDING, policy_approval=approval)
    adapter.apply(snapshot, BINDING)
    adapter.verify(snapshot, BINDING)
    assert adapter._rules() == plan['candidate_rules']
    adapter.restore(snapshot, BINDING, early_boot=True)
    assert adapter.main.read_bytes() == MAIN
    assert not adapter.fragment.exists()
    assert adapter._rules() == original


@pytest.fixture
def receipt(planner):
    wall, mono = time.time(), time.monotonic()
    request = {'schema_version': 1, 'nonce': 'd'*32, 'hostname': 'node-one',
               'root_filesystem_uuid': '00000000-0000-0000-0000-000000000001',
               **{key: BINDING[key] for key in ('inventory_alias', 'public_address', 'ssh_port', 'public_sources', 'host_key_sha256', 'source_revision', 'deployable_digest')},
               'expires_at': int(wall)+600}
    return {'schema_version': 1, 'request': request, 'boot_id': '00000000-0000-0000-0000-000000000002',
            'monotonic_started': mono, 'wall_started': wall, 'monotonic_deadline': mono+request['expires_at']-wall,
            'before_rules': [], 'before_sha256': 'a'*64, 'main_sha256': 'b'*64,
            'before_text_b64': base64.b64encode(b'table inet filter {}').decode(), 'request_sha256': 'c'*64,
            'leased_rules': [{}], 'leased_sha256': 'd'*64}


def test_receipt_requires_exact_clock_and_replay_contract(planner, receipt):
    planner.validate_console_receipt(receipt)


@pytest.mark.parametrize('change', [
    {'schema_version': True}, {'boot_id': 'bad'}, {'wall_started': float('nan')},
    {'monotonic_started': True}, {'monotonic_deadline': float('inf')}, {'before_rules': {}},
    {'leased_rules': []}, {'extra': 'undeclared'}, {'before_text_b64': 'invalid!'},
])
def test_noncanonical_receipt_refuses(planner, receipt, change):
    with pytest.raises((planner.ProbeError, ValueError)):
        planner.validate_console_receipt({**receipt, **change})


@pytest.mark.native_runtime
@pytest.mark.parametrize('quartet', ['none', 'complete', 'partial', 'objectful'])
def test_native_console_witness_accepts_only_exact_inert_install_delta(planner, monkeypatch, native_root, quartet):
    """Kernel/replay proof with explicit service and node-identity fixtures."""
    root = native_root
    main = root/'etc/nftables.conf'
    main.parent.mkdir()
    main.write_bytes(MAIN)
    main.chmod(0o644)
    state = root/'run/vpn-console-bootstrap'
    state.mkdir(parents=True, mode=0o700)
    real = planner.command
    real(['nft', '-f', '-'], input_data=b'flush ruleset\n'+MAIN)
    before = planner.stable_rules(json.loads(real(['nft', '-j', 'list', 'ruleset'])))
    before_text = real(['nft', '-s', 'list', 'ruleset'])
    wall, mono = time.time(), time.monotonic()
    request = {'schema_version': 1, 'nonce': 'd'*32, 'hostname': 'node-one',
               'root_filesystem_uuid': '00000000-0000-0000-0000-000000000001',
               **{key: BINDING[key] for key in ('inventory_alias', 'public_address', 'ssh_port', 'public_sources', 'host_key_sha256', 'source_revision', 'deployable_digest')},
               'expires_at': int(wall)+600}
    real(['nft', '-f', '-'], input_data=(f'insert rule inet filter input ip saddr 198.51.100.20 tcp dport 22 counter accept comment "vpn-console-lease:{request["nonce"]}"\n').encode())
    leased = planner.stable_rules(json.loads(real(['nft', '-j', 'list', 'ruleset'])))
    marked = [row['rule'] for row in leased if row.get('rule', {}).get('comment') == 'vpn-console-lease:'+request['nonce']]
    boot_id = '00000000-0000-0000-0000-000000000002'
    value = {'schema_version': 1, 'request': request, 'boot_id': boot_id,
             'monotonic_started': mono, 'wall_started': wall,
             'monotonic_deadline': mono+request['expires_at']-wall,
             'before_rules': before, 'before_sha256': planner.policy_digest(before),
             'main_sha256': __import__('hashlib').sha256(MAIN).hexdigest(),
             'before_text_b64': base64.b64encode(before_text).decode(), 'request_sha256': planner.policy_digest(request),
             'leased_rules': marked, 'leased_sha256': planner.policy_digest(leased)}
    receipt_path = state/'receipt.json'
    receipt_path.write_text(json.dumps(value))
    receipt_path.chmod(0o600)
    boot = root/'proc/sys/kernel/random/boot_id'
    boot.parent.mkdir(parents=True)
    boot.write_text(boot_id)
    def command(argv, *, input_data=None):
        if argv[0] == 'systemctl':
            return b'ActiveState=active\nUnitFileState=enabled\n' if argv[2] == 'nftables.service' else b'inactive\n'
        if argv[0] == 'hostname':
            return b'node-one\n'
        if argv[0] == 'findmnt':
            return request['root_filesystem_uuid'].encode()
        return real(argv, input_data=input_data)
    monkeypatch.setattr(planner, 'command', command)
    original_plan = planner.inspect_legacy_policy(BINDING, FRAGMENT, root=root)
    if quartet != 'none':
        entries = [f'table {family} {name} {{}}\n' for family in ('ip', 'ip6') for name in ('filter', 'nat')]
        if quartet == 'partial':
            entries.pop()
        real(['nft', '-f', '-'], input_data=''.join(entries).encode())
        if quartet == 'objectful':
            real(['nft', 'add', 'chain', 'ip', 'filter', 'foreign'])
    if quartet in {'partial', 'objectful'}:
        with pytest.raises(planner.ProbeError, match='foreign-firewall'):
            planner.inspect_legacy_policy(BINDING, FRAGMENT, root=root)
    else:
        after = planner.inspect_legacy_policy(BINDING, FRAGMENT, root=root)
        assert after['plan_sha256'] == original_plan['plan_sha256']
        replay = planner.parse_policy(base64.b64decode(after['base_text_b64']))
        assert replay == after['base_rules']
        assert not any(row.get('rule', {}).get('comment', '').startswith('vpn-console-lease:') for row in replay)


@pytest.mark.native_runtime
@pytest.mark.parametrize('entry', ['confirmed.json', 'transaction.lock', 'unknown.json'])
def test_absent_bundle_never_adopts_orphaned_durable_state(planner, native_root, entry):
    state = native_root/'var/lib/vpn-tailnet-management'
    state.mkdir(parents=True, mode=0o700)
    leftover = state/entry
    leftover.write_text('untouched prior authority')
    leftover.chmod(0o600)
    expected = {'/usr/local/lib/vpn-tailnet/domain.py': 'a'*64}
    with pytest.raises(planner.ProbeError, match='orphaned-state'):
        planner.inspect_installed_bundle(expected, root=native_root)
    assert leftover.read_text() == 'untouched prior authority'
    assert not (native_root/'usr/local/lib/vpn-tailnet').exists()


@pytest.mark.native_runtime
def test_absent_bundle_accepts_only_absent_or_empty_safe_state(planner, native_root):
    expected = {'/usr/local/lib/vpn-tailnet/domain.py': 'a'*64}
    assert planner.inspect_installed_bundle(expected, root=native_root) == {'status': 'absent'}
    state = native_root/'var/lib/vpn-tailnet-management'
    state.mkdir(parents=True, mode=0o700)
    assert planner.inspect_installed_bundle(expected, root=native_root) == {'status': 'absent'}


@pytest.mark.native_runtime
@pytest.mark.parametrize('entry,value', [('unknown.json', '{}'), ('confirmed.json', '{"schema_version":3,"generation":"tailnet-recovery-v3"}'), ('transaction.json', '{"schema_version":4,"generation":"tailnet-recovery-v4"}')])
def test_current_bundle_refuses_unknown_old_or_invalid_records_readonly(planner, native_root, entry, value):
    import hashlib
    directory = native_root/'usr/local/lib/vpn-tailnet'
    directory.mkdir(parents=True)
    domain = directory/'tailnet_management.py'
    content = (ROOT/'scripts/tailnet_management.py').read_bytes()
    domain.write_bytes(content)
    domain.chmod(0o644)
    state = native_root/'var/lib/vpn-tailnet-management'
    state.mkdir(parents=True, mode=0o700)
    record = state/entry
    record.write_text(value)
    record.chmod(0o600)
    expected = {'/usr/local/lib/vpn-tailnet/tailnet_management.py': hashlib.sha256(content).hexdigest()}
    with pytest.raises(planner.ProbeError, match='installed-bundle-(unknown|old|state-invalid)'):
        planner.inspect_installed_bundle(expected, root=native_root)
    assert record.read_text() == value
    assert {item.name for item in state.iterdir()} == {entry}
