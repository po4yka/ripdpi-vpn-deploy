"""Real local maintenance lifecycle, encrypted diagnostics and recovery archives."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.error
import zipfile
import yaml

import pytest

import operator_maintenance_io as private

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def write(path, value, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else value.encode())
    path.chmod(mode)
    return path


@pytest.fixture
def authority(tmp_path):
    tmp_path.chmod(0o700)
    identity = tmp_path / 'identity'
    subprocess.run(['age-keygen', '-o', str(identity)], capture_output=True, check=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    return tmp_path, identity, recipient


def decrypt(identity, path):
    return subprocess.run(['age', '-d', '-i', str(identity), str(path)], check=True, capture_output=True).stdout


def test_real_encrypted_command_retains_nonzero_output_without_plaintext(authority):
    directory, identity, recipient = authority
    destination = directory / 'diagnostic.age'
    code = private.encrypted_command([sys.executable, '-c', 'import sys; print("private-marker"); sys.exit(7)'],
                                     destination, recipient, environment=private.command_environment(), cwd=directory)
    assert code == 7
    assert b'private-marker' not in destination.read_bytes()
    assert b'private-marker' in decrypt(identity, destination)
    assert destination.stat().st_mode & 0o777 == 0o600


def test_timeout_reclaims_child_and_keeps_authenticated_diagnostics(authority):
    directory, identity, recipient = authority
    destination = directory / 'timeout.age'
    from bootstrap_readiness import CommandTimeout
    with pytest.raises(CommandTimeout):
        private.encrypted_command([sys.executable, '-u', '-c',
                                   'import time; print("before-timeout"); time.sleep(30)'],
                                  destination, recipient, environment=private.command_environment(),
                                  cwd=directory, timeout=0.2)
    assert b'before-timeout' in decrypt(identity, destination)


@pytest.mark.parametrize('failure', [RuntimeError, KeyboardInterrupt, SystemExit])
def test_encrypted_command_publishes_diagnostics_before_reraising(authority, monkeypatch, failure):
    directory, identity, recipient = authority
    destination = directory / 'interrupted.age'
    error = failure('command-interrupted')

    def interrupted_command(*args, output_fd, **kwargs):
        os.write(output_fd, b'partial-private-diagnostic')
        raise error

    monkeypatch.setattr(private, 'run_command', interrupted_command)
    with pytest.raises(failure) as caught:
        private.encrypted_command(['unused-command'], destination, recipient,
                                  environment=private.command_environment(), cwd=directory)
    assert caught.value is error
    assert decrypt(identity, destination) == b'partial-private-diagnostic'
    assert b'partial-private-diagnostic' not in destination.read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o600


def test_resource_lock_stays_held_until_stack_closes_after_failure(authority):
    directory, _, _ = authority
    fleet = load('fleet-maintenance')
    path = directory / 'resource.lock'
    with pytest.raises(FileNotFoundError):
        with ExitStack() as stack:
            stack.enter_context(fleet.resource_lock(path))
            with path.open('r+b') as contender:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (directory / 'missing').read_bytes()
    with path.open('r+b') as contender:
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize('fault', ['unsafe-file', 'contended-lock'])
def test_resource_lock_closes_stream_when_entry_fails(authority, monkeypatch, fault):
    directory, _, _ = authority
    fleet = load('fleet-maintenance')
    path = write(directory / 'resource.lock', b'', 0o644 if fault == 'unsafe-file' else 0o600)
    streams = []

    def tracked_open(*args, **kwargs):
        stream = open(*args, **kwargs)
        streams.append(stream)
        return stream

    monkeypatch.setattr(fleet, 'open', tracked_open, raising=False)
    with path.open('r+b') as contender:
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        expected = private.MaintenanceError if fault == 'unsafe-file' else BlockingIOError
        with pytest.raises(expected):
            with fleet.resource_lock(path):
                pytest.fail('invalid lock was admitted')
    assert len(streams) == 1 and streams[0].closed


@pytest.mark.parametrize('extra', [False, True])
def test_routine_context_decrypts_only_exact_profile_and_excludes_admin(authority, monkeypatch, extra):
    directory, identity, recipient = authority
    profile = {'B2_APPLICATION_KEY_ID': 'synthetic-id', 'B2_APPLICATION_KEY': 'synthetic-key'}
    if extra:
        profile['VULTR_API_KEY'] = 'synthetic-admin'
    cipher = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json',
                             '--output-type', 'json', '/dev/stdin'], input=json.dumps(profile).encode(),
                            check=True, capture_output=True).stdout
    path = write(directory / 'profile.sops.json', cipher)
    monkeypatch.setenv('VULTR_API_KEY', 'ambient-admin')
    context = load('operator-context')
    if extra:
        with pytest.raises(private.MaintenanceError, match='scope'):
            context.routine_environment(path, identity)
    else:
        environment = context.routine_environment(path, identity)
        assert environment['B2_APPLICATION_KEY_ID'] == 'synthetic-id'
        assert environment['B2_APPLICATION_KEY'] == 'synthetic-key'
        assert 'VULTR_API_KEY' not in environment
        assert 'SOPS_AGE_KEY_FILE' not in environment
    assert b'synthetic-key' not in path.read_bytes()


def binary(arch):
    data = bytearray(64)
    data[:6] = b'\x7fELF\x02\x01'
    data[18:20] = struct.pack('<H', {'amd64': 62, 'arm64': 183}[arch])
    return bytes(data)


def release_artifact(path, arch, *, version='3.15.1', duplicate=False, unsafe=False):
    with tarfile.open(path, 'w:gz') as archive:
        names = [f'prometheus-{version}.linux-{arch}/{name}' for name in ('prometheus', 'promtool')]
        if duplicate:
            names.append(names[0])
        if unsafe:
            names.append('../escape')
        for name in names:
            raw = binary(arch)
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(raw), 0o755
            archive.addfile(member, io.BytesIO(raw))
    path.chmod(0o600)
    return {'url': f'https://example.com/prometheus-3.15.1-{arch}.tar.gz', 'path': str(path),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'format': 'tar'}


@pytest.mark.parametrize('fault', ['none', 'old-members', 'checksum', 'duplicate', 'unsafe', 'architecture'])
def test_release_members_and_actual_binary_architectures(authority, fault):
    directory, _, _ = authority
    release = load('release-inputs')
    config = {'schema_version': 1, 'component': 'prometheus', 'version': '3.15.1', 'artifacts': {}}
    for arch in ('amd64', 'arm64'):
        config['artifacts'][arch] = release_artifact(directory / f'{arch}.tar.gz', arch,
            version='3.14.0' if fault == 'old-members' else '3.15.1',
            duplicate=fault == 'duplicate', unsafe=fault == 'unsafe')
    if fault == 'checksum':
        config['artifacts']['amd64']['sha256'] = '0' * 64
    if fault == 'architecture':
        config['artifacts']['arm64'] = dict(config['artifacts']['amd64'])
    if fault == 'none':
        result = release.prepare(config)
        assert result['ansible_variables']['observability_control_plane']['prometheus']['promtool_archive_members']['arm64'] == 'prometheus-3.15.1.linux-arm64/promtool'
        assert result['artifact_verification']['amd64']['ELF_architecture_verified']
    else:
        with pytest.raises(private.MaintenanceError):
            release.prepare(config)


@pytest.fixture
def kit(authority):
    directory, identity, recipient = authority
    root = directory / 'kit'
    root.mkdir(mode=0o700)
    for name in ('config', 'plans', 'receipts', 'recovery', 'runtime', 'state-backups'):
        (root / name).mkdir(mode=0o700)
    write(root / 'README.md', 'Private recovery kit')
    write(root / 'catalog.json', '{"schema_version":1}')
    write(root / 'config' / 'authority.sops.json', '{"sops":{"encrypted":true}}')
    write(root / 'runtime' / 'unrelated-working-key', 'excluded-marker')
    write(root / 'state-backups' / 'current.tfstate.age', 'encrypted-state-fixture')
    return load('operator-kit'), {'kit': str(root), 'recipient': recipient, 'identity': str(identity),
                                  'required_paths': ['config/authority.sops.json', 'state-backups/current.tfstate.age']}


def test_real_operator_kit_roundtrip_excludes_runtime_and_includes_states(kit):
    module, config = kit
    root = Path(config['kit'])
    result = module.backup(config, root / 'receipts' / 'verified.json', remote=False)
    receipt = json.loads((root / 'receipts/verified.json').read_bytes())
    restored = module.verify(config, (root / receipt['archive']).read_bytes())
    assert result['phase'] == 'local-decrypt-manifest-verified'
    assert 'state-backups/current.tfstate.age' in restored
    assert not any(name.startswith('runtime/') for name in restored)
    assert 'receipts/verified.json' not in restored


def test_operator_kit_refuses_changes_during_verification(kit, monkeypatch):
    module, config = kit
    real = module.verify
    def change_after_verify(*args):
        result = real(*args)
        write(Path(config['kit']) / 'config' / 'new.json', '{}')
        return result
    monkeypatch.setattr(module, 'verify', change_after_verify)
    with pytest.raises(private.MaintenanceError, match='inputs-changed'):
        module.backup(config, Path(config['kit']) / 'receipts' / 'false-claim.json', remote=False)
    assert not (Path(config['kit']) / 'receipts' / 'false-claim.json').exists()


@pytest.mark.parametrize('fault', ['none', 'single-request', 'wide-key', 'public', 'corrupt-download', 'anonymous'])
def test_offsite_backup_exercises_upload_download_scope_and_manifest(kit, authority, monkeypatch, fault):
    module, config = kit
    directory, _, _ = authority
    remote = directory / 'remote.age'
    mode = directory / 'upload-mode'
    if fault == 'single-request':
        write(Path(config['kit']) / 'config/opaque.bin', os.urandom(11 * 1024 * 1024))
    executable = write(directory / 'rclone', '#!/usr/bin/env python3\nimport pathlib,sys\n'
                       'source=pathlib.Path(sys.argv[4])\n'
                       'cutoff=int(sys.argv[sys.argv.index("--b2-upload-cutoff")+1].removesuffix("Mi"))*1024*1024\n'
                       f'pathlib.Path({str(mode)!r}).write_text("single" if source.stat().st_size <= cutoff else "multipart")\n'
                       f'pathlib.Path({str(remote)!r}).write_bytes(source.read_bytes())\n', 0o700)
    config.update(rclone=str(executable), rclone_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                  bucket_id='abc123', bucket_name='private-recovery-fixture')
    monkeypatch.setenv('B2_APPLICATION_KEY_ID', 'synthetic-id')
    monkeypatch.setenv('B2_APPLICATION_KEY', 'synthetic-key')
    calls = []
    class Response(io.BytesIO):
        status = 200
    class Backend:
        def open(self, request, timeout):
            url = request if isinstance(request, str) else request.full_url
            calls.append(url)
            if url.endswith('b2_authorize_account'):
                allowed = {'buckets': [{'id': 'abc123', 'name': config['bucket_name']}],
                           'namePrefix': None if fault == 'wide-key' else 'operator-kit/',
                           'capabilities': sorted(module.CAPABILITIES)}
                data = {'accountId': 'fixture', 'authorizationToken': 'synthetic-token',
                        'apiInfo': {'storageApi': {'apiUrl': 'https://api001.backblazeb2.com',
                         'downloadUrl': 'https://f001.backblazeb2.com', 'allowed': allowed}}}
            elif url.endswith('b2_list_buckets'):
                data = {'buckets': [{'bucketId': 'abc123', 'bucketName': config['bucket_name'],
                        'bucketType': 'allPublic' if fault == 'public' else 'allPrivate',
                        'defaultServerSideEncryption': {'value': {'algorithm': 'AES256', 'mode': 'SSE-B2'}}}]}
            elif url.endswith('b2_list_file_names'):
                data = {'files': [{'fileName': 'operator-kit/current.tar.age', 'fileId': 'fixture-object'}]}
            elif url.endswith('b2_get_file_info'):
                data = {'bucketId': 'abc123', 'fileName': 'operator-kit/current.tar.age',
                        'fileId': 'fixture-object', 'contentLength': remote.stat().st_size,
                        'serverSideEncryption': {'algorithm': 'AES256', 'mode': 'SSE-B2'}}
            else:
                if isinstance(request, str):
                    if fault == 'anonymous':
                        return Response(b'public')
                    raise urllib.error.HTTPError(url, 401, 'denied', {}, None)
                return Response(b'corrupt' if fault == 'corrupt-download' else remote.read_bytes())
            return Response(json.dumps(data).encode())
    monkeypatch.setattr(module.urllib.request, 'build_opener', lambda *_: Backend())
    output = Path(config['kit']) / 'receipts' / 'remote-verified.json'
    if fault in ('none', 'single-request'):
        result = module.backup(config, output, remote=True)
        assert result['phase'] == 'offsite-download-decrypt-manifest-verified'
        receipt = json.loads(output.read_text())
        assert receipt['delivery']['anonymous_status'] == 401
        catalog = json.loads((Path(config['kit']) / 'catalog.json').read_text())
        assert catalog['offsite_operator_kit']['receipt'] == 'receipts/remote-verified.json'
        assert catalog['offsite_operator_kit']['post_snapshot_acknowledgement_only']
        if fault == 'single-request':
            assert remote.stat().st_size > 10 * 1024 * 1024
            assert mode.read_text() == 'single'
    else:
        with pytest.raises(private.MaintenanceError):
            module.backup(config, output, remote=True)
        assert not output.exists()
        if fault == 'wide-key':
            assert len(calls) == 1


@pytest.mark.parametrize('kind', ['duplicate', 'traversal', 'symlink', 'manifest'])
def test_operator_kit_rejects_unsafe_or_ambiguous_decrypted_archives(kit, kind):
    module, config = kit
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w:gz') as archive:
        data = b'{}'
        for name in ('catalog.json', 'MANIFEST.json'):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        member = tarfile.TarInfo({'duplicate': 'catalog.json', 'traversal': '../out',
                                 'symlink': 'link', 'manifest': 'different.json'}[kind])
        if kind == 'symlink':
            member.type, member.linkname = tarfile.SYMTYPE, '/etc/passwd'
            archive.addfile(member)
        else:
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    cipher = subprocess.run(['age', '-r', config['recipient']], input=raw.getvalue(), check=True, capture_output=True).stdout
    with pytest.raises(private.MaintenanceError):
        module.verify(config, cipher)


@pytest.fixture
def maintenance(authority, isolated_synthetic_git_config, request):
    directory, identity, recipient = authority
    root = directory / 'controller'
    root.mkdir(mode=0o700)
    shutil.copytree(ROOT / 'scripts', root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT / 'contract', root / 'contract')
    write(root / '.gitignore', 'secrets/\n__pycache__/\n')
    write(root / 'Makefile', '.PHONY: decrypt dry-run deploy verify security-verify smoke-test clean\n'
          'decrypt dry-run deploy verify security-verify smoke-test clean:\n\t@python3 boundary.py $@\n')
    write(root / 'boundary.py', '''import os,pathlib,sys,time,subprocess,json
root=pathlib.Path('secrets/local');goal=sys.argv[1];host=os.environ['ANSIBLE_LIMIT']
with (root/'calls').open('a') as f:f.write(host+':'+goal+'\\n')
print('encrypted-diagnostic-fixture',flush=True)
secret=pathlib.Path(os.environ['SECRETS_FILE'])
if goal=='decrypt':secret.write_text('synthetic-credential');secret.chmod(0o600)
if goal=='clean':secret.unlink(missing_ok=True)
if (root/'delay').exists() and goal=='deploy':time.sleep(.5)
if (root/'hang').exists() and (root/'hang').read_text()==goal:(root/'hang.pid').write_text(str(os.getpid()));time.sleep(60)
if (root/'catalog-race').exists() and goal=='deploy':
 c=json.loads((root/'catalog.json').read_bytes());c['current_actual_configuration'].setdefault(host,{})['core_source_revision']='a'*40
 (root/'catalog.json').write_text(json.dumps(c))
if (root/'fail').exists() and (root/'fail').read_text()==host+':'+goal:sys.exit(9)
if goal=='deploy':
 rev,gen=subprocess.check_output(['bash','scripts/deploy-source-identity.sh'],text=True).split()
 (root/(host+'-manifest.json')).write_text(json.dumps({'schema_version':2,'status':'observed','source_revision':rev,'deployable_digest':gen}))
''')
    kit = root / 'secrets/local'
    kit.mkdir(mode=0o700, parents=True)
    key = write(kit / 'ssh', 'synthetic-ssh-key')
    inventory = '[vpn]\n'
    for index, name in enumerate(('node-a', 'node-b'), 1):
        provider = 'upcloud' if index == 1 else 'vultr'
        inventory += f'{name} ansible_host=192.0.2.{index} ansible_port=22 ansible_user=admin ansible_ssh_private_key_file={key} env=prod provider={provider}\n'
    write(root / 'ansible/inventory/generated.ini', inventory)
    # This inventory is an admitted private input, not source in the synthetic controller.
    write(root / '.gitignore', 'secrets/\n__pycache__/\nansible/inventory/generated.ini\n')
    for name in ('sops', 'extra', 'pins', 'contexts'):
        write(kit / name, '{}')
    write(kit / 'extra', '{"ansible_port":22}')
    if getattr(request, 'param', None) == 'override-transport':
        write(kit / 'extra', json.dumps({'ansible_host': '100.64.0.1', 'ansible_port': 2222}))
        write(kit / 'extra-b', '{"ansible_port":22}')
        write(kit / 'expected-transport', '100.64.0.1')
    if getattr(request, 'param', None) == 'known-inputs':
        site = kit / 'site'
        site.mkdir(mode=0o700)
        write(site / 'index.html', '<html>fixture</html>')
        write(site / '404.html', 'missing')
        write(kit / 'exposure.json', '{}')
        write(kit / 'trusted.pem', 'synthetic-public-key')
        write(kit / 'extra', json.dumps({'nginx_xhttp_public_site_dir': str(site),
              'network_exposure_gate': {'mode': 'log_only', 'artifact': str(kit / 'exposure.json'),
                                        'trusted_key': str(kit / 'trusted.pem')}}))
    runtime, state = kit / 'runtime', kit / 'state'
    runtime.mkdir(mode=0o700);state.mkdir(mode=0o700)
    config = {'schema_version': 2, 'id': 'test-maintenance', 'catalog': str(kit / 'catalog.json'),
              'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
              'state_directory': str(state), 'runtime_parent': str(runtime),
              'age_identity': str(identity), 'log_recipient': recipient, 'nodes': [],
              'liveness_config': str(kit / 'liveness.yml'), 'liveness_inputs': []}
    live = {'schema_version': 2, 'probe_url': 'https://probe.example.org/check', 'expected_status': 204,
            'expected_runtime': {'awg': '1.0.0', 'awg_toolchain': 'a' * 64},
            'policies': [{'id': 'udp', 'required_profiles': ['p2-amneziawg'], 'min_failed_vantages': 1}],
            'sentinels': []}
    for name in ('node-a', 'node-b'):
        provider = 'upcloud' if name == 'node-a' else 'vultr'
        config['nodes'].append({'host': name, 'environment': 'prod', 'provider': provider,
            'sops_file': str(kit / 'sops'), 'extra_vars': str(kit / 'extra'),
            'known_hosts': str(kit / 'pins'), 'ssh_contexts': str(kit / 'contexts'), 'inputs': []})
        if name == 'node-b' and (kit / 'extra-b').exists():
            config['nodes'][-1]['extra_vars'] = str(kit / 'extra-b')
        address = '192.0.2.' + str(len(live['sentinels']) + 1)
        live['sentinels'].append({'id': name, 'ssh_target': name, 'vantage': 'external', 'policy': 'udp',
            'target': {'inventory_alias': name, 'public_service_address_sha256': hashlib.sha256(address.encode()).hexdigest(),
                       'deployable_digest': 'f' * 64, 'applied_at': 1},
            'awg_target': {'provider': provider, 'environment': 'prod', 'instance': 'awg0'}})
    write(kit / 'liveness.yml', yaml.safe_dump(live))
    write(kit / 'bin/ssh', '''#!/usr/bin/env python3
import json,pathlib,sys,time,datetime
k=pathlib.Path('secrets/local')
if '--' not in sys.argv:
 sys.stdin.read()
 sys.path.insert(0,'scripts');import fleet_inspection
 name='node-a' if any('HostKeyAlias=192.0.2.1' == arg or 'HostKeyAlias=[192.0.2.1]:2222' == arg for arg in sys.argv) else 'node-b'
 if name=='node-a' and (k/'expected-transport').exists():
  assert sys.argv[-2]=='100.64.0.1' and sys.argv[sys.argv.index('-p')+1]=='2222'
 manifest=json.loads((k/(name+'-manifest.json')).read_bytes())
 if (k/'wrong-source').exists():manifest['deployable_digest']='0'*64
 print(json.dumps({'schema_version':1,'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),
  'services':{unit:{'status':'unknown'} for unit in fleet_inspection.SERVICES},'manifest':manifest,
  'listeners':{'status':'unknown'},'backup':{'latest_snapshot':{'status':'unknown'},'restore':{'status':'unknown'}}}))
 sys.exit(0)
name=sys.argv[sys.argv.index('--')+1]
import yaml
c=yaml.safe_load((k/'liveness.yml').read_bytes());s=next(s for s in c['sentinels'] if s['id']==name)
rev='b'*40
target={**s['target'],'source_revision':rev,
 'required_profiles':['p2-amneziawg'],'runner_sha256':'c'*64,'public_profile_digest':'d'*64}
report={'schema_version':2,'sentinel':name,'observed_at':int(time.time()),'control':{'verdict':'ok'},
 'runtime':c['expected_runtime'],'provenance':{'controller_revision':rev,'runner_sha256':'c'*64,
 'public_profile_digest':'d'*64,'vantage':'external','client_generation_id':'7f574d16-931e-42b4-a940-853b92f53a14'},
 'target_identity':target,'profiles':[{'profile':'p2-amneziawg','verdict':'ok','payload_transport':'tcp-https',
 'target_address_family':'dualstack','dns_through_tunnel':not (k/'fail-protocol').exists(),
 'authenticated_handshake':True,'fresh_handshake':True,
 'family_results':{f:{'verdict':'ok','payload_transport':'tcp-https'} for f in ('ipv4','ipv6')}}]}
print(json.dumps(report))
''', mode=0o700)
    for command in (['git', 'init', '-q'], ['git', 'config', 'user.name', 'Maintenance fixture'],
                    ['git', 'config', 'user.email', 'fixture@example.invalid'], ['git', 'add', '.'],
                    ['git', 'commit', '-qm', 'test: create maintenance fixture']):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    write(kit / 'catalog.json', json.dumps({'current_actual_configuration': {}, 'unrelated': 'preserve'}))
    config_path = write(kit / 'config.json', json.dumps(config))
    plan = kit / 'plan.json'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PATH': str(kit / 'bin') + os.pathsep + os.environ['PATH']}
    def command(action, *extra):
        return subprocess.run([sys.executable, str(root / 'scripts/fleet-maintenance.py'), action,
                               '--config', str(config_path), '--plan', str(plan), *extra],
                              cwd=root, env=env, capture_output=True, text=True, timeout=20)
    result = command('prepare')
    assert result.returncode == 0, result.stderr
    def finish():
        end = time.monotonic() + 20
        while time.monotonic() < end:
            result = command('status')
            assert result.returncode == 0, result.stderr
            observed = json.loads(result.stdout)
            if not observed['worker_active']:
                return observed
            time.sleep(.05)
        raise AssertionError('maintenance worker did not finish')
    return root, kit, state, command, finish


def preview(maintenance):
    _, _, _, command, finish = maintenance
    result = command('preview')
    assert result.returncode == 0, result.stderr
    state = finish()
    assert state['status'] == 'previewed', state
    return state['review_sha256']


@pytest.mark.parametrize('maintenance', ['default', 'override-transport'], indirect=True)
def test_detached_maintenance_requires_review_and_accepts_nodes_in_order(maintenance):
    root, kit, state, command, finish = maintenance
    assert command('start').returncode != 0
    approval = preview(maintenance)
    write(kit / 'delay', 'delay')
    assert command('start', '--approval', approval).returncode == 0
    observed = finish()
    assert observed['status'] == 'complete'
    assert observed['accepted_nodes'] == ['node-a', 'node-b']
    calls = (kit / 'calls').read_text().splitlines()
    assert calls.index('node-a:smoke-test') < calls.index('node-b:deploy')
    assert not list((kit / 'runtime').iterdir())
    assert all(b'synthetic-credential' not in p.read_bytes() for p in state.iterdir())


@pytest.mark.parametrize('held', ['node-b', 'inventory'])
def test_contended_resource_lock_refuses_with_named_holder(maintenance, held):
    root, kit, _, command, _ = maintenance
    resources = json.loads((kit / 'plan.json').read_text())['resources']
    inventory = str(root / 'ansible/inventory/generated.ini')
    resource = inventory if held == 'inventory' else next(r for r in resources if r != inventory and r.endswith('.2'))
    locks = root / '.git/maintenance-locks'
    locks.mkdir(mode=0o700, exist_ok=True)
    path = write(locks / (hashlib.sha256(resource.encode()).hexdigest() + '.lock'), b'', 0o600)
    with path.open('r+b') as contender:
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = command('preview')
    expected = ('resource=inventory held-as=shared-inventory' if held == 'inventory'
                else 'alias=node-b held-as=target')
    assert result.returncode == 1
    assert f'operation refused (node-lock-busy: {expected})' in result.stderr


def test_prepare_refuses_missing_generated_inventory_with_render_command(maintenance):
    root, kit, _, command, _ = maintenance
    (root / 'ansible/inventory/generated.ini').unlink()
    (kit / 'plan.json').unlink()
    result = command('prepare')
    assert result.returncode == 1
    assert ('operation refused (generated-inventory-missing: run make inventory '
            'PROVIDER=<provider> ENV=<env>)') in result.stderr
    assert not (kit / 'plan.json').exists()


def test_failed_mutation_preserves_intent_cleans_and_resumes_exact_boundary(maintenance):
    _, kit, state, command, finish = maintenance
    approval = preview(maintenance)
    write(kit / 'fail', 'node-b:deploy')
    assert command('start', '--approval', approval).returncode == 0
    observed = finish()
    assert observed['status'] == 'failed'
    assert observed['accepted_nodes'] == ['node-a']
    journal = json.loads((state / 'journal.json').read_text())
    assert journal['intent']['name'] == 'deploy'
    assert not list((kit / 'runtime').iterdir())
    (kit / 'fail').unlink()
    assert command('resume', '--approval', approval).returncode == 0
    observed = finish()
    assert observed['status'] == 'complete'
    assert (kit / 'calls').read_text().count('node-a:deploy') == 1


@pytest.mark.parametrize('live', ['plan-source', 'changed-source'])
def test_resume_after_completed_deploy_reruns_acceptance_only_when_live_source_matches(maintenance, live):
    _, kit, state, command, finish = maintenance
    approval = preview(maintenance)
    write(kit / 'fail', 'node-b:verify')
    assert command('start', '--approval', approval).returncode == 0
    failed = finish()
    journal = json.loads((state / 'journal.json').read_text())
    (kit / 'fail').unlink()
    if live == 'changed-source':
        write(kit / 'wrong-source', 'wrong-source')
    assert command('resume', '--approval', approval).returncode == 0
    resumed = finish()
    calls = (kit / 'calls').read_text().splitlines()
    assert failed['status'] == 'failed' and journal['intent']['name'] == 'verify'
    plan_source = json.loads((kit / 'plan.json').read_text())['source']
    assert journal['observed']['converged'] == {'host': 'node-b', 'source': plan_source}
    if live == 'plan-source':
        # One preview dry-run plus one start dry-run; resume goes straight to acceptance.
        assert resumed['status'] == 'complete'
        assert calls.count('node-b:dry-run') == 2 and calls.count('node-b:deploy') == 1
        assert calls.count('node-b:decrypt') == 3 and calls.count('node-b:verify') == 2
        last_decrypt = len(calls) - 1 - calls[::-1].index('node-b:decrypt')
        assert calls[last_decrypt + 1:last_decrypt + 4] == ['node-b:verify', 'node-b:security-verify',
                                                            'node-b:smoke-test']
    else:
        # No live proof: the node converges again, and the protocol gate still refuses the wrong source.
        assert resumed['status'] == 'failed'
        assert calls.count('node-b:dry-run') == 3 and calls.count('node-b:deploy') == 2
    assert not list((kit / 'runtime').iterdir())


def test_failed_redeploy_clears_convergence_so_a_later_resume_deploys_again(maintenance):
    _, kit, state, command, finish = maintenance
    approval = preview(maintenance)
    write(kit / 'fail', 'node-b:verify')
    assert command('start', '--approval', approval).returncode == 0
    finish()
    # The probe sees another source, so resume converges again, and that deploy fails.
    write(kit / 'wrong-source', 'wrong-source')
    write(kit / 'fail', 'node-b:deploy')
    assert command('resume', '--approval', approval).returncode == 0
    second = finish()
    cleared = json.loads((state / 'journal.json').read_text())['observed']['converged']
    # The live manifest still reports the plan source from the first deploy.
    (kit / 'wrong-source').unlink()
    (kit / 'fail').unlink()
    assert command('resume', '--approval', approval).returncode == 0
    third = finish()
    calls = (kit / 'calls').read_text().splitlines()
    assert second['status'] == 'failed' and cleared is None
    assert third['status'] == 'complete'
    assert calls.count('node-b:deploy') == 3


def test_protocol_failure_stops_before_next_node_and_keeps_cleanup(maintenance):
    _, kit, state, command, finish = maintenance
    approval = preview(maintenance)
    write(kit / 'fail-protocol', 'dns')
    assert command('start', '--approval', approval).returncode == 0
    observed = finish()
    assert observed['status'] == 'failed'
    assert observed['accepted_nodes'] == []
    assert 'node-b:deploy' not in (kit / 'calls').read_text()
    assert json.loads((state / 'journal.json').read_text())['intent']['name'] == 'protocol-gate'
    assert not list((kit / 'runtime').iterdir())


def test_healthy_old_client_cannot_hide_wrong_deployed_server_source(maintenance):
    _, kit, _, command, finish = maintenance
    approval = preview(maintenance)
    write(kit / 'wrong-source', 'wrong-source')
    assert command('start', '--approval', approval).returncode == 0
    observed = finish()
    assert observed['status'] == 'failed'
    assert observed['accepted_nodes'] == []
    assert 'node-b:deploy' not in (kit / 'calls').read_text()
    assert not list((kit / 'runtime').iterdir())


def test_changed_frozen_private_input_refuses_before_decrypt(maintenance):
    _, kit, _, command, finish = maintenance
    approval = preview(maintenance)
    before = (kit / 'calls').read_bytes()
    write(kit / 'extra', '{"changed":true}')
    assert command('start', '--approval', approval).returncode != 0
    assert (kit / 'calls').read_bytes() == before


def test_concurrent_start_cannot_share_node_or_inventory(maintenance):
    _, kit, _, command, finish = maintenance
    approval = preview(maintenance)
    write(kit / 'delay', 'delay')
    assert command('start', '--approval', approval).returncode == 0
    assert command('resume', '--approval', approval).returncode != 0
    assert finish()['status'] == 'complete'
    assert (kit / 'calls').read_text().count('node-a:deploy') == 1


def test_preview_failure_never_authorizes_a_deploy(maintenance):
    _, kit, _, command, finish = maintenance
    write(kit / 'fail', 'node-a:dry-run')
    assert command('preview').returncode == 0
    assert finish()['status'] == 'failed'
    assert command('start').returncode != 0
    assert ':deploy' not in (kit / 'calls').read_text()
    assert not list((kit / 'runtime').iterdir())


def test_make_dispatch_refuses_expansion_and_does_not_load_fleet_file(authority):
    directory, _, _ = authority
    marker = directory / 'executed'
    write(directory / '.fleet.mk', f'$(shell touch {marker})\n')
    value = f'$(shell touch {marker})'
    result = subprocess.run(['make', '-f', str(ROOT / 'Makefile'), 'release-inputs',
                             'ACTION=verify', 'CONFIG=' + value], cwd=directory,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not marker.exists()


def test_status_reads_admitted_whole_inode_during_atomic_replacement(authority, monkeypatch):
    module = load('fleet-maintenance')
    directory, _, _ = authority
    state = directory / 'state'
    state.mkdir(mode=0o700)
    plan = {'state_directory': str(state)}
    real_open = os.open
    with module.Journal(plan) as journal:
        journal.observe('maintenance', {'status': 'prepared'})
        replaced = False
        def replace_after_open(path, *args, **kwargs):
            nonlocal replaced
            fd = real_open(path, *args, **kwargs)
            if Path(path).name == 'journal.json' and not replaced:
                replaced = True
                journal.observe('maintenance', {'status': 'running'})
            return fd
        monkeypatch.setattr(module.os, 'open', replace_after_open)
        result = module.status(plan)
        assert replaced
        assert result['status'] == 'prepared'
        assert not result['fresh_live_verification']
        assert json.loads((state / 'journal.json').read_bytes())['observed']['maintenance']['status'] == 'running'


def test_retained_cleanup_only_removes_owned_decrypt_outputs(authority):
    module = load('fleet-maintenance')
    directory, _, _ = authority
    state, runtime = directory / 'state', directory / 'runtime'
    state.mkdir(mode=0o700);runtime.mkdir(mode=0o700)
    attempt = runtime / 'maintenance-fixture'
    attempt.mkdir(mode=0o700)
    info = attempt.stat()
    plan = {'state_directory': str(state), 'runtime_parent': str(runtime)}
    with module.Journal(plan) as journal:
        journal.observe('runtime', {'path': str(attempt), 'identity': [info.st_dev, info.st_ino], 'environment': 'prod'})
        write(attempt / 'credentials.yaml', 'synthetic-secret')
        write(attempt / '.vpn-prod.secrets.abcdef', 'interrupted-sops-output')
        for name in module.ATTEMPT_INPUTS:
            write(attempt / name, 'owned-input-copy')
        foreign = write(attempt / 'unrelated', 'preserve')
        with pytest.raises(private.MaintenanceError, match='foreign-runtime-material'):
            module.cleanup_retained(plan, journal)
        assert (attempt / 'credentials.yaml').exists()
        foreign.unlink()
        module.cleanup_retained(plan, journal)
        assert not attempt.exists()
        assert journal.state['observed']['runtime'] is None


@pytest.mark.parametrize('replace_before_copy', [False, True])
def test_decrypt_consumes_only_approved_attempt_copies(authority, replace_before_copy):
    module = load('fleet-maintenance')
    directory, identity, _ = authority
    encrypted = write(directory / 'authority.sops.yaml', 'approved encrypted bytes')
    attempt = directory / 'attempt'
    attempt.mkdir(mode=0o700)
    plan = {'age_identity': str(identity), 'site_trees': {},
            'inputs': {str(path): {'private': True, 'sha256': private.digest_file(path)}
                       for path in (identity, encrypted)}}
    node = {'sops_file': str(encrypted), 'environment': 'prod', 'provider': 'upcloud', 'host': 'node-a'}
    if replace_before_copy:
        encrypted.write_text('unapproved encrypted bytes')
        with pytest.raises(private.MaintenanceError, match='frozen-input-changed'):
            module.prepare_attempt(plan, node, attempt)
        assert not list(attempt.iterdir())
    else:
        module.prepare_attempt(plan, node, attempt)
        encrypted.write_text('later authority replacement')
        env = module.node_environment(plan, node, attempt / 'credentials.yaml')
        assert Path(env['SOPS_FILE']).read_bytes() == b'approved encrypted bytes'
        assert private.digest_file(env['SOPS_AGE_KEY_FILE']) == plan['inputs'][str(identity)]['sha256']
        assert env['AGE_KEY'] == env['SOPS_AGE_KEY_FILE']
        assert json.loads(Path(env['DEPLOY_APPROVED_INPUTS_FILE']).read_bytes()) == {
            'files': plan['inputs'], 'trees': {}}


def test_failed_age_writer_cannot_produce_a_success_receipt(authority, monkeypatch):
    directory, _, recipient = authority
    tools = directory / 'bin'
    tools.mkdir(mode=0o700)
    write(tools / 'age', '#!/bin/sh\nexit 9\n', 0o700)
    monkeypatch.setenv('PATH', str(tools) + ':' + os.environ['PATH'])
    output = directory / 'invalid.age'
    with pytest.raises(private.MaintenanceError, match='encryption-failed'):
        private.encrypted_command([sys.executable, '-c', 'print("diagnostic")'], output, recipient,
                                  environment=private.command_environment(), cwd=directory)
    assert not output.exists()


def test_missing_required_recovery_file_refuses_before_sealing(kit):
    module, config = kit
    root = Path(config['kit'])
    (root / 'state-backups/current.tfstate.age').unlink()
    with pytest.raises(private.MaintenanceError, match='required-recovery-input-missing'):
        module.backup(config, root / 'receipts' / 'missing.json', remote=False)
    assert not list((root / 'state-backups').iterdir())


def test_storage_never_executes_a_relative_binary_under_another_directory(kit, authority, monkeypatch):
    module, config = kit
    directory, _, _ = authority
    marker = directory / 'executed'
    selected = write(directory / 'rclone', '#!/bin/sh\nexit 0\n', 0o700)
    write(Path(config['kit']) / 'rclone', f'#!/bin/sh\ntouch {marker}\n', 0o700)
    config.update(rclone='rclone', rclone_sha256=hashlib.sha256(selected.read_bytes()).hexdigest())
    monkeypatch.chdir(directory)
    storage = object.__new__(module.Storage)
    storage.config = config
    with pytest.raises(private.MaintenanceError, match='absolute-private-path-required'):
        storage.upload(directory / 'archive', b'cipher', directory / 'upload.age')
    assert not marker.exists()


@pytest.mark.parametrize('replacement', [False, True])
def test_resume_reconciles_removed_runtime_without_adopting_replacement(authority, replacement):
    module = load('fleet-maintenance')
    directory, _, _ = authority
    state, runtime = directory / 'state', directory / 'runtime'
    state.mkdir(mode=0o700);runtime.mkdir(mode=0o700)
    attempt = runtime / 'maintenance-retained'
    attempt.mkdir(mode=0o700)
    info = attempt.stat()
    plan = {'state_directory': str(state), 'runtime_parent': str(runtime)}
    with module.Journal(plan) as journal:
        journal.observe('runtime', {'path': str(attempt), 'identity': [info.st_dev, info.st_ino], 'environment': 'prod'})
        attempt.rmdir()
        if replacement:
            attempt.mkdir(mode=0o700)
            marker = write(attempt / 'foreign', 'preserve')
            with pytest.raises(private.MaintenanceError):
                module.cleanup_retained(plan, journal)
            assert marker.read_text() == 'preserve'
        else:
            module.cleanup_retained(plan, journal)
            assert journal.state['observed']['runtime'] is None


def test_cleanup_admits_empty_owned_files_left_before_first_decrypt_byte(authority):
    module = load('fleet-maintenance')
    directory, _, _ = authority
    state, runtime = directory / 'state', directory / 'runtime'
    state.mkdir(mode=0o700);runtime.mkdir(mode=0o700)
    attempt = runtime / 'maintenance-empty'
    attempt.mkdir(mode=0o700)
    info = attempt.stat()
    plan = {'state_directory': str(state), 'runtime_parent': str(runtime)}
    with module.Journal(plan) as journal:
        journal.observe('runtime', {'path': str(attempt), 'identity': [info.st_dev, info.st_ino], 'environment': 'prod'})
        write(attempt / 'credentials.yaml', '')
        write(attempt / '.vpn-prod.secrets.abcdef', '')
        module.cleanup_retained(plan, journal)
        assert not attempt.exists()


@pytest.mark.parametrize('expiry', [None, True, '2000-01-01T00:00:00Z', '2099-01-01'])
def test_deadline_rejects_missing_expired_or_timezone_free_grants(expiry):
    module = load('fleet-maintenance')
    with pytest.raises(private.MaintenanceError, match='authorization-expired-or-invalid'):
        module.deadline({'expires_at': expiry})


@pytest.mark.parametrize('component', ['prometheus', 'alertmanager', 'rclone', 'xray', 'vmagent', 'hysteria'])
def test_release_refuses_formats_not_used_by_the_actual_consumer(authority, component):
    directory, _, _ = authority
    module = load('release-inputs')
    raw = binary('amd64')
    path = write(directory / 'artifact', raw)
    config = {'schema_version': 1, 'component': component, 'version': '1.2.3',
              'artifacts': {arch: {'url': 'https://example.com/artifact', 'path': str(path),
                  'sha256': hashlib.sha256(raw).hexdigest(),
                  'format': 'zip' if component == 'hysteria' else 'binary'} for arch in ('amd64', 'arm64')}}
    if component == 'hysteria':
        config['runtime_release_version'] = 'v1.2.3-go1.27.3'
    with pytest.raises(private.MaintenanceError, match='invalid-artifact-configuration'):
        module.prepare(config)


def tar_bytes(entries):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w:xz') as archive:
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), 0o755
            archive.addfile(member, io.BytesIO(data))
    return result.getvalue()


def deb_bytes(arch, version, package='rclone'):
    control = f'Package: {package}\nVersion: {version}\nArchitecture: {arch}\nDescription: fixture\n'.encode()
    output = b'!<arch>\n'
    entries = [('debian-binary', b'2.0\n'), ('control.tar.xz', tar_bytes({'./control': control})),
               ('data.tar.xz', tar_bytes({'./usr/bin/rclone': binary(arch)}))]
    for name, data in entries:
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode()
        output += header + data + (b'\n' if len(data) % 2 else b'')
    return output


@pytest.mark.parametrize('component', ['prometheus', 'alertmanager', 'rclone', 'xray', 'vmagent', 'hysteria'])
def test_release_emits_current_role_variables_for_every_component(authority, component):
    directory, _, _ = authority
    module = load('release-inputs')
    version = '1.75.2+go1.27.3-1' if component == 'rclone' else '1.2.3'
    config = {'schema_version': 1, 'component': component, 'version': version, 'artifacts': {}}
    if component == 'hysteria':
        config['runtime_release_version'] = 'v1.2.3-go1.27.3'
    for arch in ('amd64', 'arm64'):
        if component == 'rclone':
            raw, kind = deb_bytes(arch, version), 'deb'
        elif component == 'xray':
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                archive.writestr('xray', binary(arch))
            raw, kind = output.getvalue(), 'zip'
        elif component == 'hysteria':
            raw, kind = binary(arch), 'binary'
        else:
            names = {'vmagent': ['vmagent-prod'],
                     'prometheus': [f'prometheus-{version}.linux-{arch}/{n}' for n in ('prometheus', 'promtool')],
                     'alertmanager': [f'alertmanager-{version}.linux-{arch}/{n}' for n in ('alertmanager', 'amtool')]}[component]
            raw, kind = tar_bytes({name: binary(arch) for name in names}), 'tar'
        path = write(directory / arch, raw)
        config['artifacts'][arch] = {'url': f'https://example.com/{arch}', 'path': str(path),
                                    'sha256': hashlib.sha256(raw).hexdigest(), 'format': kind}
    values = module.prepare(config)['ansible_variables']
    if component == 'prometheus':
        assert values['observability_control_plane']['prometheus']['version'] == '1.2.3'
    elif component == 'alertmanager':
        assert values['observability_control_plane']['alerting']['alertmanager']['amtool_archive_members']['amd64'] == 'alertmanager-1.2.3.linux-amd64/amtool'
    elif component == 'rclone':
        assert values['backup_rclone_version'] == '1.75.2+go1.27.3-1'
        assert values['backup_rclone_binary_sha256']['arm64'] == hashlib.sha256(binary('arm64')).hexdigest()
        assert set(values['backup_rclone_packages']) == {'amd64', 'arm64'}
    elif component == 'vmagent':
        assert values['observability_agent']['version'] == '1.2.3'
        assert values['observability_agent']['release_urls']['arm64'] == 'https://example.com/arm64'
        assert values['observability_control_plane']['relay'] == {
            'version': '1.2.3',
            'urls': {arch: f'https://example.com/{arch}' for arch in ('amd64', 'arm64')},
            'sha256': {arch: config['artifacts'][arch]['sha256'] for arch in ('amd64', 'arm64')},
            'archive_members': {'amd64': 'vmagent-prod', 'arm64': 'vmagent-prod'},
        }
    else:
        assert values[component]['linux_amd64_sha256'] == config['artifacts']['amd64']['sha256']
        assert values['hysteria_release_urls' if component == 'hysteria' else 'xray_runtime_release_urls']['amd64'] == 'https://example.com/amd64'
        if component == 'hysteria':
            assert values['hysteria_runtime_release_version'] == 'v1.2.3-go1.27.3'


@pytest.mark.parametrize('fault', ['name', 'version', 'architecture'])
def test_rclone_deb_identity_is_verified_before_role_input_generation(authority, fault):
    directory, _, _ = authority
    module = load('release-inputs')
    raw = deb_bytes('arm64' if fault == 'architecture' else 'amd64',
                    '1.2.2' if fault == 'version' else '1.2.3',
                    package='other' if fault == 'name' else 'rclone')
    with pytest.raises(private.MaintenanceError, match='deb-package-identity-mismatch'):
        list(module.deb_contents(raw, '1.2.3', 'amd64'))


@pytest.mark.parametrize('maintenance', ['known-inputs'], indirect=True)
@pytest.mark.parametrize('change', ['site-add', 'site-remove', 'site-empty', 'artifact', 'trusted-key'])
def test_known_omitted_dependencies_are_discovered_and_frozen(maintenance, change):
    _, kit, _, command, _ = maintenance
    approval = preview(maintenance)
    before = (kit / 'calls').read_bytes()
    if change == 'site-add':
        write(kit / 'site' / 'new.txt', '')
    elif change == 'site-remove':
        (kit / 'site' / 'index.html').unlink()
    elif change == 'site-empty':
        write(kit / 'site' / 'index.html', '')
    else:
        write(kit / ('exposure.json' if change == 'artifact' else 'trusted.pem'), 'changed')
    assert command('start', '--approval', approval).returncode != 0
    assert (kit / 'calls').read_bytes() == before


def test_kit_roundtrip_retains_empty_control_files_without_admitting_empty_secrets(kit, authority):
    module, config = kit
    directory, _, _ = authority
    root = Path(config['kit'])
    write(root / 'config' / 'operation.lock', '')
    write(root / 'config' / 'authority.sops.json.new-client.lock', '')
    write(root / 'receipts' / 'interrupted-diagnostic.log.age', '')
    result = module.backup(config, root / 'receipts' / 'empty-control.json', remote=False)
    assert result['phase'] == 'local-decrypt-manifest-verified'
    receipt = json.loads((root / 'receipts/empty-control.json').read_bytes())
    actual = module.verify(config, (root / receipt['archive']).read_bytes())
    assert actual['config/operation.lock'] == 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    assert actual['receipts/interrupted-diagnostic.log.age'] == 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    empty = write(directory / 'empty-private-config.json', '')
    with pytest.raises(private.MaintenanceError):
        private.read_bytes(empty)
    assert private.read_bytes(empty, allow_empty=True) == b''
    write(root / 'config' / 'bad.sops.json', '')
    with pytest.raises(private.MaintenanceError, match='empty-encrypted-authority'):
        module.snapshot(config)


def test_child_tools_keep_the_executing_python_and_exclude_administrative_credentials(authority, monkeypatch):
    directory, _, _ = authority
    tools = directory / 'shadow-tools'
    tools.mkdir(mode=0o700)
    write(tools / 'python3', '#!/bin/sh\necho wrong-interpreter\nexit 9\n', 0o700)
    monkeypatch.setenv('PATH', str(tools) + ':' + os.environ['PATH'])
    monkeypatch.setenv('B2_APPLICATION_KEY', 'synthetic-administrative-key')
    monkeypatch.setenv('VULTR_API_KEY', 'synthetic-administrative-key')
    environment = private.command_environment()
    result = subprocess.run(['python3', '-c', 'import sys; print(sys.executable)'], env=environment,
                            capture_output=True, text=True, check=True, timeout=10)
    assert Path(result.stdout.strip()).resolve() == Path(sys.executable).resolve()
    assert 'B2_APPLICATION_KEY' not in environment
    assert 'VULTR_API_KEY' not in environment


def test_opaque_sops_publication_keeps_mac_and_metadata_writer_refuses_it(authority):
    directory, identity, recipient = authority
    data = b'{"B2_APPLICATION_KEY_ID":"synthetic-id","B2_APPLICATION_KEY":"synthetic-key"}'
    env = private.command_environment({'SOPS_AGE_KEY_FILE': str(identity)})
    cipher = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json',
                             '--output-type', 'json', '/dev/stdin'], input=data, env=env,
                            capture_output=True, check=True, timeout=30).stdout
    target = directory / 'authority.sops.json'
    with private.new_file(target) as stream:
        stream.write(cipher)
    decoded = subprocess.run(['sops', '--decrypt', str(target)], env=env,
                             capture_output=True, check=True, timeout=30).stdout
    assert json.loads(decoded) == json.loads(data)
    encrypted = json.loads(cipher)
    with pytest.raises(private.MaintenanceError, match='byte-preserving'):
        private.update_document(target, hashlib.sha256(cipher).hexdigest(), encrypted)
    with pytest.raises(private.MaintenanceError, match='byte-preserving'):
        private.write_document(directory / 'sorted.sops.json', encrypted)
    assert target.read_bytes() == cipher
    assert not (directory / 'sorted.sops.json').exists()


def test_catalog_reconciles_only_accepted_core_and_resumes_publication(maintenance):
    _, kit, state, command, finish = maintenance
    approval = preview(maintenance)
    catalog = {'unrelated': 'preserve', 'current_actual_configuration': {
        'node-a': {'core_source_revision': 'a' * 40, 'monitoring_source_revision': 'b' * 40}}}
    write(kit / 'catalog.json', json.dumps(catalog))
    # A core change after preparation refuses before any host mutation.
    assert command('start', '--approval', approval).returncode == 1
    assert finish()['status'] == 'previewed'
    assert not (kit / 'calls').read_text().count(':deploy')
    catalog['current_actual_configuration']['node-a'].pop('core_source_revision')
    write(kit / 'catalog.json', json.dumps(catalog))
    # A competing writer during deploy is found at publication, after acceptance.
    write(kit / 'catalog-race', '')
    assert command('start', '--approval', approval).returncode == 0
    interrupted = finish()
    (kit / 'catalog-race').unlink()
    assert interrupted['accepted_nodes'] == ['node-a']
    assert interrupted['status'] == 'reconciliation-required'
    assert 'node-b:deploy' not in (kit / 'calls').read_text()
    write(kit / 'catalog.json', json.dumps(catalog))
    assert command('resume', '--approval', approval).returncode == 0
    assert finish()['status'] == 'complete'
    current = json.loads((kit / 'catalog.json').read_bytes())
    expected = json.loads((kit / 'plan.json').read_bytes())['source']
    record = current['current_actual_configuration']['node-a']
    assert record['core_source_revision'] == expected['revision']
    assert record['core_deployable_digest'] == expected['deployable_digest']
    assert record['monitoring_source_revision'] == 'b' * 40
    # The referenced evidence is inside the kit selection that offsite backups seal.
    assert record['current_operation_receipt'].startswith('receipts/maintenance/test-maintenance-')
    receipt = kit / record['current_operation_receipt']
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == record['current_operation_receipt_sha256']
    assert current['unrelated'] == 'preserve'
    assert (kit / 'calls').read_text().count('node-a:deploy') == 1


@pytest.mark.parametrize('fault', ['none', 'missing', 'symlink', 'duplicate'])
def test_generate_selects_catalog_nodes_and_rejects_unsafe_dependencies(maintenance, fault):
    _, kit, _, _, _ = maintenance
    import maintenance_catalog
    fleet = load('fleet-maintenance')
    existing = json.loads((kit / 'config.json').read_bytes())
    defaults = {key: existing[key] for key in ('age_identity', 'log_recipient', 'liveness_config', 'liveness_inputs')}
    nodes = {node['host']: node for node in existing['nodes']}
    nodes['node-b']['sops_file'] = 'sops'
    if fault == 'missing':
        nodes['node-b']['sops_file'] = 'missing'
    if fault == 'symlink':
        (kit / 'linked').symlink_to(kit / 'sops')
        nodes['node-b']['sops_file'] = 'linked'
    write(kit / 'catalog.json', json.dumps({'maintenance': {'defaults': defaults, 'nodes': nodes}}))
    request = {key: existing[key] for key in ('id', 'expires_at', 'catalog', 'state_directory', 'runtime_parent')}
    request.update(schema_version=1, nodes=['node-b', 'node-b'] if fault == 'duplicate' else ['node-b'])
    source = write(kit / 'request.json', json.dumps(request))
    destination = kit / 'generated.json'
    if fault != 'none':
        with pytest.raises(private.MaintenanceError):
            maintenance_catalog.generate(source, destination, fleet)
        assert not destination.exists()
    else:
        result = maintenance_catalog.generate(source, destination, fleet)
        generated = json.loads(destination.read_bytes())
        assert result['deployment_authorized'] is False
        assert generated['nodes'] == [{**existing['nodes'][1], 'sops_file': str(kit / 'sops')}]
        assert generated['schema_version'] == 2
        assert not (kit / 'calls').exists()


def test_check_verifies_without_deploy_or_catalog_reconciliation(maintenance):
    _, kit, _, command, finish = maintenance
    plan = json.loads((kit / 'plan.json').read_bytes())
    for host in ('node-a', 'node-b'):
        write(kit / (host + '-manifest.json'), json.dumps({'schema_version': 2, 'status': 'observed',
              'source_revision': plan['source']['revision'], 'deployable_digest': plan['source']['deployable_digest']}))
    before = (kit / 'catalog.json').read_bytes()
    assert command('check').returncode == 0
    assert finish()['status'] == 'checked'
    calls = (kit / 'calls').read_text().splitlines()
    assert calls == [host + ':' + goal for host in ('node-a', 'node-b')
                     for goal in ('decrypt', 'dry-run', 'verify', 'security-verify', 'clean')]
    assert (kit / 'catalog.json').read_bytes() == before
    assert not list((kit / 'runtime').iterdir())
    assert command('check').returncode == 1


def test_check_cannot_close_a_previewed_deployment(maintenance):
    _, _, _, command, finish = maintenance
    approval = preview(maintenance)
    assert command('check').returncode == 1
    assert finish()['status'] == 'previewed'
    assert command('start', '--approval', approval).returncode == 0
    assert finish()['status'] == 'complete'


def test_scheduler_render_preserves_argv_and_reports_overdue(authority):
    scheduler = load('operator-schedule')
    directory, _, recipient = authority
    plan = {'id': 'test-jobs', 'state_directory': str(directory), 'path': '/usr/bin:/bin',
            'python': sys.executable, 'expires_at': '2099-01-01T00:00:00Z',
            'jobs': {job: {'interval_seconds': 3600, 'timeout_seconds': 1200, 'max_age_seconds': 7200}
                     for job in scheduler.JOBS}}
    config = directory / 'plan with space.json'
    rendered = scheduler.render(plan, config, 'Darwin')
    import plistlib
    for value in rendered.values():
        plist = plistlib.loads(value.encode())
        assert str(config) in plist['ProgramArguments']
        assert plist['StartInterval'] == 3600
        assert plist['StandardOutPath'] == '/dev/null'
    relative = scheduler.render(plan, Path('relative-plan.json'), 'Linux')
    assert all(str(Path('relative-plan.json').absolute()) in line for line in relative.values())
    cron = scheduler.render(plan, config, 'Linux')
    assert all(line.startswith('0 */1 * * * ') for line in cron.values())
    assert all("'" + str(config) + "'" in line for line in cron.values())
    write(directory / 'drift.json', json.dumps({'phase': 'succeeded', 'plan_sha256': scheduler.digest(plan), 'last_success_at': '2000-01-01T00:00:00Z'}))
    report = scheduler.status(plan)
    assert report['jobs']['drift']['overdue']
    assert report['jobs']['backup']['phase'] == 'never-run'
    with pytest.raises(private.MaintenanceError):
        scheduler.render(plan, directory / 'bad%path', 'Linux')


@pytest.mark.parametrize('outcome', ['verified', 'no-readback', 'command-failed', 'overlap', 'expiry', 'expired'])
def test_scheduled_backup_requires_real_canonical_receipt(authority, monkeypatch, outcome):
    scheduler = load('operator-schedule')
    directory, identity, recipient = authority
    state = directory / 'scheduled'
    state.mkdir(mode=0o700)
    config = write(directory / 'backup-config.json', json.dumps({'identity': str(identity)}))
    profile = write(directory / 'profile.sops.json', '{"sops":{}}')
    plan = {'expires_at': '2099-01-01T00:00:00Z', 'state_directory': str(state), 'log_recipient': recipient, 'path': os.environ['PATH'],
            'backup_config': str(config), 'backup_profile': str(profile),
            'inputs': {str(path): {'sha256': private.digest_file(path)} for path in (config, profile, identity)},
            'jobs': {'backup': {'timeout_seconds': 60}}, 'backup_code': scheduler.backup_code()}
    if outcome in {'expiry', 'expired'}:
        plan['expires_at'] = (datetime.now(timezone.utc) + timedelta(seconds=0.5 if outcome == 'expiry' else -1)).isoformat()
    # Only the external routine-backup/storage boundary is replaced. Execute a real child,
    # real encryption and the scheduler's receipt validation and status writes.
    original = scheduler.encrypted_command
    def boundary(command, destination, recipient, **kwargs):
        output = next(value.removeprefix('--output=') for value in command if value.startswith('--output='))
        script = 'import json,os,sys,datetime,time; from pathlib import Path; '
        if outcome == 'expiry':
            script += 'print("private-backup-diagnostic",flush=True); time.sleep(2); '
        script += 'p=Path(sys.argv[1]); p.write_text(json.dumps({"phase":"offsite-download-decrypt-manifest-verified",'
        script += '"delivery":{"remote_verified":' + ('False' if outcome == 'no-readback' else 'True') + '},'
        script += '"files_verified":2,"manifest_sha256":"a"*64,"at":datetime.datetime.now(datetime.timezone.utc).isoformat()})); p.chmod(0o600); '
        script += 'print("private-backup-diagnostic"); sys.exit(' + ('7' if outcome == 'command-failed' else '0') + ')'
        return original([sys.executable, '-c', script, output], destination, recipient, **kwargs)
    monkeypatch.setattr(scheduler, 'encrypted_command', boundary)
    config_path = directory / 'schedule.json'
    if outcome == 'overlap':
        with private.private_lock(state / 'backup.lock'):
            with pytest.raises(BlockingIOError):
                scheduler.run(plan, config_path, 'backup')
        assert not (state / 'backup.json').exists()
        return
    if outcome == 'verified':
        assert scheduler.run(plan, config_path, 'backup')['phase'] == 'succeeded'
    else:
        from bootstrap_readiness import ReadinessError
        with pytest.raises((private.MaintenanceError, ReadinessError)):
            scheduler.run(plan, config_path, 'backup')
    status = json.loads((state / 'backup.json').read_bytes())
    assert bool(status['last_success_at']) == (outcome == 'verified')
    if outcome == 'expired':
        # An expired grant refuses before private inputs are copied or a command starts.
        assert 'run_directory' not in status and not list(state.glob('backup-*'))
        return
    runtime = Path(status['run_directory'])
    assert not (runtime / 'working-age.key').exists()
    if outcome == 'expiry':
        assert not (runtime / 'backup.json').exists()
    assert b'private-backup-diagnostic' not in (runtime / 'command.log.age').read_bytes()
    assert b'private-backup-diagnostic' in decrypt(identity, runtime / 'command.log.age')


@pytest.mark.parametrize('changed', [False, True])
def test_actual_ansible_check_counts_refuse_configuration_drift(authority, changed):
    directory, _, _ = authority
    controller = load('deploy-controller')
    # An already enabled controller callback keeps running beside the statistics callback.
    environment = controller.check_statistics_environment(ROOT, directory, private.command_environment(
        {'ANSIBLE_CALLBACKS_ENABLED': 'ansible.builtin.junit', 'JUNIT_OUTPUT_DIR': str(directory / 'junit')}))
    # Real check-mode execution, including a change that leaves the live file untouched.
    target = write(directory / 'managed.txt', 'old')
    play = write(directory / 'check.yml', yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'tasks': [{'ansible.builtin.copy': {'dest': str(target), 'content': 'new' if changed else 'old'}}]}]))
    environment.update(ANSIBLE_LOCAL_TEMP=str(directory / 'ansible-local'),
                       ANSIBLE_REMOTE_TEMP=str(directory / 'ansible-remote'),
                       ANSIBLE_INVENTORY_ENABLED='host_list',
                       ANSIBLE_CONFIG=str(write(directory / 'ansible.cfg', '[defaults]\n')))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', '--check', str(play)],
                            capture_output=True, env=environment, timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    assert target.read_text() == 'old'
    if changed:
        with pytest.raises(controller.DeployError, match='configuration-drift-detected'):
            controller.require_no_check_changes(directory / 'check-statistics.json')
    else:
        controller.require_no_check_changes(directory / 'check-statistics.json')
    counts = json.loads((directory / 'check-statistics.json').read_bytes())
    assert counts == {'hosts': 1, 'changed': int(changed), 'failures': 0, 'unreachable': 0}
    assert list((directory / 'junit').glob('*.xml'))


def test_scheduler_prepare_and_real_drift_child(maintenance):
    root, kit, _, _, _ = maintenance
    existing = json.loads((kit / 'config.json').read_bytes())
    backup = write(kit / 'backup-config.json', json.dumps({'schema_version': 1,
        'kit': str(kit), 'recipient': existing['log_recipient'], 'identity': existing['age_identity'],
        'rclone': sys.executable, 'rclone_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        'bucket_id': 'aabbcc', 'bucket_name': 'example-backup', 'required_paths': ['catalog.json']}))
    profile = write(kit / 'routine.sops.json', '{"sops":{}}')
    state = kit / 'runtime/scheduler'
    state.mkdir(mode=0o700)
    request = write(kit / 'schedule-request.json', json.dumps({'schema_version': 1, 'id': 'test-schedule',
        'expires_at': existing['expires_at'], 'state_directory': str(state),
        'maintenance_config': str(kit / 'config.json'), 'backup_config': str(backup), 'backup_profile': str(profile),
        'jobs': {job: {'interval_seconds': 3600, 'timeout_seconds': 60, 'max_age_seconds': 7200}
                 for job in ('drift', 'backup')}}))
    plan_path = kit / 'schedule.json'
    env = {**os.environ, 'PATH': str(kit / 'bin') + os.pathsep + os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'}
    def command(action, *args):
        return subprocess.run([sys.executable, str(root / 'scripts/operator-schedule.py'), action, *args],
                              env=env, cwd=root, capture_output=True, text=True, timeout=30)
    result = command('prepare', '--config', str(request), '--output', str(plan_path))
    assert result.returncode == 0, result.stderr
    plan = json.loads(plan_path.read_bytes())
    for host in ('node-a', 'node-b'):
        write(kit / (host + '-manifest.json'), json.dumps({'schema_version': 2, 'status': 'observed',
              'source_revision': plan['source']['revision'], 'deployable_digest': plan['source']['deployable_digest']}))
    for attempt in range(2):
        result = command('run', '--config', str(plan_path), '--job', 'drift')
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['phase'] == 'succeeded'
    write(kit / 'fail', 'node-a:verify')
    result = command('run', '--config', str(plan_path), '--job', 'drift')
    assert result.returncode == 1
    status = json.loads(command('status', '--config', str(plan_path)).stdout)
    assert status['jobs']['drift']['phase'] == 'failed'
    assert status['jobs']['drift']['last_success_at']
    assert not any(':deploy' in line for line in (kit / 'calls').read_text().splitlines())
    # A stage that outlives the drift budget is cancelled in its own session and the
    # node plaintext is cleaned before the child exits, not left for the next run.
    (kit / 'fail').unlink()
    write(kit / 'hang', 'dry-run')
    plan['jobs']['drift']['timeout_seconds'] = 3
    short = write(kit / 'schedule-short.json', json.dumps(plan))
    output = kit / 'runtime/scheduler/drift-short'
    output.mkdir(mode=0o700)
    started = time.monotonic()
    result = command('_drift', '--config', str(short), '--output', str(output))
    assert result.returncode != 0
    assert time.monotonic() - started < 25
    assert (kit / 'calls').read_text().splitlines()[-2:] == ['node-a:dry-run', 'node-a:clean']
    assert not list((kit / 'runtime').glob('maintenance-*'))
    hung = int((kit / 'hang.pid').read_text())
    end = time.monotonic() + 5
    while time.monotonic() < end:
        try:
            os.kill(hung, 0)
        except ProcessLookupError:
            break
        time.sleep(.05)
    else:
        raise AssertionError('timed-out stage outlived the drift child')
    # Backups bind the code they execute, not the controller revision or fleet inputs.
    backup_check = ('import json,sys; sys.path.insert(0, "scripts"); from recovery_io import module; '
                    'module("operator-schedule").recheck_backup(json.load(open(sys.argv[1])))')
    def recheck_backup():
        return subprocess.run([sys.executable, '-c', backup_check, str(plan_path)], cwd=root, env=env,
                              capture_output=True, text=True, timeout=30)
    write(root / 'ansible/inventory/generated.ini', '[vpn]\n')
    write(root / 'unrelated.md', 'operator edit')
    assert command('run', '--config', str(plan_path), '--job', 'drift').returncode == 1
    assert recheck_backup().returncode == 0
    with (root / 'scripts/operator-kit.py').open('a') as stream:
        stream.write('\n')
    assert 'backup-code-changed' in recheck_backup().stderr


@pytest.mark.parametrize('system', ['Linux', 'Darwin'])
def test_scheduler_install_remove_preserves_foreign_jobs(authority, monkeypatch, system):
    scheduler = load('operator-schedule')
    directory, _, _ = authority
    plan = {'id': 'owned', 'state_directory': str(directory), 'path': os.environ['PATH'], 'python': sys.executable,
            'jobs': {job: {'interval_seconds': 3600} for job in scheduler.JOBS}}
    monkeypatch.setattr(scheduler.os, 'uname', type('Uname', (), {'sysname': system}))
    monkeypatch.setattr(scheduler.Path, 'home', lambda: directory)
    monkeypatch.setattr(scheduler, 'recheck', lambda value: None)
    bin_path = directory / 'bin'
    write(bin_path / 'crontab', '#!/usr/bin/env python3\nimport os,pathlib,sys\np=pathlib.Path(os.environ["HOME"])/"crontab"\nif sys.argv[1]=="-l": print(p.read_text(),end="")\nelse: p.write_text(sys.stdin.read())\n', 0o700)
    write(bin_path / 'launchctl', '#!/usr/bin/env python3\nimport os,pathlib,sys\np=pathlib.Path(os.environ["HOME"])/"launch-calls"\nwith p.open("a") as f:f.write(" ".join(sys.argv[1:])+"\\n")\n', 0o700)
    foreign = '17 * * * * /usr/bin/true\n'
    write(directory / 'crontab', foreign)
    monkeypatch.setenv('HOME', str(directory))
    monkeypatch.setenv('PATH', str(bin_path) + os.pathsep + os.environ['PATH'])
    config = directory / 'plan.json'
    assert scheduler.install(plan, config)['phase'] == 'installed'
    assert scheduler.install(plan, config)['phase'] == 'installed'
    if system == 'Linux':
        installed = (directory / 'crontab').read_text()
        assert installed.count('# ripdpi-operator:owned:BEGIN') == 1
        assert installed.startswith(foreign)
    else:
        assert len(list((directory / 'Library/LaunchAgents').glob('*.plist'))) == 2
        assert (directory / 'launch-calls').read_text().count('bootstrap ') == 2
    assert scheduler.install(plan, config, remove=True)['phase'] == 'removed'
    assert (directory / 'crontab').read_text() == foreign
    assert not list((directory / 'Library/LaunchAgents').glob('*.plist'))
