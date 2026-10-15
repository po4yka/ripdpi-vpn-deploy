"""Real systemd/AWG configuration failure restores complete prior authority."""
from __future__ import annotations

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
from test_awg_dualstack_native import ECHO, PROBE
from test_transport_semantics_native import command, exact_awg_sources

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('previous', [True, False])
def test_failed_complete_config_restores_addresses_mtu_service_and_private_bytes(tmp_path, previous):
    go, tools = exact_awg_sources()
    assert Path('/run/systemd/system').is_dir(), 'AWG compensation requires an isolated systemd root host'
    token=uuid.uuid4().hex[:7]
    server,client='ars'+token,'arc'+token
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
    def run(ns,argv,data=None): return command(['ip','netns','exec',ns,*map(str,argv)],data=data)
    try:
        for ns in (server,client):
            command(['ip','netns','add',ns]); namespaces.append(ns)
            command(['ip','-n',ns,'link','set','lo','up'])
        left,right='rl'+token,'rr'+token
        command(['ip','link','add',left,'type','veth','peer','name',right])
        for ns,link,address in ((server,left,'192.0.2.1/30'),(client,right,'192.0.2.2/30')):
            command(['ip','link','set',link,'netns',ns]); command(['ip','-n',ns,'address','add',address,'dev',link])
            command(['ip','-n',ns,'link','set',link,'up'])
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
            for address in ('10.70.0.1','fd42:10::1'):
                processes.append(subprocess.Popen(['ip','netns','exec',server,sys.executable,'-c',ECHO,address],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            time.sleep(.2)
            for address in ('10.70.0.1','fd42:10::1'): run(client,[sys.executable,'-c',PROBE,address])
        candidate={**effective,'mtu':1280}
        play=directory/'failure.yml'
        play.write_text(yaml.safe_dump([{'hosts':'localhost','connection':'local','gather_facts':False,
            'vars':{'amneziawg_config_dir':str(directory),'_awg_instances':[candidate],
                    '_awg_unit_plan':{'changed':False},'amneziawg_role_enabled':True},
            'tasks':[{'ansible.builtin.include_role':{'name':'amneziawg','tasks_from':'configure'}}]}]))
        result=subprocess.run(['ansible-playbook','-i','localhost,',str(play)],capture_output=True,text=True,timeout=90,
                              env={**os.environ,'ANSIBLE_ROLES_PATH':str(ROOT/'ansible/roles'),'ANSIBLE_CONFIG':str(ROOT/'ansible/ansible.cfg')})
        assert result.returncode!=0 and 'awg-complete-config-activation-failed' in result.stdout+result.stderr
        assert ('BEGIN PRIVATE' not in result.stdout+result.stderr)
        boot=subprocess.run(['systemctl','is-enabled',unit.name],capture_output=True,text=True)
        assert boot.returncode==1 and boot.stdout.strip()=='disabled'
        if previous:
            assert path.read_text()==accepted and path.stat().st_mode & 0o777==0o600
            assert command(['systemctl','is-active',unit.name]).strip()=='active'
            link=json.loads(command(['ip','-n',server,'-j','link','show',iface]))[0]
            assert link['mtu']==1420
            for address in ('10.70.0.1','fd42:10::1'): run(client,[sys.executable,'-c',PROBE,address])
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
