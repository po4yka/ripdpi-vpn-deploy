"""Native Hysteria admission with a durable, exact isolated-resource lease."""
from __future__ import annotations

from contextlib import ExitStack
import grp
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

from transport_runtime_probe import ProbeRefused, child, private_file, run
from transport_runtime_transaction import Transaction, Refusal, identity, node, read_private, validate_claim

STATE = Path('/var/lib/ripdpi/transport-runtime')
UNIT_ROOT = Path('/run/systemd/system')
NAMESPACE_ROOT = Path('/run/netns')
STAGING_ROOT = Path('/var/lib')
FILES = {'server.fullchain.pem', 'server.key', 'server.yaml', 'gateway.json'}


def boot_id():
    value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value) is None:
        raise Refusal('validation-boot-unconfirmed')
    return value


def inspect_lease(tx):
    value = read_private(tx.root / 'validation.json', tx.uid)
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'schema', 'boot_id', 'phase', 'unit', 'namespace', 'directory', 'files'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not isinstance(value['boot_id'], str)
            or re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value['boot_id']) is None
            or not isinstance(value['phase'], str) or value['phase'] not in {'prepared', 'cleaning'}):
        raise Refusal('validation-lease-invalid')
    for key in ('unit', 'namespace', 'directory'):
        expected_keys = {'name', 'identity', 'sha256'} if key == 'unit' else {'name', 'identity'}
        if not isinstance(value[key], dict) or set(value[key]) != expected_keys:
            raise Refusal('validation-lease-invalid')
        claimed = value[key]['identity']
        if (not isinstance(claimed, list) or len(claimed) != 5 or any(type(item) is not int for item in claimed)
                or not all(0 <= item < 2**64 for item in claimed[:2]) or claimed[2] != tx.uid
                or not 0 <= claimed[3] < 2**32 - 1 or not 0 <= claimed[4] <= 0o7777
                or key == 'unit' and claimed[4] != 0o600):
            raise Refusal('validation-lease-invalid')
    namespace = value['namespace']['name']
    if not isinstance(namespace, str) or not re.fullmatch('ripdpi-candidate-[0-9a-f]{16}', namespace):
        raise Refusal('validation-lease-invalid')
    if value['unit']['name'] != namespace + '.service':
        raise Refusal('validation-lease-invalid')
    directory_name = value['directory']['name']
    if (not isinstance(directory_name, str) or Path(directory_name).name != directory_name
            or not directory_name.startswith(namespace + '-') or value['directory']['identity'][4] != 0o750
            or not isinstance(value['files'], dict) or set(value['files']) != FILES):
        raise Refusal('validation-lease-invalid')
    validate_claim({key: value['unit'][key] for key in ('identity', 'sha256')}, tx.uid)
    unit_path = UNIT_ROOT / value['unit']['name']
    namespace_path = NAMESPACE_ROOT / namespace
    directory = STAGING_ROOT / directory_name
    rebooted = value['boot_id'] != boot_id()
    for volatile_root in (UNIT_ROOT, NAMESPACE_ROOT):
        tx.parent(volatile_root if os.path.lexists(volatile_root) else volatile_root.parent)
    tx.parent(STAGING_ROOT)
    for key, path in (('unit', unit_path), ('namespace', namespace_path), ('directory', directory)):
        try:
            observed = path.lstat()
        except FileNotFoundError:
            if value['phase'] != 'cleaning' and not (rebooted and key in {'unit', 'namespace'}):
                raise Refusal('validation-resource-absent') from None
            continue
        if identity(observed) != value[key]['identity']:
            raise Refusal('validation-resource-changed')
        if (key == 'directory' and not stat.S_ISDIR(observed.st_mode)
                or key != 'directory' and not stat.S_ISREG(observed.st_mode)):
            raise Refusal('validation-resource-changed')
    if unit_path.exists() and node(unit_path, tx.uid) != {key: value['unit'][key] for key in ('identity', 'sha256')}:
        raise Refusal('validation-unit-changed')
    if directory.exists():
        tx.parent(directory)
        names = set(os.listdir(directory))
        if names - FILES or value['phase'] == 'prepared' and names != FILES:
            raise Refusal('validation-foreign-file')
    for name, claimed in value['files'].items():
        validate_claim(claimed, tx.uid)
        if claimed is None or 'sha256' not in claimed:
            raise Refusal('validation-lease-invalid')
        observed = node(directory / name, tx.uid)
        if observed is None and value['phase'] == 'cleaning':
            continue
        if observed != claimed:
            raise Refusal('validation-file-changed')
    return value


def unit_state(name):
    raw = run(['/usr/bin/systemctl', 'show', name,
               '--property=LoadState,FragmentPath,ActiveState,MainPID'], 5).decode()
    value = dict(row.split('=', 1) for row in raw.splitlines() if '=' in row)
    if (set(value) != {'LoadState', 'FragmentPath', 'ActiveState', 'MainPID'}
            or value['LoadState'] not in {'loaded', 'not-found'}
            or value['ActiveState'] not in {'active', 'inactive', 'failed', 'activating', 'deactivating'}
            or not value['MainPID'].isdigit()):
        raise Refusal('validation-unit-unconfirmed')
    return value


def recover_validation(tx):
    """Caller retains the shared transaction lock until this exact lease closes."""
    value = inspect_lease(tx)
    if value is None:
        return False
    unit = UNIT_ROOT / value['unit']['name']
    namespace = NAMESPACE_ROOT / value['namespace']['name']
    directory = STAGING_ROOT / value['directory']['name']
    if not unit.exists() and value['boot_id'] != boot_id():
        # /run authority and its processes cannot survive a proven reboot.
        # A new manager's same-named unit is foreign and must remain untouched.
        state = unit_state(unit.name)
        if (state['LoadState'] != 'not-found' or state['FragmentPath'] or state['MainPID'] != '0'
                or state['ActiveState'] != 'inactive'):
            raise Refusal('validation-foreign-unit')
    if unit.exists():
        state = unit_state(unit.name)
        if state['LoadState'] == 'loaded':
            if state['FragmentPath'] != str(unit):
                raise Refusal('validation-foreign-unit')
            run(['/usr/bin/systemctl', 'stop', unit.name], 10)
        elif state['MainPID'] != '0' or state['ActiveState'] == 'active':
            raise Refusal('validation-unit-unconfirmed')
        state = unit_state(unit.name)
        if state['MainPID'] != '0' or state['ActiveState'] in {'active', 'activating', 'deactivating'}:
            raise Refusal('validation-cleanup-unconfirmed')
    if namespace.exists():
        if run(['/usr/sbin/ip', 'netns', 'pids', namespace.name], 5).strip():
            raise Refusal('validation-namespace-not-empty')
    if value['phase'] != 'cleaning':
        value = {**value, 'phase': 'cleaning'}
        tx.record('validation.json', value)
    # A process death during cleanup permits only recorded absence on retry.
    # A replacement or added inode still refuses before the first deletion.
    inspect_lease(tx)
    if unit.exists():
        fd = tx.parent(UNIT_ROOT)
        os.unlink(unit.name, dir_fd=fd)
        os.fsync(fd)
        run(['/usr/bin/systemctl', 'daemon-reload'], 5)
    if namespace.exists():
        if identity(namespace.lstat()) != value['namespace']['identity']:
            raise Refusal('validation-resource-changed')
        run(['/usr/sbin/ip', 'netns', 'delete', namespace.name], 5)
        if namespace.exists():
            raise Refusal('validation-cleanup-unconfirmed')
    if directory.exists():
        fd = tx.parent(directory)
        for name, claimed in value['files'].items():
            observed = node(directory / name, tx.uid)
            if observed is not None:
                if observed != claimed:
                    raise Refusal('validation-file-changed')
                os.unlink(name, dir_fd=fd)
        os.fsync(fd)
        if identity(directory.lstat()) != value['directory']['identity']:
            raise Refusal('validation-resource-changed')
        parent = tx.parent(STAGING_ROOT)
        os.rmdir(directory.name, dir_fd=parent)
        os.fsync(parent)
    if read_private(tx.root / 'validation.json', tx.uid) != value:
        raise Refusal('validation-lease-changed')
    os.unlink('validation.json', dir_fd=tx.state_fd)
    os.fsync(tx.state_fd)
    return True


def validate_hysteria(binary, raw, certificate, key, unit, timeout, client_name, *, transaction=None, checkpoint=lambda _stage: None):
    if transaction is None:
        with Transaction(STATE) as tx:
            return validate_hysteria(binary, raw, certificate, key, unit, timeout, client_name,
                                     transaction=tx, checkpoint=checkpoint)
    tx = transaction
    recover_validation(tx)
    import yaml
    token = 'ripdpi-candidate-' + secrets.token_hex(8)
    unit_path = UNIT_ROOT / (token + '.service')
    tx.parent(UNIT_ROOT)
    tx.parent(STAGING_ROOT)
    # Unique, not yet active resources have no cleanup authority until the
    # complete exact lease is durable. Unclaimed preparation cannot collide.
    directory = Path(tempfile.mkdtemp(prefix=token + '-', dir=STAGING_ROOT))
    gid = grp.getgrnam('hysteria').gr_gid
    os.chown(directory, 0, gid)
    directory.chmod(0o750)
    claimed = False
    try:
        with ExitStack() as resources:
            document = yaml.safe_load(raw)
            cert = private_file(directory, 'server.fullchain.pem', certificate)
            private = private_file(directory, 'server.key', key)
            document['tls']['cert'], document['tls']['key'] = str(cert), str(private)
            server = private_file(directory, 'server.yaml', yaml.safe_dump(document))
            for path in (cert, private, server):
                os.chown(path, 0, gid)
                path.chmod(0o640)
            run(['/usr/sbin/ip', 'netns', 'add', token], 5)
            run(['/usr/sbin/ip', '-n', token, 'link', 'set', 'lo', 'up'], 5)
            run(['/usr/sbin/ip', '-n', token, 'addr', 'add', '192.0.2.80/32', 'dev', 'lo'], 5)
            outbound = document['outbounds'][0]['socks5']
            host, port = outbound['addr'].rsplit(':', 1)
            gateway = private_file(directory, 'gateway.json', json.dumps({
                'log': {'loglevel': 'none'}, 'inbounds': [{'listen': host, 'port': int(port),
                    'protocol': 'socks', 'settings': {'auth': 'password', 'udp': True,
                    'accounts': [{'user': outbound['username'], 'pass': outbound['password']}]}}],
                'outbounds': [{'protocol': 'freedom'}]}))
            gateway_unit = Path('/etc/systemd/system/ripdpi-transport-direct.service').read_text()
            executables = [line.split('=', 1)[1].split()[0] for line in gateway_unit.splitlines() if line.startswith('ExecStart=')]
            if len(executables) != 1 or not executables[0].startswith('/'):
                raise Refusal('gateway-runtime-unavailable')
            resources.enter_context(child(['/usr/sbin/ip', 'netns', 'exec', token,
                                           executables[0], 'run', '-config', str(gateway)]))
            canary_source = '''from http.server import BaseHTTPRequestHandler, HTTPServer
class Canary(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(204); self.end_headers()
 def log_message(self, *args): pass
HTTPServer(('192.0.2.80', 18080), Canary).serve_forever()
'''
            resources.enter_context(child(['/usr/sbin/ip', 'netns', 'exec', token,
                                           '/usr/bin/python3', '-c', canary_source]))
            # Empty dependency assignments do not reset systemd's graph.
            # Preserve the service sandbox, but keep candidate admission from
            # pulling the production normalizer into its owned namespace.
            dependencies = ('After=', 'Before=', 'BindsTo=', 'Requires=', 'Wants=',
                            'Requisite=', 'PartOf=', 'Upholds=')
            validation_unit = '\n'.join(line for line in unit.splitlines()
                                       if not line.startswith(dependencies))
            validation_unit += '\n[Service]\nNetworkNamespacePath=' + str(NAMESPACE_ROOT / token)
            validation_unit += '\nExecStart=\nExecStart=' + binary + ' server -c ' + str(server)
            validation_unit += '\nBindReadOnlyPaths=\nRestart=no\nRuntimeMaxSec=' + str(timeout + 5)
            validation_unit += '\nTimeoutStopSec=5\nKillMode=control-group'
            validation_unit += '\nStandardOutput=null\nStandardError=null\n'
            fd = os.open(unit_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as target:
                os.fchmod(target.fileno(), 0o600)
                target.write(validation_unit)
                target.flush()
                os.fsync(target.fileno())
            unit_info = node(unit_path, tx.uid)
            claim = {'schema': 1, 'boot_id': boot_id(), 'phase': 'prepared',
                     'unit': {'name': unit_path.name, 'identity': unit_info['identity']},
                     'namespace': {'name': token, 'identity': identity((NAMESPACE_ROOT / token).lstat())},
                     'directory': {'name': directory.name, 'identity': identity(directory.lstat())},
                     'files': {name: node(directory / name, tx.uid) for name in FILES}}
            # Unit content is independently checked through its SHA256 authority.
            claim['unit']['sha256'] = unit_info['sha256']
            for name in FILES:
                fd = os.open(directory / name, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            os.fsync(tx.parent(directory))
            os.fsync(tx.parent(UNIT_ROOT))
            tx.record('validation.json', claim)
            claimed = True
            run(['/usr/bin/systemctl', 'daemon-reload'], 5)
            try:
                run(['/usr/bin/systemctl', 'start', token], timeout)
            except ProbeRefused:
                raw_state = run(['/usr/bin/systemctl', 'show', unit_path.name,
                    '--property=Result,ExecMainStatus,LoadState'], 5).decode()
                state = dict(row.split('=', 1) for row in raw_state.splitlines() if '=' in row)
                code = state.get('ExecMainStatus', '')
                if code.isdigit() and len(code) <= 3 and int(code) > 0:
                    raise ProbeRefused('candidate-start-' + str(int(code))) from None
                result = state.get('Result')
                known = {'success', 'exit-code', 'signal', 'core-dump', 'timeout', 'resources',
                         'protocol', 'start-limit-hit', 'dependency', 'assert'}
                loaded = state.get('LoadState')
                if result in known and loaded in {'loaded', 'not-found', 'error', 'bad-setting'}:
                    raise ProbeRefused('candidate-start-' + result + '-' + loaded) from None
                raise ProbeRefused('candidate-start-unconfirmed') from None
            checkpoint('validation-active')
            request = {'binary': binary, 'config': str(server), 'url': 'http://192.0.2.80:18080/', 'timeout': timeout, 'client_name': client_name}
            source = ('import json,sys;sys.path.insert(0,sys.argv[1]);'
                      'from transport_runtime_probe import probe;probe(**json.load(sys.stdin))')
            run(['/usr/sbin/ip', 'netns', 'exec', token, '/usr/bin/python3', '-c', source,
                 str(Path(__file__).parent)], timeout + 5, data=json.dumps(request).encode())
    finally:
        if claimed:
            recover_validation(tx)
