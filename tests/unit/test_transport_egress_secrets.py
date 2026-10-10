"""Internal adapter credentials are typed and generated without diagnostics leaks."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from transport_semantics import EGRESS_CREDENTIALS, egress_errors, transport_errors
from transport_egress_config import build

ROOT = Path(__file__).resolve().parents[2]


def credentials():
    return {name: 'synthetic '+name+' 00000000000000000000000000000000' for name in EGRESS_CREDENTIALS}


def test_only_enabled_paths_require_authority():
    secret = {'direct_gateway_password': credentials()['direct_gateway_password'], 'direct_hysteria_password': credentials()['direct_hysteria_password']}
    vpn = {'enable_xray_reality': False, 'enable_nginx_xhttp': False, 'enable_hysteria': True, 'enable_warp_outbound': False}
    assert not egress_errors(secret, vpn, required=True)
    assert egress_errors({}, vpn, required=True)


@pytest.mark.parametrize('value', ['', 'x'*31, 'x'*129, 'x'*32+'\n', 'é'*32,
    yaml.safe_load((ROOT/'secrets/prod.secrets.example.yaml').read_text())['transport_egress_secrets'][EGRESS_CREDENTIALS[0]],
    None, True])
def test_bad_credential_is_categorical(value):
    secret = credentials()
    secret[EGRESS_CREDENTIALS[0]] = value
    errors = egress_errors(secret, required=True)
    assert errors
    assert all('synthetic' not in error and repr(value) not in error for error in errors)


def test_space_is_printable_and_pairwise_authorities_are_distinct():
    assert not egress_errors(credentials(), required=True)
    secret = credentials()
    secret[EGRESS_CREDENTIALS[1]] = secret[EGRESS_CREDENTIALS[0]]
    assert egress_errors(secret, required=True)


def test_disabling_boundary_with_proxies_refuses():
    assert egress_errors(credentials(), {'enable_transport_egress': False}, required=True)


def test_synthetic_fixture_contains_admitted_generated_contract():
    sample = yaml.safe_load((ROOT/'tests/fixtures/secrets-sample.yml').read_text())
    assert not egress_errors(sample['transport_egress_secrets'], required=True)


def test_input_preflight_cannot_publish_missing_or_private_authority():
    payload = {'vpn': {'enable_xray_reality': False, 'enable_nginx_xhttp': False, 'enable_hysteria': True}, 'secrets': {}, 'owned_addresses': [], 'management_tcp_ports': [], 'management_udp_ports': []}
    result = subprocess.run([sys.executable, str(ROOT/'scripts/transport_egress_config.py'), '--input-only'], input=json.dumps(payload), text=True, capture_output=True)
    assert result.returncode == 1 and result.stdout == ''
    assert result.stderr == 'transport-egress-context-refused\n'

@pytest.mark.parametrize('check_mode', [False, True])
def test_subscription_only_preflight_requires_no_inactive_runtime_credentials(tmp_path, check_mode):
    import shutil
    executable = shutil.which('ansible-playbook')
    assert executable, 'actual Ansible preflight is required'
    marker = tmp_path/'marker'
    play = {'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
            'vars': {'ansible_python_interpreter': sys.executable,
                     'role_path': str(ROOT/'ansible/roles/xray'),
                     'vpn_subscription_only': True,
                     'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': True,
                             'enable_hysteria': True, 'enable_amneziawg': True}},
            'tasks': [{'ansible.builtin.import_tasks': str(ROOT/'ansible/playbooks/tasks/transport-input-preflight.yml')},
                      {'name': 'Publish only the subscription-only test marker', 'ansible.builtin.copy': {'dest': str(marker), 'content': 'admitted'}}]}
    path = tmp_path/'play.yml';path.write_text(yaml.safe_dump([play]))
    args = [executable, '-i', 'localhost,', str(path)]
    if check_mode:args.append('--check')
    result = subprocess.run(args, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    assert marker.exists() is (not check_mode)


@pytest.mark.parametrize('check_mode', [False, True])
@pytest.mark.parametrize('override', [{'xray_runtime_user': 'custom-xray'}, {'xray_runtime_group': 'custom-xray'}])
def test_alternate_xray_identity_refuses_before_fresh_or_retained_mutation(tmp_path, check_mode, override):
    import shutil
    executable = shutil.which('ansible-playbook')
    assert executable, 'actual Ansible identity admission is required'
    accepted = tmp_path/'accepted'
    accepted.write_text('retained runtime authority')
    before = accepted.stat().st_mtime_ns
    mutation = tmp_path/'mutation'
    tasks = yaml.safe_load((ROOT/'ansible/playbooks/tasks/transport-egress-prepare.yml').read_text())
    guard = next(t for t in tasks if t['name'] == 'Require the fixed protected Xray identity before host mutation')
    play = {'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
            'vars': {'ansible_python_interpreter': sys.executable, 'transport_egress_role_enabled': True,
                     'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': False}, **override},
            'tasks': [guard, {'ansible.builtin.copy': {'dest': str(mutation), 'content': 'unexpected mutation'}}]}
    path = tmp_path/'play.yml';path.write_text(yaml.safe_dump([play]))
    args = [executable, '-i', 'localhost,', str(path)]
    if check_mode:args.append('--check')
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and 'Protected Xray runtime user and group must both be xray.' in result.stdout
    assert not mutation.exists() and accepted.read_text() == 'retained runtime authority'
    assert accepted.stat().st_mtime_ns == before
