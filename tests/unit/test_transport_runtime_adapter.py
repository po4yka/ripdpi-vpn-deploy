"""The actual consumer adapter preserves enable/active state and rejects missing authentication."""
import base64
from contextlib import contextmanager, nullcontext
import errno
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / 'ansible/roles/runtime-release/files'
sys.path.insert(0, str(LIBRARY))
import transport_runtime_transaction as core
spec = importlib.util.spec_from_file_location('runtime_acceptance_adapter_test', LIBRARY / 'transport_runtime_accept.py')
accept = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accept)


@pytest.fixture
def tmp_path(private_authority_path):
    return private_authority_path


def state(active='inactive', enabled='disabled', loaded='loaded'):
    return {'LoadState': loaded, 'ActiveState': active, 'UnitFileState': enabled,
            'MainPID': '10' if active == 'active' else '0'}


@pytest.mark.parametrize('controller_active', [True, False])
def test_restore_preserves_disabled_controller_and_exact_frontend_activity(monkeypatch, controller_active):
    wanted = {accept.CONTROLLER: state('active' if controller_active else 'inactive'),
              accept.UNITS[0]: state('active', 'enabled'), accept.UNITS[1]: state()}
    actual = {unit: state(enabled='enabled') for unit in wanted}
    calls = []
    def run(argv, _timeout):
        calls.append(argv)
        if argv[1] != 'daemon-reload':
            action, unit = argv[1:]
            if action in {'enable', 'disable'}:
                actual[unit]['UnitFileState'] = action + 'd'
            elif action in {'start', 'stop'}:
                actual[unit]['ActiveState'] = 'active' if action == 'start' else 'inactive'
        return b''
    monkeypatch.setattr(accept, 'run', run)
    monkeypatch.setattr(accept, 'fields', lambda unit, **_options: actual[unit])
    adapter = accept.Adapter([], 'http://owned.example/', 204, 10, {'xray':'probe', 'hysteria':'probe'})
    def generation_ready(_deadline):
        for unit in accept.UNITS:
            actual[unit]['ActiveState'] = wanted[unit]['ActiveState']
    monkeypatch.setattr(adapter, 'generation_ready', generation_ready)
    adapter.restore(wanted)
    if controller_active:
        assert not any(argv[1] in {'start', 'stop'} and argv[2] in accept.UNITS for argv in calls)
    assert actual[accept.CONTROLLER]['UnitFileState'] == 'disabled'
    assert actual[accept.CONTROLLER]['ActiveState'] == wanted[accept.CONTROLLER]['ActiveState']
    assert actual[accept.UNITS[0]]['ActiveState'] == 'active'
    assert actual[accept.UNITS[1]]['ActiveState'] == 'inactive'
    assert ['/usr/bin/systemctl', 'disable', accept.CONTROLLER] in calls


def test_xray_missing_probe_credentials_refuse_before_native_execution(monkeypatch):
    document = {'inbounds': [{'protocol':'vless', 'port':10085, 'tag':'vless-xhttp',
                 'settings':{'clients':[{'email':'recipient-xhttp','id':'synthetic'}]},
                 'streamSettings':{'network':'xhttp','xhttpSettings':{'path':'/owned'}}}]}
    candidates = [{'path':'/etc/systemd/system/xray.service', 'data':base64.b64encode(
        b'Environment=XRAY_LOCATION_ASSET=/owned/assets\nExecStart=/owned/xray run -config /etc/xray/config.json').decode()},
        {'path':'/etc/xray/config.json', 'data':base64.b64encode(json.dumps(document).encode()).decode()}]
    monkeypatch.setattr(accept, 'run', lambda *_args, **_kwargs: pytest.fail('native command before credential admission'))
    adapter = accept.Adapter(candidates, 'http://owned.example/', 204, 10, {'xray':'probe', 'hysteria':'probe'})
    with pytest.raises(RuntimeError, match='frontend-credentials-empty'):
        adapter.validate()


@pytest.mark.parametrize('directory', ['/etc/hysteria', '/etc/hysteria/profile'])
@pytest.mark.parametrize('credential', ['selected', 'missing', 'duplicate', 'relative', 'unselected'])
def test_ech_admission_uses_exact_staged_unit_credential(monkeypatch, directory, credential):
    import transport_runtime_validate as native
    import yaml
    config = directory + '/config.yaml'
    key = directory + '/ech.key'
    source = {'selected': key, 'missing': None, 'duplicate': key,
              'relative': 'ech.key', 'unselected': '/etc/foreign/ech.key'}[credential]
    unit = 'ExecStart=/owned/hysteria server -c ' + config + '\n'
    if source is not None:
        unit += 'LoadCredential=hysteria-ech:' + source + '\n'
        if credential == 'duplicate':
            unit += 'LoadCredential=hysteria-ech:' + source + '\n'
    document = {'tls': {'cert': directory + '/cert.pem', 'key': directory + '/tls.key'},
                'ech': {'keyPath': '/run/credentials/hysteria-server.service/hysteria-ech'}}
    contents = {'/etc/systemd/system/hysteria-server.service': unit.encode(),
                config: yaml.safe_dump(document).encode(), key: b'selected-private-authority',
                directory + '/cert.pem': b'certificate', directory + '/tls.key': b'tls-key'}
    candidates = [{'path': path, 'data': base64.b64encode(raw).decode()} for path, raw in contents.items()]
    observed = []
    monkeypatch.setattr(native, 'validate_hysteria', lambda *args, **kwargs: observed.append((args, kwargs)))
    adapter = accept.Adapter(candidates, 'http://owned.example/', 204, 10, {'xray': 'probe', 'hysteria': 'probe'})
    if credential == 'selected':
        adapter.validate()
        assert len(observed) == 1
        assert observed[0][0][4] == unit
        assert observed[0][1]['ech_key'] == contents[key]
    else:
        reason = 'candidate-incomplete' if credential == 'unselected' else 'unit-credential-invalid'
        with pytest.raises(accept.Refusal, match=reason):
            adapter.validate()
        assert not observed


def test_full_retirement_cannot_report_readiness_with_running_process(monkeypatch):
    adapter = accept.Adapter([], 'http://owned.example/', 204, 10, {'xray':'probe', 'hysteria':'probe'})
    monkeypatch.setattr(adapter, 'frontends', lambda: [])
    monkeypatch.setattr(accept, 'fields', lambda _unit, **_options: state('active'))
    with pytest.raises(accept.Refusal, match='retirement-unconfirmed'):
        adapter.ready()


def test_failed_restore_is_not_reported_complete(monkeypatch):
    wanted = {unit:state() for unit in (accept.CONTROLLER,*accept.UNITS)}
    monkeypatch.setattr(accept, 'run', lambda *_args: b'')
    monkeypatch.setattr(accept, 'fields', lambda _unit, **_options: state(enabled='enabled'))
    adapter = accept.Adapter([], 'http://owned.example/', 204, 10, {'xray':'probe', 'hysteria':'probe'})
    with pytest.raises(accept.Refusal, match='unit-restoration-unconfirmed'):
        adapter.restore(wanted)


def parameters(name, *, timeout=10, expected=204):
    return {'probe_url': 'https://' + name + '.example/canary', 'expected_status': expected,
            'timeout': timeout, 'clients': {'xray': name, 'hysteria': name + '-h'}, 'asset_dir': None}


@pytest.fixture
def parameter_area(tmp_path, monkeypatch):
    import os
    root = tmp_path.resolve()
    root.chmod(0o755)
    state_root = root / 'state'
    actual = state_root / 'parameters.json'
    monkeypatch.setattr(accept, 'STATE', state_root)
    monkeypatch.setattr(accept, 'PARAMETERS', actual)
    return root, state_root, actual, os.getuid(), os.getgid()


def test_actual_parameters_precede_bootstrap_intent_and_missing_authority_refuses(parameter_area):
    _root, state_root, actual, uid, _gid = parameter_area
    initial, desired = parameters('context-a'), parameters('context-b')
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('parameters.json', initial)
    assert accept.read_parameters(uid=uid) == initial
    actual.write_text(json.dumps(desired))
    actual.chmod(0o600)
    assert accept.read_parameters(uid=uid) == desired
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('accepted.json', {'schema': 1, 'nodes': {str(actual): core.node(actual, uid)},
                                   'previous': None, 'units': {}})
    actual.unlink()
    with pytest.raises(accept.Refusal, match='accepted-parameters-absent'):
        accept.read_parameters(uid=uid)
    assert not actual.exists()


def test_unsafe_published_parameters_never_fall_back_to_bootstrap(parameter_area):
    _root, state_root, actual, uid, _gid = parameter_area
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('parameters.json', parameters('context-a'))
    actual.write_text(json.dumps(parameters('context-b')))
    actual.chmod(0o644)
    with pytest.raises(accept.Refusal, match='unsafe-record'):
        accept.read_parameters(uid=uid)


def parameter_adapter(parameter_area, monkeypatch, desired, captured, *, reject=None):
    import copy
    root, _state_root, _actual, uid, _gid = parameter_area
    units_directory = root / 'units'
    units_directory.mkdir(exist_ok=True)
    (units_directory / accept.UNITS[0]).write_text(
        'Environment=XRAY_LOCATION_ASSET=/owned/assets\nExecStart=/owned/xray run -config /owned/config.json\n')
    original_path = Path
    monkeypatch.setattr(accept, 'Path', lambda raw: units_directory if str(raw) == '/etc/systemd/system' else original_path(raw))
    read_parameters = accept.read_parameters
    monkeypatch.setattr(accept, 'read_parameters', lambda **_kwargs: read_parameters(uid=uid))
    actual = {accept.CONTROLLER: state(), accept.UNITS[0]: state(),
              accept.UNITS[1]: state(enabled='', loaded='not-found')}
    monkeypatch.setattr(accept, 'fields', lambda unit, **_options: actual[unit])
    monkeypatch.setattr(accept, 'run', lambda *_args, **_kwargs: b'')
    monkeypatch.setattr(accept.os.path, 'samefile', lambda *_args: True)
    def probe(_binary, _config, **opts):
        captured.append({key: opts[key] for key in ('url', 'expected', 'client_name')})
        if opts['client_name'] == reject:
            raise RuntimeError('candidate-probe-refused')
    monkeypatch.setattr(accept, 'probe', probe)
    def stop():
        for unit in (accept.CONTROLLER, accept.UNITS[0]):
            actual[unit] = state()
    def start():
        for unit in (accept.CONTROLLER, accept.UNITS[0]):
            actual[unit] = state('active', 'enabled')
    def restore(units):
        if units is None:
            stop()
        else:
            actual.update(copy.deepcopy(units))
    adapter = accept.Adapter([], desired['probe_url'], desired['expected_status'], desired['timeout'], desired['clients'])
    monkeypatch.setattr(adapter, 'stop', stop)
    monkeypatch.setattr(adapter, 'start', start)
    monkeypatch.setattr(adapter, 'restore', restore)
    return adapter


def parameter_plan(value, gid):
    candidate = accept.parameter_candidate(value)
    candidate['gid'] = gid
    return [candidate]


def test_context_b_publication_and_compensation_probe_restored_context_a(parameter_area, monkeypatch):
    _root, state_root, actual, uid, gid = parameter_area
    initial, desired = parameters('context-a'), parameters('context-b', timeout=12, expected=202)
    captured = []
    owner = parameter_adapter(parameter_area, monkeypatch, desired, captured)
    with core.Transaction(state_root, uid=uid) as tx:
        tx.apply(parameter_plan(initial, gid), owner)
    original_receipt = (state_root / 'accepted.json').read_bytes()
    original_inode = actual.stat().st_ino
    with core.Transaction(state_root, uid=uid) as tx:
        assert tx.apply(parameter_plan(desired, gid), owner)['published']
    with core.Transaction(state_root, uid=uid) as tx:
        tx.compensate_latest(owner)
    assert captured == [
        {'url': initial['probe_url'], 'expected': 204, 'client_name': 'context-a'},
        {'url': desired['probe_url'], 'expected': 202, 'client_name': 'context-b'},
        {'url': initial['probe_url'], 'expected': 204, 'client_name': 'context-a'}]
    assert actual.stat().st_ino == original_inode
    assert json.loads(actual.read_bytes()) == initial
    assert (state_root / 'accepted.json').read_bytes() == original_receipt
    # Candidate validation retains the requested B options; live readiness reads
    # the restored publication independently rather than mutating those options.
    assert owner.url == desired['probe_url'] and owner.clients == desired['clients']


def test_failed_context_b_probe_recovers_with_context_a_not_candidate_options(parameter_area, monkeypatch):
    _root, state_root, actual, uid, gid = parameter_area
    initial, desired = parameters('context-a'), parameters('context-b', expected=202)
    captured = []
    owner = parameter_adapter(parameter_area, monkeypatch, desired, captured, reject='context-b')
    with core.Transaction(state_root, uid=uid) as tx:
        tx.apply(parameter_plan(initial, gid), owner)
    before = (state_root / 'accepted.json').read_bytes()
    inode = actual.stat().st_ino
    with core.Transaction(state_root, uid=uid) as tx:
        with pytest.raises(accept.Refusal, match='candidate-refused'):
            tx.apply(parameter_plan(desired, gid), owner)
    assert [value['client_name'] for value in captured] == ['context-a', 'context-b', 'context-a']
    assert actual.stat().st_ino == inode
    assert json.loads(actual.read_bytes()) == initial
    assert (state_root / 'accepted.json').read_bytes() == before
    assert not (state_root / 'pending.json').exists()


def test_linked_parameter_backup_requires_exact_durable_claim(parameter_area, monkeypatch):
    import os
    _root, state_root, actual, uid, gid = parameter_area
    initial, desired = parameters('context-a'), parameters('context-b')
    captured = []
    owner = parameter_adapter(parameter_area, monkeypatch, desired, captured)
    with core.Transaction(state_root, uid=uid) as tx:
        tx.apply(parameter_plan(initial, gid), owner)
    def interrupted(stage):
        if stage == 'materialized-0':
            raise SystemExit(99)
    with core.Transaction(state_root, uid=uid) as tx:
        with pytest.raises(SystemExit):
            tx.apply(parameter_plan(desired, gid), owner, checkpoint=interrupted)
    assert actual.stat().st_nlink == 2
    assert accept.read_parameters() == initial
    with core.Transaction(state_root, uid=uid) as tx:
        assert tx.recover(owner)
    foreign = state_root / 'foreign-backup'
    os.link(actual, foreign)
    with pytest.raises(accept.Refusal, match='unclaimed-parameters-link'):
        accept.read_parameters()
    assert foreign.exists() and actual.stat().st_nlink == 2


def test_only_reserved_parameters_are_selectable_inside_state(parameter_area):
    _root, state_root, _actual, uid, gid = parameter_area
    with core.Transaction(state_root, uid=uid) as tx:
        tx.validate(parameter_plan(parameters('context-a'), gid))
        for name in ('accepted.json', 'pending.json', 'last.json', 'outer.json', 'arbitrary.json'):
            candidate = parameter_plan(parameters('context-a'), gid)[0]
            candidate['path'] = str(state_root / name)
            with pytest.raises(accept.Refusal, match='candidate-invalid'):
                tx.validate([candidate])


def outer_module(parameter_area, monkeypatch):
    _root, state_root, _actual, uid, _gid = parameter_area
    spec = importlib.util.spec_from_file_location('runtime_outer_adapter_test', LIBRARY / 'transport_runtime_outer.py')
    outer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(outer)
    monkeypatch.setattr(outer, 'STATE', state_root)
    monkeypatch.setattr(outer.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(outer, 'Transaction', lambda path, **kwargs: core.Transaction(path, uid=uid, **kwargs))
    monkeypatch.setattr(outer, 'read_private', lambda path, _uid: core.read_private(path, uid))
    owner = accept.Adapter([], 'http://owned.example/', 204, 10, {'xray': 'probe', 'hysteria': 'probe'})
    monkeypatch.setattr(outer, 'adapter', lambda: owner)
    return outer


def receipt(units=None, nodes=None):
    return {'schema': 1, 'nodes': {} if nodes is None else nodes, 'previous': None,
            'units': units or {unit: state() for unit in (accept.CONTROLLER, *accept.UNITS)}}


@pytest.mark.parametrize('baseline', ["foreign", {'schema': 1},
    receipt(units={unit: {**state(), 'MainPID': 0} for unit in (accept.CONTROLLER, *accept.UNITS)}),
    receipt(nodes={'relative-authority': None})])
def test_outer_finish_preserves_malformed_embedded_receipt(parameter_area, monkeypatch, baseline):
    _root, state_root, _actual, uid, _gid = parameter_area
    outer = outer_module(parameter_area, monkeypatch)
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('accepted.json', receipt())
        tx.record('outer.json', {'schema': 1, 'receipt': baseline, 'consumer_receipt': baseline})
    before = (state_root / 'outer.json').read_bytes()
    monkeypatch.setattr(sys, 'argv', ['outer', 'finish'])
    with pytest.raises(accept.Refusal):
        outer.main()
    assert (state_root / 'outer.json').read_bytes() == before


def test_outer_finish_preserves_typed_unknown_baseline_without_known_transition(parameter_area, monkeypatch):
    _root, state_root, _actual, uid, _gid = parameter_area
    outer = outer_module(parameter_area, monkeypatch)
    baseline = receipt()
    baseline['units'][accept.CONTROLLER] = state('active', 'enabled')
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('accepted.json', receipt())
        tx.record('outer.json', {'schema': 1, 'receipt': baseline, 'consumer_receipt': baseline})
    before = (state_root / 'outer.json').read_bytes()
    monkeypatch.setattr(sys, 'argv', ['outer', 'finish'])
    with pytest.raises(accept.Refusal, match='outer-authority-unconfirmed'):
        outer.main()
    assert (state_root / 'outer.json').read_bytes() == before


def test_outer_finish_accepts_only_exact_current_or_typed_known_transition(parameter_area, monkeypatch):
    root, state_root, _actual, uid, _gid = parameter_area
    outer = outer_module(parameter_area, monkeypatch)
    baseline = receipt()
    absent = str(root / 'retired-owned-node')
    current = receipt(nodes={absent: None})
    transition = {'schema': 1, 'before_receipt': baseline, 'after_receipt': current,
                  'before_backups': None,
                  'units': baseline['units'],
                  'entries': [{'path': absent, 'before': None, 'after': None, 'deferred': False, 'storage': None}]}
    monkeypatch.setattr(sys, 'argv', ['outer', 'finish'])
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('accepted.json', baseline)
        tx.record('outer.json', {'schema': 1, 'receipt': baseline, 'consumer_receipt': baseline})
    outer.main()
    assert not (state_root / 'outer.json').exists()
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('accepted.json', current)
        tx.record('outer.json', {'schema': 1, 'receipt': baseline, 'consumer_receipt': current})
        tx.storage(absent, create=True)
        transition['entries'][0]['storage'] = core.storage_claim(absent)
        tx.record('last.json', transition)
    outer.main()
    assert not (state_root / 'outer.json').exists()


@pytest.mark.parametrize('mutation', [
    lambda claim: claim['identity'].__setitem__(0, True),
    lambda claim: claim['identity'].__setitem__(1, -1),
    lambda claim: claim['identity'].__setitem__(3, 2**32),
    lambda claim: claim['identity'].__setitem__(4, '0600'),
    lambda claim: claim.__setitem__('sha256', 'unverified'),
])
def test_embedded_node_claims_have_bounded_scalar_types(parameter_area, mutation):
    root, state_root, _actual, uid, gid = parameter_area
    claim = {'identity': [1, 1, uid, gid, 0o600], 'sha256': 'a' * 64}
    mutation(claim)
    with pytest.raises(accept.Refusal, match='node-claim-invalid'):
        core.validate_receipt(receipt(nodes={str(root / 'owned'): claim}), root=state_root, uid=uid)


@pytest.fixture
def directory_descriptors(monkeypatch):
    acquired = []
    original = core.TrustedDirectory
    @contextmanager
    def observe(path, owner):
        with original(path, owner) as fd:
            acquired.append(fd)
            yield fd
    monkeypatch.setattr(core, 'TrustedDirectory', observe)
    return acquired


def assert_descriptors_closed(acquired):
    assert acquired
    for fd in acquired:
        with pytest.raises(OSError) as error:
            os.fstat(fd)
        assert error.value.errno == errno.EBADF


def test_failed_transaction_entry_closes_acquired_directory_descriptors(parameter_area, directory_descriptors):
    _root, state_root, _actual, uid, _gid = parameter_area
    state_root.mkdir(mode=0o755)
    state_root.chmod(0o755)
    with pytest.raises(accept.Refusal, match='unsafe-state-directory'):
        with core.Transaction(state_root, uid=uid):
            pytest.fail('unsafe entry was admitted')
    assert_descriptors_closed(directory_descriptors)


@pytest.mark.parametrize('check', [False, True])
@pytest.mark.parametrize('failure', [None, RuntimeError, KeyboardInterrupt])
def test_transaction_retains_descriptors_until_scope_exit(parameter_area, directory_descriptors, check, failure):
    root, state_root, _actual, uid, _gid = parameter_area
    with pytest.raises(failure) if failure else nullcontext():
        with core.Transaction(state_root, uid=uid, check=check) as tx:
            fd = tx.parent(root)
            assert tx.parent(root) == fd
            if check:
                tx.parent(root / 'missing')
                assert not state_root.exists()
            for retained in directory_descriptors:
                os.fstat(retained)
            if failure:
                raise failure('scope-exit')
    assert_descriptors_closed(directory_descriptors)


def test_failed_lock_acquisition_closes_all_directory_descriptors(parameter_area, directory_descriptors, monkeypatch):
    _root, state_root, _actual, uid, _gid = parameter_area
    def busy(_fd, _flags):
        raise BlockingIOError('publisher-busy')
    monkeypatch.setattr(core.fcntl, 'flock', busy)
    with pytest.raises(BlockingIOError, match='publisher-busy'):
        with core.Transaction(state_root, uid=uid):
            pytest.fail('busy publisher lock was acquired')
    assert_descriptors_closed(directory_descriptors)


@pytest.mark.parametrize('operation', ['refresh', 'rollback'])
def test_external_acceptance_operation_preserves_open_outer_owner(parameter_area, monkeypatch, operation):
    import io
    import transport_runtime_validate as validation
    _root, state_root, _actual, uid, _gid = parameter_area
    current = parameters('context-a')
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('parameters.json', current)
        tx.record('outer.json', {'schema': 1, 'receipt': None, 'consumer_receipt': None})
    before = {p.name: p.read_bytes() for p in state_root.glob('*.json')}
    if operation == 'refresh':
        module = accept
        monkeypatch.setattr(sys, 'argv', ['accept', '--refresh-assets'])
        request = {'install_dir':str(_root/'assets'), 'candidate_dir':str(_root/'candidate'),
                   'desired':{'geoip.dat':'a'*64, 'geosite.dat':'b'*64}}
        monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(json.dumps(request).encode())))
    else:
        spec = importlib.util.spec_from_file_location('runtime_rollback_owner_test', LIBRARY/'transport_runtime_rollback.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, 'STATE', state_root)
        monkeypatch.setattr(sys, 'argv', ['rollback', 'config'])
        monkeypatch.setattr(module, 'read_parameters', lambda: current)
    monkeypatch.setattr(module.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(module, 'Transaction', lambda path, **kwargs: core.Transaction(path, uid=uid, **kwargs))
    monkeypatch.setattr(accept, 'read_parameters', lambda: current)
    monkeypatch.setattr(validation, 'recover_validation', lambda _tx: pytest.fail('lease recovery crossed open outer owner'))
    with pytest.raises(core.Refusal, match='outer-transaction-active'):
        module.main()
    assert {p.name:p.read_bytes() for p in state_root.glob('*.json')} == before


@pytest.mark.parametrize('phase', ['activating', 'deactivating', 'auto-restart'])
def test_transient_owned_candidate_can_be_quiesced_but_never_journaled_as_accepted(monkeypatch, phase):
    raw = ('LoadState=loaded\nActiveState=' + phase + '\nUnitFileState=enabled\nMainPID=42\n').encode()
    monkeypatch.setattr(accept, 'run', lambda *_args, **_kwargs: raw)
    assert accept.fields(accept.UNITS[0], quiescing=True)['ActiveState'] == phase
    with pytest.raises(accept.Refusal, match='unit-state-loaded-' + phase):
        accept.fields(accept.UNITS[0])


@pytest.mark.parametrize('refused', [False, True])
def test_outer_recovery_without_inner_journal_still_requires_restored_native_boundary(parameter_area, monkeypatch, refused):
    _root, state_root, _actual, uid, _gid = parameter_area
    outer = outer_module(parameter_area, monkeypatch)
    baseline = receipt()
    with core.Transaction(state_root, uid=uid) as tx:
        tx.record('accepted.json', baseline)
        tx.record('outer.json', {'schema':1,'receipt':baseline,'consumer_receipt':None})
    calls = []
    owner = outer.adapter()
    monkeypatch.setattr(owner, 'restore', lambda units: calls.append(('restore',units)))
    def ready():
        calls.append(('ready',None))
        if refused: raise RuntimeError('model-native-readiness-refused')
    monkeypatch.setattr(owner, 'ready', ready)
    monkeypatch.setattr(outer, 'read_parameters', lambda: parameters('context-a'))
    monkeypatch.setattr(sys, 'argv', ['outer','recover'])
    if refused:
        with pytest.raises(RuntimeError, match='model-native-readiness-refused'): outer.main()
        assert (state_root/'outer.json').exists()
    else:
        outer.main()
        assert not (state_root/'outer.json').exists()
    assert calls == [('restore',baseline['units']),('ready',None)]
    assert json.loads((state_root/'accepted.json').read_bytes()) == baseline


@pytest.mark.parametrize('raw,expected', [
    ('v26.3.27', ('v26.3.27-archive', 'v26.3.27')),
    ('v26.3.27-archive', ('v26.3.27-archive', 'v26.3.27')),
    ('v26.3.27-source-' + 'a' * 40, ('v26.3.27-source-' + 'a' * 40, 'v26.3.27')),
])
def test_operator_rollback_selects_exact_mode_bound_identity(raw, expected):
    from transport_runtime_rollback import release_versions
    assert release_versions(raw) == expected


@pytest.mark.parametrize('raw', [None, '../v26.3.27', 'v26.3.27-source-short', 'v26.3.27-other'])
def test_operator_rollback_rejects_ambiguous_identity(raw):
    from transport_runtime_rollback import release_versions
    with pytest.raises(accept.Refusal, match='rollback-version-invalid'):
        release_versions(raw)


def make_directories(path):
    # mkdir honours the umask, and the ownership contract refuses group-writable ancestry.
    created = [directory for directory in (path, *path.parents) if not directory.exists()]
    path.mkdir(parents=True)
    for directory in created:
        directory.chmod(0o755)


def retained_release(base, version, name, mode, data):
    import hashlib
    release = base / 'releases' / version
    make_directories(release)
    artifact = release / name
    artifact.write_bytes(data)
    artifact.chmod(mode)
    digest = hashlib.sha256(data).hexdigest()
    byte_receipt = release / '.runtime-release.json'
    byte_receipt.write_text(json.dumps({'schema_version':1,'version':version,
        'arch_key':'arm64','arch_slug':'arm64-v8a','binary_name':name,
        'artifact_sha256':digest,'binary_sha256':digest}))
    byte_receipt.chmod(0o644)
    return release


def test_operator_release_digest_is_verified_before_selection(parameter_area):
    from transport_runtime_rollback import verified_release
    root, state, _actual, uid, _gid = parameter_area
    version = 'v26.3.27-source-' + 'a' * 40
    release = retained_release(root, version, 'xray', 0o755, b'exact-private-byte-ownership-contract')
    binary = release / 'xray'
    with core.Transaction(state, uid=uid) as tx:
        assert verified_release(tx, root, version, 'xray', 0o755) == release
        binary.write_bytes(b'changed-binary')
        with pytest.raises(core.Refusal, match='rollback-release-changed'):
            verified_release(tx, root, version, 'xray', 0o755)


SELECTED_RELEASE, RETAINED_RELEASE = 'v26.5.3-archive', 'v26.3.27-archive'


def unit_text(release, assets, config):
    return ('[Service]\nEnvironment=XRAY_LOCATION_ASSET=' + str(assets) + '\nEnvironment=XRAY_RUNTIME_BINARY='
            + str(release / 'xray') + '\nExecStart=' + str(release / 'xray') + ' run -config ' + str(config) + '\n')


def runtime_tree(root, *, bundled=True):
    """An /opt/xray analogue with the newer release selected and the older one retained."""
    selected = retained_release(root, SELECTED_RELEASE, 'xray', 0o755, b'selected-xray')
    retained = retained_release(root, RETAINED_RELEASE, 'xray', 0o755, b'retained-xray')
    (root / 'current').symlink_to(selected)
    assets = root / 'assets/geoip'
    selected_assets = retained_release(assets, 'v26.5.3', 'geoip.dat', 0o644, b'selected-geoip')
    retained_release(assets, 'v26.3.27', 'geoip.dat', 0o644, b'retained-geoip')
    (assets / 'current').symlink_to(selected_assets)
    config = root / 'etc/config.json'
    make_directories(config.parent)
    config.write_bytes(b'{"log": {}}')
    unit = root / 'units/xray.service'
    make_directories(unit.parent)
    unit.write_text(unit_text(selected, selected_assets if bundled else root / 'unmanaged-assets', config))
    return unit, config, selected, retained, assets


def tree_snapshot(root):
    # The accepted receipt claims nodes by inode, so a same-bytes replacement is a change too.
    def entry(path):
        status = path.lstat()
        content = path.readlink() if path.is_symlink() else path.read_bytes() if path.is_file() else None
        return (status.st_ino, status.st_mode, status.st_uid, status.st_gid, status.st_nlink, content)
    return {path: entry(path) for path in root.rglob('*')}


@pytest.mark.parametrize('bundled', [True, False])
def test_operator_runtime_rollback_retargets_unit_text_and_exact_link_set(parameter_area, bundled):
    import base64
    from transport_runtime_rollback import runtime_candidates
    root, state, _actual, uid, gid = parameter_area
    unit, config, selected, retained, assets = runtime_tree(root, bundled=bundled)
    with core.Transaction(state, uid=uid) as tx:
        before = tree_snapshot(root)
        plan = runtime_candidates(tx, 'v26.3.27', unit, config, gid, gateway_paths=[], root=root)
        # Planning publishes nothing: the candidates are only a plan until the transaction applies them.
        assert tree_snapshot(root) == before
    files = [item for item in plan if 'data' in item]
    assert [(item['path'], item['gid'], item['mode']) for item in files] == [
        (str(unit), 0, 0o644), (str(config), gid, 0o640)]
    rolled_back_assets = assets / 'releases/v26.3.27' if bundled else root / 'unmanaged-assets'
    # Both the environment and ExecStart name the retained release; the selected one is gone.
    assert base64.b64decode(files[0]['data']).decode() == unit_text(retained, rolled_back_assets, config)
    assert str(selected) not in base64.b64decode(files[0]['data']).decode()
    assert base64.b64decode(files[1]['data']) == b'{"log": {}}'
    links = [{'path': str(root / 'current'), 'target': str(retained)},
             {'path': str(root / 'previous'), 'target': str(selected)},
             {'path': '/usr/local/bin/xray', 'target': str(root / 'current/xray')}]
    if bundled:
        links = [{'path': str(assets / 'current'), 'target': str(assets / 'releases/v26.3.27')},
                 {'path': str(assets / 'previous'), 'target': str(assets / 'releases/v26.5.3')},
                 {'path': str(root / 'bundled-assets/geoip.dat'), 'target': str(assets / 'current/geoip.dat')}] + links
    assert [item for item in plan if 'target' in item] == links
    assert len({item['path'] for item in plan}) == len(plan)


def test_operator_runtime_rollback_refuses_the_selected_release(parameter_area):
    from transport_runtime_rollback import runtime_candidates
    root, state, _actual, uid, gid = parameter_area
    unit, config, _selected, _retained, _assets = runtime_tree(root)
    with core.Transaction(state, uid=uid) as tx:
        with pytest.raises(core.Refusal, match='rollback-no-change'):
            runtime_candidates(tx, 'v26.5.3', unit, config, gid, gateway_paths=[], root=root)


@pytest.mark.parametrize('damage,category', [
    ('xray-binary', 'rollback-release-changed'),
    ('geoip-binary', 'rollback-release-changed'),
    ('xray-receipt', 'rollback-release-unowned'),
])
def test_operator_runtime_rollback_plans_nothing_from_an_unverified_release(parameter_area, damage, category):
    from transport_runtime_rollback import runtime_candidates
    root, state, _actual, uid, gid = parameter_area
    unit, config, _selected, retained, assets = runtime_tree(root)
    if damage == 'xray-binary':
        (retained / 'xray').write_bytes(b'tampered-xray')
    elif damage == 'geoip-binary':
        (assets / 'releases/v26.3.27/geoip.dat').write_bytes(b'tampered-geoip')
    else:
        (retained / '.runtime-release.json').unlink()
    with core.Transaction(state, uid=uid) as tx:
        before = tree_snapshot(root)
        with pytest.raises(core.Refusal, match=category):
            runtime_candidates(tx, 'v26.3.27', unit, config, gid, gateway_paths=[], root=root)
        # Refusal publishes nothing: the runtime tree and the transaction state are untouched.
        assert tree_snapshot(root) == before


@pytest.mark.parametrize('count', [1, 2])
def test_operator_runtime_rollback_plans_every_generation_gateway(parameter_area, count):
    from transport_runtime_rollback import runtime_candidates
    root, state, _actual, uid, gid = parameter_area
    unit, config, selected, retained, _assets = runtime_tree(root)
    gateways = [unit.parent / name for name in
                ['ripdpi-transport-direct.service', 'ripdpi-transport-warp.service'][:count]]
    for gateway in gateways:
        gateway.write_text('[Service]\nExecStart=' + str(selected / 'xray') + ' run -config %d/config.json\n')
    with core.Transaction(state, uid=uid) as tx:
        before = tree_snapshot(root)
        plan = runtime_candidates(tx, 'v26.3.27', unit, config, gid, gateway_paths=gateways, root=root)
        assert tree_snapshot(root) == before
    assert [item['path'] for item in plan if item['path'].endswith('.service')] == [str(unit), *map(str, gateways)]
    for item in plan[1:1 + count]:
        assert base64.b64decode(item['data']).decode() == ('[Service]\nExecStart=' + str(retained / 'xray')
                                                        + ' run -config %d/config.json\n')


def test_gateway_runtime_disagreement_refuses_before_publication(parameter_area):
    from transport_runtime_rollback import runtime_candidates
    root, state, _actual, uid, gid = parameter_area
    unit, config, _selected, retained, _assets = runtime_tree(root)
    gateway = unit.parent / 'ripdpi-transport-direct.service'
    gateway.write_text('ExecStart=' + str(retained / 'xray') + ' run -config %d/config.json\n')
    with core.Transaction(state, uid=uid) as tx:
        before = tree_snapshot(root)
        with pytest.raises(core.Refusal, match='rollback-gateway-runtime-mismatch'):
            runtime_candidates(tx, 'v26.3.27', unit, config, gid, gateway_paths=[gateway], root=root)
        assert tree_snapshot(root) == before


@pytest.mark.parametrize('bad', ['none', 'inactive', 'wrong-executable'])
def test_rollback_requires_each_gateway_loaded_executable(tmp_path, monkeypatch, bad):
    import transport_runtime_rollback as rollback
    monkeypatch.setattr(rollback, 'UNIT_ROOT', tmp_path)
    monkeypatch.setattr(rollback.Adapter, 'ready', lambda self: None)
    units = ['ripdpi-transport-direct.service', 'ripdpi-transport-warp.service']
    monkeypatch.setattr(rollback, 'gateway_units', lambda: units)
    for unit in units:
        (tmp_path / unit).write_text('ExecStart=/owned/xray run -config %d/config.json\n')
    monkeypatch.setattr(rollback, 'fields', lambda unit: state('inactive' if bad == 'inactive' and unit == units[1] else 'active'))
    proofs = []
    def samefile(proc, binary):
        proofs.append((proc, binary))
        return not (bad == 'wrong-executable' and len(proofs) == 2)
    monkeypatch.setattr(rollback.os.path, 'samefile', samefile)
    adapter = rollback.RollbackAdapter([], 'https://owned.example/', 204, 10, {'xray':'probe', 'hysteria':'probe'})
    if bad == 'none':
        adapter.ready()
        assert proofs == [('/proc/10/exe', '/owned/xray')] * 2
    else:
        with pytest.raises(core.Refusal, match='gateway-runtime-mismatch'):
            adapter.ready()


@pytest.mark.parametrize('source', ['/etc/egress/direct.json', 'relative.json', '/etc/../secret', None])
def test_rollback_validates_gateway_with_target_binary(monkeypatch, source):
    import transport_runtime_rollback as rollback
    monkeypatch.setattr(rollback.Adapter, 'validate', lambda self: None)
    monkeypatch.setattr(rollback, 'gateway_units', lambda: ['ripdpi-transport-direct.service'])
    text = 'ExecStart=/retained/xray run -config %d/config.json\n'
    if source is not None:
        text += 'LoadCredential=config.json:' + source + '\n'
    candidates = [{'path': '/etc/systemd/system/ripdpi-transport-direct.service',
                   'data': base64.b64encode(text.encode()).decode()}]
    calls = []
    monkeypatch.setattr(rollback, 'run', lambda argv, timeout: calls.append(argv))
    adapter = rollback.RollbackAdapter(candidates, 'https://owned.example/', 204, 10, {'xray':'probe', 'hysteria':'probe'})
    if source == '/etc/egress/direct.json':
        adapter.validate()
        assert calls == [['/retained/xray', 'run', '-test', '-config', source]]
    else:
        with pytest.raises(core.Refusal, match='gateway-credential-invalid'):
            adapter.validate()
        assert calls == []


def test_absent_parent_retirement_is_verified_without_manufacturing_storage(parameter_area):
    root, state_root, _actual, uid, _gid = parameter_area
    path = root / 'missing-frontend' / 'config.yaml'
    plan = [{'path':str(path), 'absent':True}, {'path':str(root / 'existing-parent-unit'), 'absent':True}]
    with core.Transaction(state_root, uid=uid) as tx:
        assert accept.omit_absent_subtrees(plan, tx) == plan[1:]
    assert not path.parent.exists()
    assert not (root / '.ripdpi-transport-runtime').exists()


def test_retirement_never_omits_a_dangling_symlink_parent(parameter_area):
    root, state_root, _actual, uid, _gid = parameter_area
    parent = root / 'foreign-parent'
    parent.symlink_to(root / 'missing-target', target_is_directory=True)
    plan = [{'path':str(parent / 'config.yaml'),'absent':True}]
    with core.Transaction(state_root, uid=uid) as tx:
        assert accept.omit_absent_subtrees(plan, tx) == plan
        with pytest.raises(OSError):
            tx.validate(plan)
    assert parent.is_symlink()


@pytest.mark.parametrize('path,extra', [
    ('/missing-frontend/config.yaml', {'unexpected':True}),
    ('/missing-frontend/config.yaml', {'deferred':True}),
    ('/missing-frontend/../foreign/config.yaml', {}),
    ('/missing-frontend/.ripdpi-transport-runtime/private', {}),
])
def test_absent_subtree_cannot_hide_invalid_candidate_authority(parameter_area, path, extra):
    _root, state_root, _actual, uid, _gid = parameter_area
    with core.Transaction(state_root, uid=uid) as tx:
        with pytest.raises(core.Refusal):
            accept.omit_absent_subtrees([{'path':path,'absent':True,**extra}], tx)
