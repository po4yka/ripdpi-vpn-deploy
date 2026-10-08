"""Exercise policy/apply identity and canonical drift comparisons offline."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o700)


@pytest.mark.parametrize('refuse', [False, True])
def test_apply_uses_the_validated_snapshot_even_if_original_is_replaced(tmp_path, refuse):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy(ROOT / 'scripts/policy-plan.sh', scripts)
    plan = tmp_path / 'terraform/providers/upcloud/prod.tfplan'
    plan.parent.mkdir(parents=True)
    plan.write_text('reviewed-plan')
    log = tmp_path / 'calls'
    executable(scripts / 'terraform-env.sh', '''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(args)+'\\n')
if args[0]=='show':
    p=pathlib.Path(args[2]); print(json.dumps({'snapshot':p.read_text()}))
    pathlib.Path(os.environ['ORIGINAL']).write_text('foreign-plan')
else:
    assert pathlib.Path(args[1]).read_text()=='reviewed-plan'
''')
    executable(scripts / 'check-tf-plan.sh', '''#!/usr/bin/env python3
import json, os, sys
assert json.load(open(sys.argv[1])) == {'snapshot':'reviewed-plan'}
sys.exit(int(os.environ['REFUSE']))
''')
    result = subprocess.run(['bash', str(scripts / 'policy-plan.sh'), 'apply'],
                            env={**os.environ, 'CALLS':str(log), 'ORIGINAL':str(plan),
                                 'REFUSE':str(int(refuse)), 'PROVIDER':'upcloud', 'ENV':'prod'},
                            capture_output=True, text=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert (result.returncode != 0) == refuse, result.stderr
    assert len(calls) == (1 if refuse else 2)
    if not refuse:
        assert calls[0][2] == calls[1][1]
    assert not Path(calls[0][2]).exists()
    assert plan.read_text() == 'foreign-plan'


@pytest.mark.parametrize('mutation', ['none', 'port', 'credential', 'malformed'])
def test_real_ansible_drift_comparison_detects_changes_without_disclosing_values(tmp_path, mutation):
    # Only the read/compare tasks run here; version/service probes need a guest.
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from template_render import merge_render_vars
    variables = merge_render_vars()
    variables.update(xray_etc_dir=str(tmp_path), role_path=str(ROOT / 'ansible/roles/xray'),
                     ansible_search_path=[str(ROOT / 'ansible/roles/xray')],
                     p0_reality_shape_template=str(ROOT / 'ansible/templates/p0-reality-shape.json.j2'))
    source_tasks = yaml.safe_load((ROOT / 'ansible/roles/xray/tasks/drift.yml').read_text())[:3]
    setup = [source_tasks[0], {'name':'Create synthetic deployed configuration',
             'ansible.builtin.template':{'src':str(ROOT / 'ansible/roles/xray/templates/config.json.j2'),
                                        'dest':str(tmp_path / 'config.json'), 'mode':'0600'}, 'no_log':True}]
    mutate = '''import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); mode=sys.argv[2]
d=json.loads(p.read_text())
if mode=='port': d['inbounds'][0]['port']=31337
if mode=='credential': d['inbounds'][0]['settings']['clients'][0]['id']='PRIVATE-DRIFT-CANARY'
p.write_text('{BROKEN-PRIVATE-CANARY' if mode=='malformed' else json.dumps(d))
'''
    setup.append({'name':'Mutate synthetic deployed config', 'ansible.builtin.command':
                  {'argv':[sys.executable, '-c', mutate, str(tmp_path / 'config.json'), mutation]},
                  'changed_when':False,'no_log':True})
    play = tmp_path / 'drift.yml'
    play.write_text(yaml.safe_dump([{'name':'Offline drift regression', 'hosts':'localhost',
                    'connection':'local','gather_facts':False, 'vars':variables,
                    'tasks':setup+source_tasks[1:]}]))
    result = subprocess.run(['ansible-playbook','-i','localhost,',str(play)], capture_output=True,
                            text=True, env={**os.environ,'ANSIBLE_CONFIG':str(ROOT / 'ansible/ansible.cfg'),
                                            'ANSIBLE_BECOME':'false'})
    assert (result.returncode == 0) == (mutation == 'none'), result.stdout + result.stderr
    assert 'could not be found' not in result.stdout + result.stderr
    assert 'PRIVATE-DRIFT-CANARY' not in result.stdout + result.stderr
    assert 'BROKEN-PRIVATE-CANARY' not in result.stdout + result.stderr
    assert 'Compare complete deployed and canonical Xray configuration' in result.stdout


@pytest.mark.parametrize('zone', ['', 'zone-b'])
def test_fleet_passes_optional_zone_as_environment_not_command(tmp_path, zone):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy(ROOT / 'scripts/fleet-rotate.sh', scripts)
    executable(scripts / 'terraform-env.sh', '#!/bin/sh\necho 192.0.2.7\n')
    executable(scripts / 'blue-green.sh', '#!/bin/sh\nprintf "%s" "$GREEN_ZONE" > "$ZONE_CAPTURE"\n')
    executable(scripts / 'audit-log.sh', '#!/bin/sh\nexit 0\n')
    executable(tmp_path / 'bin/timeout', '#!/bin/sh\nexit 0\n')
    plan = tmp_path / 'plan.yml'
    plan.write_text(yaml.safe_dump({'id':'zone-test','min_active':1,'rotations':[
        {'current':'upcloud:prod','new_env':'green','new_zone':zone}]}))
    capture = tmp_path / 'zone'
    result = subprocess.run(['bash',str(scripts / 'fleet-rotate.sh'),'--plan',str(plan)],
                            input='yes\n', capture_output=True, text=True,
                            env={**os.environ,'ZONE_CAPTURE':str(capture),
                                 'PATH':str(tmp_path / 'bin')+os.pathsep+os.environ['PATH']})
    assert result.returncode == 0, result.stdout + result.stderr
    assert capture.read_text() == zone


@pytest.mark.parametrize('present', [False, True])
def test_drift_requires_nonempty_exact_host_selection_and_preserves_failure(tmp_path, present):
    bindir = tmp_path / 'bin'
    called = tmp_path / 'playbook-called'
    inventory = {'vpn': {'hosts':['node-a']} if present else {}}
    executable(bindir / 'ansible-inventory', '#!/bin/sh\nprintf \'%s\\n\' \''+json.dumps(inventory)+'\'\n')
    executable(bindir / 'ansible-playbook', '#!/bin/sh\ntest "$ANSIBLE_HOST_KEY_CHECKING" = True\ntouch "$CALLED"\nexit 23\n')
    secrets = tmp_path / 'secrets.yml'
    secrets.write_text((ROOT / 'secrets/prod.secrets.example.yaml').read_text())
    result = subprocess.run(['bash',str(ROOT / 'scripts/diff-secrets.sh')],
                            env={**os.environ,'PATH':str(bindir)+os.pathsep+os.environ['PATH'],
                                 'ANSIBLE_SSH_PRIVATE_KEY_FILE':str(tmp_path / 'key'),
                                 'ANSIBLE_LIMIT':'node-a','SECRETS_FILE':str(secrets),'CALLED':str(called)},
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert called.exists() == present
    if present:
        assert result.returncode == 23


@pytest.mark.parametrize('version,success', [('26.3.27',True),('26.3.270',False)])
def test_binary_version_pins_compare_complete_versions(tmp_path, version, success):
    xray_tasks = yaml.safe_load((ROOT / 'ansible/roles/xray/tasks/drift.yml').read_text())
    drift_play = yaml.safe_load((ROOT / 'ansible/playbooks/diff-secrets.yml').read_text())[0]
    tasks = [xray_tasks[-1],next(t for t in drift_play['tasks'] if t['name']=='Compare Hysteria binary version with its pin')]
    play = tmp_path / 'versions.yml'
    play.write_text(yaml.safe_dump([{'hosts':'localhost','gather_facts':False,'connection':'local',
        'vars':{'vpn':{'enable_hysteria':True}, 'xray':{'version':'v26.3.27'},
                'hysteria':{'version':'v2.9.0'},
                '_xray_drift_version':{'stdout_lines':[f'Xray {version} fixture']},
                '_hysteria_drift_version':{'stdout':'Version: v2.9.0\n'}},'tasks':tasks}]))
    result = subprocess.run(['ansible-playbook','-i','localhost,',str(play)], capture_output=True,text=True)
    assert (result.returncode==0) == success, result.stdout + result.stderr


@pytest.mark.parametrize('deploy_failure, blue_present, green_present, pinned', [
    (False, True, True, True), (True, True, True, True),
    (False, False, True, True), (False, True, False, True), (False, True, True, False),
])
def test_blue_green_uses_exact_alias_and_one_secret_file_through_make(tmp_path, deploy_failure, blue_present, green_present, pinned):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy(ROOT / 'scripts/blue-green.sh', scripts)
    tfvars = tmp_path / 'terraform/providers/upcloud/environments/green.tfvars'
    tfvars.parent.mkdir(parents=True)
    tfvars.write_text('# synthetic input\n')
    executable(scripts / 'terraform-env.sh', '''#!/bin/sh
case "$*" in
  *server_hostname*) printf 'node-%s\\n' "$ENV" ;;
  *server_ipv4*) echo 192.0.2.7 ;;
  *ssh_port*) echo 2222 ;;
  *) exit 1 ;;
esac
''')
    executable(scripts / 'render-inventory.sh', '#!/bin/sh\ntouch "$RENDER_CALLS"\n')
    executable(tmp_path / 'bin/sops', '#!/bin/sh\necho "synthetic: true"\n')
    executable(tmp_path / 'bin/make', '''#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
with open(os.environ['CALLS'], 'a') as f:
    f.write(json.dumps({'args':args, 'limit':os.environ.get('ANSIBLE_LIMIT'),
                       'secrets':os.environ.get('SECRETS_FILE')})+'\\n')
if 'deploy' in args and os.environ['DEPLOY_FAILURE']=='1': sys.exit(23)
''')
    executable(tmp_path / 'bin/ansible-inventory', '#!/bin/sh\necho \'{"vpn":{"hosts":' + json.dumps((['node-green'] if green_present else []) + (['node-prod'] if blue_present else [])) + '}}\'\n')
    executable(tmp_path / 'bin/ssh-keygen', '#!/bin/sh\nexit ' + ('0' if pinned else '1') + '\n')
    sops = tmp_path / 'synthetic.sops.yaml'
    sops.touch()
    log = tmp_path / 'calls'
    result = subprocess.run(['bash',str(scripts / 'blue-green.sh')], input='\n\nyes\n',
        capture_output=True,text=True,env={**os.environ, 'PATH':str(tmp_path / 'bin')+os.pathsep+os.environ['PATH'],
        'CALLS':str(log),'RENDER_CALLS':str(tmp_path / 'rendered'),'DEPLOY_FAILURE':str(int(deploy_failure)), 'BLUE_ENV':'prod','GREEN_ENV':'green',
        'PROVIDER':'upcloud','SOPS_FILE':str(sops),'ANSIBLE_SSH_PRIVATE_KEY_FILE':str(tmp_path / 'key'),
        'GREEN_TAILNET_HANDOFF':str(tmp_path / 'handoff'),'DEPLOY_SSH_CONTEXTS_FILE':str(tmp_path / 'contexts')})
    if not blue_present:
        assert result.returncode != 0
        assert not log.exists()
        return
    if not pinned or not green_present:
        assert result.returncode != 0
        if not pinned:
            assert not (tmp_path / 'rendered').exists()
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert not any('deploy' in c['args'] for c in calls)
        return
    assert result.returncode == (23 if deploy_failure else 0), result.stdout + result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    deploy = next(c for c in calls if 'deploy' in c['args'])
    assert deploy['limit']=='node-green'
    assert 'dry-run' in deploy['args']
    assert calls[0]['limit']=='node-prod'
    assert deploy['secrets']==calls[0]['secrets']
    assert not Path(deploy['secrets']).exists()
    green_verifications = [c for c in calls if 'smoke-test' in c['args']]
    assert bool(green_verifications) != deploy_failure
    if not deploy_failure:
        assert green_verifications[0]['limit']=='node-green'
        assert green_verifications[0]['secrets']==deploy['secrets']


@pytest.mark.parametrize('probe_failure', ['none', 'exit', 'missing', 'malformed'])
def test_single_profile_matrix_requires_fresh_complete_probe_reports(tmp_path, probe_failure):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy(ROOT / 'scripts/transport-reachability-matrix.sh', scripts)
    executable(scripts / 'terraform-env.sh', '''#!/bin/sh
case "$*" in *server_hostname*) echo node-a ;; *server_ipv4*) echo 192.0.2.7 ;; *) exit 1 ;; esac
''')
    executable(scripts / 'render-inventory.sh', '#!/bin/sh\ntest "$COHORTS" = ci-p0\n')
    executable(tmp_path / 'bin/make', '#!/bin/sh\ntest "$ANSIBLE_LIMIT" = node-a\n')
    executable(scripts / 'probe-sni-survival.sh', '''#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = --out ]; then shift; echo '{"synthetic":true}' > "$1"; fi
  shift
done
''')
    executable(scripts / 'run-rkn-block-checker.sh', '''#!/usr/bin/env python3
import os, pathlib, sys
mode=os.environ['PROBE_FAILURE']
if mode=='exit': sys.exit(23)
if mode=='missing': sys.exit(0)
p=pathlib.Path(sys.argv[sys.argv.index('--state-dir')+1])/sys.argv[1]/'latest.json'
p.parent.mkdir(parents=True)
p.write_text('{malformed' if mode=='malformed' else '{"synthetic":true}')
''')
    secrets = tmp_path / 'secrets.yml'
    secrets.write_text('synthetic: true\n')
    output = tmp_path / 'output'
    env={**os.environ,'PATH':str(tmp_path / 'bin')+os.pathsep+os.environ['PATH'],
         'PROVIDER':'upcloud','ENV':'test','TAILNET_HANDOFFS':'synthetic', 'PROBE_FAILURE':probe_failure}
    command=['bash', str(scripts / 'transport-reachability-matrix.sh'), '--profile','p0',
             '--secrets',str(secrets),'--output-dir',str(output)]
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    assert (result.returncode==0) == (probe_failure=='none'),result.stderr
    assert (output / 'index.json').exists() == (probe_failure=='none')
    if probe_failure=='none':
        index=json.loads((output / 'index.json').read_text())
        assert index['transport_client_acceptance']=='not_measured'
        assert 'runner_direct_baseline' in index['reports']
        repeat=subprocess.run(command,env=env,capture_output=True,text=True)
        assert repeat.returncode != 0


@pytest.mark.parametrize('profile', ['self-steal', 'cdn', 'subscription', 'subscription-only'])
def test_drift_shared_nginx_and_subscription_service_ownership(tmp_path, profile):
    play = yaml.safe_load((ROOT / 'ansible/playbooks/diff-secrets.yml').read_text())[0]
    toggles = {
        'enable_xray_reality': False, 'enable_nginx_xhttp': False,
        'enable_hysteria': False, 'enable_amneziawg': False,
        {'self-steal': 'enable_reality_self_steal', 'cdn': 'enable_cdn_front',
         'subscription': 'enable_subscription_host', 'subscription-only': 'enable_xray_reality'}[profile]: True,
    }
    tasks = [t for t in play['tasks'] if t['name'] in {
        'Compare transport service state with profile toggles',
        'Reject active AmneziaWG instances in a disabled profile',
    }]
    if profile == 'subscription-only':
        toggles.update(enable_hysteria=True, enable_amneziawg=True)
        # Actual production include must skip on this profile, even with inherited toggles.
        tasks.insert(0, next(t for t in play['tasks'] if t['name']=='Compare canonical Xray configuration and version'))
    path = tmp_path / 'ownership.yml'
    path.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'connection': 'local',
        'vars': {'vpn': toggles, 'vpn_subscription_only': profile=='subscription-only',
                 'ansible_facts': {'services': {'nginx.service': {'state': 'running'}}}}, 'tasks': tasks}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path)], capture_output=True, text=True,
                            env={**os.environ, 'ANSIBLE_ROLES_PATH': str(ROOT / 'ansible/roles')})
    assert result.returncode == 0, result.stdout + result.stderr
