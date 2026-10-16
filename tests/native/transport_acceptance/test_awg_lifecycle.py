"""Existing exact-pair lab plus real canonical retirement and restart handlers."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from native_common import ROOT

pytestmark = pytest.mark.native_runtime


def test_exact_pair_wire_warm_adoption_and_canonical_retirement(tmp_path):
    area = ROOT/'tests/integration/awg_source_candidate'
    assert not Path('/lab').exists(), 'isolated-AWG-lab-already-owned'
    sys.path.insert(0,str(ROOT/'ansible/roles/runtime-release/files'))
    Path('/lab').mkdir(mode=0o700)
    sources = []
    try:
        for name in ('sources.json','acceptance.py'):
            shutil.copyfile(area/name,Path('/lab')/name)
        shutil.copyfile(ROOT/'ansible/roles/amneziawg/templates/awg-quick@.service.j2','/lab/awg-quick@.service')
        for pair in ('baseline','candidate'):
            destination = Path('/opt')/pair
            assert not destination.exists(), 'isolated-AWG-source-already-owned'
            destination.symlink_to(ROOT/'.cache/four-transport-sources'/pair)
            sources.append(destination)
        spec = importlib.util.spec_from_file_location('four_awg_lab',area/'acceptance.py')
        lab = importlib.util.module_from_spec(spec);spec.loader.exec_module(lab)
        # The lab's disconnected-root assertion applies to its own namespaces;
        # this source lane retains external access only to acquire pinned engines.
        # Run the existing positive cases in an owned disconnected root namespace.
        shutil.copyfile(ROOT/'ansible/roles/runtime-release/files/runtime_build_receipt.py','/lab/runtime_build_receipt.py')
        script = tmp_path/'acceptance'
        script.write_text('import sys;sys.path.insert(0,sys.argv[1]);import acceptance;acceptance.unittest.main(module=acceptance,argv=["acceptance"],verbosity=2)')
        namespace = 'four-awg-root'
        lab.command('ip','netns','add',namespace)
        try:
            observed = subprocess.run(['ip','netns','exec',namespace,sys.executable,str(script),'/lab'],
                env={**os.environ,'PYTHONPATH':str(ROOT/'ansible/roles/runtime-release/files')},
                capture_output=True,text=True,timeout=900)
            assert observed.returncode == 0, 'exact-AWG-pair-warm-acceptance-failed'
        finally:
            lab.command('ip','netns','delete',namespace)
        # Exercise canonical handlers and two-to-one retirement with actual TUNs.
        shape = tuple(lab.PINS['wire_shapes'][0][key] for key in ('jc','jmin','jmax','s1','s2','h1','h2','h3','h4'))
        tunnels = [lab.Tunnel(i,'live','baseline',shape) for i in (60,61,62)]
        for tunnel in tunnels:
            tunnel.units = ['awg-quick@'+name+'.service' for name in tunnel.names]
        record = Path('/var/lib/ripdpi/amneziawg/instances.json')
        assert not record.exists()
        record.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            for tunnel in tunnels:
                tunnel.start();tunnel.probe()
            # Make the native unit itself restore its live TUN configuration on restart.
            for tunnel in tunnels[:2]:
                unit = Path('/etc/systemd/system')/tunnel.units[0]
                lines = '\n'.join('ExecStartPost='+line for line in (
                    f'/usr/bin/python3 /lab/wait-tun.py {tunnel.names[0]}',
                    f'/usr/sbin/ip netns exec {tunnel.names[0]} {tunnel.tools(0)} setconf {tunnel.names[0]} {tunnel.configs[0]}',
                    f'/usr/sbin/ip -n {tunnel.names[0]} address replace 10.{tunnel.index}.0.1/24 dev {tunnel.names[0]}',
                    f'/usr/sbin/ip -n {tunnel.names[0]} link set {tunnel.names[0]} up'))
                unit.write_text(unit.read_text()+'\n[Service]\n'+lines+'\n')
            Path('/lab/wait-tun.py').write_text("import subprocess,sys,time\ndeadline=time.monotonic()+10\nwhile subprocess.run(['ip','-n',sys.argv[1],'link','show',sys.argv[1]],capture_output=True).returncode:\n if time.monotonic()>deadline: raise SystemExit(1)\n time.sleep(.05)\n")
            lab.command('systemctl','daemon-reload')
            tasks = yaml.safe_load((ROOT/'ansible/roles/amneziawg/tasks/enable.yml').read_text())
            activate = next(row for row in tasks if row['name'] == 'Apply changed AmneziaWG runtimes to current instances')
            handlers = yaml.safe_load((ROOT/'ansible/roles/amneziawg/handlers/main.yml').read_text())
            def converge(changed):
                play = [{'hosts':'localhost','connection':'local','gather_facts':False,
                    'vars':{'_awg_instances':[{'name':t.names[0]} for t in tunnels[:2]],'amneziawg_role_enabled':True,
                            'runtime_build_results':{'amneziawg-go':{'changed':changed}}},
                    'tasks':[activate,{'ansible.builtin.meta':'flush_handlers'}], 'handlers':handlers}]
                path = tmp_path/'activate.yml';path.write_text(yaml.safe_dump(play))
                result = subprocess.run(['ansible-playbook','-i','localhost,',str(path)],capture_output=True,text=True,timeout=60)
                assert result.returncode == 0, 'canonical-AWG-runtime-handler-refused'
            pids = [t.pid() for t in tunnels]
            converge(True)
            assert all(t.pid() != pid for t,pid in zip(tunnels[:2],pids))
            for tunnel in tunnels[:2]:
                tunnel.initiator=0;tunnel.probe()
            assert tunnels[2].pid() == pids[2];tunnels[2].probe()
            pids = [t.pid() for t in tunnels]
            converge(False)
            assert pids == [t.pid() for t in tunnels]
            retired = tunnels[1]
            for tunnel in tunnels[:2]:
                lab.command('systemctl','enable',tunnel.units[0])
            play = [{'hosts':'localhost','connection':'local','gather_facts':False,
                'vars':{'amneziawg_config_dir':'/lab','_awg_instances':[{'name':tunnels[0].names[0]}], '_awg_previous':{'config_dir':'/lab'},
                        '_awg_obsolete':[retired.names[0]]},
                'tasks':[{'ansible.builtin.import_tasks':str(ROOT/'ansible/roles/amneziawg/tasks/retire-instances.yml')}]}]
            path=tmp_path/'retire.yml';path.write_text(yaml.safe_dump(play))
            for _ in range(2):
                result=subprocess.run(['ansible-playbook','-i','localhost,',str(path)],capture_output=True,text=True,timeout=60,env={**os.environ,'ANSIBLE_ROLES_PATH':str(ROOT/'ansible/roles')})
                assert result.returncode == 0, 'canonical-AWG-retirement-refused'
                assert subprocess.run(['ip','-n',retired.names[0],'link','show',retired.names[0]],capture_output=True).returncode != 0
                tunnels[0].probe();tunnels[2].probe()
        finally:
            for tunnel in tunnels:
                for unit in tunnel.units:
                    subprocess.run(['systemctl','disable',unit],capture_output=True,timeout=15)
                tunnel.close()
            lab.command('systemctl','daemon-reload')
            record.unlink(missing_ok=True)
            record.parent.rmdir()
    finally:
        for path in sources:
            path.unlink()
        shutil.rmtree('/lab')
        for path in ('/usr/local/lib/awg-candidate','/var/lib/ripdpi/runtime-build-staging/awg-candidate'):
            if Path(path).exists():shutil.rmtree(path)
        Path('/var/lib/ripdpi/runtime-build-receipts/awg-candidate.json').unlink(missing_ok=True)
