"""Alternate emission consumes the real shared materializer and TLS authority."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

import client_payload
from liveness_profiles import ProfileError, build_profiles
from transport_semantics import transport_errors, xhttp_endpoints

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def inputs(monkeypatch):
    document = yaml.safe_load((ROOT / 'tests/fixtures/secrets-sample.yml').read_text())
    document['client_registry'] = {'laptop': {'status': 'active'}}
    document['nginx_xhttp'].update(fallback_server_name='alternate.example.test',
                                  fallback_cert_pem='synthetic certificate', fallback_key_pem='synthetic key')
    context = client_payload.context('fullstack')
    context['vpn'].update(enable_xray_reality=False, enable_hysteria=False,
                          enable_amneziawg=False, enable_snell=False, enable_nginx_xhttp=True)
    context['nginx_xhttp'] = {'fallback_enabled': True}
    context.update(nginx_xhttp_public_port=8443, nginx_xhttp_fallback_port=2083)
    monkeypatch.setattr(client_payload, 'context', lambda _: copy.deepcopy(context))
    monkeypatch.setattr(client_payload, 'command', lambda *a, **k: b'192.0.2.10')
    options = client_payload.options('ripdpi', hosts=['upcloud:fixture'], cohorts=['fullstack'])
    # Sources are canonicalized by the materializer.
    def emit():
        return client_payload.materialize('laptop', options, documents={str(Path('fixture').absolute()): document}, source_paths=['fixture'])
    return document, context, options, emit


@pytest.mark.parametrize('mode', ['auto', 'stream-up'])
def test_selected_device_receives_both_identities_and_matching_native_mode(inputs, mode):
    document, _, _, emit = inputs
    document['xray']['xhttp_mode'] = mode
    payload, _ = emit()
    outbounds = [v for v in payload['outbounds'] if v['type'] == 'vless']
    assert [(v['tls']['server_name'], v['server_port']) for v in outbounds] == [
        (document['nginx_xhttp']['server_name'], 8443), ('alternate.example.test', 2083)]
    assert all(v['uuid'] == next(v['uuid'] for v in document['xray']['clients'] if v['name'] == 'laptop') for v in outbounds)
    assert outbounds[1]['tag'] in next(v for v in payload['outbounds'] if v['tag'] == 'select')['outbounds']
    built = build_profiles(None, payload, document, 'laptop', ['p1-xhttp'], None, None, None,
                           lambda _: pytest.fail('unused AWG key requested'), '/private/generation',
                           awg_defaults={}, awg_cohort={})
    native = built['files']['xray.json']['outbounds']
    assert [v['streamSettings']['tlsSettings']['serverName'] for v in native] == [
        document['nginx_xhttp']['server_name'], 'alternate.example.test']
    assert all(v['streamSettings']['xhttpSettings']['mode'] == mode for v in native)
    assert [v['endpoint'] for v in built['public_profiles']] == ['primary', 'alternate']
    assert len(built['runtime']['xray']['profiles']['p1-xhttp']) == 2
    public = json.dumps(built['public_profiles'])
    assert all(client['uuid'] not in public for client in document['xray']['clients'])


def test_disabled_alternate_never_exports_stale_identity(inputs):
    document, context, _, emit = inputs
    context['nginx_xhttp']['fallback_enabled'] = False
    document['nginx_xhttp']['fallback_server_name'] = 'invalid/private-identity'
    payload, _ = emit()
    assert len([v for v in payload['outbounds'] if v['type'] == 'vless']) == 1


@pytest.mark.parametrize('fault', ['hostname', 'port', 'boolean-port', 'collision', 'cert', 'key', 'toggle'])
def test_invalid_alternate_refuses_before_artifact(inputs, fault):
    document, context, _, emit = inputs
    if fault == 'hostname':
        document['nginx_xhttp']['fallback_server_name'] = 'invalid/private-identity'
    elif fault == 'port':
        context['nginx_xhttp_fallback_port'] = 65536
    elif fault == 'boolean-port':
        context['nginx_xhttp_fallback_port'] = True
    elif fault == 'collision':
        context['nginx_xhttp_fallback_port'] = 8443
    elif fault in ('cert', 'key'):
        del document['nginx_xhttp']['fallback_' + fault + '_pem']
    else:
        context['nginx_xhttp']['fallback_enabled'] = 'false'
    errors = transport_errors(document, context)
    assert any(field == 'nginx_xhttp' for field, _ in errors)
    assert 'invalid/private-identity' not in json.dumps(errors)
    with pytest.raises(ValueError, match='invalid-transport-input'):
        emit()


def test_shared_hostname_alternate_uses_primary_tls_pair(inputs):
    document, context, _, emit = inputs
    for key in ('fallback_server_name', 'fallback_cert_pem', 'fallback_key_pem'):
        document['nginx_xhttp'].pop(key)
    assert xhttp_endpoints(document, context)[1]['host'] == document['nginx_xhttp']['server_name']
    assert len([v for v in emit()[0]['outbounds'] if v['type'] == 'vless']) == 2


def test_unsupported_mode_and_unknown_client_transport_fields_refuse(inputs):
    document, _, _, emit = inputs
    document['xray']['xhttp_mode'] = 'packet-up'
    with pytest.raises(ValueError, match='unsupported-recipient-xhttp-mode'):
        emit()
    document['xray']['xhttp_mode'] = 'auto'
    payload, _ = emit()
    payload['outbounds'][0]['transport']['xmux'] = {'maxConnections': 1}
    with pytest.raises(ProfileError, match='wrong-xhttp-mode-or-tuning'):
        build_profiles(None, payload, document, 'laptop', ['p1-xhttp'], None, None, None, None,
                       '/private/generation', awg_defaults={}, awg_cohort={})


def test_official_singbox_keeps_supported_primary_without_xhttp(inputs):
    _, context, options, _ = inputs
    context['vpn']['enable_xray_reality'] = True
    options['format'] = 'singbox'
    document = inputs[0]
    payload, _ = client_payload.materialize('laptop', options,
        documents={str(Path('fixture').absolute()): document}, source_paths=['fixture'])
    assert all(v.get('transport', {}).get('type') != 'xhttp' for v in payload['outbounds'])


def tuning():
    return dict(profile='bounded-pool', max_connections=2)


def test_native_format_retains_typed_tuning_and_routes_each_endpoint(inputs):
    mode = 'stream-up'
    document, _, options, _ = inputs
    options['format'] = 'xray'
    document['xray'].update(xhttp_mode=mode, xhttp_tuning=tuning())
    payload, _ = client_payload.materialize('laptop', options,
        documents={str(Path('fixture').absolute()): document}, source_paths=['fixture'])
    assert [(v['listen'], v['port']) for v in payload['inbounds']] == [('127.0.0.1', 1080), ('127.0.0.1', 1081)]
    assert payload['outbounds'][0]['protocol'] == 'blackhole'
    assert all(v['streamSettings']['xhttpSettings']['xmux'] == {
        'maxConnections': 2, 'hMaxRequestTimes': 0, 'hMaxReusableSecs': 0, 'cMaxReuseTimes': 0} for v in payload['outbounds'][1:])
    for inbound, rule, outbound in zip(payload['inbounds'], payload['routing']['rules'], payload['outbounds'][1:]):
        assert rule == dict(type='field', inboundTag=[inbound['tag']], outboundTag=outbound['tag'])
        assert outbound['streamSettings']['xhttpSettings']['mode'] == mode


@pytest.mark.parametrize('field,limit', [('max_connections', 4)])
@pytest.mark.parametrize('kind', ['zero', 'overflow', 'bool', 'text', 'float', 'missing'])
def test_tuning_bounds_refuse_before_materialization(inputs, field, limit, kind):
    document, _, options, emit = inputs
    options['format'] = 'xray'
    document['xray'].update(xhttp_mode='stream-up', xhttp_tuning=tuning())
    if kind == 'missing':
        del document['xray']['xhttp_tuning'][field]
    else:
        document['xray']['xhttp_tuning'][field] = dict(zero=0, overflow=limit + 1, bool=True, text='1', float=1.5)[kind]
    with pytest.raises(ValueError, match='invalid-transport-input'):
        emit()


@pytest.mark.parametrize('fault', ['unknown', 'profile', 'engine'])
def test_unknown_or_unqualified_tuning_refuses(inputs, fault):
    document, _, options, emit = inputs
    options['format'] = 'xray'
    document['xray'].update(xhttp_mode='stream-up', xhttp_tuning=tuning())
    if fault == 'unknown':
        document['xray']['xhttp_tuning']['extra'] = {}
    elif fault == 'profile':
        document['xray']['xhttp_tuning']['profile'] = 'unreviewed'
    else:
        document['xray']['version'] = 'v26.5.3'
    with pytest.raises(ValueError, match='invalid-transport-input'):
        emit()


def test_ripdpi_never_silently_discards_native_tuning(inputs):
    document, _, _, emit = inputs
    document['xray'].update(xhttp_mode='stream-up', xhttp_tuning=tuning())
    with pytest.raises(ValueError, match='unsupported-recipient-xhttp-mode'):
        emit()


def test_alternate_tag_does_not_collide_with_another_primary_name(inputs):
    document, _, options, _ = inputs
    options['hosts'] = ['upcloud:fixture', 'upcloud:fixture-alternate']
    options['cohorts'] = ['fullstack', 'fullstack']
    source = str(Path('fixture').absolute())
    payload, _ = client_payload.materialize('laptop', options,
        documents={source: document}, source_paths=['fixture', 'fixture'])
    tags = [v['tag'] for v in payload['outbounds']]
    assert len(tags) == len(set(tags))


@pytest.mark.parametrize('value', [None, [], '', True, {'extra': 1}])
def test_tuning_is_never_normalized_from_invalid_types(inputs, value):
    document, _, options, emit = inputs
    options['format'] = 'xray'
    document['xray']['xhttp_tuning'] = value
    with pytest.raises(ValueError, match='invalid-transport-input'):
        emit()


def test_native_format_refuses_options_it_cannot_enforce_before_source_reads():
    options = client_payload.options('xray', hosts=['upcloud:fixture'], cohorts=['fullstack'])
    with pytest.raises(ValueError, match='unsupported-native-xhttp-options'):
        client_payload.materialize('laptop', options, per_app_bypass='example.app')


def test_tuning_schema_matches_semantic_allowlist():
    import jsonschema
    schema = json.loads((ROOT / 'secrets/schema.json').read_text())['properties']['xray']['properties']['xhttp_tuning']
    for connections in (1, 4):
        jsonschema.validate(dict(profile='bounded-pool', max_connections=connections), schema)
    for invalid in (None, {}, {**tuning(), 'extra': {}}, {**tuning(), 'max_connections': True},
                    {**tuning(), 'h_max_request_times': 8}, {**tuning(), 'h_max_reusable_secs': 2}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


def test_liveness_keeps_failed_primary_when_alternate_completes(inputs):
    import importlib.util
    document, _, _, emit = inputs
    payload, _ = emit()
    built = build_profiles(None, payload, document, 'laptop', ['p1-xhttp'], None, None, None, None,
                           '/private/generation', awg_defaults={}, awg_cohort={})
    spec = importlib.util.spec_from_file_location('xhttp_variant_runner', ROOT / 'scripts/vpn-protocol-liveness.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    failed = dict(verdict='blocked', duration_ms=10, error_kind='connect', payload_transport='unknown',
                  target_address_family='unknown')
    delivered = dict(verdict='ok', duration_ms=20, payload_transport='tcp', target_address_family='ipv4')
    observation = runner.aggregate_variants('p1-xhttp', [failed, delivered])
    assert observation['verdict'] == 'ok'
    assert [(identity['endpoint'], result['verdict']) for identity, result in
            zip(built['public_profiles'], observation['variants'])] == [('primary', 'blocked'), ('alternate', 'ok')]


@pytest.mark.parametrize('mode', ['auto', 'packet-up'])
def test_bounded_pool_refuses_modes_without_a_qualified_live_connection_bound(inputs, mode):
    document, _, options, emit = inputs
    options['format'] = 'xray'
    document['xray'].update(xhttp_mode=mode, xhttp_tuning=tuning())
    with pytest.raises(ValueError, match='invalid-transport-input'):
        emit()


@pytest.mark.parametrize('value', ['$(shell touch injected)', '$(touch injected)', '`touch injected`', '"; touch injected; #'])
def test_make_native_emitter_preserves_literal_inputs(tmp_path, value):
    import os
    import subprocess
    (tmp_path / 'Makefile').write_bytes((ROOT / 'Makefile').read_bytes())
    (tmp_path / '.fleet.mk').write_text('$(error native emission must not load fleet configuration)\n')
    (tmp_path / 'scripts').mkdir()
    recorder = tmp_path / 'scripts/emit-singbox.sh'
    recorder.write_text('#!/bin/sh\nexec python3 -c \'import json,os,sys; print(json.dumps([sys.argv[1:],os.environ["SOPS_FILE"],os.environ["HOSTS"]]))\' "$@"\n')
    recorder.chmod(0o700)
    env = {key: val for key, val in os.environ.items() if key not in {'MAKEFILES', 'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS'}}
    result = subprocess.run(['make', '--no-print-directory', 'emit-xray', 'CLIENT=' + value,
                             'SOPS_FILE=' + value, 'HOSTS=' + value], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [[value, '--profile-format', 'xray'], value, value]
    assert not (tmp_path / 'injected').exists()


@pytest.mark.parametrize('port', [443, 2053, 8443])
def test_alternate_cannot_advertise_a_role_rejected_listener_collision(inputs, port):
    _, context, _, emit = inputs
    context['xray_fallback_port'] = 2053
    context['nginx_xhttp_fallback_port'] = port
    with pytest.raises(ValueError, match='invalid-transport-input'):
        emit()


def test_disabled_reality_alternate_does_not_reserve_its_former_port(inputs):
    _, context, _, emit = inputs
    assert context['xray_fallback_port'] == 0
    context['nginx_xhttp_fallback_port'] = 2053
    payload, _ = emit()
    assert [outbound['server_port'] for outbound in payload['outbounds']
            if outbound.get('transport', {}).get('type') == 'xhttp'] == [8443, 2053]
