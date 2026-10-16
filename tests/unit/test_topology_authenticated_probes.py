"""Effective topology and private authenticated probe rendering contracts."""
import json
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/watchdog'


@pytest.mark.parametrize('max_connections', [None, 1, 2, 4])
@pytest.mark.parametrize('reality', [False, True])
@pytest.mark.parametrize('fallback', [False, True])
def test_effective_xhttp_routes_have_distinct_tls_authorities_and_no_missing_base(reality, fallback, max_connections):
    values = merge_render_vars()
    values['vpn'].update(enable_xray_reality=reality, enable_nginx_xhttp=True)
    if max_connections is not None:
        values['xray'].update(xhttp_mode='stream-up', xhttp_tuning={
            'profile': 'bounded-pool', 'max_connections': max_connections})
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
    for row in p1:
        settings = row['streamSettings']['xhttpSettings']
        assert settings['mode'] == values['xray'].get('xhttp_mode', 'auto')
        assert settings.get('xmux') == ({'maxConnections': max_connections,
            'hMaxRequestTimes': 0, 'hMaxReusableSecs': 0, 'cMaxReuseTimes': 0}
            if max_connections is not None else None)
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


def test_disabled_xhttp_needs_no_xhttp_configuration():
    values = merge_render_vars()
    values['vpn']['enable_nginx_xhttp'] = False
    for name in ('nginx_xhttp', 'nginx_xhttp_public_port', 'nginx_xhttp_port',
                 'nginx_xhttp_fallback_port'):
        values.pop(name)
    env = render_template(ROLE / 'templates/vpn-watchdog.env.j2', values)
    assert 'XRAY_XHTTP_PROBES=\n' in env
    for name in ('NGINX_PORT', 'XHTTP_BACKEND_PORT', 'NGINX_FALLBACK_PORT'):
        assert f'{name}=0\n' in env


@pytest.mark.parametrize('omitted', [('enable_nginx_xhttp',), ('enable_hysteria',),
                                    ('enable_nginx_xhttp', 'enable_hysteria')])
def test_omitted_transport_toggles_preserve_canonical_probe_authority(omitted):
    canonical = merge_render_vars()
    canonical['vpn']['enable_xray_reality'] = False
    actual = {**canonical, 'vpn': {key: value for key, value in canonical['vpn'].items()
                                 if key not in omitted}}
    for name in ('vpn-watchdog.env.j2', 'reality-probe.json.j2', 'vpn-watchdog.service.j2'):
        assert render_template(ROLE / 'templates' / name, actual) == render_template(
            ROLE / 'templates' / name, canonical)

    # Evaluate the real role's selection/retirement conditions as well as renders.
    # The values here are typed booleans, matching the canonical toggle contract.
    environment = Environment(undefined=StrictUndefined, autoescape=True)
    environment.filters['bool'] = bool
    conditions = []
    for task in yaml.safe_load((ROLE / 'tasks/enable.yml').read_text()):
        when = task.get('when', [])
        for condition in ([when] if isinstance(when, str) else when):
            if any('vpn.' + toggle in condition for toggle in omitted):
                conditions.append(environment.compile_expression(condition))
    assert conditions
    for evaluate in conditions:
        assert evaluate(**actual) == evaluate(**canonical)
