#!/usr/bin/env python3
"""Exercise the pinned production client against the candidate Xray source."""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tempfile
import time
import tomllib

import yaml

from operator_maintenance_io import ROOT, command_environment
from bootstrap_readiness import ReadinessError, cancellation, run_command


def pins():
    value = json.loads((ROOT / 'tools/engine-interop.json').read_bytes())
    if (set(value) != {'schema_version', 'client_revision', 'xray_revision', 'xray_version',
                       'go_version', 'rust_version'} or value['schema_version'] != 1
            or any(not re.fullmatch('[0-9a-f]{40}', value[key])
                   for key in ('client_revision', 'xray_revision'))
            or any(not re.fullmatch(r'v?\d+\.\d+\.\d+', value[key])
                   for key in ('xray_version', 'go_version', 'rust_version'))):
        raise ValueError('invalid-engine-pins')
    expected = yaml.safe_load((ROOT / 'secrets/prod.secrets.example.yaml').read_bytes())['xray']['version']
    tools = tomllib.loads((ROOT / 'mise.toml').read_text())['tools']
    if value['xray_version'] != expected or value['go_version'] != tools['go']:
        raise ValueError('engine-release-pin-drift')
    return value


def checkout(path, revision):
    environment = command_environment()
    if (subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True, env=environment).strip() != revision
            or subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain'], env=environment)):
        raise ValueError('clean-pinned-engine-checkout-required')


def checked(command, cwd, environment, *, limit=600, expected_test=None):
    print('engine-check: ' + (expected_test or Path(command[0]).name), flush=True)
    code, output = run_command(command, cwd=cwd, environment=environment, timeout=limit,
                               capture=True, output_limit=1024 * 1024, forward_stderr=True)
    text = output.decode(errors='replace')
    if expected_test:
        print(text, end='', flush=True)
        if (f'test {expected_test} ... ok' not in text
                or re.findall(r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', text, re.MULTILINE)
                != [('1', '0', '0')]):
            raise RuntimeError('exactly-one-executed-upstream-test-required')
    if code:
        raise RuntimeError('engine-command-failed')
    return text


def stop_peer(peer):
    try:
        if peer.poll() is None:
            peer.terminate()
            try:
                peer.wait(timeout=5)
            except subprocess.TimeoutExpired:
                peer.kill()
                peer.wait(timeout=5)
    finally:
        for stream in (peer.stdin, peer.stdout):
            if stream is not None:
                stream.close()


def announcement(peer, timeout=15):
    payload = bytearray()
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        selector.register(peer.stdout, selectors.EVENT_READ)
        while not payload.endswith(b'\n'):
            if not selector.select(max(0, deadline - time.monotonic())):
                raise TimeoutError('peer-startup-deadline')
            data = os.read(peer.stdout.fileno(), 1)
            if not data or len(payload) >= 4096:
                raise ValueError('bounded-peer-announcement-required')
            payload.extend(data)
    endpoints = json.loads(payload)
    if not isinstance(endpoints, dict):
        raise ValueError('peer-announcement-required')
    for name, value in endpoints.items():
        if not re.fullmatch('[a-z][a-z0-9_]*', name) or not isinstance(value, str) or len(value) > 4096:
            raise ValueError('peer-field-refused')
    for name in ('endpoint', 'tcp', 'udp', 'udp2', 'stats', 'tls', 'vision', 'minimum',
                 'maximum', 'stall', 'closed', 'stall_relay', 'xhttp'):
        if name in endpoints:
            if not isinstance(endpoints[name], str):
                raise ValueError('peer-address-required')
            host, port = endpoints[name].rsplit(':', 1)
            if not ipaddress.ip_address(host).is_loopback or not 0 < int(port) <= 65535:
                raise ValueError('loopback-only-peer-required')
    if 'endpoint' not in endpoints:
        raise ValueError('peer-endpoint-required')
    return endpoints


def run(client, candidate):
    policy = pins()
    checkout(client, policy['client_revision'])
    checkout(candidate, policy['xray_revision'])
    rust = tomllib.loads((client / 'native/rust/rust-toolchain.toml').read_text())['toolchain']['channel']
    if rust != policy['rust_version']:
        raise ValueError('client-rust-pin-drift')
    if subprocess.check_output(['git', '-C', str(candidate), 'rev-parse', policy['xray_version']],
                               text=True, env=command_environment()).strip() != policy['xray_revision']:
        raise ValueError('candidate-release-tag-mismatch')
    if sys.platform == 'darwin' and os.environ.get('BUILD_GATE_HELD') != '1':
        raise ValueError('build-gate-required')
    spec = importlib.util.spec_from_file_location('supported_client_oracle', client / 'scripts/tests/run-outbound-interop.py')
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    env = command_environment({'GOMAXPROCS': '2', 'GOTOOLCHAIN': 'local',
              'GOFLAGS': '-p=2', 'GOWORK': 'off', 'RUSTUP_TOOLCHAIN': policy['rust_version'],
              'CARGO_BUILD_JOBS': '2', 'CMAKE_BUILD_PARALLEL_LEVEL': '2'})
    if os.environ.get('BUILD_GATE_HELD') == '1':
        env['BUILD_GATE_HELD'] = '1'
    if checked(['go', 'env', 'GOVERSION'], candidate, env, limit=30).strip() != 'go' + policy['go_version']:
        raise ValueError('go-toolchain-mismatch')
    if not checked(['rustc', '--version'], candidate, env, limit=30).startswith('rustc ' + policy['rust_version'] + ' '):
        raise ValueError('rust-toolchain-mismatch')
    native = client / 'native/rust'
    with tempfile.TemporaryDirectory(prefix='vpn-engine-interop-') as temp:
        binary = Path(temp) / 'xray-peer'
        checked(['go', 'build', '-mod=readonly', '-trimpath', '-o', str(binary),
                        str(client / 'scripts/tests/outbound-vless-oracle/main.go')], candidate, env)
        for test in oracle.TESTS['vless']:
            backend = test.startswith('tests::')
            command = ['cargo', 'test', '--locked', '-p', 'ripdpi-relay-core' if backend else 'ripdpi-vless',
                       *(['--lib'] if backend else ['--test', 'upstream_interop']), '--jobs', '2', test]
            checked(command + ['--no-run'], native, env)
            peer = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, start_new_session=True, env=env)
            try:
                endpoints = announcement(peer)
                selected = dict(env, RIPDPI_OUTBOUND_INTEROP_ENDPOINT=endpoints['endpoint'])
                for name, value in endpoints.items():
                    selected['RIPDPI_OUTBOUND_' + name.upper()] = value
                if backend:
                    selected['RIPDPI_OUTBOUND_EXPECT_IDLE'] = '1'
                checked(command + ['--', '--ignored', '--exact', '--nocapture'], native,
                               selected, limit=35, expected_test=test)
                peer.stdin.write(b'stop\n');peer.stdin.flush()
                if peer.wait(timeout=5):
                    raise ValueError('peer-stop-failed')
            finally:
                stop_peer(peer)
    print(json.dumps({'phase': 'real-engine-interop-passed', **policy,
                      'executed_tests': list(oracle.TESTS['vless'])}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    args = parser.parse_args()
    try:
        with cancellation():
            run(args.client.resolve(), args.candidate.resolve())
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ReadinessError, subprocess.SubprocessError, TimeoutError):
        print('engine interoperability failed; no production acceptance claimed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
