"""Admit a bounded private collector before firewall publication."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/firewall'
POLICY = {'address': '100.64.0.2', 'sources': ['100.64.0.3', '100.64.0.4']}


@pytest.mark.parametrize('policy,enabled,address,accepted', [
    ({}, False, '', True),
    (POLICY, True, '100.64.0.2', True),
    (POLICY, False, '100.64.0.2', False),
    (POLICY, True, '', False),
    (POLICY, True, '100.64.0.9', False),
    ([], True, '100.64.0.2', False),
    ({**POLICY, 'port': 443}, True, '100.64.0.2', False),
    ({'address': '100.64.0.2'}, True, '100.64.0.2', False),
    ({**POLICY, 'address': True}, True, '100.64.0.2', False),
    ({**POLICY, 'address': '192.0.2.2'}, True, '192.0.2.2', False),
    ({**POLICY, 'sources': []}, True, '100.64.0.2', False),
    ({**POLICY, 'sources': ['100.64.0.3'] * 2}, True, '100.64.0.2', False),
    ({**POLICY, 'sources': [f'100.64.0.{i}' for i in range(11)]}, True, '100.64.0.2', False),
    *[({**POLICY, 'sources': [source]}, True, '100.64.0.2', False)
      for source in ['0.0.0.0/0', '100.64.0.0/10', '192.0.2.3', 'fd7a:115c:a1e0::1',
                     '100.064.0.3', '100.64.0.3; accept', True]],
])
@pytest.mark.parametrize('check', [False, True])
def test_real_admission_refuses_unsafe_scope_before_mutation(tmp_path, policy, enabled, address, accepted, check):
    marker = tmp_path / 'mutation'
    play = [{
        'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'become': False,
        'vars': {
            'ansible_python_interpreter': sys.executable,
            'ansible_facts': {'tailscale0': {'ipv4': {'address': address}}},
            'vpn': {'enable_tailnet_management': enabled},
            'firewall_tailnet_collector_ingress': policy,
        },
        'tasks': [
            {'name': 'Admit collector', 'ansible.builtin.import_tasks': str(ROLE / 'tasks/collector-admission.yml')},
            {'name': 'Observe mutation', 'ansible.builtin.copy': {'dest': str(marker), 'content': 'admitted', 'mode': '0600'}},
        ],
    }]
    path = tmp_path / 'admission.yml'
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path), *(['--check'] if check else [])],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    assert marker.exists() is (accepted and not check)
    if not accepted:
        assert 'collector-invalid-tailnet-ingress' in result.stdout


def test_render_is_inert_by_default_and_exact_when_enabled():
    variables = merge_render_vars()
    variables['public_listener_contract'] = []
    template = ROLE / 'templates/nftables.conf.j2'
    assert '9443' not in render_template(template, variables)
    variables['firewall_tailnet_collector_ingress'] = POLICY
    rendered = render_template(template, variables)
    rule = ('    iifname "tailscale0" ip daddr 100.64.0.2 ip saddr { 100.64.0.3, 100.64.0.4 } '
            'tcp dport 9443 accept comment "private-collector-ingress"')
    assert rule in rendered.splitlines()
    assert rendered.count('9443') == 1


def test_collector_admission_precedes_retained_firewall_mutation():
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    assert tasks[1]['ansible.builtin.import_tasks'] == 'collector-admission.yml'
    names = [task['name'] for task in tasks]
    assert names.index('Reserve the private collector port') < names.index('Prepare retained firewall consumer authority')
    assert names.index('Reject public listeners on the effective SSH port') < names.index('Prepare retained firewall consumer authority')


@pytest.mark.parametrize('enabled,port,protocol,public_port,public_range,accepted', [
    (False, 9443, 'tcp', 9443, None, True),
    (True, 22, 'tcp', 443, None, True),
    (True, 9443, 'tcp', 443, None, False),
    (True, 22, 'tcp', 9443, None, False),
    (True, 22, 'tcp', None, '9400-9500', False),
    (True, 22, 'tcp', None, '9443-9444', False),
    (True, 22, 'tcp', None, '9442-9443', False),
    (True, 22, 'tcp', None, '9444-9500', True),
    (True, 22, 'udp', 9443, None, True),
])
@pytest.mark.parametrize('check', [False, True])
def test_real_port_admission_refuses_shared_ownership(tmp_path, enabled, port, protocol, public_port, public_range, accepted, check):
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    admission = next(task for task in tasks if task['name'] == 'Reserve the private collector port')
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
             'vars': {'firewall_effective_ssh_ports': [port],
                      'firewall_tailnet_collector_ingress': POLICY if enabled else {},
                      'public_listener_contract': [{'name': 'fixture', 'protocol': protocol, 'port': public_port, 'port_range': public_range}]},
             'tasks': [admission]}]
    path = tmp_path / 'port-admission.yml'
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path), *(['--check'] if check else [])],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    if not accepted:
        assert 'collector-ingress-port-overlap' in result.stdout
