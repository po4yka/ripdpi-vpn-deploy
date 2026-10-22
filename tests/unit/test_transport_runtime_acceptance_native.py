"""Exact pinned upgrade acceptance through the real canonical Ansible consumers."""
import importlib.util
import base64
import json
import os
import sys
from pathlib import Path
import signal
import re
import socket
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_runtime_transaction_lab', ROOT / 'tests/integration/transport_runtime_acceptance/fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize('profile', ['xray', 'hysteria'])
def test_complete_native_upgrade_and_unchanged_retry_preserve_distinct_previous(profile):
    with fixture.Lab() as lab:
        if profile == 'hysteria':
            lab.enable_hysteria_hopping()
        # Successful byte acquisition must not admit an unready first install.
        if profile == 'xray':
            original = lab.context['xray']['target']
            lab.context['xray']['target'] = '192.0.2.90:8445'
        else:
            original = lab.context['hysteria']['key_pem']
            # A valid but unmatched key reaches native TLS admission after
            # checksum-verified acquisition, rather than failing PEM preflight.
            wrong_key = lab.private / 'unmatched-key.pem'
            fixture.command(['openssl', 'genpkey', '-algorithm', 'RSA',
                             '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(wrong_key)])
            wrong_key.chmod(0o600)
            lab.context['hysteria']['key_pem'] = wrong_key.read_text()
        assert lab.converge(profile, allow_failure=True) != 0
        initial_root = Path('/opt/xray' if profile == 'xray' else '/opt/hysteria')
        initial_version = 'v26.3.27-archive' if profile == 'xray' else 'v2.8.2'
        assert (initial_root / 'releases' / initial_version / profile).is_file()
        assert not os.path.lexists(initial_root / 'current')
        assert not Path('/var/lib/ripdpi/transport-runtime/accepted.json').exists()
        assert not os.path.lexists(Path('/etc/systemd/system/multi-user.target.wants') /
            ('xray.service' if profile == 'xray' else 'hysteria-server.service'))
        if profile == 'xray':
            lab.context['xray']['target'] = original
        else:
            lab.context['hysteria']['key_pem'] = original
        assert lab.converge(profile, site=True, interrupt_first_adoption=True) == -signal.SIGKILL
        assert lab.converge('none', site=True) == 0
        state = Path('/var/lib/ripdpi/transport-runtime')
        for name in ('pending.json', 'preparation.json', 'compensating.json', 'outer.json', 'validation.json'):
            assert not (state / name).exists()
        assert lab.converge(profile) == 0
        root = Path('/opt/xray' if profile == 'xray' else '/opt/hysteria')
        previous = os.readlink(root / 'current')
        if profile == 'hysteria':
            lab.assert_hysteria_hopping()
        # The accepted receipt exists and parses before the upgrade.
        json.loads(Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_text())
        lab.upgrade(profile)
        assert lab.converge(profile) == 0
        assert os.readlink(root / 'current') != previous
        assert os.readlink(root / 'previous') == previous
        if profile == 'hysteria':
            from transport_runtime_accept import fields
            observed = fields('hysteria-server.service')
            assert os.path.samefile('/proc/' + observed['MainPID'] + '/exe', str(root / 'current' / 'hysteria'))
            lab.assert_hysteria_hopping()
        receipt = Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes()
        assert not Path('/var/lib/ripdpi/transport-runtime/pending.json').exists()
        assert lab.converge(profile) == 0
        assert Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes() == receipt
        assert os.readlink(root / 'previous') == previous
        assert lab.converge(profile, check=True) == 0
        assert Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes() == receipt
        if profile == 'xray':
            pins = lab.geodata()
            assert lab.converge(profile) == 0
            accepted = json.loads(Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_text())
            for name, digest in pins.items():
                assert accepted['nodes'][str(lab.selected_assets / name)]['sha256'] == digest
            before_timer = Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes()
            result = subprocess.run(['systemctl', 'start', 'vpn-geodata-refresh.service'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            assert result.returncode == 0, 'protected-native-geodata-timer-refused'
            assert Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes() == before_timer
        exercise_native_refusals_and_process_death(lab, profile)
        if profile == 'hysteria':
            lab.assert_hysteria_hopping()
        if profile == 'xray':
            result = subprocess.run(['/usr/bin/python3', '-Es',
                '/usr/local/libexec/ripdpi-transport-egress/transport_runtime_rollback.py',
                'config'], capture_output=True, timeout=90)
            assert result.returncode == 0, 'native-config-rollback-refused'
            upgraded = os.readlink(root / 'current')
            exercise_gateway_rollback_compensation()
            result = subprocess.run(['/usr/bin/python3', '-Es',
                '/usr/local/libexec/ripdpi-transport-egress/transport_runtime_rollback.py',
                'runtime', '--version', 'v26.3.27'], capture_output=True, timeout=90)
            assert result.returncode == 0, 'native-runtime-rollback-refused'
            assert os.readlink(root / 'current') == previous
            from transport_runtime_accept import gateway_units
            published = json.loads((state / 'accepted.json').read_text())
            for name in gateway_units():
                assert published['nodes']['/etc/systemd/system/' + name] is not None
            assert_xray_generation(previous)
            # The next ordinary converge with the newer pin must still be accepted and move the
            # unit, the links and the running process forward again, keeping the rolled-back release as previous.
            assert lab.converge(profile) == 0
            assert os.readlink(root / 'current') == upgraded
            assert os.readlink(root / 'previous') == previous
            assert_xray_generation(upgraded)
        assert lab.converge(profile, retire=True) == 0
        retired_unit = '/etc/systemd/system/' + ('xray.service' if profile == 'xray' else 'hysteria-server.service')
        assert not os.path.lexists(retired_unit)
        retired = json.loads(Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_text())
        assert retired['nodes'][retired_unit] is None
        assert not Path('/var/lib/ripdpi/transport-runtime/outer.json').exists()
        assert lab.converge(profile) == 0
        assert Path(retired_unit).is_file()


def assert_xray_generation(release):
    from transport_runtime_accept import fields, gateway_units, unit_binary
    binary = str(Path(release) / 'xray')
    for name in ['xray.service', *gateway_units()]:
        text = Path('/etc/systemd/system', name).read_text()
        assert unit_binary(text)[0] == binary
        observed = fields(name)
        assert observed['ActiveState'] == 'active' and int(observed['MainPID']) > 0
        assert os.path.samefile('/proc/' + observed['MainPID'] + '/exe', binary), name
    assert 'Environment=XRAY_RUNTIME_BINARY=' + binary in Path('/etc/systemd/system/xray.service').read_text().splitlines()


def exercise_gateway_rollback_compensation():
    from transport_runtime_accept import STATE, gateway_units, read_parameters
    from transport_runtime_rollback import RollbackAdapter, runtime_candidates
    from transport_runtime_transaction import Transaction, Refusal
    parameters = read_parameters()
    paths = [Path('/etc/systemd/system', name) for name in ['xray.service', *gateway_units()]]
    original = {path: (path.read_bytes(), path.stat().st_ino) for path in paths}
    before = (STATE / 'accepted.json').read_bytes()
    release = os.readlink('/opt/xray/current')
    config = Path('/etc/xray/config.json')
    with Transaction(STATE) as tx:
        tx.accepted()
        candidate = runtime_candidates(tx, 'v26.3.27', paths[0], config, config.stat().st_gid,
                                       gateway_paths=paths[1:])
        # A real sandbox refusal in a gateway must compensate every runtime unit.
        gateway = next(item for item in candidate if item['path'] == str(paths[1]))
        gateway['data'] = base64.b64encode(base64.b64decode(gateway['data']) +
            b'\n[Service]\nReadWritePaths=/var/lib/rta-missing-gateway-sandbox\n').decode()
        owner = RollbackAdapter(candidate, parameters['probe_url'], parameters['expected_status'],
                                parameters['timeout'], parameters['clients'])
        with pytest.raises(Refusal, match='candidate-refused'):
            tx.apply(candidate, owner)
        tx.accepted()
    assert (STATE / 'accepted.json').read_bytes() == before
    assert {path: (path.read_bytes(), path.stat().st_ino) for path in paths} == original
    assert_xray_generation(release)
    # Kill the actual publisher after a gateway publication and after adoption.
    source = '''import json,os,signal,sys
sys.path.insert(0,sys.argv[1])
from pathlib import Path
from transport_runtime_accept import STATE,gateway_units,read_parameters
from transport_runtime_rollback import RollbackAdapter,runtime_candidates
from transport_runtime_transaction import Transaction
p=read_parameters()
config=Path('/etc/xray/config.json')
with Transaction(STATE) as tx:
 tx.accepted()
 plan=runtime_candidates(tx,'v26.3.27',Path('/etc/systemd/system/xray.service'),config,config.stat().st_gid,
  gateway_paths=[Path('/etc/systemd/system',name) for name in gateway_units()])
 owner=RollbackAdapter(plan,p['probe_url'],p['expected_status'],p['timeout'],p['clients'])
 def checkpoint(stage):
  if stage==sys.argv[2]: os.kill(os.getpid(),signal.SIGKILL)
 tx.apply(plan,owner,checkpoint=checkpoint)
'''
    for stage in ('published-1', 'adopted'):
        result = subprocess.run(['/usr/bin/python3', '-Es', '-c', source,
            '/usr/local/libexec/ripdpi-transport-egress', stage], capture_output=True, timeout=180)
        assert result.returncode == -signal.SIGKILL, stage
        owner = RollbackAdapter([], parameters['probe_url'], parameters['expected_status'],
                                parameters['timeout'], parameters['clients'])
        with Transaction(STATE) as tx:
            tx.recover(owner)
            tx.accepted()
        owner.ready()
        assert (STATE / 'accepted.json').read_bytes() == before
        assert {path: (path.read_bytes(), path.stat().st_ino) for path in paths} == original
        assert_xray_generation(release)


def test_native_site_retirement_and_remaining_upgrade_commit_once():
    state = Path('/var/lib/ripdpi/transport-runtime')
    with fixture.Lab() as lab:
        assert lab.converge('both', site=True) == 0
        initial = json.loads((state / 'accepted.json').read_bytes())
        lab.upgrade('hysteria')
        assert lab.converge('hysteria', site=True) == 0
        accepted = json.loads((state / 'accepted.json').read_bytes())
        assert accepted['nodes']['/etc/systemd/system/xray.service'] is None
        assert os.readlink('/opt/hysteria/current').endswith('/v2.13.0')
        assert json.loads((state / 'last.json').read_bytes())['before_receipt'] == initial
        assert not (state / 'outer.json').exists()
        baseline = (state / 'accepted.json').read_bytes()
        assert lab.converge('none', site=True, fail_after_acceptance=True, allow_failure=True) != 0
        assert (state / 'accepted.json').read_bytes() == baseline
        assert not (state / 'outer.json').exists()
        from transport_runtime_accept import Adapter, read_parameters
        parameters = read_parameters()
        Adapter([], parameters['probe_url'], parameters['expected_status'], parameters['timeout'],
                parameters['clients']).ready()
        assert lab.converge('both', site=True, stage_only=True) == 0
        assert (state / 'outer.json').exists()
        assert lab.converge('none', site=True) == 0
        retired = json.loads((state / 'accepted.json').read_bytes())
        for unit in ('xray.service', 'hysteria-server.service'):
            assert retired['nodes']['/etc/systemd/system/' + unit] is None
        assert not (state / 'outer.json').exists()
        assert lab.converge('both', site=True) == 0


def exercise_native_refusals_and_process_death(lab, profile):
    from transport_runtime_accept import Adapter, STATE, read_parameters, restore_points
    from transport_runtime_transaction import Transaction, Refusal
    parameters = read_parameters()
    config = Path('/etc/xray/config.json' if profile == 'xray' else '/etc/hysteria/config.yaml')
    unit = Path('/etc/systemd/system/' + ('xray.service' if profile == 'xray' else 'hysteria-server.service'))

    def owner(plan, assets=None):
        return Adapter(plan, parameters['probe_url'], parameters['expected_status'],
                       parameters['timeout'], parameters['clients'], assets)

    def plan(data, unit_data=None):
        return restore_points([
            {'path': str(config), 'data': base64.b64encode(data).decode(),
             'gid': config.stat().st_gid, 'mode': 0o640},
            {'path': str(unit), 'data': base64.b64encode(unit_data or unit.read_bytes()).decode(),
             'gid': 0, 'mode': 0o644}])

    def changed(index):
        if profile == 'xray':
            document = json.loads(config.read_bytes())
            document['log']['loglevel'] = 'info' if document['log'].get('loglevel') != 'info' else 'warning'
            return json.dumps(document).encode()
        data, count = re.subn(r'^  up:.*$', '  up:   ' + json.dumps(str(110 + index) + ' mbps'),
                              config.read_text(), flags=re.MULTILINE)
        assert count == 1
        return data.encode()

    for failure in ('parser', 'native-sandbox', 'authenticated-route'):
        before = (STATE / 'accepted.json').read_bytes()
        inode = config.stat().st_ino
        if failure == 'parser':
            # Keep the document parseable; rejection must come from the native
            # runtime's configuration parser, not Python JSON/YAML decoding.
            if profile == 'xray':
                document = json.loads(config.read_bytes())
                document['inbounds'][0]['streamSettings']['network'] = 'invalid-native-network'
                data = json.dumps(document).encode()
            else:
                data, count = re.subn(r'^listen:.*$', 'listen: \":invalid-native-port\"',
                                      config.read_text(), flags=re.MULTILINE)
                assert count == 1
                data = data.encode()
            candidate = plan(data)
        elif failure == 'native-sandbox':
            candidate = plan(changed(0), unit.read_bytes() + b'\n[Service]\nReadWritePaths=/var/lib/rta-missing-sandbox-authority\n')
        else:
            if profile == 'xray':
                document = json.loads(config.read_bytes())
                for outbound in document['outbounds']:
                    if outbound['protocol'] == 'socks':
                        outbound['settings']['servers'][0]['users'][0]['pass'] = 'deliberately-rejected-candidate'
                data = json.dumps(document).encode()
            else:
                data, count = re.subn(r'^      password:.*$', '      password: \"deliberately-rejected-candidate\"',
                                      config.read_text(), flags=re.MULTILINE)
                assert count == 1
                data = data.encode()
            candidate = plan(data)
        with Transaction(STATE) as tx:
            with pytest.raises((Refusal, RuntimeError)):
                tx.apply(candidate, owner(candidate))
            assert tx.accepted() is not None
        assert config.stat().st_ino == inode
        assert (STATE / 'accepted.json').read_bytes() == before
        owner([]).ready()  # Real positive traffic through the exact restored native process.

    # Missing or invalid candidate asset/TLS bytes must be refused before the
    # selected runtime or the original private authority changes.
    before = (STATE / 'accepted.json').read_bytes()
    inode = config.stat().st_ino
    candidate = plan(changed(0))
    if profile == 'xray':
        document = json.loads(config.read_bytes())
        denied = next(item['tag'] for item in document['outbounds'] if item['protocol'] == 'blackhole')
        document.setdefault('routing', {}).setdefault('rules', []).insert(0,
            {'type': 'field', 'ip': ['geoip:private'], 'outboundTag': denied})
        candidate = plan(json.dumps(document).encode())
        assets = lab.private / 'invalid-assets'
        assets.mkdir(mode=0o755)
        (assets / 'geoip.dat').write_bytes(b'invalid-native-geodata')
        (assets / 'geoip.dat').chmod(0o644)
        failed_owner = owner(candidate, str(assets))
    else:
        tls_key = Path('/etc/hysteria/server.key')
        candidate.append({'path': str(tls_key), 'data': base64.b64encode(b'invalid-candidate-TLS-key').decode(),
                          'mode': 0o640, 'gid': tls_key.stat().st_gid})
        failed_owner = owner(candidate)
    with Transaction(STATE) as tx:
        with pytest.raises((Refusal, RuntimeError)):
            tx.apply(candidate, failed_owner)
    assert config.stat().st_ino == inode
    assert (STATE / 'accepted.json').read_bytes() == before
    owner([]).ready()

    # Valid native candidate admission is separate from real live forwarding.
    # The fixture owns only canary port 18080; a selected closed port must not
    # become accepted just because the exact frontend executable is active.
    from transport_runtime_probe import ProbeRefused
    from transport_runtime_accept import fields, unit_binary, parameter_candidate
    closed_canary = 'https://192.0.2.80:18081/'
    original_parameters = (STATE / 'parameters.json').read_bytes()
    parameter_inode = (STATE / 'parameters.json').stat().st_ino
    class ActiveBrokenForwarding(Adapter):
        active_observed = False
        native_refusal = None

        def ready(self):
            if read_parameters()['probe_url'] != closed_canary:
                super().ready()
                return
            self.generation_ready(__import__('time').monotonic() + self.timeout)
            observed = fields('xray.service' if profile == 'xray' else 'hysteria-server.service')
            assert observed['ActiveState'] == 'active' and int(observed['MainPID']) > 0
            executable, _assets, _config = unit_binary(unit.read_text())
            assert os.path.samefile('/proc/' + observed['MainPID'] + '/exe', executable)
            self.active_observed = True
            try:
                super().ready()
            except ProbeRefused as error:
                self.native_refusal = error
                raise

    candidate = plan(changed(20)) + [parameter_candidate({**parameters, 'probe_url':closed_canary})]
    refused = ActiveBrokenForwarding(candidate, closed_canary, parameters['expected_status'],
                                     parameters['timeout'], parameters['clients'])
    with Transaction(STATE) as tx:
        with pytest.raises(Refusal, match='candidate-refused'):
            tx.apply(candidate, refused)
    assert refused.active_observed and isinstance(refused.native_refusal, ProbeRefused)
    assert config.stat().st_ino == inode
    assert (STATE / 'accepted.json').read_bytes() == before
    assert (STATE / 'parameters.json').read_bytes() == original_parameters
    assert (STATE / 'parameters.json').stat().st_ino == parameter_inode
    owner([]).ready()

    class OccupiedListener(Adapter):
        blocker = None

        def start(self):
            self.blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM if profile == 'xray' else socket.SOCK_DGRAM)
            self.blocker.bind(('127.0.0.1', 443))
            if profile == 'xray':
                self.blocker.listen(1)
            super().start()

        def restore(self, units):
            if self.blocker is not None:
                self.blocker.close()
                self.blocker = None
            super().restore(units)

    candidate = plan(changed(0))
    refused = OccupiedListener(candidate, parameters['probe_url'], parameters['expected_status'],
                               parameters['timeout'], parameters['clients'])
    try:
        with Transaction(STATE) as tx:
            with pytest.raises((Refusal, RuntimeError)):
                tx.apply(candidate, refused)
    finally:
        if refused.blocker is not None:
            refused.blocker.close()
    assert config.stat().st_ino == inode
    assert (STATE / 'accepted.json').read_bytes() == before
    owner([]).ready()

    # SIGKILL occurs in a separate publisher process, never through an exception
    # fixture. Recovery must re-adopt the real frontend and prove native traffic.
    stages = ('staged-0', 'prepared', 'materialized-0', 'intent', 'stopped',
              'published-0', 'adopted', 'ready', 'committed')
    source = '''import json,os,signal,sys
sys.path.insert(0,sys.argv[1])
from transport_runtime_accept import Adapter,STATE
from transport_runtime_transaction import Transaction,Refusal
value=json.load(sys.stdin)
adapter=Adapter(value['plan'],value['url'],value['expected'],60,value['clients'])
def checkpoint(stage):
 if stage==value['stage']: os.kill(os.getpid(),signal.SIGKILL)
try:
 with Transaction(STATE) as tx: tx.apply(value['plan'],adapter,checkpoint=checkpoint)
except Exception as error:
 print(str(error) if isinstance(error,Refusal) else type(error).__name__,flush=True)
 raise SystemExit(1)
'''
    for index, stage in enumerate(stages):
        candidate = plan(changed(index))
        original = config.read_bytes()
        original_inode = config.stat().st_ino
        request = {'plan': candidate, 'stage': stage, 'url': parameters['probe_url'],
                   'expected': parameters['expected_status'], 'clients': parameters['clients']}
        process = subprocess.run(['/usr/bin/python3', '-Es', '-c', source,
            '/usr/local/libexec/ripdpi-transport-egress'], input=json.dumps(request).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
        assert process.returncode == -signal.SIGKILL, 'native-kill-point-not-reached-' + stage + ':' + process.stdout.decode()
        with Transaction(STATE) as tx:
            tx.recover(owner([]))
            tx.accepted()
        if stage != 'committed':
            exact_private_content = config.read_bytes() == original
            assert exact_private_content
            assert config.stat().st_ino == original_inode
        owner([]).ready()
        assert not (STATE / 'pending.json').exists()
        assert not (STATE / 'preparation.json').exists()


def test_hysteria_admission_sigkill_reconciles_exact_validation_lease():
    import selectors
    with fixture.Lab() as lab:
        from transport_runtime_accept import Adapter, STATE, read_parameters
        assert lab.converge('hysteria') == 0
        original = (STATE / 'accepted.json').read_bytes()
        parameters = read_parameters()
        source = '''import os,sys
sys.path.insert(0,sys.argv[1])
from pathlib import Path
from transport_runtime_transaction import Transaction
from transport_runtime_accept import STATE,read_parameters,gateway_units,unit_binary
from transport_runtime_validate import validate_hysteria
values=read_parameters()
unit=Path('/etc/systemd/system/hysteria-server.service').read_text()
binary=[line.split('=',1)[1].split()[0] for line in unit.splitlines() if line.startswith('ExecStart=')][0]
def checkpoint(stage):
 if stage=='validation-active':
  print('validation-active',flush=True)
  while True: os.pause()
with Transaction(STATE) as tx:
 validate_hysteria(binary,Path('/etc/hysteria/config.yaml').read_bytes(),
  Path('/etc/hysteria/server.fullchain.pem').read_bytes(),Path('/etc/hysteria/server.key').read_bytes(),
  unit,values['timeout'],values['clients']['hysteria'],
  gateway_binary=unit_binary(Path('/etc/systemd/system',gateway_units()[0]).read_text())[0],
  transaction=tx,checkpoint=checkpoint)
'''
        process = subprocess.Popen(['/usr/bin/python3', '-Es', '-c', source,
            '/usr/local/libexec/ripdpi-transport-egress'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                assert selector.select(10), 'native-validation-active-checkpoint-timeout'
                assert process.stdout.readline() == b'validation-active\n', 'native-validation-not-active'
            assert process.poll() is None
            lease = json.loads((STATE / 'validation.json').read_bytes())
            unit = Path('/run/systemd/system') / lease['unit']['name']
            namespace = Path('/run/netns') / lease['namespace']['name']
            directory = Path('/var/lib') / lease['directory']['name']
            assert unit.exists() and namespace.exists() and directory.exists()
            assert unit.stat().st_uid == 0 and unit.stat().st_mode & 0o777 == 0o600
            assert lease['unit']['identity'][4] == 0o600
            os.kill(process.pid, signal.SIGKILL)
            assert process.wait(timeout=10) == -signal.SIGKILL
            assert (STATE / 'validation.json').exists()
            request = {**parameters, 'candidates': []}
            result = subprocess.run(['/usr/bin/python3', '-Es',
                '/usr/local/libexec/ripdpi-transport-egress/transport_runtime_accept.py', '--bootstrap'],
                input=json.dumps(request).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            assert result.returncode == 0, 'native-validation-lease-recovery-refused'
            assert not (STATE / 'validation.json').exists()
            assert not unit.exists() and not namespace.exists() and not directory.exists()
            loaded = subprocess.run(['/usr/bin/systemctl', 'show', lease['unit']['name'],
                '--property=MainPID,ActiveState'], capture_output=True, timeout=10)
            assert loaded.returncode == 0 and b'MainPID=0' in loaded.stdout
            assert b'ActiveState=active' not in loaded.stdout
            assert (STATE / 'accepted.json').read_bytes() == original
            Adapter([], parameters['probe_url'], parameters['expected_status'],
                    parameters['timeout'], parameters['clients']).ready()
        finally:
            if process.poll() is None:
                os.kill(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            process.stdout.close()


def test_native_ech_admission_retains_custom_configuration_directory():
    from hysteria_ech import generate
    with fixture.Lab() as lab:
        from transport_runtime_accept import fields
        lab.upgrade('hysteria')
        directory = Path('/etc/hysteria/profile')
        lab.context['hysteria_config_dir'] = str(directory)
        authority = generate(lab.artifacts / 'hysteria-v2.13.0', 'outer.example', 'owned.example')
        lab.context['hysteria']['ech'] = authority
        assert lab.converge('hysteria') == 0
        key = directory / 'ech.key'
        matches = key.read_text() == authority['keys_pem']
        assert matches, 'native-custom-directory-ECH-authority-mismatch'
        assert key.stat().st_mode & 0o777 == 0o600
        assert not Path('/etc/hysteria/ech.key').exists()
        unit = Path('/etc/systemd/system/hysteria-server.service').read_text()
        assert 'LoadCredential=hysteria-ech:' + str(key) in unit
        before = fields('hysteria-server.service')['MainPID']
        assert int(before) > 0
        assert lab.converge('hysteria') == 0
        assert fields('hysteria-server.service')['MainPID'] == before


def test_native_ech_rotation_idempotence_and_complete_compensation():
    from hysteria_ech import generate
    with fixture.Lab() as lab:
        from transport_runtime_accept import fields
        assert lab.converge('hysteria') == 0
        lab.upgrade('hysteria')
        binary = lab.artifacts / 'hysteria-v2.13.0'
        ech = generate(binary, 'outer.example', 'owned.example')
        lab.context['hysteria'].update(ech=ech, resource_profile='bbr-conservative')
        assert lab.converge('hysteria') == 0
        key = Path('/etc/hysteria/ech.key')
        def assert_key(expected):
            matched = key.read_text() == expected['keys_pem']
            assert matched, 'native-ech-private-generation-mismatch'
        assert_key(ech)
        assert key.stat().st_mode & 0o777 == 0o600
        assert key.stat().st_uid == 0 and key.stat().st_gid == 0
        before = fields('hysteria-server.service')['MainPID']
        receipt = Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes()
        assert lab.converge('hysteria') == 0
        assert fields('hysteria-server.service')['MainPID'] == before
        assert Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes() == receipt
        # Existing native failure/kill matrix now runs with ECH credential authority.
        exercise_native_refusals_and_process_death(lab, 'hysteria')
        assert_key(ech)
        rotated = generate(binary, 'outer.example', 'owned.example')
        baseline_receipt = Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes()
        lab.context['hysteria']['ech'] = rotated
        assert lab.converge('hysteria', site=True, fail_after_acceptance=True, allow_failure=True) != 0
        failures = lab.failure_categories()
        assert 'Inject failure after native consumer acceptance' in failures['failed_tasks'], failures
        assert_key(ech)
        receipt_restored = Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_bytes() == baseline_receipt
        assert receipt_restored, 'native-ech-receipt-compensation-mismatch'
        assert not Path('/var/lib/ripdpi/transport-runtime/outer.json').exists()
        rotation_pid = fields('hysteria-server.service')['MainPID']
        assert lab.converge('hysteria') == 0
        assert_key(rotated)
        assert fields('hysteria-server.service')['MainPID'] != rotation_pid
        lab.context['hysteria']['resource_profile'] = 'bbr-standard'
        assert lab.converge('hysteria') == 0
        import yaml
        assert yaml.safe_load(Path('/etc/hysteria/config.yaml').read_bytes())['congestion']['bbrProfile'] == 'standard'
        del lab.context['hysteria']['ech']
        assert lab.converge('hysteria') == 0
        assert not key.exists()
        assert lab.converge('hysteria', retire=True) == 0


@pytest.mark.parametrize('boundary', ['before-decision', 'after-decision', 'before-egress-finish',
                                      'after-egress-finish', 'before-ingress-clear', 'after-ingress-clear'])
def test_native_ingress_egress_commit_sigkill_recovers_one_accepted_generation(boundary):
    """Real ingress journal plus canonical egress rollback/readiness and authenticated traffic."""
    import yaml
    from test_nginx_site_transaction import load, install_accepted, publish_candidate
    with fixture.Lab() as lab:
        from transport_runtime_outer import adapter
        assert lab.converge('xray') == 0
        accepted = Path('/var/lib/ripdpi/transport-runtime/accepted.json')
        previous = json.loads(accepted.read_text())
        tx = load()
        tx.STATE_ROOT = lab.private / 'ingress-journal'
        ingress = lab.private / 'ingress'
        ingress.mkdir(mode=0o700)
        context = {'check': False, 'owners': [
            {'owner': owner, 'roots': [str(ingress)], 'paths': [str(ingress / (owner + '.conf'))],
             'prune_releases': None} for owner in sorted(tx.SITE_OWNERS)]}
        state = install_accepted(tx, context)
        tx.site_transaction('begin', context)
        lab.upgrade('xray')
        assert lab.converge('xray', site=True, retain_commit=True) == 0
        current = json.loads(accepted.read_text())
        assert current != previous
        candidate = publish_candidate(tx, context)
        pid = os.fork()
        if pid == 0:
            def kill():
                os.kill(os.getpid(), signal.SIGKILL)
            persist, clear, command = tx.persist, tx.clear, tx.command
            def marked(path, value):
                if path.name == 'site.json' and value['phase'] == 'committing':
                    if boundary == 'before-decision': kill()
                    persist(path, value)
                    if boundary == 'after-decision': kill()
                else:
                    persist(path, value)
            def finish(argv):
                if boundary == 'before-egress-finish': kill()
                result = command(argv)
                if boundary == 'after-egress-finish': kill()
                return result
            def removed(path):
                if boundary == 'before-ingress-clear': kill()
                clear(path)
                if boundary == 'after-ingress-clear': kill()
            tx.persist, tx.clear, tx.command = marked, removed, finish
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
        if boundary == 'before-decision':
            assert result['status'] == 'open'
            recovery = lab.private / 'recover-commit.yml'
            recovery.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local',
                'gather_facts': True, 'vars': {**lab.context, '_transport_egress_transaction_started': True},
                'tasks': [{'ansible.builtin.include_role': {'name': 'transport-egress', 'tasks_from': 'quiesce'}}]}]))
            recovery.chmod(0o600)
            env = {**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg'),
                   'ANSIBLE_ROLES_PATH': str(ROOT / 'ansible/roles'), 'ANSIBLE_STDOUT_CALLBACK': 'default'}
            fixture.command(['ansible-playbook', '-i', 'localhost,', str(recovery)], env=env, timeout=180)
            tx.site_transaction('restore', context)
            play = yaml.safe_load(recovery.read_text())
            play[0]['tasks'][0]['ansible.builtin.include_role']['tasks_from'] = 'rollback'
            recovery.write_text(yaml.safe_dump(play))
            fixture.command(['ansible-playbook', '-i', 'localhost,', str(recovery)], env=env, timeout=180)
            assert json.loads(accepted.read_text()) == previous
            assert candidate.read_bytes() == b'accepted'
        else:
            assert result['status'] == ('absent' if boundary == 'after-ingress-clear' else 'committed')
            assert json.loads(accepted.read_text()) == current
            assert candidate.read_bytes() == b'candidate'
        assert not (state / 'site.json').exists()
        assert not accepted.with_name('outer.json').exists()
        # This executes actual authenticated frontend canary traffic after recovery.
        adapter().ready()


@pytest.mark.parametrize('profile', ['xray', 'hysteria'])
@pytest.mark.parametrize('interruption', ['published-0', 'adopted', 'outer-failure'])
def test_native_revocation_never_restores_credentials_and_exact_resume_converges(profile, interruption):
    """Real PID1, native authentication and canonical convergence across failure."""
    import secrets
    import uuid
    import yaml
    with fixture.Lab() as lab:
        from transport_runtime_accept import Adapter, STATE, read_parameters, unit_binary
        from transport_runtime_probe import ProbeRefused, probe
        from transport_runtime_transaction import Refusal, Transaction
        removed = {'name': 'native-revoked', **({'uuid': str(uuid.uuid4()), 'short_id': secrets.token_hex(4)}
                  if profile == 'xray' else {'password': secrets.token_hex(24)})}
        lab.context[profile]['clients'].append(removed)
        assert lab.converge(profile, site=True) == 0
        config = Path('/etc/xray/config.json' if profile == 'xray' else '/etc/hysteria/config.yaml')
        unit = Path('/etc/systemd/system/' + ('xray.service' if profile == 'xray' else 'hysteria-server.service'))
        old = lab.private / 'revoked-client-source'
        old.write_bytes(config.read_bytes()); old.chmod(0o600)
        parameters = read_parameters()
        binary, assets, _ = unit_binary(unit.read_text())
        options = dict(asset_dir=assets if profile == 'xray' else None,
                       url=parameters['probe_url'], client_name=removed['name'], timeout=8)
        probe(binary, old, **options)
        authority = {'operation_id': str(uuid.uuid4()), 'intent_sha256': secrets.token_hex(32)}
        lab.context[profile]['clients'].remove(removed)
        if interruption == 'outer-failure':
            lab.context['vpn_device_revocation'] = authority
            assert lab.converge(profile, site=True, fail_after_acceptance=True, allow_failure=True) != 0
            assert (STATE / 'outer.json').exists()
            assert config.read_bytes() != old.read_bytes()
            assert subprocess.run(['systemctl', 'is-active', '--quiet', unit.name], capture_output=True).returncode != 0
            assert lab.converge(profile, site=True) == 0
            lab.context.pop('vpn_device_revocation')
        else:
            if profile == 'xray':
                document = json.loads(config.read_bytes())
                for inbound in document['inbounds']:
                    if inbound.get('protocol') != 'vless':
                        continue
                    users = inbound['settings']['clients']
                    keep = [index for index, user in enumerate(users) if user['id'] != removed['uuid']]
                    inbound['settings']['clients'] = [users[index] for index in keep]
                    stream = inbound['streamSettings']
                    if stream.get('security') == 'reality':
                        ids = stream['realitySettings']['shortIds']
                        stream['realitySettings']['shortIds'] = [ids[index] for index in keep]
                data = json.dumps(document).encode()
            else:
                document = yaml.safe_load(config.read_bytes())
                del document['auth']['userpass'][removed['name']]
                data = yaml.safe_dump(document).encode()
            plan = [{'path': str(config), 'data': base64.b64encode(data).decode(), 'mode': 0o640,
                     'gid': config.stat().st_gid},
                    {'path': str(unit), 'data': base64.b64encode(unit.read_bytes()).decode(), 'mode': 0o644, 'gid': 0}]
            source = '''import json,os,signal,sys
sys.path.insert(0,sys.argv[1])
from transport_runtime_accept import Adapter,STATE,read_parameters
from transport_runtime_transaction import Transaction
v=json.load(sys.stdin);p=read_parameters()
a=Adapter(v['plan'],p['probe_url'],p['expected_status'],p['timeout'],p['clients'])
def checkpoint(stage):
 if stage==v['stage']: os.kill(os.getpid(),signal.SIGKILL)
with Transaction(STATE,revocation=v['authority']) as tx: tx.apply(v['plan'],a,checkpoint=checkpoint)
'''
            result = subprocess.run(['/usr/bin/python3', '-Es', '-c', source,
                '/usr/local/libexec/ripdpi-transport-egress'], input=json.dumps(
                {'plan': plan, 'authority': authority, 'stage': interruption}).encode(),
                capture_output=True, timeout=120)
            assert result.returncode == -signal.SIGKILL, 'native-revocation-kill-point-not-reached'
            assert config.read_bytes() != old.read_bytes()
            assert lab.converge(profile, site=True, allow_failure=True) != 0
            adapter = Adapter(plan, parameters['probe_url'], parameters['expected_status'],
                              parameters['timeout'], parameters['clients'])
            with Transaction(STATE, revocation=authority) as tx:
                assert tx.apply(plan, adapter)['status'] == 'accepted'
            with Transaction(STATE) as tx, pytest.raises(Refusal, match='revocation-rollback-forbidden'):
                tx.compensate_latest(adapter)
        # Both retained-device traffic and the retired credential are exercised
        # through new native clients while the actual service is healthy.
        with pytest.raises(ProbeRefused):
            probe(binary, old, **options)
        surviving = parameters['clients'][profile]
        probe(binary, config, **{**options, 'client_name': surviving})
        assert lab.converge(profile, site=True) == 0
        with pytest.raises(ProbeRefused):
            probe(binary, old, **options)
        probe(binary, config, **{**options, 'client_name': surviving})
        assert not (STATE / 'pending.json').exists() and not (STATE / 'outer.json').exists()
