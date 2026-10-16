"""Effective topology and private authenticated probe rendering contracts."""
import json
from pathlib import Path

import pytest
import yaml

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/watchdog'


@pytest.mark.parametrize('reality', [False, True])
@pytest.mark.parametrize('fallback', [False, True])
def test_effective_xhttp_routes_have_distinct_tls_authorities_and_no_missing_base(reality, fallback):
    values = merge_render_vars()
    values['vpn'].update(enable_xray_reality=reality, enable_nginx_xhttp=True)
    values['nginx_xhttp'].update(server_name='primary.example', fallback_server_name='fallback.example',
                                 fallback_enabled=fallback)
    values['watchdog_reality_probes'] = ([{'name': 'cohort', 'port': 2443, 'p0_reality_shape_input': {}}]
                                         if reality else [])
    config = json.loads(render_template(ROLE / 'templates/reality-probe.json.j2', values))
    assert len({row['port'] for row in config['inbounds']}) == 1 + int(reality) + int(fallback)
    p1 = [row for row in config['outbounds'] if row['tag'].startswith('watchdog-xhttp-')]
    assert len(p1) == 1 + int(fallback)
    assert [row['settings']['vnext'][0]['port'] for row in p1] == [values['nginx_xhttp_public_port']] + (
        [values['nginx_xhttp_fallback_port']] if fallback else [])
    assert [row['streamSettings']['tlsSettings']['serverName'] for row in p1] == ['primary.example'] + (
        ['fallback.example'] if fallback else [])
    assert all(row['streamSettings']['tlsSettings']['allowInsecure'] is False for row in p1)
    assert len(config['routing']['rules']) == len(config['inbounds'])
    assert all(row['settings']['vnext'][0]['port'] != 443 for row in config['outbounds'])


@pytest.mark.parametrize('salamander', [False, True])
def test_hysteria_private_client_matches_dedicated_identity_sni_trust_and_obfuscation(salamander):
    values = merge_render_vars()
    values['hysteria'].update(server_name='hysteria.example', salamander_enabled=salamander,
                              salamander_password='synthetic-obfs-authority')
    values['hysteria']['clients'] = [{'name': 'watchdog', 'password': 'synthetic-probe-password'},
                                    {'name': 'device', 'password': 'synthetic-device-password'}]
    client = yaml.safe_load(render_template(ROLE / 'templates/hysteria-probe.yaml.j2', values))
    assert client['auth'] == 'watchdog:synthetic-probe-password'
    assert client['tls'] == {'sni': 'hysteria.example', 'insecure': False,
                             'ca': values['hysteria_config_dir'] + '/server.fullchain.pem'}
    assert client.get('obfs') == ({'type': 'salamander', 'salamander': {'password': 'synthetic-obfs-authority'}}
                                  if salamander else None)
    ordinary = render_template(ROLE / 'templates/vpn-watchdog.env.j2', values)
    assert all(value not in ordinary for value in ('synthetic-probe-password', 'synthetic-obfs-authority',
                                                   'synthetic-device-password'))


def test_subscription_only_environment_has_no_transport_probe_authority():
    values = merge_render_vars()
    values['vpn_subscription_only'] = True
    env = render_template(ROLE / 'templates/vpn-watchdog.env.j2', values)
    for feature in ('XRAY', 'NGINX_XHTTP', 'HYSTERIA', 'AMNEZIAWG'):
        assert f'ENABLE_{feature}=false' in env
