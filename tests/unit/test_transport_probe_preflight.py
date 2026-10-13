"""Real Ansible probe admission refuses incomplete credentials before host mutation."""
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PREPARE = ROOT / 'ansible/playbooks/tasks/transport-egress-prepare.yml'


@pytest.mark.parametrize('case', ['accepted', 'missing-client', 'missing-url', 'missing-cohort-client', 'hysteria-missing-client'])
def test_probe_admission_precedes_any_mutation(tmp_path, case):
    tasks = yaml.safe_load(PREPARE.read_text())[:3]
    tasks.append({'name':'Observe admitted inputs', 'ansible.builtin.copy':{
        'dest':str(tmp_path/'admitted'), 'content':'admitted'}})
    variables = {
        'vpn':{'enable_xray_reality':True, 'enable_nginx_xhttp':False, 'enable_hysteria':False},
        'transport_runtime_probe_url':'http://owned.example/healthz',
        'transport_runtime_probe_clients':{'xray':'acceptance','hysteria':'acceptance-h'},
        'xray':{'clients':[{'name':'acceptance','uuid':'synthetic-private-uuid'}], 'cohorts':[]},
        'hysteria':{'clients':[]}}
    if case == 'missing-client':
        variables['xray']['clients'] = []
    elif case == 'missing-url':
        variables['transport_runtime_probe_url'] = ''
    elif case == 'missing-cohort-client':
        variables['xray']['cohorts'] = [{'name':'cohort-one', 'clients':['recipient']}]
    elif case == 'hysteria-missing-client':
        variables['vpn'].update(enable_xray_reality=False, enable_hysteria=True)
    playbook = tmp_path/'play.yml'
    playbook.write_text(yaml.safe_dump([{'hosts':'localhost','connection':'local','gather_facts':False,
        'vars':variables,'tasks':tasks}], sort_keys=False))
    result = subprocess.run([str(Path(sys.executable).parent/'ansible-playbook'), '-i', 'localhost,',
        str(playbook)], cwd=tmp_path, text=True, capture_output=True, timeout=30)
    assert (result.returncode == 0) == (case == 'accepted'), result.stdout+result.stderr
    assert (tmp_path/'admitted').exists() == (case == 'accepted')
    assert 'synthetic-private-uuid' not in result.stdout+result.stderr
