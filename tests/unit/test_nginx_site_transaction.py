"""Portable real-file compensation/authority proof; runtime adoption stays native."""
import base64
import copy
import fcntl
import importlib.util
import json
import os
import sys
from pathlib import Path
import stat

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'ansible/roles/nginx-xhttp/files/nginx_transaction.py'


def load():
    spec = importlib.util.spec_from_file_location('site_nginx', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    tx = load()
    root = tmp_path.resolve()
    root.chmod(0o700)
    def safe(path, *, missing=False):
        path = Path(path)
        assert path.is_absolute() and '..' not in path.parts
        assert path == root or path.is_relative_to(root)
        for parent in [root, *list(path.relative_to(root).parents)[::-1], path.relative_to(root)]:
            current = parent if parent.is_absolute() else root / parent
            if not current.exists():
                if missing:
                    return
                raise tx.TransactionError('missing-parent')
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise tx.TransactionError('unsafe-parent')
    monkeypatch.setattr(tx, 'safe', safe)
    monkeypatch.setattr(tx, 'STATE_ROOT', root / 'state')
    commands = []
    monkeypatch.setattr(tx, 'command', lambda argv: commands.append(argv) or '')
    monkeypatch.setattr(tx, 'service_state', lambda unit: {'active': False, 'exists': True, 'unit_file_state': 'disabled'})
    monkeypatch.setattr(tx, 'restore_enabled', lambda *args: None)
    ingress = root / 'ingress'
    ingress.mkdir(mode=0o700)
    owners = [{'owner': owner, 'roots': [str(ingress)],
               'paths': [str(ingress / (owner + '.conf'))], 'prune_releases': None}
              for owner in sorted(tx.SITE_OWNERS)]
    return tx, {'owners': owners, 'check': False}, commands


def desired(tx, context, owner='nginx-xhttp', content=b'candidate', path=None):
    value = next(value for value in tx.site_request(context) if value['owner'] == owner)
    value['files'] = [{'path': path or value['files'][0]['path'], 'kind': 'file',
                       'uid': os.geteuid(), 'gid': os.getegid(), 'mode': 0o640,
                       'content_b64': base64.b64encode(content).decode()}]
    return value


def install_accepted(tx, context, *, content=b'accepted'):
    state = tx.STATE_ROOT / 'nginx.service'
    with tx.unit_lock(state):
        for owner in tx.SITE_OWNERS:
            document = desired(tx, context, owner, content)
            for row in document['files']:
                tx.apply(Path(row['path']), {k: v for k, v in row.items() if k != 'path'}, [])
            tx.persist(state / (owner + '.activated.json'), tx.owned_receipt(document))
    return state


def publish_candidate(tx, context, content=b'candidate'):
    state = tx.STATE_ROOT / 'nginx.service'
    document = desired(tx, context, content=content)
    receipt = tx.owned_receipt(document)
    with tx.unit_lock(state):
        tx.site_authorize(state, document, receipt)
        for row in document['files']:
            tx.apply(Path(row['path']), {k: v for k, v in row.items() if k != 'path'}, [])
        tx.persist(state / 'nginx-xhttp.activated.json', receipt)
    return Path(document['files'][0]['path'])


def test_fresh_then_warm_private_snapshot_restores_exact_bytes_and_receipts(fixture):
    tx, context, commands = fixture
    tx.site_transaction('begin', context)
    candidate = publish_candidate(tx, context)
    tx.site_transaction('commit', context)
    assert candidate.read_bytes() == b'candidate'
    receipt = tx.private_json(tx.STATE_ROOT / 'nginx.service/nginx-xhttp.activated.json')
    assert receipt['schema'] == 2 and 'content_b64' not in json.dumps(receipt)
    before = tx.capture(candidate)
    receipt_before = tx.capture(tx.STATE_ROOT / 'nginx.service/nginx-xhttp.activated.json')
    tx.site_transaction('begin', context)
    publish_candidate(tx, context, b'changed private fixture')
    assert tx.site_transaction('restore', context)['changed'] is True
    assert tx.capture(candidate) == before
    assert tx.capture(tx.STATE_ROOT / 'nginx.service/nginx-xhttp.activated.json') == receipt_before
    assert not (tx.STATE_ROOT / 'nginx.service/site.json').exists()
    assert commands == [['systemctl', 'stop', 'nginx.service']]


def test_old_owned_paths_union_new_declared_paths_and_durable_restore(fixture):
    tx, context, _ = fixture
    state = install_accepted(tx, context)
    old = Path(next(value for value in context['owners'] if value['owner'] == 'nginx-xhttp')['paths'][0])
    new = old.with_name('new-host.key')
    changed = copy.deepcopy(context)
    next(value for value in changed['owners'] if value['owner'] == 'nginx-xhttp')['paths'] = [str(new)]
    tx.site_transaction('begin', changed)
    journal = tx.read_site(state)
    assert {str(old), str(new)} <= set(journal['files'])
    document = desired(tx, changed, path=str(new))
    receipt = tx.owned_receipt(document, {**tx.private_json(state / 'nginx-xhttp.activated.json')['files'], str(new): tx.witness({k:v for k,v in document['files'][0].items() if k != 'path'})})
    tx.site_authorize(state, document, receipt)
    tx.apply(new, {k:v for k,v in document['files'][0].items() if k != 'path'}, [])
    tx.persist(state / 'nginx-xhttp.activated.json', receipt)
    # A new invocation reconstructs authority exclusively from the private journal.
    tx.site_transaction('restore', changed)
    assert old.read_bytes() == b'accepted' and not new.exists()


@pytest.mark.parametrize('case', ['legacy', 'owner', 'unit', 'path', 'digest'])
def test_invalid_receipt_refuses_before_any_mutation(fixture, case):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    path = state / 'nginx-xhttp.activated.json'
    receipt = tx.private_json(path)
    if case == 'legacy':
        receipt = {'schema': 1, 'fingerprint': receipt['fingerprint'], 'active': True}
    elif case == 'owner':
        receipt['owner'] = 'foreign'
    elif case == 'unit':
        receipt['unit'] = 'foreign.service'
    elif case == 'path':
        receipt['files']['/outside/authority'] = {'kind': 'absent'}
    else:
        next(iter(receipt['files'].values()))['sha256'] = '0' * 64
    tx.persist(path, receipt)
    before = {p: tx.capture(p) for p in state.iterdir() if p.name != 'lock'}
    with pytest.raises(tx.TransactionError):
        tx.site_transaction('begin', context)
    assert before == {p: tx.capture(p) for p in state.iterdir() if p.name != 'lock'}
    assert not (state / 'site.json').exists() and not commands


@pytest.mark.parametrize('action', ['restore', 'commit'])
def test_foreign_edit_is_never_overwritten_or_committed(fixture, action):
    tx, context, commands = fixture
    install_accepted(tx, context)
    tx.site_transaction('begin', context)
    path = publish_candidate(tx, context)
    path.write_bytes(b'foreign concurrent edit')
    before = tx.capture(path)
    with pytest.raises(tx.TransactionError, match='^foreign-publication$'):
        tx.site_transaction(action, context)
    assert tx.capture(path) == before and not commands
    assert (tx.STATE_ROOT / 'nginx.service/site.json').exists()


def test_existing_journal_is_not_clobbered_and_check_mode_is_read_only(fixture):
    tx, context, commands = fixture
    install_accepted(tx, context)
    tx.site_transaction('begin', context)
    journal = tx.STATE_ROOT / 'nginx.service/site.json'
    before = tx.capture(journal)
    with pytest.raises(tx.TransactionError, match='^recovery-required$'):
        tx.site_transaction('begin', context)
    assert tx.capture(journal) == before
    tx.site_transaction('restore', context)
    context['check'] = True
    before = {p: tx.capture(p) for p in journal.parent.iterdir()}
    tx.site_transaction('begin', context)
    assert {p: tx.capture(p) for p in journal.parent.iterdir()} == before


def test_foreign_owner_and_undeclared_candidate_paths_refuse(fixture):
    tx, context, _ = fixture
    install_accepted(tx, context)
    tx.site_transaction('begin', context)
    document = desired(tx, context)
    document['owner'] = 'foreign'
    with pytest.raises(tx.TransactionError, match='^site-transaction-busy$'):
        tx.site_authorize(tx.STATE_ROOT / 'nginx.service', document, tx.owned_receipt(document))
    document['owner'] = 'nginx-xhttp'
    document['files'][0]['path'] += '.foreign'
    with pytest.raises(tx.TransactionError, match='^site-write-set$'):
        tx.site_authorize(tx.STATE_ROOT / 'nginx.service', document, tx.owned_receipt(document))


def test_ordinary_disabled_publisher_fresh_warm_schema2_receipt(fixture, monkeypatch):
    tx, context, _ = fixture
    monkeypatch.setattr(tx, 'boot_clock', lambda: ('0' * 8 + '-0000-0000-0000-' + '0' * 12, 10))
    monkeypatch.setattr(tx, 'inactive_absence_receipt', lambda unit, receipt: {**receipt, 'active': False, 'boot_id': tx.boot_clock()[0], 'inactive_after_ticks': 10})
    document = tx.site_request(context)[0]
    assert tx.publish(document) == {'status': 'unchanged', 'changed': False}
    receipt = tx.private_json(tx.STATE_ROOT / 'nginx.service' / (document['owner'] + '.activated.json'))
    assert receipt['schema'] == 2
    assert tx.publish(document) == {'status': 'unchanged', 'changed': False}


def test_interrupted_ordinary_publication_restores_prior_receipt_and_files(fixture):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    document = desired(tx, context)
    path = Path(document['files'][0]['path'])
    original = tx.capture(path)
    receipt_path = state / 'nginx-xhttp.activated.json'
    prior_receipt = tx.capture(receipt_path)
    tx.apply(path, {k:v for k,v in document['files'][0].items() if k != 'path'}, [])
    tx.persist(receipt_path, tx.owned_receipt(document))
    journal = {'schema': 2, 'phase': 'activated', 'candidate': 'candidate-' + '0' * 32,
               'request': document, 'files': {str(path): original}, 'active': False,
               'service': {'active': False, 'exists': True, 'unit_file_state': 'disabled'},
               'owner': document['owner'], 'receipt': prior_receipt, 'next_receipt': tx.receipt_row(tx.owned_receipt(document))}
    tx.persist(state / 'pending.json', journal)
    assert tx.recover(state / 'pending.json', 'nginx.service') is True
    assert tx.capture(path) == original and tx.capture(receipt_path) == prior_receipt
    tx.validate_receipt(tx.private_json(receipt_path), 'nginx-xhttp', 'nginx.service')
    tx.verify_witnesses(tx.private_json(receipt_path)['files'])
    assert not (state / 'pending.json').exists()


def test_unclaimed_existing_ingress_refuses_without_runtime_changes(fixture):
    tx, context, commands = fixture
    path = Path(context['owners'][0]['paths'][0])
    path.write_bytes(b'foreign unclaimed configuration')
    path.chmod(0o640)
    before = tx.capture(path)
    with pytest.raises(tx.TransactionError, match='^unclaimed-ingress$'):
        tx.site_transaction('begin', context)
    assert tx.capture(path) == before and not commands
    assert not (tx.STATE_ROOT / 'nginx.service/site.json').exists()


def test_partial_restore_can_resume_after_runtime_failure(fixture, monkeypatch):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    path = publish_candidate(tx, context)
    def interrupted(*args):
        raise tx.TransactionError('enablement-restore-failed')
    monkeypatch.setattr(tx, 'restore_enabled', interrupted)
    with pytest.raises(tx.TransactionError, match='^enablement-restore-failed$'):
        tx.site_transaction('restore', context)
    assert path.read_bytes() == b'accepted' and (state / 'site.json').exists()
    monkeypatch.setattr(tx, 'restore_enabled', lambda *args: None)
    assert tx.site_transaction('restore', context)['status'] == 'restored'
    assert not (state / 'site.json').exists()


def test_commit_refuses_candidate_file_receipt_mismatch(fixture):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    path = publish_candidate(tx, context)
    # Even an earlier authorized version is not the adopted current receipt.
    tx.apply(path, tx.read_site(state)['files'][str(path)], [])
    with pytest.raises(tx.TransactionError, match='^foreign-publication$'):
        tx.site_transaction('commit', context)
    assert (state / 'site.json').exists() and not commands


def test_fresh_package_default_link_is_removed_and_rollback_retains_original_absence(fixture, monkeypatch):
    tx, context, commands = fixture
    root = Path(context['owners'][0]['roots'][0])
    enabled = root / 'sites-enabled/default'
    available = root / 'sites-available/default'
    monkeypatch.setattr(tx, 'DEFAULT_ENABLED', enabled)
    monkeypatch.setattr(tx, 'DEFAULT_AVAILABLE', available)
    for value in context['owners']:
        value['paths'].append(str(enabled))
    tx.site_transaction('begin', context)
    # Actual package-shaped files arrive after begin, before one-shot publication.
    available.parent.mkdir(mode=0o755)
    available.write_bytes(b'distribution default configuration')
    available.chmod(0o644)
    enabled.parent.mkdir(mode=0o755)
    enabled.symlink_to('../sites-available/default')
    if stat.S_IMODE(enabled.lstat().st_mode) != 0o777:
        os.chmod(enabled, 0o777, follow_symlinks=False)
    assert stat.S_IMODE(enabled.lstat().st_mode) == 0o777
    def package(argv):
        commands.append(argv)
        return 'nginx-common: ' + str(available) if argv[0] == 'dpkg-query' else ''
    monkeypatch.setattr(tx, 'command', package)
    document = desired(tx, context)
    document['files'].append({'path': str(enabled), 'kind': 'absent'})
    state = tx.STATE_ROOT / 'nginx.service'
    receipt = tx.owned_receipt(document)
    with tx.unit_lock(state):
        tx.site_authorize(state, document, receipt)
        assert tx.witness(tx.capture(enabled)) in tx.read_site(state)['allowed'][str(enabled)]
        for row in document['files']:
            tx.apply(Path(row['path']), {k:v for k,v in row.items() if k != 'path'}, [])
        tx.persist(state / 'nginx-xhttp.activated.json', receipt)
    assert not enabled.exists()
    tx.site_transaction('restore', context)
    assert not enabled.exists() and not Path(document['files'][0]['path']).exists()
    assert available.read_bytes() == b'distribution default configuration'


@pytest.mark.parametrize('case', ['wrong-target', 'unknown-package', 'regular-file'])
def test_package_default_admission_is_exact_and_refuses_foreign_shapes(fixture, monkeypatch, case):
    tx, context, commands = fixture
    root = Path(context['owners'][0]['roots'][0])
    enabled, available = root / 'default-link', root / 'package-default'
    monkeypatch.setattr(tx, 'DEFAULT_ENABLED', enabled)
    monkeypatch.setattr(tx, 'DEFAULT_AVAILABLE', available)
    for value in context['owners']:
        value['paths'].append(str(enabled))
    tx.site_transaction('begin', context)
    available.write_bytes(b'distro file')
    available.chmod(0o644)
    if case == 'regular-file':
        enabled.write_bytes(b'foreign file')
        enabled.chmod(0o644)
    else:
        enabled.symlink_to(str(available) + ('.foreign' if case == 'wrong-target' else ''))
        if stat.S_IMODE(enabled.lstat().st_mode) != 0o777:
            os.chmod(enabled, 0o777, follow_symlinks=False)
    monkeypatch.setattr(tx, 'command', lambda argv: 'foreign-package: ' + str(available))
    before = tx.capture(enabled)
    document = desired(tx, context)
    document['files'].append({'path': str(enabled), 'kind': 'absent'})
    with pytest.raises(tx.TransactionError, match='^foreign-publication$'):
        tx.site_authorize(tx.STATE_ROOT / 'nginx.service', document, tx.owned_receipt(document))
    assert tx.capture(enabled) == before


def test_valid_foreign_receipt_is_not_overwritten_during_ordinary_recovery(fixture):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    document = desired(tx, context)
    path = Path(document['files'][0]['path'])
    receipt = state / 'nginx-xhttp.activated.json'
    prior = tx.capture(receipt)
    original = tx.capture(path)
    journal = {'schema': 2, 'phase': 'activated', 'candidate': 'candidate-' + '0' * 32,
               'request': document, 'files': {str(path): original}, 'active': False,
               'service': {'active': False, 'exists': True, 'unit_file_state': 'disabled'},
               'owner': document['owner'], 'receipt': prior,
               'next_receipt': tx.receipt_row(tx.owned_receipt(document))}
    tx.persist(state / 'pending.json', journal)
    foreign = tx.owned_receipt(document)
    foreign['fingerprint'] = '0' * 64
    tx.persist(receipt, foreign)
    before = (tx.capture(receipt), receipt.stat().st_ino, tx.capture(path), tx.capture(state / 'pending.json'))
    with pytest.raises(tx.TransactionError, match='^foreign-receipt$'):
        tx.recover(state / 'pending.json', 'nginx.service')
    assert (tx.capture(receipt), receipt.stat().st_ino, tx.capture(path), tx.capture(state / 'pending.json')) == before
    assert not commands


def test_interrupted_ordinary_compensation_can_retry_exact_next_receipt(fixture, monkeypatch):
    tx, context, _ = fixture
    state = install_accepted(tx, context)
    document = desired(tx, context)
    path = Path(document['files'][0]['path'])
    receipt = state / 'nginx-xhttp.activated.json'
    prior, original = tx.capture(receipt), tx.capture(path)
    tx.apply(path, {k:v for k,v in document['files'][0].items() if k != 'path'}, [])
    tx.persist(receipt, tx.owned_receipt(document))
    tx.persist(state / 'pending.json', {
        'schema': 2, 'phase': 'activated', 'candidate': 'candidate-' + '0' * 32,
        'request': document, 'files': {str(path): original}, 'active': False,
        'service': {'active': False, 'exists': True, 'unit_file_state': 'disabled'},
        'owner': document['owner'], 'receipt': prior,
        'next_receipt': tx.receipt_row(tx.owned_receipt(document))})
    original_apply = tx.apply
    def interrupted(path, row, created):
        if path == receipt:
            raise tx.TransactionError('interrupted-receipt-restore')
        original_apply(path, row, created)
    monkeypatch.setattr(tx, 'apply', interrupted)
    with pytest.raises(tx.TransactionError, match='^interrupted-receipt-restore$'):
        tx.recover(state / 'pending.json', 'nginx.service')
    assert tx.private_json(state / 'pending.json')['phase'] == 'recovering'
    assert tx.capture(path) == original and tx.capture(receipt) != prior
    monkeypatch.setattr(tx, 'apply', original_apply)
    assert tx.recover(state / 'pending.json', 'nginx.service') is True
    assert tx.capture(receipt) == prior and tx.capture(path) == original
    assert not (state / 'pending.json').exists()


@pytest.mark.parametrize('action', ['restore', 'commit'])
def test_site_never_recovers_an_unrelated_owner_pending_journal(fixture, action):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    document = desired(tx, context)
    document['owner'] = 'foreign-owner'
    tx.persist(state / 'pending.json', {'request': document})
    before = tx.capture(state / 'pending.json')
    with pytest.raises(tx.TransactionError, match='^(site-write-set|recovery-required)$'):
        tx.site_transaction(action, context)
    assert tx.capture(state / 'pending.json') == before and not commands


def test_public_origin_pages_assets_and_retirement_restore_exact_authority(fixture):
    tx, context, _ = fixture
    owner = next(value for value in context['owners'] if value['owner'] == 'nginx-xhttp')
    root = Path(owner['roots'][0])
    names = ['index.html', 'assets/site.css', 'notes/reading.html', '.well-known/security.txt']
    owner['paths'] += [str(root / name) for name in names]
    old = tx.site_request(context)[0]
    old['owner'] = 'nginx-xhttp'
    old['files'] = [{'path': str(root / name), 'kind': 'file', 'uid': os.geteuid(), 'gid': os.getegid(), 'mode': 0o644,
                     'content_b64': base64.b64encode(b'accepted https://old-origin.example.invalid/' + name.encode()).decode()}
                    for name in names]
    state = tx.STATE_ROOT / 'nginx.service'
    with tx.unit_lock(state):
        for row in old['files']:
            tx.apply(Path(row['path']), {k:v for k,v in row.items() if k != 'path'}, [])
        tx.persist(state / 'nginx-xhttp.activated.json', tx.owned_receipt(old))
    before = {row['path']: tx.capture(Path(row['path'])) for row in old['files']}
    tx.site_transaction('begin', context)
    candidate = copy.deepcopy(old)
    for row in candidate['files']:
        row['content_b64'] = base64.b64encode(b'candidate https://new-origin.example.invalid').decode()
    candidate['files'][-1] = {'path': str(root / names[-1]), 'kind': 'absent'}
    with tx.unit_lock(state):
        receipt = tx.owned_receipt(candidate)
        tx.site_authorize(state, candidate, receipt)
        for row in candidate['files']:
            tx.apply(Path(row['path']), {k:v for k,v in row.items() if k != 'path'}, [])
        tx.persist(state / 'nginx-xhttp.activated.json', receipt)
    assert not (root / names[-1]).exists()
    tx.site_transaction('restore', context)
    assert {path: tx.capture(Path(path)) for path in before} == before


def interrupted_publication(tx, context, phase, receipt_state='prior'):
    state = install_accepted(tx, context)
    document = desired(tx, context)
    path = Path(document['files'][0]['path'])
    receipt = state / 'nginx-xhttp.activated.json'
    prior, original = tx.capture(receipt), tx.capture(path)
    next_receipt = tx.receipt_row(tx.owned_receipt(document))
    tx.persist(state / 'pending.json', {
        'schema': 2, 'phase': phase, 'candidate': 'candidate-' + '0' * 32,
        'request': document, 'files': {str(path): original}, 'active': False,
        'service': {'active': False, 'exists': True, 'unit_file_state': 'disabled'},
        'owner': document['owner'], 'receipt': prior, 'next_receipt': next_receipt})
    if phase != 'prepared':
        tx.apply(path, {k:v for k,v in document['files'][0].items() if k != 'path'}, [])
    if receipt_state == 'next':
        tx.apply(receipt, next_receipt, [])
    elif receipt_state == 'absent':
        tx.clear(receipt)
    return state, document, path, receipt


@pytest.mark.parametrize('phase,receipt_state', [
    *[(phase, 'prior') for phase in ['prepared', 'publishing', 'activating', 'activated', 'recovering']],
    ('activated', 'next'), ('recovering', 'next'),
    ('activated', 'absent'), ('recovering', 'absent'),
])
def test_publish_entrypoint_recovers_owned_interruption_before_disk_witness_check(fixture, monkeypatch, phase, receipt_state):
    tx, context, _ = fixture
    state, document, path, _ = interrupted_publication(tx, context, phase, receipt_state)
    recovered = []
    original = tx.recover
    def observe(pending, unit):
        result = original(pending, unit)
        recovered.append(result)
        return result
    monkeypatch.setattr(tx, 'recover', observe)
    result = tx.publish(document)
    assert recovered == [True]
    assert result == {'status': 'committed', 'changed': True}
    assert path.read_bytes() == b'candidate'
    assert not (state / 'pending.json').exists() and not list(state.glob('candidate-*'))


@pytest.mark.parametrize('phase', ['prepared', 'publishing', 'activating'])
def test_publish_rejects_a_next_receipt_before_its_owned_commit_phase(fixture, phase):
    tx, context, commands = fixture
    state, document, path, receipt = interrupted_publication(tx, context, phase, 'next')
    before = (tx.capture(path), tx.capture(receipt), tx.capture(state / 'pending.json'))
    with pytest.raises(tx.TransactionError, match='^foreign-receipt$'):
        tx.publish(document)
    assert (tx.capture(path), tx.capture(receipt), tx.capture(state / 'pending.json')) == before
    assert not commands


@pytest.mark.parametrize('mutation', ['file', 'receipt'])
def test_publish_pending_foreign_authority_refuses_before_recovery_mutation(fixture, mutation):
    tx, context, commands = fixture
    state, document, path, receipt = interrupted_publication(tx, context, 'activated')
    if mutation == 'file':
        path.write_bytes(b'foreign actual bytes')
    else:
        value = tx.private_json(receipt)
        value['fingerprint'] = '0' * 64
        tx.persist(receipt, value)
    before = (tx.capture(path), tx.capture(receipt), receipt.stat().st_ino, tx.capture(state / 'pending.json'))
    with pytest.raises(tx.TransactionError, match='^foreign-(publication|receipt)$'):
        tx.publish(document)
    assert (tx.capture(path), tx.capture(receipt), receipt.stat().st_ino, tx.capture(state / 'pending.json')) == before
    assert not commands


def test_check_mode_owned_pending_refuses_without_recovery_or_publication(fixture):
    tx, context, commands = fixture
    state, document, path, receipt = interrupted_publication(tx, context, 'prepared')
    document['check'] = True
    before = (tx.capture(path), tx.capture(receipt), tx.capture(state / 'pending.json'))
    with pytest.raises(tx.TransactionError, match='^recovery-required$'):
        tx.publish(document)
    assert (tx.capture(path), tx.capture(receipt), tx.capture(state / 'pending.json')) == before
    assert not commands


@pytest.mark.parametrize('phase,receipt_state', [
    ('prepared', 'prior'), ('publishing', 'prior'), ('activated', 'prior'), ('activated', 'next'),
])
def test_begin_recovers_a_pending_only_publication_under_the_unit_lock_then_captures(fixture, monkeypatch, phase, receipt_state):
    tx, context, _ = fixture
    state, _, path, receipt = interrupted_publication(tx, context, phase, receipt_state)
    prior_receipt = tx.private_json(state / 'pending.json')['receipt']
    held = []
    recover = tx.recover
    def under_lock(pending, unit):
        # A second descriptor cannot take the exclusive lock while begin holds it.
        descriptor = os.open(state / 'lock', os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held.append(True)
        finally:
            os.close(descriptor)
        return recover(pending, unit)
    monkeypatch.setattr(tx, 'recover', under_lock)
    assert tx.site_transaction('begin', context) == {'status': 'captured', 'changed': False}
    assert held == [True]
    assert path.read_bytes() == b'accepted' and tx.capture(receipt) == prior_receipt
    assert not (state / 'pending.json').exists() and not list(state.glob('candidate-*'))
    assert tx.read_site(state) is not None


def test_check_mode_begin_refuses_a_pending_only_journal_without_recovery(fixture):
    tx, context, commands = fixture
    state, _, path, receipt = interrupted_publication(tx, context, 'activated')
    before = (tx.capture(path), tx.capture(receipt), tx.capture(state / 'pending.json'))
    with pytest.raises(tx.TransactionError, match='^recovery-required$'):
        tx.site_transaction('begin', {**context, 'check': True})
    assert (tx.capture(path), tx.capture(receipt), tx.capture(state / 'pending.json')) == before
    assert not commands and not (state / 'site.json').exists()


@pytest.mark.parametrize('case,refusal', [
    ('unrecognized', 'manual-recovery-required'), ('foreign-file', 'foreign-publication'), ('foreign-receipt', 'foreign-receipt'),
])
def test_begin_retains_unrecognized_or_foreign_pending_journals_without_mutation(fixture, case, refusal):
    tx, context, commands = fixture
    state, document, path, receipt = interrupted_publication(tx, context, 'activated')
    if case == 'unrecognized':
        tx.persist(state / 'pending.json', {'request': document})
    elif case == 'foreign-file':
        path.write_bytes(b'foreign actual bytes')
    else:
        value = tx.private_json(receipt)
        value['fingerprint'] = '0' * 64
        tx.persist(receipt, value)
    before = (tx.capture(path), tx.capture(receipt), receipt.stat().st_ino, tx.capture(state / 'pending.json'))
    with pytest.raises(tx.TransactionError, match='^' + refusal + '$'):
        tx.site_transaction('begin', context)
    assert (tx.capture(path), tx.capture(receipt), receipt.stat().st_ino, tx.capture(state / 'pending.json')) == before
    assert not commands and not (state / 'site.json').exists()


def test_begin_with_an_open_site_journal_never_recovers_a_pending_journal(fixture):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    # Recovery of this unrecognized journal would raise manual-recovery-required.
    tx.persist(state / 'pending.json', {'request': desired(tx, context)})
    before = {p: tx.capture(p) for p in state.iterdir() if p.name != 'lock'}
    with pytest.raises(tx.TransactionError, match='^recovery-required$'):
        tx.site_transaction('begin', context)
    assert {p: tx.capture(p) for p in state.iterdir() if p.name != 'lock'} == before
    assert not commands


@pytest.mark.parametrize('mutation', ['nonabsent-foreign', 'undeclared-missing'])
def test_declared_retirement_never_adopts_foreign_bytes_or_undeclared_absence(fixture, mutation):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    document = desired(tx, context)
    path = Path(document['files'][0]['path'])
    if mutation == 'nonabsent-foreign':
        path.write_bytes(b'foreign body')
        document['files'] = [{'path': str(path), 'kind': 'absent'}]
    else:
        path.unlink()
    receipt = state / 'nginx-xhttp.activated.json'
    before = (tx.capture(path), tx.capture(receipt), receipt.stat().st_ino)
    with pytest.raises(tx.TransactionError, match='^foreign-publication$'):
        tx.publish(document)
    assert (tx.capture(path), tx.capture(receipt), receipt.stat().st_ino) == before and not commands


def test_explicit_already_absent_retirement_reaches_active_runtime_adoption(fixture, monkeypatch):
    tx, context, _ = fixture
    state = install_accepted(tx, context)
    document = desired(tx, context)
    path = Path(document['files'][0]['path'])
    path.unlink()
    document['files'] = [{'path': str(path), 'kind': 'absent'}]
    monkeypatch.setattr(tx, 'service_state', lambda unit: {'active': True, 'exists': True, 'unit_file_state': 'disabled'})
    class AdoptionBoundary(BaseException):
        pass
    # Observe actual publisher selection before any platform-specific runtime
    # operation. Real nginx reload/listener retirement remains a native proof.
    def adoption(unit):
        assert unit == 'nginx.service'
        raise AdoptionBoundary()
    monkeypatch.setattr(tx, 'nginx_master', adoption)
    with pytest.raises(AdoptionBoundary):
        tx.publish(document)
    assert tx.private_json(state / 'pending.json')['phase'] == 'activating'


def test_typed_prune_accounts_for_owned_release_pairs_already_absent(fixture, monkeypatch):
    tx, context, _ = fixture
    state = install_accepted(tx, context)
    owner = next(value for value in tx.site_request(context) if value['owner'] == 'reality-self-steal')
    root = Path(owner['roots'][0]) / 'releases'
    release = root / ('a' * 64)
    kept = root / ('b' * 64)
    receipt_path = state / 'reality-self-steal.activated.json'
    receipt = tx.private_json(receipt_path)
    for pair in [release, kept]:
        for name in ['fullchain.pem', 'privkey.pem']:
            path = pair / name
            row = {'kind': 'file', 'uid': os.geteuid(), 'gid': os.getegid(), 'mode': 0o600, 'content_b64': base64.b64encode(b'owned pair authority').decode()}
            tx.apply(path, row, [])
            receipt['files'][str(path)] = tx.witness(row)
    tx.persist(receipt_path, receipt)
    for path in release.iterdir():
        path.unlink()
    owner['prune_releases'] = {'root': str(root), 'keep': kept.name}
    expanded = tx.expand_release_prune(owner, receipt['files'])
    removed = {row['path'] for row in expanded['files'] if row['kind'] == 'absent'}
    assert {str(release / name) for name in ['fullchain.pem', 'privkey.pem']} <= removed
    assert not {str(kept / name) for name in ['fullchain.pem', 'privkey.pem']} & removed
    assert tx.verify_witnesses(receipt['files'], removed) is True
    owner['prune_releases']['keep'] = None
    monkeypatch.setattr(tx, 'inactive_absence_receipt', lambda unit, value: {**value, 'active': False, 'boot_id': '00000000-0000-0000-0000-000000000000', 'inactive_after_ticks': 0})
    assert tx.publish(owner)['status'] in {'committed', 'unchanged'}
    assert not list(root.glob('*/*'))
    assert tx.private_json(receipt_path) is None  # Inactive changed publication claims no live adoption.
    assert tx.publish(owner) == {'status': 'unchanged', 'changed': False}
    assert all(row['kind'] == 'absent' for row in tx.private_json(receipt_path)['files'].values())


def test_site_authority_does_not_admit_external_deletion_as_retirement(fixture, monkeypatch):
    tx, context, commands = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    document = desired(tx, context)
    path = Path(document['files'][0]['path'])
    path.unlink()
    document['files'] = [{'path': str(path), 'kind': 'absent'}]
    monkeypatch.setattr(tx, 'inactive_absence_receipt', lambda unit, value: {**value, 'active': False, 'boot_id': '00000000-0000-0000-0000-000000000000', 'inactive_after_ticks': 0})
    monkeypatch.setattr(tx, 'boot_clock', lambda: ('00000000-0000-0000-0000-000000000000', 1))
    before = (tx.capture(state / 'site.json'), tx.capture(state / 'nginx-xhttp.activated.json'))
    with pytest.raises(tx.TransactionError, match='^foreign-publication$'):
        tx.publish(document)
    assert (tx.capture(state / 'site.json'), tx.capture(state / 'nginx-xhttp.activated.json')) == before
    assert not commands


@pytest.mark.parametrize('boundary', ['before-decision', 'after-decision', 'before-egress-finish',
                                      'after-egress-finish', 'before-ingress-clear', 'after-ingress-clear'])
def test_sigkill_commit_boundary_recovers_one_generation(fixture, boundary):
    """Real process death and journal I/O; the portable egress adapter is modeled."""
    import signal
    tx, context, _ = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    candidate = publish_candidate(tx, context)
    outer = state / 'modeled-outer'
    outer.write_text('previous')
    def finish(argv):
        assert argv[-1] == 'finish'
        outer.unlink(missing_ok=True)
        return ''
    tx.command = finish
    pid = os.fork()
    if pid == 0:
        def kill():
            os.kill(os.getpid(), signal.SIGKILL)
        persist, clear = tx.persist, tx.clear
        def marked(path, value):
            if path.name == 'site.json' and value['phase'] == 'committing':
                if boundary == 'before-decision': kill()
                persist(path, value)
                if boundary == 'after-decision': kill()
            else:
                persist(path, value)
        def egress(argv):
            if boundary == 'before-egress-finish': kill()
            result = finish(argv)
            if boundary == 'after-egress-finish': kill()
            return result
        def removed(path):
            if boundary == 'before-ingress-clear': kill()
            clear(path)
            if boundary == 'after-ingress-clear': kill()
        tx.persist, tx.command, tx.clear = marked, egress, removed
        try:
            tx.site_transaction('commit', context, finish_egress=True)
        finally:
            # A forked worker must never unwind into the parent pytest runner.
            failed = sys.exc_info()[0] is not None
            if failed:
                import traceback
                traceback.print_exc()
            os._exit(2 if failed else 1)
    _, status = os.waitpid(pid, 0)
    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
    result = tx.site_transaction('recover-commit', context)
    if result['status'] == 'open':
        assert boundary == 'before-decision'
        tx.command = lambda argv: ''
        tx.site_transaction('restore', context)
        outer.unlink()
        assert candidate.read_bytes() == b'accepted'
    else:
        assert result['status'] == ('absent' if boundary == 'after-ingress-clear' else 'committed')
        assert candidate.read_bytes() == b'candidate'
    assert not outer.exists() and not (state / 'site.json').exists()
    assert tx.site_transaction('recover-commit', context)['status'] == 'absent'


def test_commit_failure_retains_decision_refuses_restore_and_retries(fixture):
    tx, context, _ = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    candidate = publish_candidate(tx, context)
    def refused(argv):
        raise tx.TransactionError('runtime-command')
    tx.command = refused
    with pytest.raises(tx.TransactionError, match='runtime-command'):
        tx.site_transaction('commit', context, finish_egress=True)
    journal = (state / 'site.json').read_bytes()
    assert json.loads(journal)['phase'] == 'committing'
    with pytest.raises(tx.TransactionError, match='commit-recovery-required'):
        tx.site_transaction('restore', context)
    with pytest.raises(tx.TransactionError, match='recovery-required'):
        tx.site_transaction('begin', {**context, 'check': True})
    assert (state / 'site.json').read_bytes() == journal and candidate.read_bytes() == b'candidate'
    tx.command = lambda argv: ''
    assert tx.site_transaction('recover-commit', context)['status'] == 'committed'


def test_revocation_commit_retries_only_exact_durable_authority(fixture):
    tx, context, _ = fixture
    authority = {'operation_id': '3fbb2baa-3a76-4f03-ae92-8ed9513fe268', 'intent_sha256': 'a' * 64}
    context = {**context, 'revocation': authority}
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    publish_candidate(tx, context)
    calls = []
    def finish(argv, *, data):
        calls.append((argv, json.loads(data)))
        if len(calls) == 1:
            raise tx.TransactionError('runtime-command')
        return ''
    tx.command = finish
    with pytest.raises(tx.TransactionError, match='runtime-command'):
        tx.site_transaction('commit', context, finish_egress=True)
    before = (state / 'site.json').read_bytes()
    for value in (None, {**authority, 'intent_sha256': 'b' * 64}):
        with pytest.raises(tx.TransactionError, match='revocation-resume-required'):
            tx.site_transaction('recover-commit', {**context, 'revocation': value})
        assert (state / 'site.json').read_bytes() == before
    assert len(calls) == 1
    assert tx.site_transaction('recover-commit', context)['status'] == 'committed'
    assert all(argv[-2:] == ['finish', '--revocation-stdin'] and value == authority for argv, value in calls)
    assert not (state / 'site.json').exists()


def test_commit_decision_freezes_exact_ingress_authority(fixture):
    tx, context, _ = fixture
    state = install_accepted(tx, context)
    tx.site_transaction('begin', context)
    candidate = publish_candidate(tx, context)
    def refused(argv):
        raise tx.TransactionError('runtime-command')
    tx.command = refused
    with pytest.raises(tx.TransactionError):
        tx.site_transaction('commit', context, finish_egress=True)
    candidate.write_bytes(b'accepted')  # Previously allowed bytes are no longer accepted after the decision.
    tx.command = lambda argv: pytest.fail('egress must not finish after ingress drift')
    with pytest.raises(tx.TransactionError, match='foreign-publication'):
        tx.site_transaction('recover-commit', context)
    assert (state / 'site.json').exists()


@pytest.mark.parametrize('previous_exists,current_exists', [(False, False), (False, True), (True, True)])
def test_pre_consumer_failure_restores_missing_or_newly_installed_unit(fixture, monkeypatch, previous_exists, current_exists):
    tx, context, commands = fixture
    state = {'active': False, 'exists': previous_exists,
             'unit_file_state': 'disabled' if previous_exists else 'not-found'}
    monkeypatch.setattr(tx, 'service_state', lambda unit: dict(state))
    restored = []
    monkeypatch.setattr(tx, 'restore_enabled', lambda unit, prior: restored.append((unit, prior)))
    def command(argv):
        commands.append(argv)
        if argv == ['systemctl', 'stop', 'nginx.service'] and not state['exists']:
            raise tx.TransactionError('runtime-command')
        return ''
    monkeypatch.setattr(tx, 'command', command)
    tx.site_transaction('begin', context)
    state.update(exists=current_exists, unit_file_state='disabled' if current_exists else 'not-found')
    if current_exists:
        candidate = publish_candidate(tx, context)
        assert candidate.exists()
    result = tx.site_transaction('restore', context)
    assert result['changed'] is current_exists
    assert (['systemctl', 'stop', 'nginx.service'] in commands) is current_exists
    assert (['systemctl', 'disable', 'nginx.service'] in commands) is (current_exists and not previous_exists)
    assert bool(restored) is previous_exists
    assert not (tx.STATE_ROOT / 'nginx.service/site.json').exists()
    for owner in context['owners']:
        assert not Path(owner['paths'][0]).exists()
