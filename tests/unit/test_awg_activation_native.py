"""Real systemd/AWG configuration failure restores complete prior authority."""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest
import yaml

from awg_client import config, export
from awg_device_binding import resolve_binding
from template_render import merge_render_vars, render_template
from test_awg_device_binding import document
from test_awg_device_binding_native import native_config
from test_awg_dualstack_native import ECHO, PROBE, path_evidence
from test_transport_semantics_native import command, exact_awg_sources

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('previous', [True, False])
def test_failed_complete_config_restores_addresses_mtu_service_and_private_bytes(tmp_path, previous):
    go, tools = exact_awg_sources()
    assert Path('/run/systemd/system').is_dir(), 'AWG compensation requires an isolated systemd root host'
    token=uuid.uuid4().hex[:7]
    server,client,uplink='ars'+token,'arc'+token,'aru'+token
    iface,ci='ar'+token,'cr'+token
    unit=Path('/etc/systemd/system')/('awg-quick@'+iface+'.service')
    assert not unit.exists(), 'the fixture may not adopt an existing systemd unit'
    directory=tmp_path/'private'; directory.mkdir(mode=0o700)
    path=directory/(iface+'.conf')
    bin_dir=directory/'bin'; bin_dir.mkdir(mode=0o700)
    (bin_dir/'awg').symlink_to(tools)
    quick=tools.parent/'wg-quick/linux.bash'
    assert quick.is_file(), 'the exact pinned awg-quick source is required'
    doc=document(); item=doc['amneziawg_secrets']['instances'][0]
    item.update(name=iface,mtu=1420,jc=0,s1=0,s2=0)
    doc['amneziawg_secrets']['instances']= [item]
    doc['client_registry']={'device0':doc['client_registry']['device0']}
    doc['client_registry']['device0']['awg_binding']['instance']=iface
    effective=resolve_binding(doc,{},'device0','upcloud:fixture',iface).instance
    values=merge_render_vars(); values['_inst']=effective
    accepted=render_template(ROOT/'ansible/roles/amneziawg/templates/awg0.conf.j2',values)
    processes=[]; namespaces=[]
    firewall=directory/'nftables.conf'
    # This adapter only enters the owned network namespace; it executes real nft.
    nft=bin_dir/'nft'
    nft.write_text(f'#!/bin/sh\nexec /usr/sbin/ip netns exec {server} /usr/sbin/nft "$@"\n')
    nft.chmod(0o700)
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
        # A real unit-level injected candidate failure occurs after old interface teardown.
        unit.write_text(f'''[Unit]\nDescription=Owned AWG compensation fixture\n[Service]\nType=oneshot\nRemainAfterExit=yes\nNetworkNamespacePath=/run/netns/{server}\nEnvironment=PATH={bin_dir}:/usr/sbin:/usr/bin:/sbin:/bin\nEnvironment=WG_QUICK_USERSPACE_IMPLEMENTATION={go}\nExecStartPre=/bin/sh -c '! grep -q "MTU = 1280" {path}'\nExecStart=/bin/bash {quick} up {path}\nExecStop=/bin/bash {quick} down {path}\n[Install]\nWantedBy=multi-user.target\n''')
        unit.chmod(0o644); command(['systemctl','daemon-reload'])
        if previous:
            path.write_text(accepted); path.chmod(0o600)
            command(['systemctl','start',unit.name])
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
        candidate['mtu']=1280
        candidate['peers'][0]['allowed_ips']={'ipv4':'10.70.0.9/32','ipv6':'fd42:10::9/128'}
        firewall.write_text(firewall_text(candidate)); firewall.chmod(0o600)
        run(server,['nft','-f',firewall])
        if previous:
            for address in ('198.18.1.2','fd88::2'):
                assert subprocess.run(['ip','netns','exec',client,sys.executable,'-c',PROBE,address],capture_output=True,timeout=12).returncode!=0
        play=directory/'failure.yml'
        play.write_text(yaml.safe_dump([{'hosts':'localhost','connection':'local','gather_facts':False,
            'environment':{'PATH':str(bin_dir)+':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'},
            'vars':{'amneziawg_config_dir':str(directory),'_awg_instances':[candidate],
                    '_firewall_awg_restore':{'path':str(firewall),'content':base64.b64encode(retained_firewall.encode()).decode(),'mode':'0600'},
                    '_awg_unit_plan':{'changed':False},'amneziawg_role_enabled':True},
            'tasks':[{'ansible.builtin.include_role':{'name':'amneziawg','tasks_from':'configure'}}]}]))
        result=subprocess.run(['ansible-playbook','-i','localhost,',str(play)],capture_output=True,text=True,timeout=90,
                              env={**os.environ,'ANSIBLE_ROLES_PATH':str(ROOT/'ansible/roles'),'ANSIBLE_CONFIG':str(ROOT/'ansible/ansible.cfg')})
        assert result.returncode!=0 and 'awg-complete-config-activation-failed' in result.stdout+result.stderr
        assert ('BEGIN PRIVATE' not in result.stdout+result.stderr)
        assert firewall.read_text()==retained_firewall
        live_firewall=run(server,['nft','list','ruleset'])
        assert '10.70.0.9' not in live_firewall and 'fd42:10::9' not in live_firewall
        boot=subprocess.run(['systemctl','is-enabled',unit.name],capture_output=True,text=True)
        assert boot.returncode==1 and boot.stdout.strip()=='disabled'
        if previous:
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
        unit.unlink(missing_ok=True); command(['systemctl','daemon-reload'])
        for process in processes:
            if process.poll() is None: process.terminate()
        for process in processes:
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        for ns in reversed(namespaces): command(['ip','netns','delete',ns])


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
        nft_file.chmod(0o644)
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
            assert 'policy drop;' in live and 'awg-nat-' not in live
            assert 'flush ruleset' not in nft_file.read_text()
    finally:
        if original is None: nft_file.unlink(missing_ok=True)
        else: nft_file.write_bytes(original); nft_file.chmod(mode)
        command(['ip','netns','delete',namespace])
