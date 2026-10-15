"""Sender publication and retained-queue compensation under one publisher lock."""
from __future__ import annotations

import base64
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import stat
import sys
import time

from transport_runtime_transaction import Transaction, Refusal, admission, node, read_private, ancestors
from observability_runtime_queue import QueueSnapshot, tree
import observability_agent_readiness as readiness

STATE = Path('/var/lib/observability-agent-activation')
QUEUE = Path('/var/lib/observability-agent/queue')
UNIT = Path('/etc/systemd/system/observability-agent.service')
PARAMETERS = STATE / 'parameters.json'
SERVICE = 'observability-agent.service'


def run(arguments):
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=40, check=True)
        return result.stdout.decode()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Refusal('sender-service-command') from None


def fields():
    raw = run(['/usr/bin/systemctl', 'show', SERVICE,
               '--property=LoadState,ActiveState,UnitFileState,MainPID,Result,ControlGroup'])
    result = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
    if (result.get('LoadState') not in {'loaded', 'not-found'} or
            result.get('ActiveState') not in {'active', 'inactive', 'failed', 'activating', 'deactivating'} or
            not result.get('MainPID', '').isdigit()):
        raise Refusal('sender-service-state')
    return result


def validate_binary(path, uid):
    # Runtime executables are larger than the publisher's metadata-node ceiling.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_nlink != 1 or
                stat.S_IMODE(info.st_mode) != 0o755 or not 0 < info.st_size <= 128 * 1024**2):
            raise Refusal('sender-binary-authority')
    finally:
        os.close(fd)


def profile(value):
    if (not isinstance(value, dict) or set(value) != {'install_root', 'receiver', 'version'} or
            not re.fullmatch(r'/opt/observability-vmagent(?:-[a-z0-9-]+)?', value['install_root']) or
            not isinstance(value['receiver'], str) or len(value['receiver']) > 1024 or
            not value['receiver'].startswith('https://') or '\n' in value['receiver'] or
            value['version'] != 'v1.153.0'):
        raise Refusal('sender-profile')
    return value


def guard():
    admission(STATE)
    if not STATE.exists():
        return
    startup = read_private(STATE / 'startup.json', 0)
    # A startup without file publication is still a queue transaction.
    pending = read_private(STATE / 'pending.json', 0)
    saved = read_private(STATE / 'queue-snapshot.json', 0)
    if pending is not None and (saved is None or saved.get('phase') not in {'retained', 'restored', 'aborted'}):
        raise Refusal('sender-queue-not-prepared')
    if startup is not None:
        if saved is None or saved.get('phase') not in {'retained', 'restored', 'aborted'}:
            raise Refusal('sender-startup-not-prepared')
        fd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            raise Refusal('unfinished-sender-without-publisher')
        finally:
            os.close(fd)


class Sender:
    def __init__(self, tx, queue=QUEUE, *, agent_uid=None, checkpoint=lambda _stage: None):
        self.transaction = tx
        self.snapshot = QueueSnapshot(tx, queue, pwd.getpwnam('observability-agent').pw_uid
                                      if agent_uid is None else agent_uid, checkpoint=checkpoint)
        self.capture = False
        self.target_active = True
        self.restored_ready = False
        self.queue_proven = False
        self.plan = None

    def validate(self):
        if self.plan.get('retire'):
            return
        parameters = profile(self.plan['profile'])
        values = {item['path']: item for item in self.plan['candidates']}
        current = parameters['install_root'] + '/current'
        release = parameters['install_root'] + '/releases/' + parameters['version']
        if (values[current].get('target') != release or
                values['/usr/local/bin/vmagent-observability-agent'].get('target') != current + '/vmagent-prod'):
            raise Refusal('sender-runtime-selection')
        generation = values['/etc/observability-agent/credentials/current'].get('target', '')
        if re.fullmatch(r'/etc/observability-agent/credentials/generations/[a-f0-9]{64}', generation) is None:
            raise Refusal('sender-credential-selection')
        unit = values[str(UNIT)]
        if unit.get('mode') != 0o644 or unit.get('gid') != 0:
            raise Refusal('sender-unit-candidate')
        content = base64.b64decode(unit['data'], validate=True).decode()
        if ' -remoteWrite.url=' + parameters['receiver'] + ' ' not in content:
            raise Refusal('sender-receiver-selection')
        required = ['User=observability-agent', 'Group=observability-agent',
                    'LoadCredential=prometheus.yml:' + generation + '/prometheus.yml',
                    ' -remoteWrite.tmpDataPath=' + str(QUEUE),
                    ' -remoteWrite.maxDiskUsagePerURL=536870912', ' -remoteWrite.queues=1',
                    ' -remoteWrite.inmemoryQueues=0', ' -remoteWrite.maxBlockSize=1048576',
                    ' -remoteWrite.maxRowsPerBlock=1000', ' -remoteWrite.forcePromProto=true']
        if any(part not in content for part in required):
            raise Refusal('sender-native-budget-contract')
        with ancestors(Path(release), self.transaction.uid):
            validate_binary(Path(release) / 'vmagent-prod', self.transaction.uid)
        binary = Path(release) / 'vmagent-prod'
        run([str(binary), '-promscrape.config=' + generation + '/prometheus.yml',
             '-dryRun'])

    def validate_units(self, value):
        if (not isinstance(value, dict) or set(value) != {'service'} or
                set(value['service']) != {'LoadState', 'ActiveState', 'UnitFileState', 'MainPID', 'Result', 'ControlGroup'} or
                value['service']['LoadState'] not in {'loaded', 'not-found'} or
                value['service']['ActiveState'] not in {'active', 'inactive', 'failed'} or
                not value['service']['MainPID'].isdigit() or
                value['service']['UnitFileState'] not in {'enabled', 'disabled', 'static', ''}):
            raise Refusal('sender-unit-record')

    def inspect(self):
        return {'service': fields()}

    def stop(self):
        before = fields()
        if before['LoadState'] == 'loaded':
            run(['/usr/bin/systemctl', 'stop', SERVICE])
        after = fields()
        if after['MainPID'] != '0' or after['ActiveState'] not in {'inactive', 'failed'}:
            raise Refusal('sender-stop-unconfirmed')
        cgroup = before['ControlGroup']
        if cgroup:
            if not re.fullmatch(r'/[A-Za-z0-9_.:/-]+', cgroup) or '..' in Path(cgroup).parts:
                raise Refusal('sender-cgroup')
            group = Path('/sys/fs/cgroup') / cgroup.lstrip('/')
            if group.exists() and any(path.read_text().strip() for path in group.rglob('cgroup.procs')):
                raise Refusal('sender-children-remain')
        if self.capture:
            self.capture = False
            if before['LoadState'] == 'loaded' and after['Result'] != 'success':
                raise Refusal('sender-stop-not-graceful')
            intent = self.transaction.journal()
            if intent is None:
                raise Refusal('sender-intent-absent')
            if any(node(Path(entry['path']), self.transaction.uid, links=2) != entry['before']
                   for entry in intent['entries']):
                raise Refusal('queue-snapshot-after-publication')
            self.snapshot.capture(intent)
            self.queue_proven = self.snapshot.saved()['phase'] == 'retained'
            if (self.plan or {}).get('retire') and before['LoadState'] == 'loaded':
                run(['/usr/bin/systemctl', 'disable', SERVICE])

    def start(self):
        self.target_active = UNIT.exists()
        run(['/usr/bin/systemctl', 'daemon-reload'])
        if self.target_active:
            run(['/usr/bin/systemctl', 'enable', SERVICE])
            run(['/usr/bin/systemctl', 'start', SERVICE])
        else:
            self.stop()

    def retained(self, _receipt):
        return

    def restore(self, units):
        intent = self.transaction.journal()
        baseline = units if units is not None else intent['units']
        self.validate_units(baseline)
        saved = self.snapshot.saved()
        if saved is not None and intent is not None and saved['intent'] != self.snapshot.signature(intent):
            raise Refusal('queue-snapshot-owner')
        if saved is None and intent is not None and any(
                node(Path(entry['path']), self.transaction.uid, links=2) != entry['before']
                for entry in intent['entries']):
            raise Refusal('queue-snapshot-absent')
        self.snapshot.restore()
        self.queue_proven = saved is not None and saved['phase'] in {'retained', 'restored'}
        prior = baseline['service']
        self.target_active = prior['ActiveState'] == 'active'
        run(['/usr/bin/systemctl', 'daemon-reload'])
        if prior['LoadState'] == 'loaded':
            if prior['UnitFileState'] in {'enabled', 'disabled'}:
                run(['/usr/bin/systemctl', 'enable' if prior['UnitFileState'] == 'enabled' else 'disable', SERVICE])
            if self.target_active:
                run(['/usr/bin/systemctl', 'start', SERVICE])
        if units is None:
            self.ready()
        self.restored_ready = True

    def ready(self):
        if not self.target_active:
            if fields()['MainPID'] != '0':
                raise Refusal('sender-inactive-unconfirmed')
            return
        claim = node(UNIT, self.transaction.uid, links=2)
        if claim is None or 'sha256' not in claim:
            raise Refusal('sender-unit-authority')
        raw = UNIT.read_text()
        kinds = re.findall(r'^ExecStart=/usr/local/bin/(vmagent|prometheus)-observability-agent(?: |$)', raw, re.M)
        listeners = re.findall(r'(?:-httpListenAddr=|--web.listen-address=)(127[.]0[.]0[.]1:[0-9]{1,5})(?=\s|$)', raw)
        if len(kinds) != 1 or len(listeners) != 1:
            raise Refusal('sender-unit-profile')
        deadline = time.monotonic() + 25
        while True:
            try:
                readiness.ready(listeners[0], kinds[0])
                fd = self.snapshot.root()
                try:
                    tree(fd, self.snapshot.agent_uid, skip_store=True)
                finally:
                    os.close(fd)
                return
            except (OSError, ValueError, KeyError, subprocess.SubprocessError, Refusal) as error:
                # The live native writer may atomically replace metadata during
                # admission. Quiescent capture still rejects identity changes.
                if isinstance(error, Refusal) and str(error) != 'queue-entry-changed':
                    raise
                if time.monotonic() >= deadline:
                    raise Refusal('sender-not-ready') from None
                time.sleep(1)

    def ensure(self):
        if not UNIT.exists():
            self.target_active = False
            self.ready()
            return False
        if fields()['ActiveState'] == 'active':
            return False
        receipt = self.transaction.accepted()
        intent = {'entries': [], 'before_receipt': receipt,
                  'after_receipt': receipt, 'units': self.inspect()}
        self.transaction.record('startup.json', {'schema': 1, 'committed': False, 'intent': intent})
        try:
            self.stop()
            self.snapshot.capture(intent)
            self.start()
            self.ready()
            self.transaction.record('startup.json', {'schema': 1, 'committed': True, 'intent': intent})
        except Exception:
            self.stop()
            self.snapshot.restore()
            self.target_active = False
            self.restored_ready = True
            self.snapshot.cleanup()
            os.unlink('startup.json', dir_fd=self.transaction.state_fd)
            os.fsync(self.transaction.state_fd)
            raise Refusal('sender-startup-refused') from None
        self.snapshot.cleanup()
        os.unlink('startup.json', dir_fd=self.transaction.state_fd)
        os.fsync(self.transaction.state_fd)
        return True


def finish_retirement(tx):
    if read_private(tx.root / 'queue-snapshot.json', tx.uid) is not None:
        return
    record = read_private(tx.root / 'retiring.json', tx.uid)
    if record is None:
        if tx.journal() is not None or tx.preparation() is not None:
            return
        accepted = read_private(tx.root / 'accepted.json', tx.uid)
        if accepted is None or any(value is not None for value in accepted['nodes'].values()):
            return
        tx.accepted()
        last = read_private(tx.root / 'last.json', tx.uid)
        tx.validate_intent(last)
        record = {'schema': 1, 'backups': tx.backups(accepted['nodes']),
                  'storage': {entry['path']: entry['storage'] for entry in last['entries']}}
        tx.record('retiring.json', record)
    if set(record) != {'schema', 'backups', 'storage'} or record['schema'] != 1:
        raise Refusal('sender-retirement-record')
    tx.validate_backup_map(record['backups'])
    accepted = read_private(tx.root / 'accepted.json', tx.uid)
    if accepted is not None and any(value is not None for value in accepted['nodes'].values()):
        raise Refusal('sender-retirement-not-committed')
    if set(record['storage']) != set(record['backups']['nodes']):
        raise Refusal('sender-retirement-storage')
    for path, claim in record['backups']['nodes'].items():
        tx.storage(path, expected=record['storage'][path])
        backup = tx.backup_path(path)
        observed = node(backup, tx.uid, links=2)
        if observed not in (None, claim):
            raise Refusal('sender-retirement-backup')
        if observed is not None:
            os.unlink(backup)
            os.fsync(tx.parent(backup.parent))
    for name in ('backups.json', 'last.json', 'accepted.json', 'retiring.json'):
        if read_private(tx.root / name, tx.uid) is not None:
            os.unlink(name, dir_fd=tx.state_fd)
            os.fsync(tx.state_fd)


def reconcile(tx, sender):
    finish_retirement(tx)
    startup = read_private(tx.root / 'startup.json', tx.uid)
    if startup is not None:
        pending = tx.journal()
        allowed_pending = pending is None or (read_private(tx.root / 'accepted.json', tx.uid) == pending['after_receipt']
                                               and startup.get('intent', {}).get('before_receipt') == pending['after_receipt'])
        if (set(startup) != {'schema', 'committed', 'intent'} or startup['schema'] != 1 or
                type(startup['committed']) is not bool or not allowed_pending):
            raise Refusal('sender-startup-record')
        intent = startup['intent']
        if (not isinstance(intent, dict) or set(intent) != {'entries', 'before_receipt', 'after_receipt', 'units'} or
                intent['entries'] != [] or intent['before_receipt'] != intent['after_receipt'] or
                intent['before_receipt'] != tx.accepted()):
            raise Refusal('sender-startup-authority')
        sender.validate_units(intent['units'])
        saved = sender.snapshot.saved()
        if saved is not None and saved['intent'] != sender.snapshot.signature(startup['intent']):
            raise Refusal('queue-startup-owner')
        if not startup['committed']:
            sender.stop()
            sender.snapshot.restore()
        sender.snapshot.cleanup()
        os.unlink('startup.json', dir_fd=tx.state_fd)
        os.fsync(tx.state_fd)
    pending = tx.journal()
    saved = sender.snapshot.saved()
    if pending is not None and saved is not None and saved['intent'] != sender.snapshot.signature(pending):
        raise Refusal('queue-snapshot-owner')
    committed = pending is not None and read_private(tx.root / 'accepted.json', tx.uid) == pending['after_receipt']
    if committed:
        tx.accepted()
        if saved is not None:
            sender.snapshot.cleanup()
        saved = None
    if pending is not None and saved is None and not committed:
        if any(node(Path(entry['path']), tx.uid, links=2) != entry['before'] for entry in pending['entries']):
            raise Refusal('sender-publication-without-queue')
        sender.capture = True
    recovered = tx.recover(sender)
    saved = sender.snapshot.saved()
    if saved is not None:
        accepted = tx.accepted()
        if saved['phase'] not in {'restored', 'aborted', 'cleaning'} and (accepted is None or accepted['nodes'] != saved['after_nodes']):
            raise Refusal('queue-cleanup-without-acceptance')
        sender.snapshot.cleanup()
    finish_retirement(tx)
    return recovered


def validate_write_set(parameters, candidates):
    expected = {parameters['install_root'] + '/current',
                '/usr/local/bin/vmagent-observability-agent', str(UNIT),
                '/etc/observability-agent/credentials/current', str(PARAMETERS)}
    selected = {item['path'] for item in candidates}
    allowed = (expected, expected | {parameters['install_root'] + '/previous'})
    if selected not in allowed or len(candidates) != len(selected):
        raise Refusal('sender-write-set')


def execute(action, request=None):
    with Transaction(STATE, check=action == 'check') as tx:
        sender = Sender(tx)
        if action == 'check':
            pending = tx.journal()
            tx.preparation()
            if pending is None:
                receipt = tx.accepted()
                if receipt is not None:
                    tx.backups(receipt['nodes'])
            saved = sender.snapshot.saved()
            if saved is not None:
                fd = sender.snapshot.backup(saved, complete=saved['phase'] in {'retained', 'restored'})
                os.close(fd)
            return {'status': 'predicted', 'changed': False}
        recovered = reconcile(tx, sender)
        if action == 'retire':
            receipt = tx.accepted()
            if receipt is not None:
                sender.plan = {'retire': True}
                sender.capture = True
                tx.apply([{'path': path, 'absent': True} for path in receipt['nodes']], sender)
                sender.snapshot.cleanup()
                tx.record('retiring.json', {'schema': 1, 'backups': tx.backups(receipt['nodes']),
                                           'storage': {entry['path']: entry['storage'] for entry in
                                                       read_private(tx.root / 'last.json', tx.uid)['entries']}})
                finish_retirement(tx)
            return {'status': 'retired', 'changed': recovered or receipt is not None}
        if action == 'recover':
            return {'status': 'recovered', 'changed': recovered}
        parameters = profile(request['profile'])
        candidates = request['candidates']
        validate_write_set(parameters, candidates)
        sender.plan = request
        sender.capture = True
        try:
            result = tx.apply(candidates, sender)
        except Refusal:
            if tx.journal() is None and sender.restored_ready and sender.queue_proven:
                sender.snapshot.cleanup()
                return {'status': 'rolled_back', 'changed': True, 'restored_ready': True}
            raise
        sender.snapshot.cleanup()
        return result


def main():
    try:
        if os.geteuid() != 0 or len(sys.argv) != 2 or sys.argv[1] not in {'guard', 'check', 'recover', 'apply', 'retire'}:
            raise Refusal('sender-action')
        action = sys.argv[1]
        if action == 'guard':
            guard()
            return 0
        raw = sys.stdin.buffer.read(1048577) if action == 'apply' else b''
        if len(raw) > 1048576:
            raise Refusal('sender-request-budget')
        result = execute(action, json.loads(raw) if raw else None)
        print(json.dumps(result, sort_keys=True))
        return 2 if result['status'] == 'rolled_back' else 0
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        category = str(error) if isinstance(error, Refusal) else 'sender-activation-refused'
        if re.fullmatch('[a-z][a-z0-9-]{0,63}', category) is None:
            category = 'sender-activation-refused'
        print(json.dumps({'status': 'refused', 'changed': False, 'category': category}, sort_keys=True))
        print(category, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
