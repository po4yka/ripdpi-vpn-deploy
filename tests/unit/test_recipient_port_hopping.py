"""Recipient capability refusal runs through the canonical materializer."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

import client_payload

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def materialize(monkeypatch):
    document = yaml.safe_load((ROOT / 'tests/fixtures/secrets-sample.yml').read_text())
    context = client_payload.context('fullstack')
    context['vpn'].update(enable_xray_reality=False, enable_nginx_xhttp=False,
                          enable_hysteria=True, enable_amneziawg=False, enable_snell=False)
    context.update(hysteria_port_range='46000-46015', hysteria_hop_interval='30s')
    monkeypatch.setattr(client_payload, 'context', lambda _: copy.deepcopy(context))
    monkeypatch.setattr(client_payload, 'command', lambda *args, **kwargs: b'192.0.2.10')
    source = str(Path('synthetic-input').absolute())

    render = client_payload.materialize

    def emit(format, **kwargs):
        options = client_payload.options(format, hosts=['upcloud:fixture'], cohorts=['fullstack'])
        return render('phone', options, documents={source: document},
                                          source_paths=[source], **kwargs)
    return context, emit


@pytest.mark.parametrize('extended', [False, True])
def test_ripdpi_refuses_hopping_without_returning_partial_payload(materialize, extended):
    _, emit = materialize
    with pytest.raises(ValueError, match='^RIPDPI Hysteria port hopping requires a qualified client$'):
        emit('ripdpi', extended=extended)


def test_official_singbox_retains_supported_hopping(materialize):
    _, emit = materialize
    payload, _ = emit('singbox')
    outbound = next(value for value in payload['outbounds'] if value['type'] == 'hysteria2')
    assert outbound['server_ports'] == ['46000:46015']
    assert outbound['hop_interval'] == '30s'


def test_ripdpi_fixed_port_remains_supported(materialize):
    context, emit = materialize
    context['hysteria_port_range'] = ''
    payload, _ = emit('ripdpi', extended=True)
    outbound = next(value for value in payload['outbounds'] if value['type'] == 'hysteria2')
    assert 'server_ports' not in outbound
    assert 'port_hopping' not in payload['ripdpi']['hysteria_extras'][outbound['tag']]


def test_unselected_hysteria_does_not_block_native_xray_format(materialize):
    context, emit = materialize
    context['vpn']['enable_nginx_xhttp'] = True
    payload, _ = emit('xray')
    assert any(value['protocol'] == 'vless' for value in payload['outbounds'])


@pytest.mark.parametrize('bundle', [False, True])
def test_actual_cli_refusal_has_no_partial_stdout(materialize, monkeypatch, capsys, bundle):
    _, emit = materialize
    monkeypatch.setattr(sys, 'argv', ['client_payload.py', 'phone', '--profile-format', 'ripdpi',
                                     *(['--bundle'] if bundle else [])])
    monkeypatch.setattr(client_payload, 'materialize', lambda *args, **kwargs: emit('ripdpi', extended=bundle))
    assert client_payload.main() == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == 'client-payload: RIPDPI Hysteria port hopping requires a qualified client\n'
