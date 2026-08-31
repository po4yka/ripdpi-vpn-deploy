"""Signed operator-artifact contract; test address data exists only in tmp_path."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import ipaddress
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/network-exposure-gate.py'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


@pytest.fixture
def signed_artifact(tmp_path, request):
    private = tmp_path / 'private.pem'
    public = tmp_path / 'trusted.pem'
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', f'rsa_keygen_bits:{getattr(request, "param", 2048)}', '-out', str(private)], check=True, capture_output=True)
    subprocess.run(['openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(public)], check=True, capture_output=True)
    der = subprocess.run(['openssl', 'pkey', '-pubin', '-in', str(public), '-outform', 'DER'], check=True, capture_output=True).stdout
    now = datetime.now(timezone.utc)
    policy = {'ingress': [str(ipaddress.ip_network((secrets.randbits(32), 32)))],
              'host_egress': [str(ipaddress.ip_network((secrets.randbits(128), 128)))], 'forwarded': []}
    data = {'schema_version': 1, 'source_id': 'reviewed-test',
            'created_at': (now - timedelta(minutes=1)).isoformat(),
            'expires_at': (now + timedelta(hours=1)).isoformat(),
            'review': {'approved': True, 'reviewer': 'test-reviewer', 'review_id': 'review-test'},
            'content_sha256': hashlib.sha256(canonical(policy)).hexdigest(), 'policy': policy}

    def write(changes=None, *, resign=True):
        value = json.loads(json.dumps(data))
        if changes:
            changes(value)
        value['content_sha256'] = hashlib.sha256(canonical(value['policy'])).hexdigest()
        signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(private)], input=canonical(value), check=True, capture_output=True).stdout
        value['signature'] = {'algorithm': 'rsa-sha256', 'value': base64.b64encode(signature).decode()}
        if not resign:
            value['policy']['forwarded'] = value['policy']['ingress']
        artifact = tmp_path / 'reviewed.json'
        artifact.write_bytes(canonical(value))
        artifact.chmod(0o600)
        return artifact, value

    artifact, value = write()
    return {'artifact': artifact, 'public': public, 'key_digest': hashlib.sha256(der).hexdigest(),
            'write': write, 'data': value}


def invoke(fixture, mode='log_only', *extra):
    return subprocess.run([sys.executable, str(SCRIPT), '--artifact', str(fixture['artifact']),
                           '--trusted-key', str(fixture['public']), '--trusted-key-sha256', fixture['key_digest'],
                           '--source-id', 'reviewed-test', '--mode', mode, *extra],
                          capture_output=True, text=True, timeout=10)


def test_valid_signed_review_has_redacted_summary_and_no_enforcement_plan(signed_artifact):
    result = invoke(signed_artifact)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['validation'] == 'valid'
    assert summary['counts'] == {'ingress': 1, 'host_egress': 1, 'forwarded': 0}
    assert summary['source_id'] == 'reviewed-test'
    for ranges in signed_artifact['data']['policy'].values():
        for value in ranges:
            assert value not in result.stdout + result.stderr
    internal = invoke(signed_artifact, 'log_only', '--internal-plan')
    assert json.loads(internal.stdout)['plan'] == {}


def test_schema_accepted_lowercase_rfc3339_timestamps_are_parsed(signed_artifact):
    def lowercase_timestamps(value):
        value['created_at'] = value['created_at'].replace('T', 't').replace('+00:00', 'z')
        value['expires_at'] = value['expires_at'].replace('T', 't').replace('+00:00', 'z')

    signed_artifact['write'](lowercase_timestamps)

    result = invoke(signed_artifact)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['validation'] == 'valid'


def test_schema_accepted_rfc3339_leap_seconds_are_parsed(signed_artifact):
    now = datetime.now(timezone.utc)

    def leap_second_timestamps(value):
        value['created_at'] = (now - timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M:60Z')
        value['expires_at'] = (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:60Z')

    signed_artifact['write'](leap_second_timestamps)

    result = invoke(signed_artifact)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['validation'] == 'valid'


def test_schema_accepted_year_zero_is_treated_as_ancient(signed_artifact):
    signed_artifact['write'](
        lambda value: value.update(created_at='0000-01-01T00:00:00Z')
    )

    result = invoke(signed_artifact)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['validation'] == 'valid'


def test_schema_accepted_maximum_leap_second_is_treated_as_latest(signed_artifact):
    signed_artifact['write'](
        lambda value: value.update(expires_at='9999-12-31T23:59:60Z')
    )

    result = invoke(signed_artifact)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['validation'] == 'valid'


def test_unknown_rfc3339_offset_fails_closed(signed_artifact):
    def unknown_offset(value):
        value['created_at'] = value['created_at'].replace('+00:00', '-00:00')

    signed_artifact['write'](unknown_offset)

    result = invoke(signed_artifact)

    assert result.returncode != 0
    assert result.stdout == ''
    assert 'network exposure validation failed' in result.stderr


@pytest.mark.parametrize('case', ['expired', 'future', 'unsigned', 'unreviewed', 'wrong-digest',
                                 'tampered', 'unknown-key', 'unknown-source', 'bad-cidr', 'extra-field'])
def test_invalid_inputs_fail_without_policy_output(signed_artifact, case):
    changes = {
        'expired': lambda v: v.update(expires_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),
        'future': lambda v: v.update(created_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()),
        'unreviewed': lambda v: v['review'].update(approved=False),
        'bad-cidr': lambda v: v['policy'].update(ingress=['not-a-prefix']),
        'extra-field': lambda v: v.update(unrecognized='value'),
    }
    artifact, value = signed_artifact['write'](changes.get(case), resign=case != 'tampered')
    if case == 'unsigned':
        del value['signature']
        artifact.write_bytes(canonical(value))
    if case == 'wrong-digest':
        value['content_sha256'] = '0' * 64
        artifact.write_bytes(canonical(value))
    if case == 'unknown-key':
        signed_artifact['key_digest'] = '0' * 64
    if case == 'unknown-source':
        value['source_id'] = 'unexpected'
        artifact.write_bytes(canonical(value))
    result = invoke(signed_artifact, 'log_only', '--internal-plan')
    assert result.returncode != 0
    assert result.stdout == ''
    assert 'network exposure validation failed' in result.stderr
    assert str(artifact) not in result.stderr
    assert str(signed_artifact['public']) not in result.stderr
    for ranges in signed_artifact['data']['policy'].values():
        for prefix in ranges:
            assert prefix not in result.stderr


@pytest.mark.parametrize('mode', ['canary', 'enforce'])
def test_promotion_requires_exact_host_approval_and_full_artifact_digest(signed_artifact, mode):
    digest = hashlib.sha256(signed_artifact['artifact'].read_bytes()).hexdigest()
    approved = ['--promotion-approved', 'true', '--promotion-digest', digest,
                '--inventory-host', 'test-target', '--authorized-hosts-json', '["test-target"]']
    result = invoke(signed_artifact, mode, '--internal-plan', *approved)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)['plan']
    assert plan['directions'] == signed_artifact['data']['policy']
    assert plan['mode'] == mode
    for index, bad in [(1, 'false'), (3, '0'*64), (5, 'another-host'), (7, '["test-*"]')]:
        options = approved.copy()
        options[index] = bad
        rejected = invoke(signed_artifact, mode, '--internal-plan', *options)
        assert rejected.returncode != 0
        assert rejected.stdout == ''


def test_disabled_needs_no_artifact_and_returns_no_plan():
    result = subprocess.run([sys.executable, str(SCRIPT), '--mode', 'disabled', '--internal-plan'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['plan'] == {}


def load_gate():
    spec = importlib.util.spec_from_file_location('network_exposure_gate', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_firewall(plan):
    spec = importlib.util.spec_from_file_location('exposure_render', ROOT / 'scripts/check-templates-render.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = module.merge_render_vars()
    values['_network_exposure_plan'] = plan
    return module.render_template(ROOT / 'ansible/roles/firewall/templates/nftables.conf.j2', values)


def test_disabled_and_log_only_preserve_pre_feature_firewall_bytes(signed_artifact):
    golden = (ROOT / 'tests/snapshot/golden/firewall/templates/nftables.conf.j2').read_text()
    assert render_firewall({}) == golden
    result = invoke(signed_artifact, 'log_only', '--internal-plan')
    assert result.returncode == 0, result.stderr
    assert render_firewall(json.loads(result.stdout)['plan']) == golden


@pytest.mark.parametrize('direction,chain,selector', [('ingress', 'input', 'saddr'),
                                                    ('host_egress', 'output', 'daddr'),
                                                    ('forwarded', 'forward', 'daddr')])
def test_each_direction_renders_only_its_explicit_chain(signed_artifact, direction, chain, selector):
    prefix = signed_artifact['data']['policy']['ingress'][0]
    plan = {'mode': 'canary', 'directions': {name: [prefix] if name == direction else []
                                         for name in ('ingress', 'host_egress', 'forwarded')}}
    rendered = render_firewall(plan)
    assert rendered.count(prefix) == 1
    rule = f'ip {selector} {prefix} counter drop comment "exposure-{direction.replace("_", "-")}"'
    section = rendered.split(f'chain {chain} {{', 1)[1].split('\n  }', 1)[0]
    assert rule in section
    if 'ct state established,related accept' in section:
        assert section.index(rule) < section.index('ct state established,related accept')


def test_signature_is_verified_not_just_present(signed_artifact):
    value = signed_artifact['data']
    value['review']['review_id'] = 'changed-after-signing'
    signed_artifact['artifact'].write_bytes(canonical(value))
    result = invoke(signed_artifact)
    assert result.returncode != 0
    assert result.stdout == ''
    assert 'signature-or-key' in result.stderr


@pytest.mark.parametrize('input_name', ['artifact', 'public'])
def test_hard_linked_trust_inputs_fail_closed_without_policy_output(signed_artifact, tmp_path, input_name):
    linked_path = tmp_path / f'linked-{input_name}'
    os.link(signed_artifact[input_name], linked_path)
    result = invoke(signed_artifact)
    assert result.returncode != 0
    assert result.stdout == ''
    assert 'unsafe-file' in result.stderr
    assert str(signed_artifact[input_name]) not in result.stderr
    for ranges in signed_artifact['data']['policy'].values():
        for prefix in ranges:
            assert prefix not in result.stderr


def test_fixture_policy_rejects_runtime_ranges_and_loadable_rules(tmp_path):
    gate = load_gate()
    gate.check_fixtures(ROOT / 'tests/fixtures/network-exposure-gate')
    for value in [str(ipaddress.ip_network((secrets.randbits(32), 32))), 'nft add table inet injected']:
        path = tmp_path / 'bad.json'
        path.write_text(json.dumps({'unexpected': value}))
        with pytest.raises(ValueError, match='non-placeholder fixture'):
            gate.check_fixtures(tmp_path)


def test_actual_ansible_review_is_read_only_idempotent_and_redacted(signed_artifact, tmp_path):
    import yaml
    gate = {'mode': 'log_only', 'artifact': str(signed_artifact['artifact']),
            'trusted_key': str(signed_artifact['public']), 'trusted_key_sha256': signed_artifact['key_digest'],
            'source_id': 'reviewed-test'}
    play = [{'name': 'Review signed policy', 'hosts': 'localhost', 'gather_facts': False,
             'vars': {'network_exposure_gate': gate},
             'roles': [{'role': str(ROOT / 'ansible/roles/network-exposure-gate')}],
             'post_tasks': [{'name': 'Verify no deployable plan', 'ansible.builtin.assert': {
                 'that': ['_network_exposure_plan == {}', '_network_exposure_summary.validation == "valid"']}}]}]
    path = tmp_path / 'review.yml'
    path.write_text(yaml.safe_dump(play))
    original = {item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()}
    for check in [False, True, False]:
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path), *(['--check'] if check else [])],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'changed=0' in result.stdout
        for ranges in signed_artifact['data']['policy'].values():
            for prefix in ranges:
                assert prefix not in result.stdout + result.stderr
        assert {item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()} == original


def test_disabled_rollback_does_not_log_removed_policy_addresses(tmp_path):
    """Execute the production template task under --check --diff against old policy."""
    import copy
    import getpass
    import grp
    import os
    import yaml
    tasks = yaml.safe_load((ROOT / 'ansible/roles/firewall/tasks/main.yml').read_text())
    task = copy.deepcopy(next(task for task in tasks if task['name'] == 'Render nftables config'))
    prefix = str(ipaddress.ip_network((secrets.randbits(32), 32)))
    target = tmp_path / 'nftables.conf'
    old = render_firewall({'mode': 'canary', 'directions': {'ingress': [prefix], 'host_egress': [], 'forwarded': []}})
    target.write_text(old)
    template = tmp_path / 'disabled.j2'
    template.write_text(render_firewall({}))
    task['ansible.builtin.template'].update(src=str(template), dest=str(target),
                                          owner=getpass.getuser(), group=grp.getgrgid(os.getgid()).gr_name)
    play = [{'name': 'Check rollback output boundary', 'hosts': 'localhost', 'gather_facts': False, 'become': False,
             'vars': {'_network_exposure_plan': {}}, 'tasks': [task]}]
    path = tmp_path / 'rollback.yml'
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path), '--check', '--diff'],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert prefix not in result.stdout + result.stderr
    assert target.read_text() == old


@pytest.mark.parametrize('signed_artifact', [512], indirect=True)
def test_valid_signature_from_weak_rsa_key_is_rejected(signed_artifact):
    result = invoke(signed_artifact)
    assert result.returncode != 0
    assert result.stdout == ''
    assert 'weak-signing-key' in result.stderr
