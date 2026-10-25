"""Native Hysteria admission with a durable, exact isolated-resource lease."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import base64
from datetime import UTC, datetime
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile

from transport_runtime_probe import ProbeRefused, child, private_file, run
from transport_runtime_transaction import Transaction, Refusal, identity, node, read_private, validate_claim

STATE = Path('/var/lib/ripdpi/transport-runtime')
UNIT_ROOT = Path('/run/systemd/system')
NAMESPACE_ROOT = Path('/run/netns')
STAGING_ROOT = Path('/var/lib')
FILES = {'server.fullchain.pem', 'server.key', 'server.yaml', 'gateway.json'}
ACME_ISSUER = 'acme-v02.api.letsencrypt.org-directory'
ACME_CACHE = Path('/var/lib/hysteria/acme')


def certmagic_key(value):
    """CertMagic v0.25.4 KeyBuilder.Safe for the admitted ASCII identities."""
    value = value.lower().strip()
    for old, new in [(' ', '_'), ('+', '_plus_'), ('*', 'wildcard_'), (':', '-'), ('..', '')]:
        value = value.replace(old, new)
    return re.sub(r'[^a-z0-9_@.\-]', '', value)


@contextmanager
def cache_descriptor(path, flags, *, dir_fd=None):
    """Keep descriptor ownership explicit on success and refusal paths."""
    descriptor = os.open(path, flags, dir_fd=dir_fd)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def cache_file(root, relative, *, private=True):
    """Read bounded snapshot bytes without following any archived link."""
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise Refusal('acme-cache-path')
    with ExitStack() as stack:
        fd = stack.enter_context(cache_descriptor(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in path.parts[:-1]:
            fd = stack.enter_context(cache_descriptor(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd))
            if os.fstat(fd).st_mode & 0o022:
                raise Refusal('acme-cache-directory')
        source = stack.enter_context(cache_descriptor(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd))
        info = os.fstat(source)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & (0o077 if private else 0o022)
                or not 1 <= info.st_size <= 1024 * 1024):
            raise Refusal('acme-cache-file')
        data = os.read(source, 1024 * 1024 + 1)
        after = os.fstat(source)
        if len(data) != info.st_size or (info.st_ino, info.st_dev, info.st_mtime_ns, info.st_ctime_ns) != (
                after.st_ino, after.st_dev, after.st_mtime_ns, after.st_ctime_ns):
            raise Refusal('acme-cache-file-changed')
        return data


def cache_authority(root, document, *, prefix=''):
    """Validate the exact restored certificate/account set, not the mutable live cache."""
    from transport_semantics import hysteria_native_acme
    if not isinstance(document, dict) or 'tls' in document or 'ech' in document:
        raise Refusal('acme-cache-policy')
    policy = hysteria_native_acme(document['acme'])
    name, email = policy['domains'][0], policy['email'].lower()
    cert = 'certificates/' + ACME_ISSUER + '/' + name + '/' + name
    account = 'acme/' + ACME_ISSUER + '/users/' + certmagic_key(email) + '/' + certmagic_key(email.split('@', 1)[0])
    names = [cert + suffix for suffix in ('.crt', '.key', '.json')] + [account + suffix for suffix in ('.json', '.key')]
    files = {path: cache_file(root, prefix + path) for path in names}
    if any(len(data) > 65536 for data in files.values()) or sum(map(len, files.values())) > 256 * 1024:
        raise Refusal('acme-cache-oversize')
    metadata = json.loads(files[cert + '.json'])
    registration = json.loads(files[account + '.json'])
    issuer = metadata.get('issuer_data') if isinstance(metadata, dict) else None
    contact = registration.get('contact') if isinstance(registration, dict) else None
    if (not isinstance(metadata, dict) or metadata.get('sans') != [name]
            or not isinstance(issuer, dict)
            or not isinstance(registration, dict) or registration.get('status') != 'valid'
            or not isinstance(contact, list) or len(contact) != 1 or not isinstance(contact[0], str)
            or contact[0].lower() != 'mailto:' + email
            or not isinstance(registration.get('location'), str)
            or re.fullmatch(r'https://acme-v02\.api\.letsencrypt\.org/acme/acct/[0-9]+', registration['location']) is None
            or issuer.get('ca') != 'https://acme-v02.api.letsencrypt.org/directory'
            or issuer.get('account') != registration['location']
            or not isinstance(issuer.get('url'), str)
            or re.fullmatch(r'https://acme-v02\.api\.letsencrypt\.org/acme/cert/[A-Za-z0-9_-]+', issuer['url']) is None):
        raise Refusal('acme-cache-metadata')
    with tempfile.TemporaryDirectory(prefix='ripdpi-acme-check-') as temporary:
        directory = Path(temporary)
        certificate = private_file(directory, 'certificate.pem', files[cert + '.crt'])
        key = private_file(directory, 'key.pem', files[cert + '.key'])
        account_key = private_file(directory, 'account.pem', files[account + '.key'])
        sans = set(re.findall(rb'DNS:([^,\s]+)', run(['openssl', 'x509', '-in', str(certificate), '-noout', '-ext', 'subjectAltName'], 10)))
        if sans != {name.encode()}:
            raise Refusal('acme-cache-identity')
        run(['openssl', 'x509', '-in', str(certificate), '-noout', '-checkend', '86400'], 10)
        run(['openssl', 'verify', '-purpose', 'sslserver', '-untrusted', str(certificate), str(certificate)], 10)
        if run(['openssl', 'x509', '-in', str(certificate), '-noout', '-pubkey'], 10).strip() != run(
                ['openssl', 'pkey', '-in', str(key), '-pubout'], 10).strip():
            raise Refusal('acme-cache-key-mismatch')
        run(['openssl', 'pkey', '-in', str(account_key), '-check', '-noout'], 10)
        if 'renewal_info' in issuer:
            validate_ari(issuer['renewal_info'], certificate)
    return files


def validate_ari(value, certificate):
    """Admit pinned acmez v3.1.6 metadata, including its zero-value ARI object."""
    if (not isinstance(value, dict) or not {'suggestedWindow', '_selectedTime'} <= set(value)
            or set(value) - {'suggestedWindow', '_selectedTime', '_uniqueIdentifier', '_retryAfter', 'explanationURL'}
            or not isinstance(value['suggestedWindow'], dict) or set(value['suggestedWindow']) != {'start', 'end'}
            or any(not isinstance(value[key], str) for key in ('_uniqueIdentifier', 'explanationURL') if key in value)):
        raise Refusal('acme-cache-ari')
    def timestamp(raw):
        if (not isinstance(raw, str) or re.fullmatch(
                r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,9})?'
                r'(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])', raw) is None):
            raise Refusal('acme-cache-ari')
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise Refusal('acme-cache-ari')
        return parsed
    start, end = (timestamp(value['suggestedWindow'][key]) for key in ('start', 'end'))
    selected = timestamp(value['_selectedTime'])
    if '_retryAfter' in value:
        timestamp(value['_retryAfter'])
    zero = all(item == datetime.min.replace(tzinfo=UTC) for item in (start, end, selected))
    if zero and '_uniqueIdentifier' not in value:
        return
    if not zero and (not start <= selected <= end or start >= end):
        raise Refusal('acme-cache-ari')
    serial = int(run(['openssl', 'x509', '-in', str(certificate), '-noout', '-serial'], 10).decode().strip().split('=', 1)[1], 16)
    encoded_serial = serial.to_bytes(max(1, (serial.bit_length() + 7) // 8), 'big')
    if encoded_serial[0] & 0x80:
        encoded_serial = b'\0' + encoded_serial
    aki_text = run(['openssl', 'x509', '-in', str(certificate), '-noout', '-ext', 'authorityKeyIdentifier'], 10)
    match = re.search(rb'(?:[0-9A-Fa-f]{2}:)+[0-9A-Fa-f]{2}', aki_text)
    aki = bytes.fromhex(match.group().decode().replace(':', '')) if match else b''
    encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip('=')
    if value.get('_uniqueIdentifier') != encode(aki) + '.' + encode(encoded_serial):
        raise Refusal('acme-cache-ari-identity')


def expand_cache(manifest, destination, *, existing=False):
    """Only an owned temporary unit or explicit fresh recovery creates these bytes."""
    if not isinstance(manifest, dict) or len(manifest) != 5:
        raise Refusal('acme-cache-manifest')
    files = {}
    for name, value in manifest.items():
        path = Path(name)
        if (not isinstance(name, str) or path.is_absolute() or '..' in path.parts or len(path.parts) not in {4, 5}
                or path.parts[0] not in {'certificates', 'acme'} or path.parts[1] != ACME_ISSUER
                or str(path) != name or not isinstance(value, str)):
            raise Refusal('acme-cache-manifest')
        data = base64.b64decode(value, validate=True)
        if not 1 <= len(data) <= 65536:
            raise Refusal('acme-cache-manifest')
        files[path] = data
    if sum(map(len, files.values())) > 256 * 1024:
        raise Refusal('acme-cache-manifest')
    if existing:
        info = destination.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700
                or os.listdir(destination)):
            raise Refusal('acme-cache-expansion-destination')
    else:
        destination.mkdir(mode=0o700)
    for path, data in files.items():
        target = destination / path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        for parent in path.parents:
            if str(parent) != '.':
                (destination / parent).chmod(0o700)
        private_file(target.parent, target.name, data)


def restored_cache(root, config_relative):
    import yaml
    info = root.lstat()
    if (not root.is_absolute() or '..' in root.parts or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise Refusal('acme-cache-restore-root')
    raw = cache_file(root, config_relative, private=False)
    document = yaml.safe_load(raw)
    return document, cache_authority(root, document, prefix='var/lib/hysteria/acme/')


def recovery_runtime(tx, binary, product):
    path = Path(binary)
    if re.fullmatch('/opt/' + product + r'/releases/v?[0-9]+\.[0-9]+\.[0-9]+/' + product, str(path)) is None:
        raise Refusal('acme-recovery-runtime')
    tx.parent(path.parent)
    observed = node(path, tx.uid, maximum=128 * 1024 * 1024)
    if observed is None or observed['identity'][4] not in {0o755, 0o555}:
        raise Refusal('acme-recovery-runtime')


def recovery_window(files, document):
    name = document['acme']['domains'][0]
    prefix = 'certificates/' + ACME_ISSUER + '/' + name + '/' + name
    with tempfile.TemporaryDirectory(prefix='ripdpi-acme-window-') as temporary:
        certificate = private_file(Path(temporary), 'certificate.pem', files[prefix + '.crt'])
        dates = run(['openssl', 'x509', '-in', str(certificate), '-noout', '-dates'], 10).decode().splitlines()
    values = {key: datetime.strptime(value, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=UTC)
              for key, value in (line.split('=', 1) for line in dates)}
    cutoff = values['notAfter'] - (values['notAfter'] - values['notBefore']) / 3
    ari = json.loads(files[prefix + '.json'])['issuer_data'].get('renewal_info')
    if ari and ari['_selectedTime'] != '0001-01-01T00:00:00Z':
        from datetime import timedelta
        selected = datetime.fromisoformat(ari['_selectedTime'].replace('Z', '+00:00'))
        cutoff = min(cutoff, selected - timedelta(minutes=10))
    if (cutoff - datetime.now(UTC)).total_seconds() < 120:
        raise Refusal('acme-cache-renewal-window')


def recover_cache(root, config_relative, request):
    """Explicit fresh recovery with a durable exact-directory publication decision."""
    import pwd
    import yaml
    if (not isinstance(request, dict)
            or set(request) != {'binary', 'gateway_binary', 'config', 'unit', 'client_name', 'snapshot_id'}
            or any(not isinstance(value, str) or not value for value in request.values())
            or re.fullmatch('[0-9a-f]{64}', request['snapshot_id']) is None):
        raise Refusal('acme-recovery-request')
    document, files = restored_cache(root, config_relative)
    desired = yaml.safe_load(request['config'])
    if desired.get('acme') != document.get('acme'):
        raise Refusal('acme-recovery-policy')
    destination = ACME_CACHE
    service = pwd.getpwnam('hysteria')
    manifest = {name: base64.b64encode(data).decode() for name, data in files.items()}
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    authority = {'schema': 1, 'snapshot_id': request['snapshot_id'], 'manifest_sha256': digest(manifest),
                 'policy_sha256': digest(desired['acme'])}
    journal_name = 'hysteria-acme-restore.json'
    with Transaction(STATE, uid=os.geteuid()) as tx:
        def live_identity():
            parent = destination.parent.lstat()
            if parent.st_uid != tx.uid or parent.st_gid != service.pw_gid or stat.S_IMODE(parent.st_mode) != 0o750:
                raise Refusal('acme-recovery-parent')
            tx.parent(destination.parent)
            info = destination.lstat()
            mounted = os.path.ismount(destination)
            if sys.platform == 'linux':
                mounted = mounted or any(line.split()[4] == str(destination) for line in Path('/proc/self/mountinfo').read_text().splitlines())
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != service.pw_uid or info.st_gid != service.pw_gid
                    or stat.S_IMODE(info.st_mode) != 0o700 or info.st_dev != parent.st_dev or mounted):
                raise Refusal('acme-recovery-cache')
            return identity(info)
        def fresh():
            if any(os.path.lexists(tx.root / name) for name in (
                    'accepted.json', 'pending.json', 'preparation.json', 'compensating.json', 'revocation.json')):
                raise Refusal('acme-recovery-requires-fresh-node')
            state = unit_state('hysteria-server.service')
            if (state['LoadState'] != 'not-found' or state.get('FragmentPath', '')
                    or state['ActiveState'] != 'inactive' or state['MainPID'] != '0'):
                raise Refusal('acme-recovery-requires-fresh-service')
        journal = read_private(tx.root / journal_name, tx.uid)
        if journal is None:
            fresh()
            before = live_identity()
            if os.listdir(destination):
                raise Refusal('acme-recovery-requires-empty-cache')
            wrapper = Path(tempfile.mkdtemp(prefix='.acme-restore-', dir=destination.parent))
            candidate = wrapper / 'acme'
            expand_cache(manifest, candidate)
            for parent, _directories, names in os.walk(candidate):
                os.chown(parent, service.pw_uid, service.pw_gid)
                for name in names:
                    path = Path(parent) / name
                    os.chown(path, service.pw_uid, service.pw_gid)
                    with path.open('rb') as source:
                        os.fsync(source.fileno())
            for parent, _directories, _names in os.walk(candidate, topdown=False):
                fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            os.fsync(tx.parent(wrapper))
            os.fsync(tx.parent(destination.parent))
            if live_identity() != before or os.listdir(destination):
                raise Refusal('acme-recovery-destination-changed')
            journal = {**authority, 'phase': 'prepared', 'wrapper': wrapper.name,
                       'wrapper_identity': identity(wrapper.lstat()), 'candidate_identity': identity(candidate.lstat()),
                       'before_identity': before}
            tx.record(journal_name, journal)
        if (not isinstance(journal, dict) or set(journal) != set(authority) | {
                'phase', 'wrapper', 'wrapper_identity', 'candidate_identity', 'before_identity'}
                or any(journal.get(key) != value for key, value in authority.items())
                or type(journal['schema']) is not int or journal['phase'] not in {'prepared', 'validated', 'publishing', 'complete'}
                or not isinstance(journal['wrapper'], str) or re.fullmatch(r'\.acme-restore-[a-z0-9_]+', journal['wrapper']) is None
                or any(not isinstance(journal[key], list) or len(journal[key]) != 5
                       or any(type(item) is not int for item in journal[key])
                       for key in ('wrapper_identity', 'candidate_identity', 'before_identity'))):
            raise Refusal('acme-recovery-journal')
        wrapper = destination.parent / journal['wrapper']
        candidate = wrapper / 'acme'
        observed = live_identity()
        renamed = observed == journal['candidate_identity'] and not os.path.lexists(candidate)
        if journal['phase'] == 'complete':
            if not renamed:
                raise Refusal('acme-recovery-commit-changed')
        elif journal['phase'] == 'publishing' and renamed:
            os.fsync(tx.parent(destination.parent))
            tx.record(journal_name, {**journal, 'phase': 'complete'})
        else:
            fresh()
            if observed != journal['before_identity'] or os.listdir(destination):
                raise Refusal('acme-recovery-destination-changed')
            if identity(wrapper.lstat()) != journal['wrapper_identity'] or identity(candidate.lstat()) != journal['candidate_identity']:
                raise Refusal('acme-recovery-candidate-changed')
            tx.parent(wrapper)
            expected = set(files) | {str(parent) for name in files for parent in Path(name).parents if str(parent) != '.'}
            if {str(path.relative_to(candidate)) for path in candidate.rglob('*')} != expected:
                raise Refusal('acme-recovery-candidate-changed')
            if any(cache_file(candidate, name) != data for name, data in files.items()):
                raise Refusal('acme-recovery-candidate-changed')
            recovery_window(files, desired)
            recovery_runtime(tx, request['binary'], 'hysteria')
            recovery_runtime(tx, request['gateway_binary'], 'xray')
            validate_hysteria(request['binary'], request['config'].encode(), None, None, request['unit'], 60,
                              request['client_name'], gateway_binary=request['gateway_binary'], transaction=tx, cache=files)
            journal = {**journal, 'phase': 'validated'}
            tx.record(journal_name, journal)
            fresh()
            recovery_window(files, desired)
            if live_identity() != journal['before_identity'] or os.listdir(destination):
                raise Refusal('acme-recovery-destination-changed')
            tx.record(journal_name, {**journal, 'phase': 'publishing'})
            os.rename(candidate, destination)
            os.fsync(tx.parent(destination.parent))
            tx.record(journal_name, {**journal, 'phase': 'complete'})
        if os.path.lexists(wrapper):
            if identity(wrapper.lstat()) != journal['wrapper_identity'] or os.listdir(wrapper):
                raise Refusal('acme-recovery-wrapper-changed')
            os.rmdir(wrapper)
            os.fsync(tx.parent(destination.parent))
        return journal['phase'] != 'complete'


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
            or not isinstance(value['files'], dict) or set(value['files']) not in (FILES, FILES | {'ech.key'}, FILES | {'acme.json'})):
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
        if names - set(value['files']) or value['phase'] == 'prepared' and names != set(value['files']):
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
    if 'acme.json' in value['files'] and os.path.lexists(Path('/run') / namespace.name):
        raise Refusal('validation-cache-cleanup-unconfirmed')
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


def project_hysteria_tls(document, directory, certificate, key):
    """Write an explicit offline TLS projection only inside the private lease."""
    if ('tls' in document) == ('acme' in document):
        raise Refusal('candidate-tls-authority')
    if 'acme' not in document:
        private_file(directory, 'server.fullchain.pem', certificate or b'')
        private_file(directory, 'server.key', key or b'')
        return None
    from transport_semantics import hysteria_native_acme
    try:
        policy = hysteria_native_acme(document['acme'])
        if certificate is not None or key is not None or 'ech' in document:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise Refusal('candidate-acme-authority') from None
    cert = private_file(directory, 'server.fullchain.pem', b'')
    private = private_file(directory, 'server.key', b'')
    name = policy['domains'][0]
    run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
         '-nodes', '-days', '1', '-subj', '/CN=' + name, '-addext', 'subjectAltName=DNS:' + name,
         '-keyout', str(private), '-out', str(cert)], 10)
    del document['acme']
    document['tls'] = {'cert': str(cert), 'key': str(private)}
    return name


def validate_hysteria(binary, raw, certificate, key, unit, timeout, client_name, *, gateway_binary, transaction=None, ech_key=None,
                      cache=None, checkpoint=lambda _stage: None):
    if (not isinstance(gateway_binary, str) or not Path(gateway_binary).is_absolute()
            or str(Path(gateway_binary)) != gateway_binary or '..' in Path(gateway_binary).parts):
        raise Refusal('gateway-runtime-unavailable')
    if transaction is None:
        with Transaction(STATE) as tx:
            validate_hysteria(binary, raw, certificate, key, unit, timeout, client_name,
                              gateway_binary=gateway_binary, transaction=tx, ech_key=ech_key, cache=cache, checkpoint=checkpoint)
        return
    tx = transaction
    recover_validation(tx)
    if cache is None:
        recovery = read_private(tx.root / 'hysteria-acme-restore.json', tx.uid)
        if recovery is not None and (not isinstance(recovery, dict) or recovery.get('phase') != 'complete'):
            raise Refusal('acme-recovery-unfinished')
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
            manifest = None
            if cache is None:
                projected_name = project_hysteria_tls(document, directory, certificate, key)
            else:
                from transport_semantics import hysteria_native_acme
                hysteria_native_acme(document['acme'])
                if certificate is not None or key is not None or 'tls' in document or 'ech' in document:
                    raise Refusal('candidate-acme-authority')
                manifest = private_file(directory, 'acme.json', json.dumps({name: base64.b64encode(data).decode() for name, data in cache.items()}))
                private_file(directory, 'server.fullchain.pem', b'')
                private_file(directory, 'server.key', b'')
                projected_name = None
            cert, private = directory / 'server.fullchain.pem', directory / 'server.key'
            if 'tls' in document:
                document['tls']['cert'], document['tls']['key'] = str(cert), str(private)
            files = FILES.copy()
            if manifest is not None:
                files.add('acme.json')
                os.chown(manifest, 0, gid)
                manifest.chmod(0o640)
            ech = None
            if 'ech' in document:
                if ech_key is None:
                    raise Refusal('ech-authority-required')
                ech = private_file(directory, 'ech.key', ech_key)
                files.add('ech.key')
                document['ech']['keyPath'] = '/run/credentials/' + token + '.service/hysteria-ech'
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
            resources.enter_context(child(['/usr/sbin/ip', 'netns', 'exec', token,
                                           gateway_binary, 'run', '-config', str(gateway)]))
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
            validation_unit += '\nLoadCredential=\n'
            if manifest is not None:
                validation_unit += '\nRuntimeDirectory=' + token + '\nRuntimeDirectoryMode=0700\nRuntimeDirectoryPreserve=no'
                validation_unit += '\nReadWritePaths=\nReadWritePaths=/var/lib/hysteria/acme'
                validation_unit += '\nBindPaths=/run/' + token + ':/var/lib/hysteria/acme'
                validation_unit += '\nExecStartPre=\nExecStartPre=/usr/bin/python3 ' + str(Path(__file__).resolve())
                validation_unit += ' --expand-cache ' + str(manifest) + ' /var/lib/hysteria/acme --existing-empty\n'
            if ech is not None:
                validation_unit += 'LoadCredential=hysteria-ech:' + str(ech) + '\n'
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
                     'files': {name: node(directory / name, tx.uid) for name in files}}
            # Unit content is independently checked through its SHA256 authority.
            claim['unit']['sha256'] = unit_info['sha256']
            for name in files:
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
            if projected_name is not None:
                request['tls_server_name'] = projected_name
            source = ('import json,sys;sys.path.insert(0,sys.argv[1]);'
                      'from transport_runtime_probe import probe;probe(**json.load(sys.stdin))')
            run(['/usr/sbin/ip', 'netns', 'exec', token, '/usr/bin/python3', '-c', source,
                 str(Path(__file__).parent)], timeout + 5, data=json.dumps(request).encode())
    finally:
        if claimed:
            recover_validation(tx)


def main():
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--check-cache', type=Path)
    actions.add_argument('--recover-cache', type=Path)
    actions.add_argument('--expand-cache', nargs=2, type=Path)
    parser.add_argument('--config-relative', default='etc/hysteria/config.yaml')
    parser.add_argument('--existing-empty', action='store_true')
    parser.add_argument('--request-stdin', action='store_true')
    args = parser.parse_args()
    try:
        if args.expand_cache:
            if args.request_stdin:
                raise Refusal('acme-cache-request')
            manifest, destination = args.expand_cache
            expand_cache(json.loads(cache_file(manifest.parent, manifest.name, private=False)), destination, existing=args.existing_empty)
        elif args.check_cache:
            if args.request_stdin or args.existing_empty:
                raise Refusal('acme-cache-request')
            restored_cache(args.check_cache, args.config_relative)
        else:
            if not args.request_stdin or args.existing_empty:
                raise Refusal('acme-cache-request')
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise Refusal('acme-cache-request')
            if os.geteuid() != 0:
                raise Refusal('acme-recovery-request')
            changed = recover_cache(args.recover_cache, args.config_relative, json.loads(raw))
            print(json.dumps({'changed': changed}))
    except (OSError, ValueError, KeyError, TypeError, Refusal, ProbeRefused):
        print('hysteria-acme-cache-refused', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
