"""Real systemd/AWG configuration failure restores complete prior authority."""
from __future__ import annotations

import base64
import copy
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import uuid

import pytest
import yaml
from jinja2 import FileSystemLoader

from awg_client import config, export
from awg_device_binding import resolve_binding
from template_render import merge_render_vars, render_template, template_environment
from test_awg_device_binding import document
from test_awg_device_binding_native import native_config
from test_awg_dualstack_native import ECHO, PROBE, path_evidence
from test_transport_semantics_native import command, exact_awg_sources

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


def render_native_awg_config(instance):
    """Match Ansible's template lookup without changing snapshot whitespace."""
    template = ROOT / 'ansible/roles/amneziawg/templates/awg0.conf.j2'
    environment = template_environment(FileSystemLoader(str(template.parent)))
    environment.trim_blocks = True
    return environment.get_template(template.name).render(_inst=instance)


class CompletePublisher:
    """Use the installed production helper and real immutable acquisition bytes."""

    helper = Path('/usr/local/libexec/ripdpi-consumer/amneziawg_consumer.py')
    record = Path('/var/lib/ripdpi/amneziawg/instances.json')
    firewall = Path('/etc/nftables.conf')

    def __init__(self, directory, environment):
        self.directory, self.environment = directory, environment

    def acquire(self, go, tools, quick):
        go_bytes, tool_bytes, quick_bytes = Path(go).read_bytes(), Path(tools).read_bytes(), Path(quick).read_bytes()
        go_commit = hashlib.sha256(go_bytes).hexdigest()
        tools_commit = hashlib.sha256(tool_bytes + quick_bytes).hexdigest()
        pairs = [('/usr/local/bin/amneziawg-go', f'go-{go_commit}', 'amneziawg-go', go_bytes),
                 ('/usr/bin/awg', f'tools-{tools_commit}', 'awg', tool_bytes),
                 ('/usr/bin/awg-quick', f'tools-{tools_commit}', 'awg-quick', quick_bytes)]
        candidates = []
        for target, release, name, content in pairs:
            source = Path('/opt/amneziawg/releases') / release / name
            source.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            if source.exists():
                assert source.read_bytes() == content, 'immutable-native-acquisition-changed'
            else:
                source.write_bytes(content); source.chmod(0o755)
            candidates.append({'path': target, 'source': str(source), 'sha256': hashlib.sha256(content).hexdigest(), 'mode': 0o755, 'gid': 0})
        self.go_commit, self.tools_commit = go_commit, tools_commit
        return candidates

    def request(self, acquired, configs, shared, *, firewall=None, absent=()):
        candidates = copy.deepcopy(acquired)
        for name, content in configs.items():
            candidates.append({'path': str(self.directory / (name + '.conf')), 'data': base64.b64encode(content.encode()).decode(), 'mode': 0o600, 'gid': 0})
        candidates.extend({'path': str(path), 'absent': True} for path in absent)
        values = merge_render_vars(); values['_awg_instances'] = [{'name': name} for name in configs]
        target = render_template(ROOT / 'ansible/roles/amneziawg/templates/awg-quick.target.j2', values)
        for path, content, mode in (
            ('/etc/systemd/system/awg-quick@.service', shared, 0o644),
            ('/etc/systemd/system/awg-quick.target', target, 0o644),
            (str(self.record), json.dumps({'schema': 1, 'config_dir': str(self.directory), 'instances': list(configs)}), 0o600),
        ):
            candidates.append({'path': path, 'data': base64.b64encode(content.encode()).decode(), 'mode': mode, 'gid': 0})
        return {'check': False, 'candidates': candidates, 'firewall': None if firewall is None else base64.b64encode(firewall.encode()).decode()}

    def apply(self, request):
        return subprocess.run([sys.executable, '-Es', str(self.helper), 'apply'], input=json.dumps(request),
                              env=self.environment, capture_output=True, text=True, timeout=90)

    def role(self, instances, *, firewall=None):
        previous = json.loads(self.record.read_text()) if self.record.exists() else {'schema': 1, 'config_dir': str(self.directory), 'instances': []}
        play = self.directory / 'converge.yml'
        play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
            'environment': {'PATH': self.environment['PATH']},
            'vars': {'amneziawg_config_dir': str(self.directory), '_awg_instances': instances,
                     'amneziawg_go_commit': self.go_commit, 'amneziawg_tools_commit': self.tools_commit,
                     '_awg_previous': previous, '_awg_obsolete': [], '_awg_configuration_owns_lifecycle': True,
                     '_firewall_consumer_candidate': None if firewall is None else base64.b64encode(firewall.encode()).decode()},
            'tasks': [{'ansible.builtin.include_role': {'name': 'amneziawg', 'tasks_from': 'consumer-prepare'}},
                      {'ansible.builtin.include_role': {'name': 'amneziawg', 'tasks_from': 'configure'}}]}]))
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)], env=self.environment,
                              capture_output=True, text=True, timeout=90)


def prepare_native_acquisition(root):
    """Create only fresh claimed directories with modes independent of umask."""
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    releases = root / 'releases'
    releases.mkdir(mode=0o755)
    releases.chmod(0o755)


@contextmanager
def complete_publisher(directory, environment=None):
    """Claim only absent fixed paths in the isolated native host; retire all of them."""
    assert sys.platform == 'linux' and os.geteuid() == 0
    roots = [Path(raw) for raw in ('/usr/local/libexec/ripdpi-consumer', '/var/lib/ripdpi/amneziawg',
             '/var/lib/ripdpi/firewall-runtime', '/opt/amneziawg')]
    files = [Path(raw) for raw in ('/usr/local/bin/amneziawg-go', '/usr/bin/awg', '/usr/bin/awg-quick',
             '/etc/systemd/system/awg-quick@.service', '/etc/systemd/system/awg-quick.target')]
    stores = {path.parent / '.ripdpi-transport-runtime' for path in [*files, Path('/etc/nftables.conf')]}
    assert all(not os.path.lexists(path) for path in [*roots, *files, *stores]), 'native-complete-AWG-authority-already-owned'
    nft = Path('/etc/nftables.conf')
    assert not nft.is_symlink(), 'native-firewall-file-is-foreign-symlink'
    saved = nft.with_name('.native-awg-' + uuid.uuid4().hex)
    if nft.exists(): os.replace(nft, saved)
    publisher = CompletePublisher(directory, {**os.environ, **(environment or {}),
        'ANSIBLE_ROLES_PATH': str(ROOT / 'ansible/roles'), 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    try:
        roots[0].mkdir(parents=True, mode=0o755)
        roots[1].mkdir(parents=True, mode=0o700)
        prepare_native_acquisition(roots[3])
        for source, name in (
            ('amneziawg/files/consumer.py', 'amneziawg_consumer.py'),
            ('firewall/files/firewall_consumer.py', 'firewall_consumer.py'),
            ('runtime-release/files/transport_runtime_transaction.py', 'transport_runtime_transaction.py'),
            ('runtime-release/files/runtime_build_receipt.py', 'runtime_build_receipt.py'),
        ):
            destination = roots[0] / name
            shutil.copyfile(ROOT / 'ansible/roles' / source, destination); destination.chmod(0o755)
        yield publisher
    finally:
        for path in files:
            path.unlink(missing_ok=True)
        for path in [*stores, *roots]:
            if path.exists():
                assert path.is_dir() and not path.is_symlink() and path.stat().st_uid == 0
                shutil.rmtree(path)
        nft.unlink(missing_ok=True)
        if saved.exists(): os.replace(saved, nft)
        subprocess.run(['systemctl', 'daemon-reload'], capture_output=True, timeout=15)


def userspace_digest(selected):
    """Require the real accepted userspace daemon, including oneshot children."""
    group=command(['systemctl','show',selected,'--property=ControlGroup','--value']).strip()
    assert group.startswith('/') and '..' not in Path(group).parts
    root=Path('/sys/fs/cgroup')/group.lstrip('/')
    daemons=[]
    for membership in root.rglob('cgroup.procs'):
        for pid in membership.read_text().split():
            try:
                executable=Path('/proc')/pid/'exe'
                if Path(os.readlink(executable)).name.split(' ')[0]=='amneziawg-go':
                    daemons.append(hashlib.sha256(executable.read_bytes()).hexdigest())
            except (FileNotFoundError,ProcessLookupError):
                continue
    assert len(daemons)==1, 'native-AWG-userspace-process-unconfirmed'
    return daemons[0]


@pytest.mark.parametrize('previous', [True, False])
@pytest.mark.parametrize('failure', ['configuration', 'binary', 'shared-unit'])
def test_failed_complete_config_restores_addresses_mtu_service_and_private_bytes(tmp_path, previous, failure):
    go, tools = exact_awg_sources()
    assert Path('/run/systemd/system').is_dir(), 'AWG compensation requires an isolated systemd root host'
    token=uuid.uuid4().hex[:7]
    server,client,uplink='ars'+token,'arc'+token,'aru'+token
    iface,ci='ar'+token,'cr'+token
    unit=Path('/etc/systemd/system')/('awg-quick@'+iface+'.service')
    assert not unit.exists(), 'the fixture may not adopt an existing systemd unit'
    dropin=unit.with_name(unit.name+'.d')
    assert not dropin.exists(), 'the fixture may not adopt an existing systemd drop-in'
    directory=Path('/var/lib/ripdpi')/('awg-native-'+token); directory.mkdir(parents=True, mode=0o700)
    path=directory/(iface+'.conf')
    bin_dir=directory/'bin'; bin_dir.mkdir(mode=0o700)
    quick=tools.parent/'wg-quick/linux.bash'
    assert quick.is_file(), 'the exact pinned awg-quick source is required'
    doc=document(); item=doc['amneziawg_secrets']['instances'][0]
    item.update(name=iface,mtu=1420,jc=0,s1=0,s2=0)
    doc['amneziawg_secrets']['instances']= [item]
    doc['client_registry']={'device0':doc['client_registry']['device0']}
    doc['client_registry']['device0']['awg_binding']['instance']=iface
    effective=resolve_binding(doc,{},'device0','upcloud:fixture',iface).instance
    accepted=render_native_awg_config(effective)
    processes=[]; namespaces=[]; ownership=ExitStack()
    firewall=Path('/etc/nftables.conf')
    # This adapter only enters the owned network namespace; it executes real nft.
    nft=bin_dir/'nft'
    nft.write_text(f'#!/bin/sh\nexec /usr/sbin/ip netns exec {server} /usr/sbin/nft "$@"\n')
    nft.chmod(0o700)
    assert os.access(nft, os.X_OK), "AWG namespace adapters require executable pytest scratch space"
    def firewall_text(item, enabled=True):
        values=merge_render_vars()
        values.update(amneziawg_secrets={'instances':[item]},firewall_awg_uplink_interface='up0',
                      security_controls={'fail2ban':False},
                      _firewall_effective_check_mode=True,_firewall_tailnet_ssh_sets_was_absent=True,
                      _firewall_tailnet_initial_fragment=(ROOT/'ansible/roles/firewall/files/vpn-tailnet-ssh-sets.empty.nft').read_text())
        values['vpn']={key:False for key in values['vpn'] if key.startswith('enable_')}
        values['vpn']['enable_amneziawg']=enabled
        return render_template(ROOT/'ansible/roles/firewall/templates/nftables.conf.j2',values)
    retained_firewall=firewall_text(effective,previous)
    def run(ns,argv,data=None): return command(['ip','netns','exec',ns,*map(str,argv)],data=data)
    try:
        publisher=ownership.enter_context(complete_publisher(directory, {'PATH':str(bin_dir)+':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}))
        acquired=publisher.acquire(go,tools,quick)
        shared=render_template(ROOT/'ansible/roles/amneziawg/templates/awg-quick@.service.j2', merge_render_vars())
        firewall.write_text(retained_firewall); firewall.chmod(0o644)
        for ns in (server,client,uplink):
            command(['ip','netns','add',ns]); namespaces.append(ns)
            command(['ip','-n',ns,'link','set','lo','up'])
        left,right='rl'+token,'rr'+token
        command(['ip','link','add',left,'type','veth','peer','name',right])
        for ns,link,address in ((server,left,'192.0.2.1/30'),(client,right,'192.0.2.2/30')):
            command(['ip','link','set',link,'netns',ns]); command(['ip','-n',ns,'address','add',address,'dev',link])
            command(['ip','-n',ns,'link','set',link,'up'])
        command(['ip','link','add','up0','type','veth','peer','name','echo0'])
        for ns,link,addresses in ((server,'up0',('198.18.1.1/30','fd88::1/64')),
                                  (uplink,'echo0',('198.18.1.2/30','fd88::2/64'))):
            command(['ip','link','set',link,'netns',ns])
            for address in addresses:
                command(['ip','-n',ns,'address','add',address,'dev',link,'nodad'] if ':' in address else ['ip','-n',ns,'address','add',address,'dev',link])
            command(['ip','-n',ns,'link','set',link,'up'])
        for setting in ('net.ipv4.ip_forward=1','net.ipv6.conf.all.forwarding=1'):
            run(server,['sysctl','-qw',setting])
        run(server,['nft','-f','-'],retained_firewall)
        # The namespace/config adapter is owned by this fixture. Executable and
        # shared-unit authority still pass through the production publisher.
        dropin.mkdir(mode=0o755)
        (dropin/'namespace.conf').write_text(f'''[Service]\nNetworkNamespacePath=/run/netns/{server}\nEnvironment=WG_QUICK_USERSPACE_IMPLEMENTATION=/usr/local/bin/amneziawg-go\nExecStartPre=/bin/sh -c '! grep -q "MTU = 1280" {path}'\nExecStart=\nExecStart=/bin/bash /usr/bin/awg-quick up {path}\nExecStop=\nExecStop=/bin/bash /usr/bin/awg-quick down {path}\nExecReload=\n''')
        command(['systemctl','daemon-reload'])
        if previous:
            initial=publisher.role([effective],firewall=retained_firewall)
            assert initial.returncode==0, 'canonical-complete-AWG-role-refused\n'+initial.stdout+initial.stderr
            assert path.read_text()==accepted
            assert userspace_digest(unit.name)==hashlib.sha256(go.read_bytes()).hexdigest()
            prior={raw:(Path(raw).stat().st_ino,Path(raw).stat().st_mode,Path(raw).read_bytes()) for raw in
                   ('/usr/local/bin/amneziawg-go','/usr/bin/awg','/usr/bin/awg-quick',
                    '/etc/systemd/system/awg-quick@.service','/etc/systemd/system/awg-quick.target')}
            process=subprocess.Popen(['ip','netns','exec',client,str(go),'-f',ci],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            processes.append(process); deadline=time.monotonic()+10
            while subprocess.run(['ip','-n',client,'link','show',ci],capture_output=True).returncode:
                assert process.poll() is None and time.monotonic()<deadline; time.sleep(.05)
            block=export(doc,{},'device0','upcloud:fixture',iface,'192.0.2.1')
            cp=directory/(ci+'.conf'); cp.write_text(native_config(config(block).replace('<CLIENT_PRIVATE_KEY>',doc['client_registry']['device0']['awg_private_key']))); cp.chmod(0o600)
            run(client,[tools,'setconf',ci,cp])
            for address in block['address']: command(['ip','-n',client,'address','add',address,'dev',ci,'nodad'] if ':' in address else ['ip','-n',client,'address','add',address,'dev',ci])
            command(['ip','-n',client,'link','set',ci,'mtu','1420','up'])
            for family in ('-4','-6'): command(['ip','-n',client,family,'route','add','default','dev',ci])
            for address in ('198.18.1.2','fd88::2'):
                processes.append(subprocess.Popen(['ip','netns','exec',uplink,sys.executable,'-c',ECHO,address],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            time.sleep(.2)
            for address in ('198.18.1.2','fd88::2'):
                observed = subprocess.run(['ip', 'netns', 'exec', client, sys.executable, '-c', PROBE, address],
                                          capture_output=True, text=True, timeout=12)
                if observed.returncode != 0:
                    pytest.fail('authenticated activation path failed: ' + json.dumps(path_evidence(
                        (client, server, uplink), ((client, ci), (server, iface)), tools, address)))
        candidate=copy.deepcopy(effective)
        if failure=='configuration': candidate['mtu']=1280
        candidate['peers'][0]['allowed_ips']={'ipv4':'10.70.0.9/32','ipv6':'fd42:10::9/128'}
        candidate_config=render_native_awg_config(candidate)
        if failure=='binary':
            rejected=directory/'rejected-amneziawg-go'; rejected.write_text('#!/bin/sh\nexit 71\n'); rejected.chmod(0o755)
            acquired=publisher.acquire(rejected,tools,quick)
        candidate_shared=shared+'\n[Service]\nExecStartPre=/bin/false\n' if failure=='shared-unit' else shared
        request=publisher.request(acquired,{iface:candidate_config},candidate_shared,firewall=firewall_text(candidate))
        result=publisher.apply(request)
        assert result.returncode!=0 and 'awg-consumer-refused' in result.stderr
        assert ('BEGIN PRIVATE' not in result.stdout+result.stderr)
        assert firewall.read_text()==retained_firewall
        live_firewall=run(server,['nft','list','ruleset'])
        assert '10.70.0.9' not in live_firewall and 'fd42:10::9' not in live_firewall
        boot=subprocess.run(['systemctl','is-enabled',unit.name],capture_output=True,text=True)
        if previous:
            assert boot.returncode==0 and boot.stdout.strip()=='enabled'
        else:
            assert boot.returncode!=0
        if previous:
            assert {raw:(Path(raw).stat().st_ino,Path(raw).stat().st_mode,Path(raw).read_bytes()) for raw in prior}==prior
            assert userspace_digest(unit.name)==hashlib.sha256(go.read_bytes()).hexdigest()
            assert path.read_text()==accepted and path.stat().st_mode & 0o777==0o600
            assert command(['systemctl','is-active',unit.name]).strip()=='active'
            link=json.loads(command(['ip','-n',server,'-j','link','show',iface]))[0]
            assert link['mtu']==1420
            # Keep the original client session: the restored server has lost its
            # old session keys. Pinned AWG starts a new handshake after 10+5s
            # without replies; allow that and the original TCP socket's retransmit.
            # This is one probe invocation, without resetting the client or retrying.
            for address in ('198.18.1.2','fd88::2'):
                observed = subprocess.run(['ip', 'netns', 'exec', client, sys.executable, '-c', PROBE, address, '', '40'],
                                          capture_output=True, text=True, timeout=55)
                if observed.returncode != 0:
                    pytest.fail('authenticated activation path failed: ' + json.dumps(path_evidence(
                        (client, server, uplink), ((client, ci), (server, iface)), tools, address)))
        else:
            assert not path.exists()
            assert subprocess.run(['systemctl','is-active',unit.name],capture_output=True).returncode!=0
            assert subprocess.run(['ip','-n',server,'link','show',iface],capture_output=True).returncode!=0
    finally:
        subprocess.run(['systemctl','stop',unit.name],capture_output=True,timeout=15)
        subprocess.run(['systemctl','disable',unit.name],capture_output=True,timeout=15)
        if dropin.exists(): shutil.rmtree(dropin)
        command(['systemctl','daemon-reload'])
        for process in processes:
            if process.poll() is None: process.terminate()
        for process in processes:
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        for ns in reversed(namespaces): command(['ip','netns','delete',ns])
        ownership.close()
        subprocess.run(['systemctl','reset-failed',unit.name],capture_output=True,timeout=15)
        shutil.rmtree(directory)


@pytest.mark.parametrize('previous', [True, False])
def test_firewall_retention_restores_owned_generation_or_fresh_closed_baseline(tmp_path, previous):
    assert sys.platform == 'linux' and os.geteuid() == 0
    token=uuid.uuid4().hex[:7]; namespace='afr'+token
    nft_file=Path('/etc/nftables.conf')
    assert not nft_file.is_symlink()
    original=nft_file.read_bytes() if nft_file.exists() else None
    mode=nft_file.stat().st_mode & 0o777 if original is not None else None
    bin_dir=tmp_path/'bin'; bin_dir.mkdir()
    wrapper=bin_dir/'nft'
    wrapper.write_text(f'#!/bin/sh\nexec /usr/sbin/ip netns exec {namespace} /usr/sbin/nft "$@"\n')
    wrapper.chmod(0o700)
    assert os.access(wrapper, os.X_OK), "AWG namespace adapters require executable pytest scratch space"
    values=merge_render_vars()
    values.update(_firewall_effective_check_mode=True,_firewall_tailnet_ssh_sets_was_absent=True,
                  _firewall_tailnet_initial_fragment=(ROOT/'ansible/roles/firewall/files/vpn-tailnet-ssh-sets.empty.nft').read_text())
    values['vpn']['enable_amneziawg']=True
    accepted=render_template(ROOT/'ansible/roles/firewall/templates/nftables.conf.j2',values)
    candidate=accepted.replace('10.66.66.2/32','10.66.66.9/32').replace('fd42:42:42::2/128','fd42:42:42::9/128')
    command(['ip','netns','add',namespace])
    def nft(*args,data=None): return command(['ip','netns','exec',namespace,'nft',*args],data=data)
    try:
        nft('-f','-',data='table inet foreign_owned {\n chain retained {\n counter comment "foreign-retained";\n }\n}\n')
        # An unowned distro starter must not restore its global flush ruleset.
        nft_file.write_text(accepted if previous else '#!/usr/sbin/nft -f\nflush ruleset\n')
        nft_file.chmod(0o644 if previous else 0o755)
        if previous: nft('-f',nft_file)
        target=tmp_path/'candidate.nft'; target.write_text(candidate)
        play=tmp_path/'firewall.yml'
        play.write_text(yaml.safe_dump([{'hosts':'localhost','connection':'local','gather_facts':False,
            'environment':{'PATH':str(bin_dir)+':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'},
            'vars':values,
            'tasks':[{'ansible.builtin.include_role':{'name':'firewall','tasks_from':'awg-retain'}},
                     {'name':'Publish real candidate policy','ansible.builtin.copy':{'src':str(target),'dest':str(nft_file),'mode':'0644'}},
                     {'name':'Apply real candidate policy','ansible.builtin.command':{'argv':['nft','-f',str(nft_file)]}},
                     {'ansible.builtin.include_role':{'name':'firewall','tasks_from':'awg-restore'}}]}]))
        result=subprocess.run(['ansible-playbook','-i','localhost,',str(play)],capture_output=True,text=True,timeout=90,
                              env={**os.environ,'ANSIBLE_ROLES_PATH':str(ROOT/'ansible/roles'),'ANSIBLE_CONFIG':str(ROOT/'ansible/ansible.cfg')})
        assert result.returncode==0, result.stdout+result.stderr
        live=nft('list','ruleset')
        assert 'foreign-retained' in live and '10.66.66.9' not in live and 'fd42:42:42::9' not in live
        if previous:
            assert nft_file.read_text()==accepted
            assert '10.66.66.2' in live and 'fd42:42:42::2' in live
        else:
            assert 'policy drop;' in live and 'awg-nat-' not in live, result.stdout+result.stderr
            assert 'flush ruleset' not in nft_file.read_text()
    finally:
        if original is None: nft_file.unlink(missing_ok=True)
        else: nft_file.write_bytes(original); nft_file.chmod(mode)
        command(['ip','netns','delete',namespace])
