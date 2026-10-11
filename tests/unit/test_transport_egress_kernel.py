"""Portable authority and rendering checks; packet proofs live in native tests."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import transport_egress_kernel as kernel
from transport_egress_config import build
from transport_egress_host_context import discover


def context(warp=False):
    return {'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': True, 'enable_hysteria': True, 'enable_warp_outbound': warp},
            'secrets': {name+'_password': 'synthetic '+name+' authority 00000000000000000000' for name in ['direct_gateway', 'direct_xray', 'direct_hysteria', 'warp_xray', 'warp_gateway']},
            'normalizer_uid': 101, 'gateway_uid': 102, 'warp_gateway_uid': 103, 'frontend_uids': {'xray': 104, 'hysteria': 105},
            'owned_addresses': ['203.0.113.1', '2001:db8::1'], 'management_tcp_ports': [2222], 'management_udp_ports': [9999]}


def test_input_topology_has_no_invented_identity():
    result = build(context(True), True)
    assert 'policy' not in result and 'runtime_uid' not in result['normalizer']
    assert all('frontend_uid' not in item for item in result['normalizer']['listeners'])


def test_projection_contains_no_credentials_and_routes_remain_udp_capable():
    result = build(context(True))
    text = json.dumps(result['policy'])
    assert 'password' not in text and 'username' not in text and 'synthetic' not in text
    rendered = kernel.render(result['policy'])
    assert 'hook output priority 300' in rendered
    assert 'fib daddr type local tcp dport { 2222 } drop' in rendered
    assert 'ip daddr 10.250.254.2 meta l4proto { tcp, udp } th dport 12091 meta skuid != 101 drop' in rendered
    assert 'udp dport 12090 accept' in rendered
    assert 'ct direction reply' in rendered
    assert 'meta skuid 102 ip daddr { 0.0.0.0/8' in rendered


def test_null_tunnel_is_deny_all_and_ifindex_is_the_only_plaintext_egress():
    policy = build(context(True))['policy']
    inactive = kernel.render(policy, True)
    assert 'meta skuid 103 drop' in inactive and 'meta oif ' not in inactive
    policy['warp']['tunnel_ifindex'] = 41
    active = kernel.render(policy, True)
    assert 'meta skuid 103 meta oif 41 meta l4proto { tcp, udp } accept' in active
    assert 'oifname "rpd-warp-ns"' in active
    assert 'ip saddr != 10.250.254.1 drop' in active


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(normalizer_uid=0),
    lambda p: p.update(gateway_uid=p['normalizer_uid']),
    lambda p: p['listeners'][0].update(frontend_uid=p['gateway_uid']),
    lambda p: p['listeners'][0].update(udp_port_min=12090),
    lambda p: p['warp'].update(tunnel_ifindex=True),
    lambda p: p['warp'].update(namespace='foreign'),
    lambda p: p['backends']['warp'].update(address='127.0.0.1'),
    lambda p: p.update(extra='arbitrary'),
])
def test_invalid_policy_cannot_render(mutation):
    policy = build(context(True))['policy']
    mutation(policy)
    with pytest.raises(kernel.BoundaryError):
        kernel.render(policy, True)


def rules(chain, expr=()):
    return {'nftables': [{'chain': {'family': 'inet', 'table': 'other', 'name': 'egress', **chain}}, {'rule': {'family': 'inet', 'table': 'other', 'chain': 'egress', 'expr': list(expr)}}]}


@pytest.mark.parametrize('chain,expr', [
    ({'hook': 'output', 'prio': 300}, ()),
    ({'hook': 'output', 'prio': 500, 'type': 'route'}, ()),
    ({'hook': 'postrouting', 'prio': 0}, ({'mangle': {'key': 'destination'}},)),
    ({'hook': 'forward', 'prio': 0}, ({'flow': {'op': 'add', 'flowtable': 'offload'}},)),
])
def test_unknown_late_rewrite_or_offload_refuses(chain, expr):
    with pytest.raises(kernel.BoundaryError):
        kernel.audit_authority(rules(chain, expr))


def test_earlier_accept_and_output_dnat_are_admitted_but_final_guard_still_applies():
    kernel.audit_authority(rules({'hook': 'output', 'prio': -100, 'type': 'nat'}, [{'dnat': {'addr': '10.0.0.1'}}]))
    kernel.audit_authority(rules({'hook': 'output', 'prio': 0}, [{'accept': None}]))


def test_flowtable_refuses_even_without_active_rule():
    with pytest.raises(kernel.BoundaryError):
        kernel.audit_authority({'nftables': [{'flowtable': {'family': 'inet', 'table': 'other', 'name': 'fast'}}]})


def test_host_context_uses_actual_ssh_and_recovery_owners(monkeypatch):
    import transport_egress_host_context as host
    monkeypatch.setattr(host.shutil, 'which', lambda name: '/usr/sbin/sshd')
    outputs = {'ip': '[{"addr_info":[{"family":"inet","local":"203.0.113.2"}]}]', 'sshd': 'port 2222\n', 'ss': 'tcp LISTEN 0 128 0.0.0.0:2200 0.0.0.0:* users:(("sshd",pid=2,fd=3))\ntcp LISTEN 0 128 0.0.0.0:443 0.0.0.0:* users:(("nginx",pid=3,fd=3))\n'}
    monkeypatch.setattr(host, 'capture', lambda argv: outputs[argv[0]])
    assert discover(['203.0.113.1']) == {'owned_addresses': ['203.0.113.1', '203.0.113.2'], 'management_tcp_ports': [2200, 2222], 'management_udp_ports': []}

def test_verified_tunnel_context_is_preserved_for_unchanged_convergence():
    active = context(True)
    active['tunnel_ifindex'] = 41
    assert build(active)['policy']['warp']['tunnel_ifindex'] == 41
    active['tunnel_ifindex'] = None
    assert build(active)['policy']['warp']['tunnel_ifindex'] is None

def test_namespace_uses_its_actual_ephemeral_and_reserved_port_authority(monkeypatch):
    calls = []
    def query(args, namespace=False, **kwargs):
        calls.append((args, namespace))
        return '12000 19000' if args[-1].endswith('ip_local_port_range') else ''
    monkeypatch.setattr(kernel, 'command', query)
    with pytest.raises(kernel.BoundaryError, match='unreserved-ephemeral-pool'):
        kernel.admit_ports(build(context(True))['policy'], True)
    assert len(calls) == 2 and all(namespace is True for args, namespace in calls)
    monkeypatch.setattr(kernel, 'command', lambda args, namespace=False, **kwargs: '12000 19000' if args[-1].endswith('ip_local_port_range') else '12000-19000,25000')
    kernel.admit_ports(build(context(True))['policy'], True)


@pytest.mark.parametrize('port,namespace', [(12080, False), (12090, False), (13000, False), (16000, False), (12091, True)])
@pytest.mark.parametrize('uid', ['', ' uid:0'])
def test_inode_less_retired_tcp_tuple_has_no_live_port_owner(monkeypatch, port, namespace, uid):
    monkeypatch.setattr(kernel, 'command', lambda *_: f'tcp TIME-WAIT 0 0 127.0.0.1:{port} 127.0.0.1:40000{uid} ino:0 sk:0\n')
    kernel.admit_owners(build(context(True))['policy'], namespace)


@pytest.mark.parametrize('record', [
    'tcp LISTEN 0 128 127.0.0.1:12080 0.0.0.0:* ino:0',
    'tcp ESTAB 0 0 127.0.0.1:12080 127.0.0.1:40000 ino:0',
    'udp UNCONN 0 0 127.0.0.1:13000 0.0.0.0:* ino:0',
    'tcp TIME-WAIT 0 0 127.0.0.1:12080 127.0.0.1:40000 uid:77 ino:0',
    'tcp TIME-WAIT 0 0 127.0.0.1:12080 127.0.0.1:40000 ino:123',
    'tcp TIME-WAIT 0 0 127.0.0.1:12080 127.0.0.1:40000',
    'tcp TIME-WAIT 0 0 127.0.0.1:12080 127.0.0.1:40000 ino:0 users:(("foreign",pid=123,fd=4))',
])
def test_retired_tuple_exception_preserves_live_and_unknown_authority_refusal(monkeypatch, record):
    monkeypatch.setattr(kernel, 'command', lambda *_: record + '\n')
    with pytest.raises(kernel.BoundaryError, match='foreign-port-owner'):
        kernel.admit_owners(build(context(True))['policy'])

@pytest.mark.parametrize('transfer', ['jump', 'goto'])
def test_postrouting_regular_chain_mutation_cannot_bypass_activation(transfer):
    ruleset = {'nftables': [
        {'chain': {'family': 'inet', 'table': 'other', 'name': 'post', 'hook': 'postrouting', 'prio': 0}},
        {'chain': {'family': 'inet', 'table': 'other', 'name': 'regular'}},
        {'rule': {'family': 'inet', 'table': 'other', 'chain': 'post', 'expr': [{transfer: {'target': 'regular'}}]}},
        {'rule': {'family': 'inet', 'table': 'other', 'chain': 'regular', 'expr': [{'mangle': {'key': {'payload': {'protocol': 'ip', 'field': 'daddr'}}, 'value': '10.0.0.1'}}]}},
    ]}
    with pytest.raises(kernel.BoundaryError, match='unsupported-postrouting-authority'):
        kernel.audit_authority(ruleset)


def test_postrouting_transfer_cycle_is_bounded_without_skipping_mutation():
    ruleset = {'nftables': [
        {'chain': {'family': 'inet', 'table': 'other', 'name': 'post', 'hook': 'postrouting', 'prio': 0}},
        {'chain': {'family': 'inet', 'table': 'other', 'name': 'regular'}},
        {'rule': {'family': 'inet', 'table': 'other', 'chain': 'post', 'expr': [{'jump': {'target': 'regular'}}]}},
        {'rule': {'family': 'inet', 'table': 'other', 'chain': 'regular', 'expr': [{'goto': {'target': 'post'}}]}},
    ]}
    kernel.audit_authority(ruleset)
    ruleset['nftables'].append({'rule': {'family': 'inet', 'table': 'other', 'chain': 'regular', 'expr': [{'mangle': {'key': 'destination'}}]}})
    with pytest.raises(kernel.BoundaryError):kernel.audit_authority(ruleset)

def test_interface_pretty_print_is_stable_across_deletion_without_loosening_drift():
    name = {'match': {'op': '==', 'left': {'meta': {'key': 'oif'}}, 'right': 'tun-test'}}
    missing = {'match': {'op': '==', 'left': {'meta': {'key': 'oif'}}, 'right': '41'}}
    number = {'match': {'op': '==', 'left': {'meta': {'key': 'oif'}}, 'right': 41}}
    assert kernel.digest(name, {'tun-test': 41}) == kernel.digest(missing) == kernel.digest(number)
    assert kernel.digest(name, {'tun-test': 42}) != kernel.digest(number)
    # iifname/oifname matchers retain names; they are intentionally a different wire authority.
    named_matcher = {'match': {'op': '==', 'left': {'meta': {'key': 'oifname'}}, 'right': 'tun-test'}}
    assert kernel.digest(named_matcher, {'tun-test': 41}) == kernel.digest(named_matcher, {'tun-test': 42})

def test_numeric_interface_name_cannot_hide_a_meaningful_index_change():
    ambiguous = {'match': {'op': '==', 'left': {'meta': {'key': 'oif'}}, 'right': '41'}}
    with pytest.raises(kernel.BoundaryError, match='ambiguous-interface-matcher'):
        kernel.digest(ambiguous, {'41': 42})
    numeric_name = {'ifname': '41', 'ifindex': 42}
    original = kernel.command
    try:
        kernel.command = lambda args, namespace=False, **kwargs: json.dumps([numeric_name])
        with pytest.raises(kernel.BoundaryError, match='ambiguous-interface-name'):
            kernel.admit_links(build(context())['policy'])
    finally:
        kernel.command = original


def test_classifier_has_independent_final_packet_boundary():
    data = context()
    data['vpn']['enable_cascade_ingress'] = True
    data['classifier_uid'] = 106
    policy = build(data)['policy']
    rendered = kernel.render(policy)
    assert 'tcp dport 10808 meta skuid != 104 drop' in rendered
    assert 'meta skuid 106 ip daddr { 0.0.0.0/8' in rendered
    assert 'meta skuid 106 fib daddr type local tcp dport { 2222 } drop' in rendered
    assert 'meta skuid 106 oifname "lo" ip daddr 127.0.0.1 tcp sport 10808 ct direction reply ct original proto-dst 10808 accept' in rendered
    assert (10808, 10808) in kernel.intervals(policy)
    policy['classifier_uid'] = policy['gateway_uid']
    with pytest.raises(kernel.BoundaryError, match='identity-not-separated'):
        kernel.render(policy)


def test_actual_ansible_host_context_source_compiles_before_discovery(tmp_path):
    import subprocess
    import yaml
    import shutil
    executable = shutil.which('ansible-playbook')
    assert executable, 'actual Ansible source assembly is required'
    tasks = yaml.safe_load((ROOT/'ansible/playbooks/tasks/transport-egress-prepare.yml').read_text())
    source = next(t for t in tasks if t['name']=='Read actual host destination authority')['ansible.builtin.command']['argv'][-1]
    play = {'hosts':'localhost','connection':'local','gather_facts':False,'become':False,
            'vars':{'role_path':str(ROOT/'ansible/roles/xray'), 'ansible_python_interpreter':sys.executable},
            'tasks':[{'name':'Compile exact source without host or fleet discovery',
                      'ansible.builtin.command':{'argv':[sys.executable,'-c','import sys; compile(sys.argv[1], "owned-host-context", "exec"); print("source-compiles")',source]},
                      'changed_when':False, 'register':'compiled'},
                     {'ansible.builtin.assert':{'that':["compiled.stdout == 'source-compiles'"]}}]}
    path=tmp_path/'play.yml';path.write_text(yaml.safe_dump([play]))
    result=subprocess.run([executable,'-i','localhost,',str(path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_backend_ipc_requires_its_owned_interface():
    rendered = kernel.render(build(context(True))['policy'])
    assert 'meta skuid 101 oifname "lo" ip daddr 127.0.0.1 tcp dport 12090 accept' in rendered
    assert 'meta skuid 101 oifname "rpd-warp-host" ip daddr 10.250.254.2 tcp dport 12091 accept' in rendered
    assert 'meta skuid 101 oifname "rpd-warp-host" ip daddr 10.250.254.2 udp sport 18000-18999 udp dport 12091 accept' in rendered
