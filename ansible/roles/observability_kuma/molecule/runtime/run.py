#!/usr/bin/env python3
"""Explicit disposable real-image test; run through build-gate, never on live data."""

import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import yaml

HERE = Path(__file__).resolve().parent
prefix = 'kuma-test-' + uuid.uuid4().hex[:16]
containers = []
volumes = []


def docker(*args, **kwargs):
    result = subprocess.run(['docker', *args], capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError('disposable runtime command failed: ' + result.stderr.decode(errors='replace')[:1024])
    return result


architecture = docker('info', '--format', '{{.Architecture}}').stdout.decode().strip()
architecture = {'arm64': 'aarch64', 'aarch64': 'aarch64', 'amd64': 'x86_64', 'x86_64': 'x86_64'}[architecture]
defaults = yaml.safe_load((HERE / '../../defaults/main.yml').read_text())['observability_kuma']
IMAGE = defaults['image_repository'] + '@' + defaults['image_digests'][architecture]


def ready(name):
    for _ in range(60):
        result = subprocess.run(['docker', 'exec', name, 'node', '-e', "fetch('http://127.0.0.1:3001/api/entry-page').then(async r=>{const j=await r.json();process.exit(r.status===200&&j.type==='entryPage'?0:1)}).catch(()=>process.exit(1))"], capture_output=True, timeout=10)
        if result.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError('container readiness failed')


def create(suffix):
    name = prefix + '-' + suffix
    volume = name + '-data'
    docker('volume', 'create', '--label', 'vpn-deploy.test=' + prefix, volume)
    volumes.append(volume)
    docker('create', '--name', name, '--label', 'vpn-deploy.test=' + prefix, '--network', 'none', '--env', 'UPTIME_KUMA_DB_TYPE=sqlite', '--user', '1000:1000', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=67108864', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '536870912', '--memory-swap', '536870912', '--cpus', '0.25', '--pids-limit', '128', '--log-driver', 'none', '--mount', 'type=volume,src=' + volume + ',dst=/app/data', IMAGE)
    containers.append(name)
    return name


LOGIN = b"""
const fs = require('node:fs');
const {io} = require('/app/node_modules/socket.io-client');
const config = JSON.parse(fs.readFileSync('/app/data/runtime-test-credentials.json'));
const socket = io('http://127.0.0.1:3001', {transports:['polling']});
let monitors = {};
socket.on('monitorList', value => {monitors = value;});
socket.on('connect', () => socket.emit('login', config, answer => {
  if (!answer.ok) process.exit(1);
  socket.emit('getMonitorList', result => {
    if (!result.ok || !config.ids.every(id => monitors[id])) process.exit(2);
    socket.disconnect(); process.exit(0);
  });
}));
setTimeout(() => process.exit(3), 15000);
"""


try:
    original = create('original')
    docker('start', original)
    ready(original)
    print('pinned rootless 512MiB/0.25CPU image ready', flush=True)
    result = docker('exec', '-i', original, 'node', '-', input=(HERE / 'push-runtime.cjs').read_bytes(), timeout=660)
    print(result.stdout.decode(), flush=True)
    docker('restart', '--time', '30', original)
    ready(original)
    docker('exec', '-i', original, 'node', '-', input=LOGIN, timeout=30)
    print('authenticated monitor persistence after restart verified', flush=True)
    docker('stop', '--time', '30', original)
    # Quiesced docker-cp tar stream -> age: no plaintext archive on disk.
    with tempfile.TemporaryDirectory(prefix='kuma-runtime-backup-') as directory:
        root = Path(directory)
        key = root / 'identity'
        subprocess.run(['age-keygen', '-o', str(key)], check=True, capture_output=True)
        recipient = subprocess.run(['age-keygen', '-y', str(key)], check=True, capture_output=True).stdout
        recipients = root / 'recipient'
        recipients.write_bytes(recipient)
        archive = root / 'data.tar.age'
        with archive.open('xb') as sink:
            tar = subprocess.Popen(['docker', 'cp', original + ':/app/data/.', '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            encrypted = subprocess.run(['age', '-R', str(recipients)], stdin=tar.stdout, stdout=sink, stderr=subprocess.PIPE, timeout=120)
            tar.stdout.close()
            assert tar.wait(timeout=30) == 0 and encrypted.returncode == 0
        os.chmod(archive, 0o600)
        restored = create('restored')
        decrypted = subprocess.Popen(['age', '-d', '-i', str(key), str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        copied = subprocess.run(['docker', 'cp', '-a', '-', restored + ':/app/data'], stdin=decrypted.stdout, capture_output=True, timeout=120)
        decrypted.stdout.close()
        assert decrypted.wait(timeout=30) == 0 and copied.returncode == 0
        docker('start', restored)
        ready(restored)
        docker('exec', '-i', restored, 'node', '-', input=LOGIN, timeout=30)
        assert docker('inspect', '--format', '{{.HostConfig.NetworkMode}}', restored).stdout.strip() == b'none'
        assert docker('inspect', '--format', '{{json .HostConfig.PortBindings}}', restored).stdout.strip() in {b'{}', b'null'}
        print('quiesced age-encrypted backup and authenticated isolated restore verified; notifications blocked by network=none', flush=True)
finally:
    for name in reversed(containers):
        docker('rm', '-f', name)
    for name in reversed(volumes):
        docker('volume', 'rm', name)
    print('removed only this run\'s disposable containers, volumes and ephemeral backup keys', flush=True)
