"""Exact pinned upgrade acceptance through the real canonical Ansible consumers."""
import importlib.util
import base64
import json
import os
from pathlib import Path
import signal
import re
import socket
import subprocess
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_runtime_transaction_lab', ROOT / 'tests/integration/transport_runtime_acceptance/fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize('profile', ['xray', 'hysteria'])
def test_complete_native_upgrade_and_unchanged_retry_preserve_distinct_previous(profile):
    with fixture.Lab() as lab:
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
        before = json.loads(Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_text())
        lab.upgrade(profile)
        assert lab.converge(profile) == 0
        assert os.readlink(root / 'current') != previous
        assert os.readlink(root / 'previous') == previous
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
        if profile == 'xray':
            result = subprocess.run(['/usr/bin/python3', '-Es',
                '/usr/local/libexec/ripdpi-transport-egress/transport_runtime_rollback.py',
                'config'], capture_output=True, timeout=90)
            assert result.returncode == 0, 'native-config-rollback-refused'
            result = subprocess.run(['/usr/bin/python3', '-Es',
                '/usr/local/libexec/ripdpi-transport-egress/transport_runtime_rollback.py',
                'runtime', '--version', 'v26.3.27'], capture_output=True, timeout=90)
            assert result.returncode == 0, 'native-runtime-rollback-refused'
            assert os.readlink(root / 'current') == previous
            # Retargeted links do not prove what runs: the unit text and the live main process
            # must both name the rolled-back release binary.
            from transport_runtime_accept import fields, unit_binary
            rolled_back = str(Path(previous) / 'xray')
            unit_text = Path('/etc/systemd/system/xray.service').read_text()
            assert unit_binary(unit_text)[0] == rolled_back
            assert 'Environment=XRAY_RUNTIME_BINARY=' + rolled_back in unit_text.splitlines()
            observed = fields('xray.service')
            assert observed['ActiveState'] == 'active' and int(observed['MainPID']) > 0
            assert os.path.samefile('/proc/' + observed['MainPID'] + '/exe', rolled_back), 'native-runtime-rollback-process-unchanged'
            # The next ordinary converge with the newer pin must still be accepted and move
            # the unit and links forward again.
            assert lab.converge(profile) == 0
            assert os.readlink(root / 'current') != previous
            assert unit_binary(Path('/etc/systemd/system/xray.service').read_text())[0] == os.readlink(root / 'current') + '/xray'
        assert lab.converge(profile, retire=True) == 0
        retired_unit = '/etc/systemd/system/' + ('xray.service' if profile == 'xray' else 'hysteria-server.service')
        assert not os.path.lexists(retired_unit)
        retired = json.loads(Path('/var/lib/ripdpi/transport-runtime/accepted.json').read_text())
        assert retired['nodes'][retired_unit] is None
        assert not Path('/var/lib/ripdpi/transport-runtime/outer.json').exists()
        assert lab.converge(profile) == 0
        assert Path(retired_unit).is_file()


def test_native_site_retirement_and_remaining_upgrade_commit_once():
    state = Path('/var/lib/ripdpi/transport-runtime')
    with fixture.Lab() as lab:
        assert lab.converge('both', site=True) == 0
        initial = json.loads((state / 'accepted.json').read_bytes())
        lab.upgrade('hysteria')
        assert lab.converge('hysteria', site=True) == 0
        accepted = json.loads((state / 'accepted.json').read_bytes())
        assert accepted['nodes']['/etc/systemd/system/xray.service'] is None
        assert os.readlink('/opt/hysteria/current').endswith('/v2.9.0')
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
                return super().ready()
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
    from transport_runtime_accept import Adapter, STATE, read_parameters
    with fixture.Lab() as lab:
        assert lab.converge('hysteria') == 0
        original = (STATE / 'accepted.json').read_bytes()
        parameters = read_parameters()
        source = '''import os,sys
sys.path.insert(0,sys.argv[1])
from pathlib import Path
from transport_runtime_transaction import Transaction
from transport_runtime_accept import STATE,read_parameters
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
  unit,values['timeout'],values['clients']['hysteria'],transaction=tx,checkpoint=checkpoint)
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
