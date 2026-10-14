"""Exact pinned AWG TUN traffic exercises real encrypted device transactions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from awg_client import config, export, public_key
from awg_device_binding import resolve_binding
from encrypted_client_document import operate
from liveness_profiles import _awg
from template_render import merge_render_vars, render_template
from test_awg_encrypted_transactions import decrypt, encrypted
from test_transport_semantics_native import command, exact_awg_sources

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]

ECHO = '''import socket, threading, sys
address = sys.argv[1]
def udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((address, 32000))
    while True:
        data, peer = s.recvfrom(1024); s.sendto(data, peer)
threading.Thread(target=udp, daemon=True).start()
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind((address, 32000)); s.listen()
while True:
    c, _ = s.accept()
    with c: c.sendall(c.recv(1024))
'''
PROBE = '''import socket, sys
address = sys.argv[1]
for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.settimeout(2); s.connect((address, 32000)); s.sendall(b'authenticated-awg-device'); data = s.recv(1024)
        if data != b'authenticated-awg-device': raise SystemExit(2)
'''


def native_config(text):
    ignored = {'Address', 'DNS', 'MTU'}
    return '\n'.join(line for line in text.splitlines() if line.split('=', 1)[0].strip() not in ignored) + '\n'


def test_encrypted_two_instance_tcp_udp_export_revocation_and_rejection(encrypted, tmp_path):
    go, tools = exact_awg_sources()
    path, original = encrypted
    token = uuid.uuid4().hex[:6]
    names = [f's{token}{i}' for i in range(2)]
    # Use owned unique IPC/interface names; no fixture can adopt another daemon.
    def rename(doc):
        for item, name in zip(doc['amneziawg_secrets']['instances'], names):
            item['name'] = name
        return doc, {}
    operate(path, rename)
    for i, name in enumerate(names):
        command([sys.executable, str(ROOT / "scripts/awg_client.py"), "enroll", f"new{i}", "--host", "upcloud:fixture", "--instance", name, "--file", str(path)])
    issued = decrypt(path)
    bin_dir = tmp_path / 'bin'; bin_dir.mkdir(mode=0o700)
    terraform = bin_dir / 'terraform'
    terraform.write_text('#!/bin/sh\ncase "$*" in *"workspace select"*) exit 0;; *"output -raw server_ipv4"*) printf "%s" "$AWG_NATIVE_ENDPOINT";; *) exit 2;; esac\n')
    terraform.chmod(0o700)
    profile = ROOT / 'ansible/group_vars' / ('vpn-awg-native-' + token + '.yml')
    profile.write_text('vpn:\n  enable_xray_reality: false\n  enable_nginx_xhttp: false\n  enable_hysteria: false\n  enable_amneziawg: true\n  enable_naive: false\n  enable_snell: false\n')
    processes = []
    namespaces = []
    try:
        for i, name in enumerate(names):
            server_ns, client_ns = f'awgs-{token}-{i}', f'awgc-{token}-{i}'
            for namespace in (server_ns, client_ns):
                command(['ip', 'netns', 'add', namespace]); namespaces.append(namespace)
                command(['ip', '-n', namespace, 'link', 'set', 'lo', 'up'])
            left, right = f'l{token}{i}', f'r{token}{i}'
            command(['ip', 'link', 'add', left, 'type', 'veth', 'peer', 'name', right])
            command(['ip', 'link', 'set', left, 'netns', server_ns])
            command(['ip', 'link', 'set', right, 'netns', client_ns])
            underlay = f'192.0.2.{i * 4 + 1}'
            for namespace, interface, address in ((server_ns, left, underlay), (client_ns, right, f'192.0.2.{i * 4 + 2}')):
                command(['ip', '-n', namespace, 'addr', 'add', address + '/30', 'dev', interface])
                command(['ip', '-n', namespace, 'link', 'set', interface, 'up'])
            client_interface = f'c{token}{i}'
            for namespace, interface in ((server_ns, name), (client_ns, client_interface)):
                process = subprocess.Popen(['ip', 'netns', 'exec', namespace, str(go), '-f', interface],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(process)
                deadline = time.monotonic() + 10
                while subprocess.run(['ip', '-n', namespace, 'link', 'show', interface], capture_output=True).returncode:
                    assert process.poll() is None and time.monotonic() < deadline, 'owned AWG TUN did not start'
                    time.sleep(0.05)
            selected = resolve_binding(issued, {}, f'new{i}', 'upcloud:fixture', name)
            block = export(issued, {}, f'new{i}', 'upcloud:fixture', name, underlay)
            private = issued['client_registry'][f'new{i}']['awg_private_key']
            environment = {**os.environ, 'PATH': str(bin_dir) + ':' + os.environ['PATH'],
                           'PROVIDER': 'upcloud', 'ENV': 'fixture', 'AWG_INSTANCE': name,
                           'AWG_NATIVE_ENDPOINT': underlay, 'SOPS_FILE': str(path),
                           'COHORT': 'awg-native-' + token, 'COHORTS': 'awg-native-' + token}
            standalone = command(['bash', str(ROOT / 'scripts/emit-awg.sh'), f'new{i}'], env=environment).replace('<CLIENT_PRIVATE_KEY>', private)
            assert standalone.strip() == config(block).replace('<CLIENT_PRIVATE_KEY>', private).strip()
            exported = subprocess.run(['bash', str(ROOT / 'scripts/emit-bundle.sh'), f'new{i}'], env=environment, capture_output=True, text=True, timeout=20)
            assert exported.returncode == 0, exported.stderr[:2000]
            bundle = json.loads(exported.stdout)
            assert bundle['ripdpi']['amneziawg'] == [block]
            bundle_path = tmp_path / (name + ".json")
            bundle_path.write_text(json.dumps(bundle)); bundle_path.chmod(0o600)
            command([sys.executable, str(ROOT / "scripts/validate-bundle.py"), str(bundle_path)])
            liveness, _, _ = _awg(issued, f'new{i}', selected.identity, underlay, private, public_key, {}, {})
            for field in ('Jc', 'Jmin', 'Jmax', 'S1', 'S2', 'H1', 'H2', 'H3', 'H4', 'Endpoint', 'PublicKey', 'PresharedKey'):
                value = next(line for line in standalone.splitlines() if line.startswith(field + ' = '))
                assert value in liveness
            values = merge_render_vars(); values['_inst'] = selected.instance
            server_text = render_template(ROOT / 'ansible/roles/amneziawg/templates/awg0.conf.j2', values)
            for namespace, interface, text, address in (
                    (server_ns, name, server_text, selected.instance['address_v4']),
                    (client_ns, client_interface, standalone, selected.peer['allowed_ips'])):
                candidate = tmp_path / (interface + '.conf')
                candidate.write_text(native_config(text)); candidate.chmod(0o600)
                command(['ip', 'netns', 'exec', namespace, str(tools), 'setconf', interface, str(candidate)])
                command(['ip', '-n', namespace, 'addr', 'add', address, 'dev', interface])
                command(['ip', '-n', namespace, 'link', 'set', interface, 'up'])
            tunnel_address = selected.instance['address_v4'].split('/')[0]
            command(['ip', '-n', client_ns, 'route', 'add', tunnel_address + '/32', 'dev', client_interface])
            echo = subprocess.Popen(['ip', 'netns', 'exec', server_ns, sys.executable, '-c', ECHO, tunnel_address],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(echo)
        time.sleep(0.2)
        def probe(i):
            return subprocess.run(['ip', 'netns', 'exec', f'awgc-{token}-{i}', sys.executable, '-c', PROBE,
                                   f'10.{70+i}.0.1'], capture_output=True, timeout=6).returncode
        assert probe(0) == 0 and probe(1) == 0, 'both actual AWG devices must authenticate TCP and UDP'
        # Exact native runtime rejects wrong device keys and mismatched headers as traffic failures.
        for mutation in ('key', 'headers'):
            candidate = tmp_path / f'c{token}0.conf'
            accepted = candidate.read_text()
            wrong = accepted.replace(issued['client_registry']['new0']['awg_private_key'], original['amneziawg_secrets']['instances'][1]['server_private_key']) if mutation == 'key' else accepted.replace('H1 = 1', 'H1 = 99')
            assert wrong != accepted
            candidate.write_text(wrong)
            command(['ip', 'netns', 'exec', f'awgc-{token}-0', str(tools), 'setconf', f'c{token}0', str(candidate)])
            assert probe(0) != 0 and probe(1) == 0
            candidate.write_text(accepted)
            command(['ip', 'netns', 'exec', f'awgc-{token}-0', str(tools), 'setconf', f'c{token}0', str(candidate)])
            assert probe(0) == 0
        command([sys.executable, str(ROOT / "scripts/awg_client.py"), "revoke", "new0", "--host", "upcloud:fixture", "--instance", names[0], "--file", str(path)])
        final = decrypt(path)
        assert final['amneziawg_secrets']['instances'][1] == issued['amneziawg_secrets']['instances'][1]
        values = merge_render_vars(); values['_inst'] = final['amneziawg_secrets']['instances'][0]
        candidate = tmp_path / (names[0] + '.conf')
        candidate.write_text(native_config(render_template(ROOT / 'ansible/roles/amneziawg/templates/awg0.conf.j2', values)))
        command(['ip', 'netns', 'exec', f'awgs-{token}-0', str(tools), 'setconf', names[0], str(candidate)])
        assert probe(0) != 0 and probe(1) == 0, 'revocation must remove only the selected authenticated device'
    finally:
        profile.unlink(missing_ok=True)
        for process in reversed(processes):
            process.terminate()
        for process in reversed(processes):
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        for namespace in reversed(namespaces):
            command(['ip', 'netns', 'delete', namespace])
        remaining = command(['ip', 'netns', 'list'])
        assert all(namespace not in remaining for namespace in namespaces), 'owned namespace cleanup must be confirmed'
