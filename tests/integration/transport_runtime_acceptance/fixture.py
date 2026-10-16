"""Canonical roles in an owned Linux lab with a disconnected native TLS peer."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
import pwd
import grp
import zipfile
from pathlib import Path
import secrets
import signal
import time
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid

import yaml

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[3]
LIBRARY = ROOT / 'ansible/roles/runtime-release/files'
OWNED_ORIGIN = 'https://owned.example'
XRAY_PINS = {
    'v26.3.27': '23cd9af937744d97776ee35ecad4972cf4b2109d1e0fe6be9930467608f7c8ae',
    'v26.5.3': 'f9d7dd7492791430d48a9828fb36f32663577af787e8b363a1548dece21a7897',
}
HYSTERIA_PINS = {
    'v2.8.2': 'b11bf0fb5f84a3f5c6baff3696e899539e68af4cee868c9203cfb896784ad3b0',
    'v2.13.0': '907ba8c9693edb104b20582681fb7dc15639d5b64a9cbb616a7b539190a86691',
}

ARM_XRAY_PINS = {
    'v26.3.27': '4d30283ae614e3057f730f67cd088a42be6fdf91f8639d82cb69e48cde80413c',
    'v26.5.3': 'd6766870478cddaeb770625bf1a61dae2d5c0a1bc160abb21455698137f6071c',
}
ARM_HYSTERIA_PINS = {
    'v2.8.2': '802d77ae3ca37bdc235ec848edfaaa7cb9109007d9044f50b0746239269cb8cf',
    'v2.13.0': 'a68a61a84452ca250ce0368202521965ca9cc9d801a404f1dc9008ac6cf677a7',
}
ARCH = 'arm64' if os.uname().machine == 'aarch64' else 'amd64'
XRAY_PINS = ARM_XRAY_PINS if ARCH == 'arm64' else XRAY_PINS
HYSTERIA_PINS = ARM_HYSTERIA_PINS if ARCH == 'arm64' else HYSTERIA_PINS


def command(argv, timeout=30, **kwargs):
    result = subprocess.run(argv, capture_output=True, timeout=timeout, **kwargs)
    if result.returncode:
        raise RuntimeError('owned-runtime-fixture-command-refused')
    return result.stdout.decode()


def artifacts(directory):
    directory = directory / ARCH
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    for name, pins in [('xray', XRAY_PINS), ('hysteria', HYSTERIA_PINS)]:
        for version, digest in pins.items():
            path = directory / (name + '-' + version + ('.zip' if name == 'xray' else ''))
            if not path.exists():
                url = ('https://github.com/XTLS/Xray-core/releases/download/' + version + '/Xray-linux-' + ('arm64-v8a' if ARCH == 'arm64' else '64') + '.zip'
                       if name == 'xray' else 'https://github.com/apernet/hysteria/releases/download/app/' + version + '/hysteria-linux-' + ARCH)
                command(['curl', '--fail', '--silent', '--show-error', '--location', '--connect-timeout', '10',
                         '--max-time', '120', url, '--output', str(path)], timeout=125)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError('owned-runtime-fixture-pin-mismatch')
            path.chmod(0o755 if name == 'hysteria' else 0o644)
    return directory


class Lab:
    def __init__(self):
        if os.geteuid() != 0 or sys.platform != 'linux' or os.environ.get('TRANSPORT_NATIVE_ISOLATED') != '1' or os.uname().machine not in {'x86_64', 'aarch64'}:
            raise RuntimeError('owned-isolated-Linux-native-required')
        self.token = 'rta' + secrets.token_hex(4)
        self.namespace = self.token
        self.host_link, self.peer_link = self.token + 'h', self.token + 'p'
        self.private = Path(tempfile.mkdtemp(prefix=self.token + '-', dir='/var/lib'))
        self.private.chmod(0o700)
        self.resources = ExitStack()
        self.cli_backup = None
        self.created = False
        self.link_created = False
        self.claimed = False
        self.storage_claims = {}
        self.generic_storage = tuple(Path(raw) / '.ripdpi-transport-runtime'
            for raw in ('/etc/systemd/system', '/usr/local/bin', '/usr/local/libexec'))
        self.prior_users = {entry.pw_name for entry in pwd.getpwall()}
        self.prior_groups = {entry.gr_name for entry in grp.getgrall()}
        self.log = self.private / 'ansible.log'
        self.selected_assets = Path('/var/lib') / (self.token + '-selected-assets')
        self.assets_created = False
        self.artifacts = artifacts(ROOT / '.cache/transport-runtime-acceptance')
        self.context = merge_render_vars()
        self.context.pop('item', None)
        # Renderer defaults describe its static pin; convergence must resolve the
        # current runtime fact on every upgrade rather than retain that asset path.
        for name in list(self.context):
            if name.startswith('_transport_egress_') or name in {
                    'transport_egress_normalizer_config', 'transport_egress_input_config',
                    'transport_egress_policy_config_data', 'transport_egress_frontend_units',
                    'transport_egress_normalizer_uid', 'transport_egress_runtime_binary',
                    'xray_runtime_binary', 'xray_runtime_bundled_asset_dir',
                    'xray_bundled_asset_dir', 'xray_asset_dir'}:
                self.context.pop(name)
        self.context['ansible_python_interpreter'] = '/usr/bin/python3'
        self.context['vpn'].update(enable_xray_reality=True, enable_nginx_xhttp=False,
                                   enable_hysteria=False, enable_geodata=False,
                                   enable_warp_outbound=False, build_xray_from_source=False,
                                   xray_flow_mode='vision', xray_finalmask=False)
        self.context['xray'].update(version='v26.3.27', linux_amd64_sha256=XRAY_PINS['v26.3.27'],
                                    linux_arm64_sha256=XRAY_PINS['v26.3.27'], target='192.0.2.90:8444',
                                    server_names=['owned.example'], cohorts=[],
                                    clients=[{'name': 'native-device', 'uuid': str(uuid.uuid4()), 'short_id': secrets.token_hex(4)}])
        self.context['xray_runtime_release_urls'] = {'amd64': 'file://' + str(self.artifacts / 'xray-v26.3.27.zip'),
                                                  'arm64': 'file://' + str(self.artifacts / 'xray-v26.3.27.zip')}
        self.context.update(xray_fallback_port=0, xray_port=443, xray_runtime_user='xray', xray_runtime_group='xray',
                            xray_install_dir='/opt/xray', hysteria_install_root='/opt/hysteria',
                            transport_runtime_probe_url='https://192.0.2.80:18080/',
                            transport_runtime_probe_expected_status=204, transport_runtime_timeout_seconds=60,
                            transport_runtime_probe_clients={'xray':'native-device', 'hysteria':'native-device-h'},
                            public_site_canonical_url=OWNED_ORIGIN,
                            ansible_port=22, vpn_service_address='')
        self.context['transport_egress_secrets'] = {name + '_password': 'synthetic-' + secrets.token_hex(24)
            for name in ('direct_xray', 'direct_hysteria', 'direct_gateway', 'warp_xray', 'warp_gateway')}

    def __enter__(self):
        try:
            return self.setup()
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def setup(self):
        sys.path.insert(0, str(LIBRARY))
        from transport_runtime_probe import child
        tables = json.loads(command(['nft', '-j', 'list', 'tables']))
        if any(item.get('table', {}).get('name') == 'ripdpi_transport' for item in tables['nftables']):
            raise RuntimeError('native-fixture-kernel-authority-already-exists')
        # Explicit claims: no existing live transport authority may be retired.
        for path in ('/etc/xray', '/etc/hysteria', '/opt/xray', '/opt/hysteria',
                     '/etc/ripdpi/transport-egress', '/var/lib/ripdpi/transport-egress', '/var/lib/ripdpi/transport-runtime',
                     '/usr/local/libexec/ripdpi-transport-egress', '/var/lib/xray', '/var/lib/hysteria',
                     '/var/log/xray', '/var/log/hysteria'):
            if os.path.lexists(path):
                raise RuntimeError('native-fixture-authority-already-exists')
        for path in self.generic_storage:
            if os.path.lexists(path):
                raise RuntimeError('native-fixture-storage-already-exists')
        for unit in ('xray.service', 'hysteria-server.service', 'ripdpi-transport-generation.service',
                     'ripdpi-transport-normalizer.service', 'ripdpi-transport-direct.service',
                     'vpn-geodata-refresh.service', 'vpn-geodata-refresh.timer'):
            if os.path.lexists(Path('/etc/systemd/system', unit)):
                raise RuntimeError('native-fixture-unit-already-exists')
        for raw in ('/usr/local/bin/hysteria', '/usr/local/sbin/vpn-geodata-refresh.sh',
                    '/usr/local/sbin/vpn-geodata-publish'):
            if os.path.lexists(raw):
                raise RuntimeError('native-fixture-authority-already-exists')
        existing = Path('/usr/local/bin/xray')
        if existing.exists():
            # CI owns this exact artifact. Preserve its original inode and never
            # adopt or replace an unknown installer binary.
            with zipfile.ZipFile(self.artifacts / 'xray-v26.3.27.zip') as archive:
                expected = hashlib.sha256(archive.read('xray')).digest()
            if existing.is_symlink() or hashlib.sha256(existing.read_bytes()).digest() != expected:
                raise RuntimeError('native-fixture-cli-unowned')
            self.cli_backup = self.private / 'prior-xray'
            os.rename(existing, self.cli_backup)
        self.claimed = True
        for path in self.generic_storage:
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            path.mkdir(mode=0o700)
            self.storage_claims[path] = (path.stat().st_dev, path.stat().st_ino)
        self.sshd_runtime_created = not Path('/run/sshd').exists()
        if self.sshd_runtime_created:
            Path('/run/sshd').mkdir(mode=0o755)
            Path('/run/sshd').chmod(0o755)
        # /run is already a tmpfs mount in the owned systemd container. Avoid
        # stacking a new bind mount over systemd's live propagation directory
        # between protocol cases.
        if subprocess.run(['mountpoint', '-q', '/run']).returncode:
            command(['mount', '--bind', '/run', '/run'])
        command(['mount', '--make-rshared', '/run'])
        command(['ip', 'netns', 'add', self.namespace]); self.created = True
        command(['ip', 'link', 'add', self.host_link, 'type', 'veth', 'peer', 'name', self.peer_link]); self.link_created = True
        command(['ip', 'link', 'set', self.peer_link, 'netns', self.namespace])
        command(['ip', 'addr', 'add', '10.247.0.1/30', 'dev', self.host_link])
        command(['ip', 'link', 'set', self.host_link, 'up'])
        command(['ip', '-n', self.namespace, 'addr', 'add', '10.247.0.2/30', 'dev', self.peer_link])
        command(['ip', '-n', self.namespace, 'link', 'set', self.peer_link, 'up'])
        command(['ip', '-n', self.namespace, 'link', 'set', 'lo', 'up'])
        for address in ('192.0.2.80/32', '192.0.2.90/32'):
            command(['ip', '-n', self.namespace, 'addr', 'add', address, 'dev', 'lo'])
        command(['ip', 'route', 'add', '192.0.2.0/24', 'via', '10.247.0.2', 'dev', self.host_link])
        command(['ip', '-n', self.namespace, 'route', 'add', 'default', 'via', '10.247.0.1'])
        self.cert, self.key = self.private / 'cert.pem', self.private / 'key.pem'
        command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(self.key),
                 '-out', str(self.cert), '-days', '2', '-subj', '/CN=owned.example',
                 '-addext', 'subjectAltName=DNS:owned.example,IP:192.0.2.80'])
        self.cert.chmod(0o600); self.key.chmod(0o600)
        self.ca_path = Path('/usr/local/share/ca-certificates') / (self.token + '.crt')
        shutil.copyfile(self.cert, self.ca_path); self.ca_path.chmod(0o644)
        command(['update-ca-certificates'])
        self.resources.enter_context(child(['ip', 'netns', 'exec', self.namespace, 'openssl', 's_server',
            '-accept', '192.0.2.90:8444', '-tls1_3', '-alpn', 'h2', '-cert', str(self.cert), '-key', str(self.key), '-quiet']))
        canary = self.private / 'canary.py'
        canary.write_text('''from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
import ssl,sys
class Canary(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(204);self.end_headers()
 def log_message(self,*args): pass
class CanaryServer(HTTPServer):
 def server_bind(self):
  TCPServer.server_bind(self)
  self.server_name,self.server_port=self.server_address
server=CanaryServer(('192.0.2.80',18080), Canary)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(sys.argv[1],sys.argv[2])
server.socket=context.wrap_socket(server.socket,server_side=True)
server.serve_forever()
''')
        canary.chmod(0o600)
        self.resources.enter_context(child(['ip', 'netns', 'exec', self.namespace, '/usr/bin/python3',
                                           str(canary), str(self.cert), str(self.key)]))
        runtime = self.private / 'initial-xray'
        runtime.mkdir(mode=0o755)
        command(['unzip', '-q', str(self.artifacts / 'xray-v26.3.27.zip'), '-d', str(runtime)])
        key_fields = dict(line.split(': ', 1) for line in command([str(runtime / 'xray'), 'x25519']).splitlines() if ': ' in line)
        self.context['xray']['reality_private_key'] = key_fields['PrivateKey']
        self.context['hysteria'].pop('resource_profile', None)
        self.context['hysteria'].update(version='v2.8.2', linux_amd64_sha256=HYSTERIA_PINS['v2.8.2'],
            linux_arm64_sha256=HYSTERIA_PINS['v2.8.2'], cert_pem=self.cert.read_text(), key_pem=self.key.read_text(),
            masquerade_url=OWNED_ORIGIN, clients=[{'name': 'native-device-h', 'password': secrets.token_hex(24)}])
        self.context['hysteria_release_urls'] = {'amd64': 'file://' + str(self.artifacts / 'hysteria-v2.8.2'),
                                               'arm64': 'file://' + str(self.artifacts / 'hysteria-v2.8.2')}
        return self

    def converge(self, profile='xray', *, check=False, allow_failure=False, retire=False, site=False,
                 stage_only=False, fail_after_acceptance=False, interrupt_first_adoption=False, retain_commit=False):
        self.context['vpn'].update(enable_xray_reality=profile in {'xray', 'both'}, enable_hysteria=profile in {'hysteria', 'both'})
        path = self.private / 'converge.yml'
        play = {'hosts': 'localhost', 'connection': 'local', 'gather_facts': True,
                'vars': self.context, 'tasks': [{'name': 'Canonical complete transport consumer',
                'ansible.builtin.include_role': {'name': 'xray' if profile == 'xray' else 'hysteria'}}]}
        if retire:
            play['vars'] = {**self.context, ('xray_role_enabled' if profile == 'xray' else 'hysteria_role_enabled'): False}
        if site:
            play['vars'] = {**self.context, 'transport_egress_site_staging': True,
                'transport_site_transaction_active': True,
                'xray_role_enabled': profile in {'xray', 'both'},
                'hysteria_role_enabled': profile in {'hysteria', 'both'}}
            play['tasks'] = [
                {'name': 'Prepare complete native site', 'ansible.builtin.include_role':
                    {'name': 'transport-egress', 'tasks_from': 'prepare-site'}},
                {'name': 'Stage canonical Xray frontend', 'ansible.builtin.include_role': {'name': 'xray'}},
                {'name': 'Stage canonical Hysteria frontend', 'ansible.builtin.include_role': {'name': 'hysteria'}},
                {'name': 'Accept complete native site', 'ansible.builtin.include_tasks':
                    str(ROOT / 'ansible/playbooks/tasks/transport-egress-activate.yml')},
                {'name': 'Finish complete native site', 'ansible.builtin.command': {
                    'argv': ['/usr/bin/python3', '-Es',
                        '/usr/local/libexec/ripdpi-transport-egress/transport_runtime_outer.py', 'finish']},
                    'when': '(transport_egress_role_enabled | bool) or (_transport_egress_full_retirement | default(false) | bool)',
                    'changed_when': False, 'no_log': True}]
            if retain_commit:
                play['tasks'] = play['tasks'][:-1]
            if stage_only:
                play['tasks'] = play['tasks'][:3]
            if fail_after_acceptance:
                play['tasks'].insert(4, {'name': 'Inject failure after native consumer acceptance',
                    'ansible.builtin.fail': {'msg': 'owned-native-composition-failure'}})
            play['tasks'] = [{'name': 'Guard complete native egress composition', 'block': play['tasks'],
                'rescue': [
                    {'name': 'Restore complete canonical guarded route', 'ansible.builtin.include_role':
                        {'name': 'transport-egress', 'tasks_from': 'rollback'},
                        'when': '_transport_egress_transaction_started | default(false) | bool'},
                    {'name': 'Report owned composition refusal', 'ansible.builtin.fail':
                        {'msg': 'owned-native-composition-refused'}}]}]
        path.write_text(yaml.safe_dump([play], sort_keys=False));path.chmod(0o600)
        env = {key: value for key, value in os.environ.items() if not key.startswith('ANSIBLE_')}
        env.update(ANSIBLE_CONFIG=str(ROOT / 'ansible/ansible.cfg'), ANSIBLE_ROLES_PATH=str(ROOT / 'ansible/roles'),
                   ANSIBLE_STDOUT_CALLBACK='default', ANSIBLE_LOAD_CALLBACK_PLUGINS='false', ANSIBLE_NOCOLOR='1')
        with self.log.open('wb') as output:
            argv = ['ansible-playbook', '-i', 'localhost,', str(path)] + (['--check'] if check else [])
            if interrupt_first_adoption:
                state = Path('/var/lib/ripdpi/transport-runtime')
                if (state / 'accepted.json').exists() or not site or profile not in {'xray', 'hysteria'}:
                    raise RuntimeError('native-first-adoption-interruption-scope-invalid')
                unit = Path('/etc/systemd/system') / ('xray.service' if profile == 'xray' else 'hysteria-server.service')
                config = Path('/etc/xray/config.json' if profile == 'xray' else '/etc/hysteria/config.yaml')
                result = subprocess.Popen(argv, env=env, stdout=output, stderr=subprocess.STDOUT,
                                          start_new_session=True)
                try:
                    deadline = time.monotonic() + 180
                    while result.poll() is None and time.monotonic() < deadline:
                        if (state / 'pending.json').exists() and unit.exists() and config.exists():
                            # Ansible starts its command in another session; kill
                            # the actual descendant publisher, then its orchestrator.
                            publisher = None
                            for entry in Path('/proc').iterdir():
                                if not entry.name.isdigit():
                                    continue
                                try:
                                    argv = (entry / 'cmdline').read_bytes().split(b'\0')[:-1]
                                    if argv[-2:] != [b'--apply', b'--apply'] or b'transport_runtime_accept' not in b' '.join(argv):
                                        continue
                                    parent = int(entry.name)
                                    for _ in range(32):
                                        if parent == result.pid:
                                            publisher = int(entry.name)
                                            break
                                        fields = Path('/proc', str(parent), 'stat').read_text().rsplit(') ', 1)[1].split()
                                        parent = int(fields[1])
                                        if parent <= 1:
                                            break
                                except (FileNotFoundError, ProcessLookupError):
                                    continue
                            if publisher is None:
                                raise RuntimeError('native-first-adoption-publisher-unconfirmed')
                            os.killpg(result.pid, signal.SIGKILL)
                            os.kill(publisher, signal.SIGKILL)
                            result.wait(timeout=10)
                            if result.returncode != -signal.SIGKILL or (state / 'accepted.json').exists():
                                raise RuntimeError('native-first-adoption-interruption-unconfirmed')
                            return result.returncode
                        time.sleep(0.01)
                    raise RuntimeError('native-first-adoption-selection-not-observed')
                finally:
                    if result.poll() is None:
                        os.killpg(result.pid, signal.SIGKILL)
                        result.wait(timeout=10)
            else:
                result = subprocess.run(argv, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=600)
        if result.returncode and not allow_failure:
            raise RuntimeError('native-canonical-role-refused:' + json.dumps(self.failure_categories(), sort_keys=True))
        return result.returncode

    def failure_categories(self):
        # Only fixed task names and result counts survive cleanup. Never retain
        # Ansible result payloads, stderr, rendered parameters or credential files.
        import re
        lines = self.log.read_text(errors='replace').splitlines() if self.log.exists() else []
        task = 'unavailable'
        failures = []
        for line in lines:
            match = re.fullmatch(r'TASK \[([A-Za-z0-9_ :—,.()/-]{1,180})\] \*+', line)
            if match:
                task = match.group(1)
            if line.startswith('fatal:'):
                failures.append(task)
        codes = re.findall(
            r'transport-runtime-(?:refused:[a-z][a-z0-9-]{0,96}|frame:[A-Za-z_][A-Za-z_0-9]*:[0-9]{1,6})',
            '\n'.join(lines))
        return {'failed_tasks': failures[-8:], 'categories': codes[-9:], 'status': 'refused'}

    def upgrade(self, profile):
        if profile == 'xray':
            self.context['xray'].update(version='v26.5.3', linux_amd64_sha256=XRAY_PINS['v26.5.3'],
                                        linux_arm64_sha256=XRAY_PINS['v26.5.3'])
            self.context['xray_runtime_release_urls'] = dict.fromkeys(('amd64','arm64'), 'file://' + str(self.artifacts / 'xray-v26.5.3.zip'))
        else:
            self.context['hysteria'].update(version='v2.13.0', linux_amd64_sha256=HYSTERIA_PINS['v2.13.0'],
                                           linux_arm64_sha256=HYSTERIA_PINS['v2.13.0'])
            self.context['hysteria_release_urls'] = dict.fromkeys(('amd64','arm64'), 'file://' + str(self.artifacts / 'hysteria-v2.13.0'))

    def enable_hysteria_hopping(self):
        self.context['vpn']['enable_hysteria'] = True
        self.context['hysteria_port_range'] = '46000-46015'
        self.context['hysteria'].update(salamander_enabled=True,
            salamander_password='synthetic-' + secrets.token_hex(24))
        rendered = render_template(ROOT / 'ansible/roles/firewall/templates/nftables.conf.j2', self.context)
        redirects = [line.strip() for line in rendered.splitlines() if 'comment "hysteria-port-hopping"' in line]
        assert len(redirects) == 1
        self.hopping_table = self.token + 'hops'
        command(['nft', 'add', 'table', 'inet', self.hopping_table])
        self.resources.callback(command, ['nft', 'delete', 'table', 'inet', self.hopping_table])
        # Instrument the exact rendered redirect without adopting the host firewall.
        rules = ('add chain inet ' + self.hopping_table + ' prerouting { type nat hook prerouting priority dstnat; }\n'
                 + ''.join('add rule inet ' + self.hopping_table + ' prerouting udp dport ' + str(port) + ' counter\n'
                           for port in range(46000, 46016))
                 + 'add rule inet ' + self.hopping_table + ' prerouting ' + redirects[0] + '\n')
        command(['nft', '-f', '-'], input=rules.encode())

    def assert_hysteria_hopping(self):
        from transport_runtime_probe import child
        def counters():
            document = json.loads(command(['nft', '-j', 'list', 'chain', 'inet', self.hopping_table, 'prerouting']))
            return [expression['counter']['packets'] for item in document['nftables'] if 'rule' in item
                    for expression in item['rule']['expr'] if 'counter' in expression][:16]
        before = counters()
        assert len(before) == 16
        document = yaml.safe_load(Path('/etc/hysteria/config.yaml').read_bytes())
        document['listen'] = '10.247.0.1:46000-46015'
        configuration = self.private / 'hopped-authority.yaml'
        configuration.write_text(yaml.safe_dump(document));configuration.chmod(0o600)
        script = self.private / 'hopped-client.py'
        observed = self.private / ('hopped-observed-' + secrets.token_hex(8))
        script.write_text("""import json,sys,tempfile,time
from pathlib import Path
import yaml
sys.path.insert(0,sys.argv[1])
from transport_runtime_probe import child,free_port,hysteria_client,private_file,request
source=yaml.safe_load(Path(sys.argv[3]).read_bytes())
port=free_port()
client=hysteria_client(source,port,source['tls']['cert'],'native-device-h')
client['transport']={'udp':{'hopInterval':'5s'}}
with tempfile.TemporaryDirectory(prefix='native-hopped-client-') as temporary:
    path=private_file(Path(temporary),'client.yaml',yaml.safe_dump(client))
    with child([sys.argv[2],'client','-c',str(path)]) as process:
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            request(port,'https://192.0.2.80:18080/',204,process,deadline)
            if Path(sys.argv[4]).exists():
                # Require fresh authenticated delivery after observed multi-port traffic.
                request(port,'https://192.0.2.80:18080/',204,process,deadline)
                break
            time.sleep(.25)
        else:
            raise RuntimeError('actual-port-hop-unobserved')
""")
        script.chmod(0o600)
        # Upstream deliberately permits reselecting the same remote port. Observe
        # two actual destinations, rather than assuming one timer event changes it.
        with child(['ip', 'netns', 'exec', self.namespace, sys.executable, str(script),
                    str(LIBRARY), '/usr/local/bin/hysteria', str(configuration), str(observed)]) as process:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                assert process.poll() is None, 'hopped-client-exited-before-observation'
                after = counters()
                if sum(right > left for left, right in zip(before, after)) >= 2:
                    observed.write_text('two-destinations-observed')
                    observed.chmod(0o600)
                    assert process.wait(timeout=max(.1, deadline-time.monotonic())) == 0, 'post-hop-authentication-refused'
                    break
                time.sleep(.2)
            else:
                raise AssertionError('actual-port-hop-unobserved')
        # A control datagram outside the hop range must remain an ordinary UDP flow.
        import threading
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
            control.bind(('10.247.0.1', 46016));control.settimeout(5)
            destination = control.getsockname()[1]
            assert not 46000 <= destination <= 46015
            def echo():
                packet, peer = control.recvfrom(1024)
                control.sendto(packet, peer)
            worker = threading.Thread(target=echo)
            worker.start()
            try:
                command(['ip', 'netns', 'exec', self.namespace, sys.executable, '-c',
                    "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(3);" +
                    "s.sendto(b'unrelated-udp',('10.247.0.1',int(sys.argv[1])));" +
                    "assert s.recv(1024)==b'unrelated-udp'", str(destination)], timeout=10)
            finally:
                worker.join(timeout=6)
                assert not worker.is_alive(), 'control-udp-cleanup-unconfirmed'

    def geodata(self):
        for raw in ('/etc/systemd/system/vpn-geodata-refresh.timer',
                    '/etc/systemd/system/vpn-geodata-refresh.service',
                    '/usr/local/sbin/vpn-geodata-refresh.sh', '/usr/local/sbin/vpn-geodata-publish'):
            if os.path.lexists(raw):
                raise RuntimeError('native-fixture-geodata-authority-already-exists')
        if os.path.lexists(self.selected_assets):
            raise RuntimeError('native-fixture-asset-authority-already-exists')
        self.selected_assets.mkdir(mode=0o755)
        self.assets_created = True
        source = self.private / 'geodata-source'
        source.mkdir(mode=0o700)
        pins = {}
        with zipfile.ZipFile(self.artifacts / 'xray-v26.5.3.zip') as archive:
            for name in ('geoip.dat', 'geosite.dat'):
                data = archive.read(name)
                path = source / name
                path.write_bytes(data)
                path.chmod(0o600)
                pins[name] = hashlib.sha256(data).hexdigest()
        self.context['vpn']['enable_geodata'] = True
        self.context['geodata'].update(install_dir=str(self.selected_assets),
            geoip_url='file://' + str(source / 'geoip.dat'), geosite_url='file://' + str(source / 'geosite.dat'),
            geoip_sha256=pins['geoip.dat'], geosite_sha256=pins['geosite.dat'])
        return pins

    def __exit__(self, *args):
        if not self.claimed:
            return
        units = ('ripdpi-transport-generation.service', 'xray.service', 'hysteria-server.service',
                 'ripdpi-transport-normalizer.service', 'ripdpi-transport-direct.service')
        for unit in units:
            path = Path('/etc/systemd/system') / unit
            if path.exists():
                command(['systemctl', 'stop', unit])
                fields = command(['systemctl', 'show', unit, '--property=ActiveState,MainPID'])
                if 'MainPID=0' not in fields or 'ActiveState=active' in fields:
                    raise RuntimeError('native-fixture-unit-stop-unconfirmed')
        self.resources.close()
        if self.assets_created:
            command(['systemctl', 'stop', 'vpn-geodata-refresh.timer', 'vpn-geodata-refresh.service'])
            command(['systemctl', 'disable', 'vpn-geodata-refresh.timer'])
            for name in ('vpn-geodata-refresh.timer', 'vpn-geodata-refresh.service'):
                (Path('/etc/systemd/system') / name).unlink(missing_ok=True)
            for name in ('vpn-geodata-refresh.sh', 'vpn-geodata-publish'):
                (Path('/usr/local/sbin') / name).unlink(missing_ok=True)
            if self.selected_assets.is_symlink() or self.selected_assets.stat().st_uid != 0:
                raise RuntimeError('native-fixture-asset-authority-changed')
            shutil.rmtree(self.selected_assets)
        # First-install compensation intentionally retains the final deny guard
        # even when the previous helper/config state was absent. Its private
        # receipt, not those restored files, proves this exact lab's ownership.
        self.retire_owned_guard()
        for unit in units:
            if (Path('/etc/systemd/system') / unit).exists():
                command(['systemctl', 'disable', unit])
        if self.link_created:
            command(['ip', 'link', 'delete', self.host_link])
        if self.created:
            command(['ip', 'netns', 'delete', self.namespace])
        if hasattr(self, 'ca_path'):
            self.ca_path.unlink(missing_ok=True);command(['update-ca-certificates'])
        # These directories were absent before the invocation claimed the lab.
        # No cleanup runs after a failed claim of pre-existing authority.
        owned = ('/etc/xray', '/etc/hysteria', '/opt/xray', '/opt/hysteria',
                 '/etc/ripdpi/transport-egress', '/var/lib/ripdpi/transport-egress',
                 '/var/lib/ripdpi/transport-runtime', '/usr/local/libexec/ripdpi-transport-egress',
                 '/var/lib/xray', '/var/lib/hysteria', '/var/log/xray', '/var/log/hysteria')
        allowed_uids = {0} | {entry.pw_uid for entry in pwd.getpwall() if entry.pw_name in {'xray','hysteria'}}
        for raw in owned:
            path = Path(raw)
            if path.exists():
                if path.is_symlink() or path.stat().st_uid not in allowed_uids:
                    raise RuntimeError('native-fixture-cleanup-authority-changed')
                shutil.rmtree(path)
        for unit in units:
            (Path('/etc/systemd/system') / unit).unlink(missing_ok=True)
        for path in ('/usr/local/bin/xray', '/usr/local/bin/hysteria'):
            target = Path(path)
            if target.is_symlink():
                if os.readlink(target) not in ('/opt/xray/current/xray', '/opt/hysteria/current/hysteria'):
                    raise RuntimeError('native-fixture-cli-authority-changed')
                target.unlink()
            elif target.exists():
                raise RuntimeError('native-fixture-cli-authority-changed')
        for path, claimed in self.storage_claims.items():
            info = path.lstat()
            if (path.is_symlink() or (info.st_dev, info.st_ino) != claimed
                    or info.st_uid != 0 or info.st_mode & 0o777 != 0o700):
                raise RuntimeError('native-fixture-storage-authority-changed')
            shutil.rmtree(path)
        if self.cli_backup is not None:
            os.rename(self.cli_backup, '/usr/local/bin/xray')
        for user in ('xray', 'hysteria', 'transport-normalizer', 'transport-gateway'):
            if user not in self.prior_users:
                existing = {entry.pw_name for entry in pwd.getpwall()}
                if user in existing:
                    command(['userdel', user])
            if user not in self.prior_groups and user in {entry.gr_name for entry in grp.getgrall()}:
                command(['groupdel', user])
        command(['systemctl', 'daemon-reload'])
        if getattr(self, 'sshd_runtime_created', False):
            Path('/run/sshd').rmdir()

    def retire_owned_guard(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import transport_egress_kernel as kernel
        tables = json.loads(command(['nft', '-j', 'list', 'tables']))
        if not any(item.get('table', {}).get('name') == kernel.TABLE for item in tables['nftables']):
            return
        receipt = kernel.private_read(kernel.STATE / 'policy-host.json')
        active = json.loads(command(['nft', '-j', 'list', 'table', 'inet', kernel.TABLE]))
        owned = [entry for entry in active['nftables'] if 'metainfo' not in entry]
        interfaces = {name: index for index, name in socket.if_nameindex()}
        if (receipt.get('schema_version') != 1 or
                hashlib.sha256(receipt['rules'].encode()).hexdigest() != receipt.get('rules_digest') or
                kernel.digest(owned, interfaces) != receipt.get('kernel_digest')):
            raise RuntimeError('native-fixture-kernel-authority-changed')
        command(['nft', 'delete', 'table', 'inet', kernel.TABLE])
