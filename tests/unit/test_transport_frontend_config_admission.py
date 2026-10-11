"""A valid native syntax cannot restore an unguarded recipient route."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest
import yaml
from transport_fixtures import guarded_xray_config

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('xray_admission', ROOT/'ansible/roles/xray/files/xray_validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_guarded_frontend_is_admitted():
    validator.admitted_frontend(guarded_xray_config())


@pytest.mark.parametrize('mutation', [
    lambda c: c['outbounds'][0].update(protocol='freedom'),
    lambda c: c['outbounds'][0].update(protocol='dns'),
    lambda c: c['outbounds'][0]['settings']['servers'][0].update(address='10.0.0.1'),
    lambda c: c['outbounds'][0]['settings']['servers'][0].update(port=40000),
    lambda c: c['outbounds'][0]['settings']['servers'][0]['users'][0].update(user='foreign'),
    lambda c: c['outbounds'][0].update(proxySettings={'tag': 'foreign'}),
    lambda c: c['outbounds'][0].update(streamSettings={'sockopt': {'dialerProxy': 'foreign'}}),
    lambda c: c['outbounds'].append(copy.deepcopy(c['outbounds'][0])),
    lambda c: c['routing'].update(domainStrategy='IPIfNonMatch'),
    lambda c: c['routing']['rules'][0].update(outboundTag='dns-out'),
])
def test_unguarded_or_unowned_route_is_refused(mutation):
    candidate = guarded_xray_config()
    mutation(candidate)
    with pytest.raises(ValueError):
        validator.admitted_frontend(candidate)


def test_ambiguous_candidate_never_invokes_binary_or_discloses_authority(tmp_path):
    candidate = tmp_path/'candidate.json'
    candidate.write_text('{"outbounds":[],"outbounds":[],"secret":"private-unit-sentinel"}')
    candidate.chmod(0o600)
    binary = tmp_path/'binary'
    binary.write_text('#!/bin/sh\nexit 77\n')
    binary.chmod(0o755)
    result = subprocess.run([sys.executable, str(ROOT/'ansible/roles/xray/files/xray_validate.py'), '--binary', str(binary), '--asset-dir', '/owned/assets', '--config', str(candidate)], text=True, capture_output=True)
    assert result.returncode == 1 and result.stdout == ''
    assert 'private-unit-sentinel' not in result.stderr and str(candidate) not in result.stderr


@pytest.mark.parametrize('replacement', [[], [{'name': 'default', 'type': 'direct'}], [{'name': 'guarded-direct', 'type': 'socks5', 'socks5': {'addr': '10.0.0.1:12081', 'username': 'normalizer-direct-hysteria', 'password': 'private-unit-sentinel-0000000000000'}}]])
def test_hysteria_bypass_candidate_is_refused_before_publication(tmp_path, replacement):
    from template_render import merge_render_vars, render_template
    config = yaml.safe_load(render_template(ROOT/'ansible/roles/hysteria/templates/config.yaml.j2', merge_render_vars()))
    config['outbounds'] = replacement
    path = tmp_path/'candidate.yaml'
    path.write_text(yaml.safe_dump(config));path.chmod(0o600)
    result = subprocess.run([sys.executable, str(ROOT/'ansible/roles/runtime-release/files/validate_yaml_mapping.py'), '--profile', 'hysteria', str(path)], text=True, capture_output=True)
    assert result.returncode == 1
    assert 'private-unit-sentinel' not in result.stderr and str(path) not in result.stderr


def test_loaded_immutable_runtime_authority_selects_validator(tmp_path):
    # This is the wrapper contract, not native runtime forwarding evidence.
    import os
    candidate = tmp_path / 'candidate.json'
    candidate.write_text(json.dumps(guarded_xray_config()))
    candidate.chmod(0o600)
    binary = tmp_path / 'accepted-release'
    binary.write_text('#!/bin/sh\nexit 47\n')
    binary.chmod(0o755)
    commands = tmp_path / 'commands'
    commands.mkdir()
    systemctl = commands / 'systemctl'
    systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$UNIT_AUTHORITY"\n')
    systemctl.chmod(0o755)
    environment = {**os.environ, 'PATH': str(commands)+os.pathsep+os.environ['PATH'],
                   'UNIT_AUTHORITY': 'XRAY_RUNTIME_BINARY='+str(binary)+' XRAY_LOCATION_ASSET=/immutable/assets'}
    command = [sys.executable, str(ROOT/'ansible/roles/xray/files/xray_validate.py'), '--config', str(candidate)]
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert result.returncode == 47
    for authority in ('XRAY_LOCATION_ASSET=/immutable/assets',
                      'XRAY_RUNTIME_BINARY=relative XRAY_LOCATION_ASSET=/immutable/assets',
                      'XRAY_RUNTIME_BINARY='+str(binary)+' XRAY_RUNTIME_BINARY=/other XRAY_LOCATION_ASSET=/immutable/assets'):
        result = subprocess.run(command, env={**environment, 'UNIT_AUTHORITY': authority}, capture_output=True, text=True)
        assert result.returncode == 1 and result.stdout == ''
        assert '/immutable/assets' not in result.stderr and str(binary) not in result.stderr


def test_frontend_does_not_split_literal_and_name_policy_with_geoip():
    from template_render import merge_render_vars, render_template
    config = json.loads(render_template(ROOT/'ansible/roles/xray/templates/config.json.j2', merge_render_vars()))
    assert config['routing']['domainStrategy'] == 'AsIs'
    assert not any('geoip:private' in rule.get('ip', []) for rule in config['routing']['rules'])
    validator.admitted_frontend(config)
