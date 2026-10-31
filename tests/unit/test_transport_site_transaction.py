"""Actual localhost Ansible composition failures; no native runtime claim."""
import ast
import copy
from html.parser import HTMLParser
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / 'ansible/playbooks/site.yml'
BEGIN = ROOT / 'ansible/playbooks/tasks/transport-ingress-begin.yml'
HELPER = ROOT / 'ansible/roles/nginx-xhttp/files/nginx_transaction.py'
EGRESS_TASKS = ROOT / 'ansible/roles/transport-egress/tasks'
JOURNAL = '/var/lib/vpn-nginx-publication/nginx.service/site.json'
PENDING = '/var/lib/vpn-nginx-publication/nginx.service/pending.json'
OUTER_HELPER = '/usr/local/libexec/ripdpi-transport-egress/transport_runtime_outer.py'
OUTER_STATE = '/var/lib/ripdpi/transport-runtime'
OUTER_RECORD = OUTER_STATE + '/outer.json'
RUNTIME_FILES = ROOT / 'ansible/roles/runtime-release/files'
DECLARE = 'Declare bounded desired ingress paths without reading runtime secrets'
CAPTURE = 'Capture or check protected ingress under its existing shared unit lock'


def _canonical_href(html):
    class CanonicalLinks(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []
            self.in_head = False
            self.in_body = False
            self.heads = 0
            self.invalid = False

        def handle_starttag(self, tag, attributes):
            if tag == 'body':
                self.in_body = True
                self.in_head = False
            if tag == 'head':
                self.heads += 1
                if self.in_body or self.heads != 1:
                    self.invalid = True
                self.in_head = not self.in_body
            if tag != 'link':
                return
            rels = [value for key, value in attributes if key == 'rel']
            if not any('canonical' in (value or '').lower().split() for value in rels):
                return
            hrefs = [value for key, value in attributes if key == 'href']
            if not self.in_head or len(rels) != 1 or len(hrefs) != 1:
                self.invalid = True
            self.links.append(hrefs[0] if len(hrefs) == 1 else None)

        def handle_endtag(self, tag):
            if tag == 'head':
                self.in_head = False

    page = CanonicalLinks()
    page.feed(html)
    page.close()
    assert not page.invalid and len(page.links) == 1
    assert page.links[0]
    return page.links[0]


@pytest.mark.parametrize('malformed', [
    '<head><link rel="canonical" href="https://wrong.example.invalid/" href="https://new-origin.example.invalid/"></head>',
    '<head><link rel="alternate" rel="canonical" href="https://new-origin.example.invalid/"></head>',
    '<body><link rel="canonical" href="https://new-origin.example.invalid/"></body>',
    '<head><body><link rel="canonical" href="https://new-origin.example.invalid/"></body>',
    '<head></head><body><head><link rel="canonical" href="https://new-origin.example.invalid/"></head></body>',
    '<head><link rel="canonical"></head>',
    '<head><link rel="canonical" href="https://new-origin.example.invalid/"><link rel="alternate canonical" href="https://wrong.example.invalid/"></head>',
])
def test_canonical_extraction_rejects_ambiguous_or_non_head_links(malformed):
    with pytest.raises(AssertionError):
        _canonical_href(malformed)


def protected():
    return copy.deepcopy(next(task for task in yaml.safe_load(SITE.read_text())[0]['tasks'] if 'block' in task))


def test_site_closes_complete_protected_block_before_unrelated_roles():
    play = yaml.safe_load(SITE.read_text())[0]
    assert [value['role'] for value in play['roles']] == ['baseline', 'package_updates']
    block = protected()
    names = [value.get('ansible.builtin.import_role', {}).get('name') for value in block['block']]
    assert [name for name in names if name] == ['firewall', 'intrusion_prevention', 'nginx-xhttp', 'geodata', 'tailnet-management',
                                             'transport-egress', 'xray', 'reality-self-steal', 'nginx-xhttp', 'hysteria', 'nginx-xhttp']
    assert block['block'][0]['ansible.builtin.import_tasks'] == 'tasks/transport-ingress-begin.yml'
    assert block['block'][1]['vars']['firewall_site_transaction'] is True
    assert 'always' in block['block'][1]['tags']
    assert block['block'][-4]['ansible.builtin.import_tasks'] == 'tasks/transport-egress-activate.yml'
    assert block['block'][-3]['ansible.builtin.import_tasks'] == 'tasks/transport-ingress-commit.yml'
    finish = block['block'][-1]
    assert finish['ansible.builtin.command']['argv'] == [
        'python3', '-Es', '/usr/local/libexec/ripdpi-consumer/firewall_consumer.py', 'finish', '--owner', 'site']
    assert finish['when'] == '_firewall_site_transaction_active | default(false) | bool'
    assert play['tasks'][2]['ansible.builtin.import_role']['name'] == 'cdn-front'
    assert 'post_tasks' not in play
    assert block['rescue'][0]['ansible.builtin.include_tasks'] == 'tasks/transport-ingress-recover-commit.yml'
    assert block['rescue'][1]['ansible.builtin.include_role']['tasks_from'] == 'quiesce'
    assert block['rescue'][2]['ansible.builtin.include_tasks'] == 'tasks/transport-ingress-restore.yml'
    rollback = next(value for value in block['rescue']
                    if value.get('ansible.builtin.include_role', {}).get('tasks_from') == 'rollback')
    restore = next(value for value in block['rescue'] if value['name'] == 'Restore initial firewall after protected convergence refusal')
    assert 2 < block['rescue'].index(restore) < block['rescue'].index(rollback)
    assert restore['ansible.builtin.command']['argv'][-1] == 'restore'
    assert restore['when'] == ['_firewall_rescue_helper.stat.exists',
                              "(_firewall_rescue_owner.stdout | from_json).owner == 'site'"]
    assert block['rescue'][-1]['ansible.builtin.fail']['msg'].startswith('Protected transport staging failed;')
    assert all(value['ansible.builtin.import_role']['public'] for value in block['block'] if 'ansible.builtin.import_role' in value)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def _prestep(root, state_owner):
    source = yaml.safe_load(BEGIN.read_text())
    names = [value['name'] for value in source]
    steps = copy.deepcopy(source[names.index(DECLARE) + 1:names.index(CAPTURE)])
    stat_paths = {JOURNAL: str(root / 'nginx-state/nginx.service/site.json'), PENDING: str(root / 'nginx-state/nginx.service/pending.json'),
                  OUTER_HELPER: str(root / 'libexec/transport_runtime_outer.py'), OUTER_STATE: str(root / 'ripdpi-state/transport-runtime'),
                  OUTER_RECORD: str(root / 'ripdpi-state/transport-runtime/outer.json')}
    for step in steps:
        if 'ansible.builtin.stat' in step:
            step['ansible.builtin.stat']['path'] = stat_paths[step['ansible.builtin.stat']['path']]
        elif 'ansible.builtin.command' in step:
            assert step['ansible.builtin.command']['argv'] == ['/usr/bin/python3', '-Es', OUTER_HELPER, 'status']
            step['ansible.builtin.command']['argv'] = [sys.executable, str(root / 'outer_status.py'), str(root)]
    # The production judgement of the outer route's state directory expects a root owner; the harness expects the test user, like the helper admission.
    retargeted = 0
    for step in steps:
        if isinstance(step.get('when'), list):
            conditions = [value.replace('.stat.uid == 0', f'.stat.uid == {state_owner}') for value in step['when']]
            retargeted += conditions != step['when']
            step['when'] = conditions
    # Under root the expected owner is already 0, so nothing is rewritten.
    assert retargeted == (0 if state_owner == 0 else 1)
    return steps


def _helper_authority(root):
    """The production admission task, retargeted at the harness tree and the test user's ownership."""
    task = copy.deepcopy(yaml.safe_load((EGRESS_TASKS / 'helper-authority.yml').read_text())[0])
    argv = task['ansible.builtin.command']['argv']
    argv[0] = sys.executable
    for old, new, count in [
            ("pathlib.Path('/var/lib/ripdpi')", f"pathlib.Path('{root}/ripdpi-state')", 1),
            ("pathlib.Path('/usr/local/libexec/ripdpi-transport-egress')", f"pathlib.Path('{root}/libexec')", 1),
            ('[*reversed(root.parents), root]', f"[*[p for p in reversed(root.parents) if p.is_relative_to('{root}')], root]", 1),
            ('info.st_uid != 0', f'info.st_uid != {os.geteuid()}', 2)]:
        assert argv[3].count(old) == count and 'consumer-helper-authority-refused' in argv[3]
        argv[3] = argv[3].replace(old, new)
    return [task]


def _fixture(tmp_path, failure, state_owner=None):
    root = tmp_path.resolve()
    root.chmod(0o700)
    accepted = root / 'frontend.conf'
    accepted.write_bytes(b'accepted frontend')
    accepted.chmod(0o640)
    (root / 'state').write_text('accepted-running')
    (root / 'events').write_text('')
    ingress = root / 'ingress'
    ingress.mkdir(mode=0o700)
    context = {'check': False, 'owners': [{'owner': owner, 'roots': [str(ingress)], 'paths': [str(ingress / (owner + '.conf'))], 'prune_releases': None}
                                        for owner in ['nginx-xhttp', 'public-tls', 'reality-self-steal']]}
    (root / 'context.json').write_text(json.dumps(context))
    driver = root / 'ingress_driver.py'
    # The real production transaction API owns all file/receipt/journal checks.
    # Only its Linux runtime adapter and root ancestors are modeled here; native
    # tests separately prove systemd/nginx adoption and privilege isolation.
    driver.write_text('''import base64,importlib.util,json,os,stat,sys
from pathlib import Path
root=Path(sys.argv[1]); action=sys.argv[2]
spec=importlib.util.spec_from_file_location('nginx',sys.argv[3]);tx=importlib.util.module_from_spec(spec);spec.loader.exec_module(tx)
def safe(path,missing=False):
 p=Path(path)
 if not p.is_relative_to(root) or '..' in p.parts: raise tx.TransactionError('path')
 for q in [root,*[root/x for x in list(p.relative_to(root).parents)[::-1]],p]:
  try: info=q.lstat()
  except FileNotFoundError:
   if missing:return
   raise
  if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:raise tx.TransactionError('unsafe-parent')
tx.safe=safe;tx.STATE_ROOT=root/'nginx-state'
tx.service_state=lambda unit:dict(active=False,exists=True,unit_file_state='disabled')
def command(argv):
 if '/usr/local/libexec/ripdpi-consumer/firewall_consumer.py' in argv:
  (root/'firewall-owner').unlink(missing_ok=True)
 if argv[-1]=='finish':
  if (root/'outer-fail').exists():raise tx.TransactionError('runtime-command')
  (root/'outer-open').unlink(missing_ok=True)
 return ''
tx.command=command;tx.restore_enabled=lambda *args:None
context=json.loads((root/'context.json').read_text()); state=tx.STATE_ROOT/'nginx.service'
def write(owner,payload):
 value=next(v for v in tx.site_request(context) if v['owner']==owner)
 value['files']=[dict(path=value['files'][0]['path'],kind='file',uid=os.geteuid(),gid=os.getegid(),mode=0o640,content_b64=base64.b64encode(payload).decode())]
 receipt=tx.owned_receipt(value)
 with tx.unit_lock(state):
  tx.site_authorize(state,value,receipt)
  for row in value['files']:tx.apply(Path(row['path']),{k:v for k,v in row.items() if k!='path'},[])
  tx.persist(state/(owner+'.activated.json'),receipt)
if action=='seed':
 for owner in tx.SITE_OWNERS:write(owner,b'accepted ingress')
elif action=='publish':write(sys.argv[4],b'changed ingress')
elif action=='interrupt':
 tx.site_transaction('begin',context)
 for owner in ['nginx-xhttp','reality-self-steal']:write(owner,b'changed ingress')
elif action=='pend':
 value=next(v for v in tx.site_request(context) if v['owner']=='nginx-xhttp')
 value['files']=[dict(path=value['files'][0]['path'],kind='file',uid=os.geteuid(),gid=os.getegid(),mode=0o640,content_b64=base64.b64encode(b'changed ingress').decode())]
 path=Path(value['files'][0]['path'])
 tx.persist(state/'pending.json',dict(schema=2,phase='prepared',candidate='candidate-'+'0'*32,request=value,files={str(path):tx.capture(path)},active=False,
  service=dict(active=False,exists=True,unit_file_state='disabled'),owner='nginx-xhttp',receipt=tx.capture(state/'nginx-xhttp.activated.json'),next_receipt=tx.receipt_row(tx.owned_receipt(value))))
else:print(json.dumps(tx.site_transaction(action,context,finish_firewall=action=='commit')))
if action!='recover-commit':
 with (root/'events').open('a') as stream:stream.write('ingress-'+action+'\\n')
''')
    script = HELPER
    argv = [sys.executable, str(driver), str(root), 'seed', str(script)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    (root / 'events').write_text('')
    def event(value):
        return {'ansible.builtin.command': {'argv': [sys.executable, '-c', 'from pathlib import Path;import sys;p=Path(sys.argv[1]);p.write_text(p.read_text()+sys.argv[2]+"\\n")', str(root / 'events'), value]},
                'changed_when': False, 'check_mode': False}
    def invoke(action, owner=None):
        args = [sys.executable, str(driver), str(root), action, str(script)] + ([owner] if owner else [])
        return {'ansible.builtin.command': {'argv': args}, 'no_log': True, 'changed_when': False}
    roles = root / 'roles'
    for role in ['transport-egress', 'xray', 'hysteria', 'nginx-xhttp', 'reality-self-steal',
                 'firewall', 'intrusion_prevention', 'geodata', 'tailnet-management']:
        _write(roles / role / 'defaults/main.yml', {role.replace('-', '_') + '_parse_visible': True})
    for role in ['intrusion_prevention', 'geodata', 'tailnet-management']:
        _write(roles / role / 'tasks/main.yml', [])
    _write(roles / 'nginx-xhttp/tasks/tls-bootstrap.yml', [])
    _write(roles / 'nginx-xhttp/tasks/tls-finish.yml', [])
    (root / 'firewall-policy').write_bytes(b'accepted firewall')
    _write(roles / 'firewall/tasks/main.yml', [
        {'ansible.builtin.set_fact': {'_firewall_site_transaction_active': True}},
        {'ansible.builtin.copy': {'content': 'candidate firewall', 'dest': str(root / 'firewall-policy'), 'mode': '0600'}},
        {'ansible.builtin.copy': {'content': 'site', 'dest': str(root / 'firewall-owner'), 'mode': '0600'}}])
    _write(roles / 'transport-egress/tasks/prepare-site.yml', [
        {'ansible.builtin.copy': {'src': str(accepted), 'dest': str(root / 'previous.conf'), 'mode': '0600'}},
        {'ansible.builtin.set_fact': {'_transport_egress_transaction_started': True, 'transport_egress_role_enabled': True, 'transport_egress_warp_enabled': False}}, event('stage')])
    for role in ['xray', 'hysteria']:
        _write(roles / role / 'tasks/main.yml', [event(role), {'ansible.builtin.copy': {'content': 'changed frontend', 'dest': str(accepted), 'mode': '0640'}},
            {'ansible.builtin.fail': {'msg': 'controlled protected failure'}, 'when': f"failure == '{role}'"}])
    for role in ['nginx-xhttp', 'reality-self-steal']:
        _write(roles / role / 'tasks/main.yml', [invoke('publish', role)])
    _write(roles / 'transport-egress/tasks/activate.yml', [event('activate'), {'ansible.builtin.copy': {'content': 'candidate-running', 'dest': str(root / 'state'), 'mode': '0600'}},
        {'ansible.builtin.fail': {'msg': 'controlled activation failure'}, 'when': "failure == 'activation'"}])
    _write(roles / 'transport-egress/tasks/quiesce.yml', [event('quiesce'), {'ansible.builtin.copy': {'content': 'stopped', 'dest': str(root / 'state'), 'mode': '0600'}}])
    _write(roles / 'transport-egress/tasks/rollback.yml', [
        {'name': 'Require accepted firewall before previous frontend readiness',
         'ansible.builtin.assert': {'that': [
             "lookup('ansible.builtin.file', " + json.dumps(str(root / 'firewall-policy')) + ") == 'accepted firewall'"]}},
        event('resume'), {'ansible.builtin.copy': {'src': str(root / 'previous.conf'), 'dest': str(accepted), 'mode': '0640'}},
        {'ansible.builtin.copy': {'content': 'accepted-running', 'dest': str(root / 'state'), 'mode': '0600'}}, {'ansible.builtin.set_fact': {'_transport_egress_transaction_started': False}}])
    # Only the host-facing stat paths, the outer-route status command and the
    # helper admission's root-owned ancestry are replaced; the production detection,
    # admission, adoption and refusal tasks run verbatim.
    (root / 'libexec').mkdir(mode=0o755)
    (root / 'libexec').chmod(0o755)
    _write(roles / 'transport-egress/tasks/helper-authority.yml', _helper_authority(root))
    (root / 'outer_status.py').write_text('''import sys
from pathlib import Path
root = Path(sys.argv[1])
(root / 'status-ran').write_text('')
if (root / 'outer-fail').exists():
    print('transport-runtime-refused:acceptance-parameters-required', file=sys.stderr)
    print('private-detail-that-must-not-be-echoed', file=sys.stderr)
    raise SystemExit(1)
print('{"open": %s}' % ('true' if (root / 'outer-open').exists() else 'false'))
''')
    _write(root / 'tasks/transport-ingress-begin.yml', _prestep(root, os.geteuid() if state_owner is None else state_owner) + [invoke('begin'), {'ansible.builtin.set_fact': {'transport_site_transaction_active': True}}])
    recovery = yaml.safe_load((ROOT / 'ansible/playbooks/tasks/transport-ingress-recover-commit.yml').read_text())
    recovery[0]['ansible.builtin.command'] = invoke('recover-commit')['ansible.builtin.command']
    _write(root / 'tasks/transport-ingress-recover-commit.yml', recovery)
    _write(root / 'tasks/transport-ingress-restore.yml', [{**invoke('restore'), 'when': 'transport_site_transaction_active | default(false) | bool'}])
    _write(root / 'tasks/transport-ingress-commit.yml', [invoke('commit'), {'ansible.builtin.set_fact': {
        'transport_site_transaction_active': False, '_transport_egress_transaction_started': False,
        '_firewall_site_transaction_active': False}}])
    (root / 'tasks/transport-egress-activate.yml').write_bytes((ROOT / 'ansible/playbooks/tasks/transport-egress-activate.yml').read_bytes())
    block = protected()
    # Retarget only the new firewall host-command boundary. The complete outer
    # block, conditions and ordering still run through real localhost Ansible.
    firewall_driver = root / 'firewall_driver.py'
    firewall_driver.write_text('''import json,sys
from pathlib import Path
root=Path(sys.argv[1]); action=sys.argv[2]; marker=root/'firewall-owner'
owner=marker.read_text() if marker.exists() else None
if action=='status': print(json.dumps({'owner':owner}))
elif action=='restore' and owner=='site':
 (root/'firewall-policy').write_bytes(b'accepted firewall')
 with (root/'events').open('a') as stream: stream.write('firewall-restore\\n')
 marker.unlink()
elif action=='finish': marker.unlink(missing_ok=True)
''')
    firewall_helper = root / 'firewall-helper.py'
    firewall_helper.write_text('synthetic helper authority\n')
    for task in [*block['block'], *block['rescue']]:
        name = task['name']
        if name == 'Admit retained consumer helpers before recovery':
            task['ansible.builtin.command']['argv'] = [sys.executable, '-c', 'pass']
        elif name == 'Inspect retained firewall helper after interrupted convergence':
            task['ansible.builtin.stat']['path'] = str(firewall_helper)
        elif name in ('Finish an initial firewall without a selected protected consumer',
                      'Read retained firewall consumer ownership before compensation',
                      'Restore initial firewall after protected convergence refusal'):
            action = {'Finish an initial firewall without a selected protected consumer': 'finish',
                      'Read retained firewall consumer ownership before compensation': 'status',
                      'Restore initial firewall after protected convergence refusal': 'restore'}[name]
            task['ansible.builtin.command']['argv'] = [sys.executable, str(firewall_driver), str(root), action]
    _write(root / 'play.yml', [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
                              'vars': {'failure': failure, 'vpn': {}, 'vpn_subscription_only': False},
                              'pre_tasks': [{'ansible.builtin.assert': {'that': ['xray_parse_visible', 'hysteria_parse_visible']}, 'tags': ['always']}],
                              'tasks': [block, {'ansible.builtin.fail': {'msg': 'controlled unrelated failure'}, 'when': "failure == 'unrelated'", 'tags': ['unrelated']}]}])
    return root, context


def _run(root, tags=None, check=False):
    env = os.environ.copy()
    env['ANSIBLE_ROLES_PATH'] = str(root / 'roles')
    env['ANSIBLE_STDOUT_CALLBACK'] = 'default'
    env['ANSIBLE_NOCOLOR'] = '1'
    argv = ['ansible-playbook', '-i', 'localhost,', str(root / 'play.yml')]
    if tags:
        argv += ['--tags', tags]
    if check:
        argv.append('--check')
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=90)


def _managed_tls_fixture(tmp_path, failure):
    root, context = _fixture(tmp_path, failure)
    tasks = yaml.safe_load((ROOT / 'ansible/roles/nginx-xhttp/tasks/tls-bootstrap.yml').read_text())
    # Keep the production DNS wait and Ansible ordering. Replace only the
    # privileged publisher/CA and public resolver boundaries of this local test.
    tasks[0]['ansible.builtin.command'] = {
        'argv': [sys.executable, str(root / 'ingress_driver.py'), str(root), 'publish', str(HELPER), 'public-tls']}
    tasks[0]['changed_when'] = False
    dns_driver = root / 'dns_driver.py'
    dns_driver.write_text('''import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location('dns',sys.argv[1]);dns=importlib.util.module_from_spec(spec);spec.loader.exec_module(dns)
root=Path(sys.argv[2]);failure=sys.argv[3]
if (root/'ingress/public-tls.conf').read_bytes()!=b'changed ingress' or not (root/'nginx-state/nginx.service/site.json').exists():
 raise RuntimeError('DNS wait requires owned prepared HTTP')
clock=SimpleNamespace(now=0)
dns.time=SimpleNamespace(monotonic=lambda:clock.now,sleep=lambda seconds:setattr(clock,'now',clock.now+seconds))
def query(resolver,name,family,timeout):
 if failure=='tls-child-interrupted':raise KeyboardInterrupt
 alias=name=='www.site.example'
 rows=[dict(name=name,type=5,data='site.example')] if alias else []
 address='8.8.8.8' if family==1 else ('2606:4700:4700::1001' if failure=='tls-dns' else '2606:4700:4700::1111')
 rows.append(dict(name='site.example' if alias else name,type=family,data=address))
 return dict(Status=0,TC=False,Question=[dict(name=name,type=family)],Answer=rows)
dns.query=query
code=dns.main()
if code==0:
 with (root/'events').open('a') as stream:stream.write('tls-dns-ready\\n')
raise SystemExit(code)
''')
    tasks[1]['ansible.builtin.command']['argv'] = [sys.executable, str(dns_driver),
        str(ROOT / 'scripts/wait-public-tls-dns.py'), str(root), '{{ failure }}']
    tasks[2]['ansible.builtin.command'] = {'argv': [sys.executable, '-c',
        'from pathlib import Path;import sys;p=Path(sys.argv[1]);p.write_text(p.read_text()+"tls-issue\\n");raise SystemExit(1 if sys.argv[2]=="tls-ca" else 0)',
        str(root / 'events'), '{{ failure }}']}
    tasks[2]['changed_when'] = False
    _write(root / 'roles/nginx-xhttp/tasks/tls-bootstrap.yml', tasks)
    play = yaml.safe_load((root / 'play.yml').read_text())
    play[0]['vars'].update(vpn_service_address='8.8.8.8', server_ipv6='2606:4700:4700::1111',
        nginx_xhttp={'server_name': 'site.example', 'acme': {'domains': ['site.example', 'www.site.example']}})
    _write(root / 'play.yml', play)
    return root, context


@pytest.mark.parametrize('failure', ['tls-dns', 'tls-child-interrupted', 'tls-ca'])
def test_managed_tls_failure_compensates_http_and_firewall_before_frontend_staging(tmp_path, failure):
    root, context = _managed_tls_fixture(tmp_path, failure)
    result = _run(root)
    assert result.returncode != 0 and 'Protected transport staging failed' in result.stdout
    assert (root / 'frontend.conf').read_bytes() == b'accepted frontend'
    assert (root / 'state').read_text() == 'accepted-running'
    assert (root / 'firewall-policy').read_bytes() == b'accepted firewall'
    assert all(Path(owner['paths'][0]).read_bytes() == b'accepted ingress' for owner in context['owners'])
    events = (root / 'events').read_text().splitlines()
    assert events.index('ingress-restore') < events.index('firewall-restore')
    assert ('tls-issue' in events) is (failure == 'tls-ca')
    assert not {'stage', 'activate', 'resume'}.intersection(events)
    assert not (root / 'nginx-state/nginx.service/site.json').exists()
    assert not (root / 'firewall-owner').exists()


def test_managed_tls_ca_failure_retries_through_the_ordinary_full_graph(tmp_path):
    root, context = _managed_tls_fixture(tmp_path, 'tls-ca')
    failed = _run(root)
    assert failed.returncode != 0
    play = yaml.safe_load((root / 'play.yml').read_text())
    play[0]['vars']['failure'] = 'none'
    _write(root / 'play.yml', play)
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (root / 'events').read_text().splitlines()
    successful = events[events.index('firewall-restore') + 1:]
    assert successful.index('tls-dns-ready') < successful.index('tls-issue') < successful.index('activate') < successful.index('ingress-commit')
    assert all(Path(owner['paths'][0]).read_bytes() == b'changed ingress' for owner in context['owners'])
    assert not (root / 'nginx-state/nginx.service/site.json').exists()
    assert not (root / 'firewall-owner').exists()


def _outer_state(root):
    """The egress outer route's private state directory under the harness ancestry, with explicit modes under any umask."""
    for path in (root / 'ripdpi-state', root / 'ripdpi-state/transport-runtime'):
        path.mkdir(exist_ok=True)
        path.chmod(0o700)
    return root / 'ripdpi-state/transport-runtime'


def _interrupt(root, outer):
    """Prepare retained state through real APIs, without claiming a process kill."""
    driver = root / 'ingress_driver.py'
    argv = [sys.executable, str(driver), str(root), 'interrupt', str(HELPER)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    (root / 'events').write_text('')
    if not outer.startswith('no-helper'):
        helper = root / 'libexec/transport_runtime_outer.py'
        helper.write_text('')
        helper.chmod(0o755)
    if outer in ('no-helper-empty-state', 'no-helper-populated-state'):
        state = _outer_state(root)
        if outer == 'no-helper-populated-state':
            # A real node's state directory holds the accepted receipt; only outer.json records an open route.
            (state / 'accepted.json').write_text('{}')
    if outer == 'open':
        # Egress began and candidate frontends were published before the kill.
        (root / 'outer-open').write_text('')
        (root / 'previous.conf').write_bytes(b'accepted frontend')
        (root / 'previous.conf').chmod(0o600)
        (root / 'frontend.conf').write_bytes(b'changed frontend')
        (root / 'state').write_text('candidate-running')


@pytest.mark.parametrize('failure', ['xray', 'hysteria', 'activation'])
def test_protected_failure_restores_ingress_before_frontend_resume(tmp_path, failure):
    root, context = _fixture(tmp_path, failure)
    result = _run(root)
    assert result.returncode != 0 and 'Protected transport staging failed' in result.stdout
    assert (root / 'frontend.conf').read_bytes() == b'accepted frontend'
    assert (root / 'frontend.conf').stat().st_mode & 0o777 == 0o640
    assert (root / 'state').read_text() == 'accepted-running'
    assert (root / 'firewall-policy').read_bytes() == b'accepted firewall'
    for owner in context['owners']:
        assert Path(owner['paths'][0]).read_bytes() == b'accepted ingress'
    events = (root / 'events').read_text().splitlines()
    assert events.index('quiesce') < events.index('ingress-restore') < events.index('resume')
    assert events.index('ingress-restore') < events.index('firewall-restore') < events.index('resume')
    assert not (root / 'nginx-state/nginx.service/site.json').exists()


def test_later_unrelated_failure_keeps_once_activated_committed_generation(tmp_path):
    root, context = _fixture(tmp_path, 'unrelated')
    result = _run(root)
    assert result.returncode != 0 and 'controlled unrelated failure' in result.stdout
    assert (root / 'frontend.conf').read_bytes() == b'changed frontend'
    assert (root / 'state').read_text() == 'candidate-running'
    assert (root / 'firewall-policy').read_bytes() == b'candidate firewall'
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])
    events = (root / 'events').read_text().splitlines()
    assert events.count('activate') == 1 and 'resume' not in events
    assert events.index('activate') < events.index('ingress-commit')
    assert not (root / 'nginx-state/nginx.service/site.json').exists()


def _journal_state(root):
    state = root / 'nginx-state/nginx.service'
    return {path: path.read_bytes() for path in sorted(state.glob('*.json'))}


@pytest.mark.parametrize('outer', ['open', 'closed', 'no-helper', 'no-helper-empty-state', 'no-helper-populated-state'])
def test_interrupted_prior_site_transaction_is_compensated_in_rescue_order_then_next_run_converges(tmp_path, outer):
    root, context = _fixture(tmp_path, 'none')
    receipts = {path: data for path, data in _journal_state(root).items() if path.name.endswith('.activated.json')}
    _interrupt(root, outer)
    assert (root / 'nginx-state/nginx.service/site.json').exists()
    result = _run(root)
    assert result.returncode != 0
    assert 'interrupted-protected-ingress-transaction' in result.stdout
    assert 'accepted-generation recovery was attempted when available' in result.stdout
    assert (root / 'status-ran').exists() == (not outer.startswith('no-helper'))
    for owner in context['owners']:
        assert Path(owner['paths'][0]).read_bytes() == b'accepted ingress'
    assert {path: data for path, data in _journal_state(root).items() if path.name.endswith('.activated.json')} == receipts
    assert not (root / 'nginx-state/nginx.service/site.json').exists()
    assert (root / 'frontend.conf').read_bytes() == b'accepted frontend'
    assert (root / 'state').read_text() == 'accepted-running'
    events = (root / 'events').read_text().splitlines()
    # Candidate transports quiesce first, but only when the outer route is open.
    assert events == (['quiesce', 'ingress-restore', 'resume'] if outer == 'open' else ['ingress-restore'])
    (root / 'events').write_text('')
    again = _run(root)
    assert again.returncode == 0, again.stdout + again.stderr
    events = (root / 'events').read_text().splitlines()
    assert events.count('activate') == 1 and events[-1] == 'ingress-commit'
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])


def test_check_mode_refuses_an_interrupted_prior_site_transaction_without_mutation(tmp_path):
    root, context = _fixture(tmp_path, 'none')
    _interrupt(root, 'open')
    before = (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text())
    result = _run(root, check=True)
    assert result.returncode != 0
    assert 'interrupted-protected-ingress-transaction' in result.stdout
    assert 'no accepted-generation recovery was attempted' in result.stdout
    assert 'recovery was attempted when available' not in result.stdout
    assert (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text()) == before
    assert (root / 'nginx-state/nginx.service/site.json').exists()
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])
    # Adoption alone records no event, so the message above catches it; these catch the outer helper or quiesce running in check mode.
    assert not (root / 'status-ran').exists() and (root / 'events').read_text() == ''


def test_pending_only_journal_refuses_dry_run_with_its_own_category_and_one_deploy_recovers_it(tmp_path):
    root, context = _fixture(tmp_path, 'none')
    pending = root / 'nginx-state/nginx.service/pending.json'
    result = subprocess.run([sys.executable, str(root / 'ingress_driver.py'), str(root), 'pend', str(HELPER)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    (root / 'events').write_text('')
    before = (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text())
    dry = _run(root, check=True)
    assert dry.returncode != 0
    assert 'interrupted-nginx-publication' in dry.stdout and 'interrupted-protected-ingress-transaction' not in dry.stdout
    assert 'recovery was attempted when available' not in dry.stdout
    # The refusal tells the operator the recovery deploy converges the whole graph unpreviewed.
    assert 'cannot preview' in dry.stdout and 'make source-drift passes' in dry.stdout
    assert (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text()) == before
    assert not (root / 'status-ran').exists() and (root / 'events').read_text() == ''
    # A deploy continues: the helper's begin recovers the recognized journal, then the block converges.
    deploy = _run(root)
    assert deploy.returncode == 0, deploy.stdout + deploy.stderr
    assert 'interrupted-nginx-publication' not in deploy.stdout
    assert not pending.exists() and not (root / 'nginx-state/nginx.service/site.json').exists()
    events = (root / 'events').read_text().splitlines()
    assert events.count('activate') == 1 and events[-1] == 'ingress-commit'
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])


@pytest.mark.parametrize('tamper', ['symlink', 'group-writable', 'hardlink', 'writable-directory'])
@pytest.mark.parametrize('helper_name', ['transport_runtime_outer.py', 'transport_semantics.py'])
def test_unsafe_outer_helper_is_refused_before_status_runs_and_the_journal_is_retained(tmp_path, tamper, helper_name):
    root, context = _fixture(tmp_path, 'none')
    _interrupt(root, 'open')
    helper = root / 'libexec' / helper_name
    if helper_name == 'transport_semantics.py':
        helper.write_text('')
        helper.chmod(0o644)
    if tamper == 'symlink':
        target = root / 'outer-target.py'
        target.write_text('')
        target.chmod(0o755)
        helper.unlink()
        helper.symlink_to(target)
    elif tamper == 'group-writable':
        helper.chmod(0o775)
    elif tamper == 'hardlink':
        os.link(helper, root / 'outer-alias.py')
    else:
        (root / 'libexec').chmod(0o775)
    before = (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text())
    result = _run(root)
    assert result.returncode != 0
    assert 'consumer-helper-authority-refused' in result.stdout
    assert 'no accepted-generation recovery was attempted' in result.stdout
    assert not (root / 'status-ran').exists()
    assert (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text()) == before
    assert (root / 'nginx-state/nginx.service/site.json').exists()
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])
    assert (root / 'events').read_text() == ''


@pytest.mark.parametrize('state', ['record', 'dangling-record', 'record-directory', 'state-symlink', 'state-file',
                                   'state-mode-755', 'state-mode-777', 'state-foreign-owner'])
def test_missing_outer_helper_with_route_state_present_or_unjudgeable_refuses_before_adoption_and_retains_the_journal(tmp_path, state):
    # The helper's own status refuses a state directory that is not a root-owned 0700 directory, so such a directory cannot prove the route closed.
    root, context = _fixture(tmp_path, 'none', state_owner=os.geteuid() + 1 if state == 'state-foreign-owner' else None)
    _interrupt(root, 'open')
    # The helper was deleted after egress began, so the outer route's own durable state is the only evidence of an open route.
    (root / 'libexec/transport_runtime_outer.py').unlink()
    runtime = root / 'ripdpi-state/transport-runtime'
    if state == 'state-symlink':
        _outer_state(root)
        runtime.rmdir()
        (root / 'elsewhere').mkdir(mode=0o700)
        runtime.symlink_to(root / 'elsewhere')
    elif state == 'state-file':
        _outer_state(root)
        runtime.rmdir()
        runtime.write_text('')
    elif state == 'state-foreign-owner':
        # Owned by the test user while the retargeted judgement expects another owner, as a directory not owned by root would be.
        _outer_state(root)
    elif state.startswith('state-mode-'):
        _outer_state(root).chmod(int(state.rsplit('-', 1)[1], 8))
    else:
        record = _outer_state(root) / 'outer.json'
        if state == 'record':
            record.write_text('{}')
            record.chmod(0o600)
        elif state == 'dangling-record':
            record.symlink_to(root / 'absent-target')
        else:
            record.mkdir(mode=0o700)
    before = (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text())
    result = _run(root)
    assert result.returncode != 0
    assert 'egress-outer-helper-missing' in result.stdout
    # The refusal names the helper set and its directory, not one helper.
    assert 'transport_runtime_*.py' in result.stdout and '/usr/local/libexec/ripdpi-transport-egress' in result.stdout
    # No status helper ran, nothing was adopted and so no compensation of any kind was attempted.
    assert 'no accepted-generation recovery was attempted' in result.stdout
    assert not (root / 'status-ran').exists() and (root / 'events').read_text() == ''
    assert (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text()) == before
    assert (root / 'nginx-state/nginx.service/site.json').exists()
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])


def test_unreadable_outer_route_refuses_categorically_and_retains_the_journal(tmp_path):
    root, context = _fixture(tmp_path, 'none')
    _interrupt(root, 'open')
    (root / 'outer-fail').write_text('')
    before = (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text())
    result = _run(root)
    assert result.returncode != 0
    assert 'transport-runtime-refused:acceptance-parameters-required' in result.stdout
    assert 'private-detail-that-must-not-be-echoed' not in result.stdout + result.stderr
    assert 'no accepted-generation recovery was attempted' in result.stdout
    assert (_journal_state(root), (root / 'frontend.conf').read_bytes(), (root / 'state').read_text()) == before
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])
    assert (root / 'events').read_text() == ''


@pytest.mark.parametrize('outer', ['no-helper', 'open'])
def test_malformed_prior_site_journal_fails_closed_before_capture_and_is_retained(tmp_path, outer):
    root, context = _fixture(tmp_path, 'none')
    _interrupt(root, outer)
    journal = root / 'nginx-state/nginx.service/site.json'
    journal.write_text('{"schema": 99}')
    before = _journal_state(root)
    result = _run(root)
    assert result.returncode != 0 and 'Complete a recorded protected commit' in result.stdout
    assert _journal_state(root) == before
    assert all(Path(value['paths'][0]).read_bytes() == (b'accepted ingress' if value['owner'] == 'public-tls' else b'changed ingress') for value in context['owners'])
    events = (root / 'events').read_text().splitlines()
    assert 'ingress-restore' not in events and 'ingress-begin' not in events and 'stage' not in events
    # An unreadable decision refuses before adoption, quiescence or compensation.
    assert events == []
    assert (root / 'state').read_text() == ('candidate-running' if outer == 'open' else 'accepted-running')


def test_interrupted_transaction_detection_matches_the_production_contract():
    source = yaml.safe_load(BEGIN.read_text())
    names = [value['name'] for value in source]
    steps = source[names.index(DECLARE) + 1:names.index(CAPTURE)]
    assert [value['name'] for value in steps] == [
        'Detect an interrupted protected ingress transaction before capturing a new one',
        'Detect an interrupted ordinary nginx publication before capturing a new transaction',
        'Refuse dry-run while an interrupted ordinary nginx publication awaits recovery',
        'Admit exact root-owned egress helper authority before running it for interrupted transaction adoption',
        'Locate the egress outer route helper for interrupted transaction adoption',
        'Resolve a recorded protected commit before interrupted transaction adoption',
        'Read the interrupted egress outer route ownership',
        'Refuse adoption when the egress outer route ownership cannot be read',
        'Locate the egress outer route state directory when its helper is missing',
        'Locate the egress outer route intent record when its helper is missing',
        'Refuse adoption when a missing egress outer route helper leaves the route state unproven',
        "Adopt the interrupted transaction as this block's sole compensation owner",
        'Refuse to capture while an interrupted protected ingress transaction awaits compensation']
    detect, pending, pending_refuse, admit, locate, recovery, outer, unreadable, state_dir, record, missing, adopt, refuse = steps
    # The playbook-side journal path must stay the helper's own state root.
    spec = importlib.util.spec_from_file_location('site_nginx_contract', HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert detect['ansible.builtin.stat'] == {'path': str(helper.STATE_ROOT / 'nginx.service' / 'site.json'), 'follow': False}
    assert detect['ansible.builtin.stat']['path'] == JOURNAL and 'when' not in detect
    assert pending['ansible.builtin.stat'] == {'path': str(helper.STATE_ROOT / 'nginx.service' / 'pending.json'), 'follow': False}
    assert pending['ansible.builtin.stat']['path'] == PENDING and 'when' not in pending
    # A pending-only journal refuses dry-run with its own category; deploys continue to the helper's begin.
    assert pending_refuse['when'] == ['ansible_check_mode', 'not _transport_ingress_interrupted.stat.exists', '_transport_ingress_pending.stat.exists']
    assert pending_refuse['ansible.builtin.fail']['msg'].startswith('interrupted-nginx-publication:') and 'no_log' not in pending_refuse
    # The outer route helper is the one the commit task already addresses.
    commit = yaml.safe_load((ROOT / 'ansible/playbooks/tasks/transport-ingress-commit.yml').read_text())
    assert '--finish-egress' in commit[0]['ansible.builtin.command']['argv']
    assert '--finish-firewall' in commit[0]['ansible.builtin.command']['argv']
    assert '_firewall_site_transaction_active | default(false) | bool' in commit[0]['ansible.builtin.command']['argv']
    assert commit[1]['ansible.builtin.set_fact']['_firewall_site_transaction_active'] is False
    assert recovery['ansible.builtin.include_tasks'] == 'transport-ingress-recover-commit.yml'
    assert recovery['when'] == ['_transport_ingress_interrupted.stat.exists', 'not ansible_check_mode']
    assert locate['ansible.builtin.stat'] == {'path': OUTER_HELPER, 'follow': False}
    # The status helper runs as root only after the role's one shared admission of its ancestry and file.
    assert admit['ansible.builtin.include_role'] == {'name': 'transport-egress', 'tasks_from': 'helper-authority'}
    assert admit['when'] == ['_transport_ingress_interrupted.stat.exists', 'not ansible_check_mode']
    prepare = yaml.safe_load((EGRESS_TASKS / 'runtime-prepare.yml').read_text())
    assert prepare[0]['ansible.builtin.import_tasks'] == 'helper-authority.yml' and 'consumer-helper-authority-refused' not in (EGRESS_TASKS / 'runtime-prepare.yml').read_text()
    shared = yaml.safe_load((EGRESS_TASKS / 'helper-authority.yml').read_text())
    assert len(shared) == 1 and shared[0]['check_mode'] is False and shared[0]['changed_when'] is False
    assert any('transport_runtime_outer.py' in part for part in shared[0]['ansible.builtin.command']['argv'])
    assert outer['ansible.builtin.command']['argv'] == ['/usr/bin/python3', '-Es', OUTER_HELPER, 'status']
    assert outer['no_log'] is True and outer['failed_when'] is False and outer['changed_when'] is False
    for step in (locate, outer, adopt):
        assert 'not ansible_check_mode' in step['when'] and '_transport_ingress_interrupted.stat.exists' in step['when']
    # Dry-run reports the category only; adoption never happens in check mode.
    assert set(adopt['ansible.builtin.set_fact']) == {'transport_site_transaction_active', '_transport_egress_transaction_started'}
    assert unreadable['when'] == '_transport_ingress_interrupted_outer.rc | default(0) != 0'
    assert 'regex_findall' in unreadable['ansible.builtin.fail']['msg'] and 'no_log' not in unreadable
    # A skipped status must never read as a closed route: with the helper missing, only the outer route's own durable state may prove it closed.
    # That state is the helper's own, and its sole open-route record is outer.json.
    assert re.search(r"^STATE = Path\('([^']+)'\)", (RUNTIME_FILES / 'transport_runtime_accept.py').read_text(), re.M).group(1) == OUTER_STATE
    transaction = (RUNTIME_FILES / 'transport_runtime_transaction.py').read_text()
    assert "read_private(root / 'outer.json', uid)" in transaction
    # The helper's own status runs as root and refuses any state directory that is not a root-owned 0700 directory, so only such a directory may be judged.
    transaction_class = next(node for node in ast.parse(transaction).body
                             if isinstance(node, ast.ClassDef) and node.name == 'Transaction')
    constructor = next(node for node in transaction_class.body
                       if isinstance(node, ast.FunctionDef) and node.name == '__init__')
    defaults = {argument.arg: ast.literal_eval(value)
                for argument, value in zip(constructor.args.kwonlyargs, constructor.args.kw_defaults)}
    assert defaults == {'uid': 0, 'check': False, 'awg': False, 'revocation': None}
    assert type(defaults['uid']) is int and defaults['check'] is False and defaults['awg'] is False
    assert 'info.st_uid != self.uid or stat.S_IMODE(info.st_mode) != 0o700' in transaction
    assert "with Transaction(STATE, check=args.action == 'status', revocation=authority) as tx:" in (RUNTIME_FILES / 'transport_runtime_outer.py').read_text()
    assert state_dir['ansible.builtin.stat'] == {'path': OUTER_STATE, 'follow': False}
    assert record['ansible.builtin.stat'] == {'path': OUTER_RECORD, 'follow': False}
    absent_helper = ['_transport_ingress_interrupted.stat.exists', 'not ansible_check_mode', 'not _transport_ingress_interrupted_helper.stat.exists']
    assert state_dir['when'] == absent_helper
    assert record['when'] == absent_helper + ['_transport_ingress_interrupted_outer_state.stat.exists', '_transport_ingress_interrupted_outer_state.stat.isdir']
    stat_state = '_transport_ingress_interrupted_outer_state.stat'
    assert missing['when'] == absent_helper + [stat_state + '.exists',
        f"not ({stat_state}.isdir and {stat_state}.uid == 0 and {stat_state}.mode == '0700') or _transport_ingress_interrupted_outer_record.stat.exists"]
    assert missing['ansible.builtin.fail']['msg'].startswith('egress-outer-helper-missing:') and 'no_log' not in missing
    # The remedy names the whole helper set the next deploy's admission checks, its directory and the admission contract, not one helper.
    admitted = ast.literal_eval(re.search(r'helper_names = (\([^)]*\))', (EGRESS_TASKS / 'helper-authority.yml').read_text()).group(1))
    assert sorted([path.name for path in RUNTIME_FILES.glob('transport_runtime_*.py')] + ['transport_semantics.py']) == sorted(admitted)
    for text in ('transport_runtime_*.py', 'transport_semantics.py', str(Path(OUTER_HELPER).parent), 'deployed revision', 'root-owned regular file with one link, not group- or world-writable',
                 'under root-owned directories that are not group- or world-writable', 'recreate the node'):
        assert text in missing['ansible.builtin.fail']['msg']
    assert 'root-owned helper' not in missing['ansible.builtin.fail']['msg']
    assert all('failed_when' not in step and 'ignore_errors' not in step for step in (state_dir, record, missing))
    assert refuse['when'] == '_transport_ingress_interrupted.stat.exists' and 'no_log' not in refuse
    assert steps[-1] is refuse
    # The rescue's ingress restore is itself gated on adoption, so a refused dry-run never restores.
    restore = yaml.safe_load((ROOT / 'ansible/playbooks/tasks/transport-ingress-restore.yml').read_text())
    assert [value['when'] for value in restore] == ['transport_site_transaction_active | default(false) | bool']


@pytest.mark.parametrize('tag', ['xray', 'hysteria', 'nginx', 'xhttp', 'reality-self-steal', 'p0', 'p1', 'p2', 'transport'])
def test_each_protected_tag_selects_both_frontends_and_once_activation(tmp_path, tag):
    root, _ = _fixture(tmp_path, 'none')
    result = _run(root, tag)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (root / 'events').read_text().splitlines()
    assert events.index('stage') < events.index('xray') < events.index('hysteria') < events.index('activate')
    assert events.count('activate') == 1 and events[-1] == 'ingress-commit'


@pytest.mark.parametrize('mode', ['enabled', 'disabled', 'subscription'])
def test_actual_ingress_declaration_has_exact_candidate_paths_and_optional_secret_boundaries(tmp_path, mode):
    import hashlib
    root = tmp_path.resolve()
    assets = root / 'roles/reality-self-steal/files/public-site'
    assets.mkdir(parents=True)
    names = [path.name for path in (ROOT / 'ansible/roles/reality-self-steal/files/public-site').iterdir() if path.is_file()]
    for name in names:
        (assets / name).write_text('public asset path fixture')
    enabled = mode == 'enabled'
    variables = {'vpn': {'enable_nginx_xhttp': mode != 'disabled', 'enable_reality_self_steal': mode != 'disabled'},
                 'vpn_subscription_only': mode == 'subscription',
                 'reality_self_steal_site_root': '/var/www/reality-self-steal',
                 'reality_self_steal_tls_dir': '/etc/nginx/reality-self-steal'}
    if enabled:
        variables['nginx_xhttp'] = {'server_name': 'primary.example.invalid', 'fallback_server_name': 'alternate.example.invalid', 'fallback_enabled': True}
        variables['reality_self_steal'] = {'cert_pem': 'synthetic certificate path identity', 'key_pem': 'synthetic key path identity'}
    # Disabled/subscription mode deliberately supplies no optional secret map.
    expected_xhttp = ['/etc/nginx/sites-available/vpn-xhttp.conf', '/etc/nginx/sites-enabled/vpn-xhttp.conf', '/etc/nginx/sites-enabled/default']
    expected_self = ['/etc/nginx/sites-available/reality-self-steal.conf', '/etc/nginx/sites-enabled/reality-self-steal.conf', '/etc/nginx/sites-enabled/default', '/etc/nginx/reality-self-steal/current'] + ['/var/www/reality-self-steal/' + name for name in sorted(names)]
    if enabled:
        expected_xhttp += ['/var/www/public-site/' + name for name in [
            'favicon.svg', 'logo.svg', '404.html', 'assets/site.css', 'index.html', 'about.html',
            'methodology.html', 'updates.html', 'notes/reading-benchmark-results.html',
            'notes/latency-throughput-context.html', 'notes/repeatable-model-comparisons.html',
            'feed.xml', 'robots.txt', 'sitemap.xml', '.well-known/security.txt']]
    if enabled:
        expected_xhttp += ['/etc/nginx/tls/' + name + suffix for name in ['primary.example.invalid', 'alternate.example.invalid'] for suffix in ['.fullchain.pem', '.key']]
        authority = variables['reality_self_steal']
        release = hashlib.sha256(''.join(hashlib.sha256(authority[key].encode()).hexdigest() for key in ['cert_pem', 'key_pem']).encode()).hexdigest()
        expected_self += ['/etc/nginx/reality-self-steal/releases/' + release + '/' + name for name in ['fullchain.pem', 'privkey.pem']]
    source = yaml.safe_load((ROOT / 'ansible/playbooks/tasks/transport-ingress-begin.yml').read_text())[:2]
    _write(root / 'playbooks/play.yml', [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False, 'vars': {**variables, 'expected_xhttp': sorted(expected_xhttp), 'expected_self': sorted(expected_self)},
                              'tasks': source + [{'ansible.builtin.assert': {'that': ["_transport_ingress_request.owners[0].paths | sort == expected_xhttp", "_transport_ingress_request.owners[2].paths | sort == expected_self", "_transport_ingress_request.owners[1].paths | sort == ['/etc/nginx/conf.d/vpn-public-acme.conf', '/etc/vpn-public-tls/config.json']"]}, 'no_log': True}]}])
    result = _run(root / "playbooks")
    assert result.returncode == 0, result.stdout + result.stderr


def test_public_pages_and_assets_are_staged_by_actual_ansible_without_direct_publication(tmp_path):
    import base64
    import shutil
    from template_render import merge_render_vars
    root = tmp_path.resolve()
    source_role = ROOT / 'ansible/roles/nginx-xhttp'
    role = root / 'roles/public-stage'
    shutil.copytree(source_role / 'templates/public-site', role / 'templates/public-site')
    shutil.copytree(source_role / 'files/public-site', role / 'files/public-site')
    source = yaml.safe_load((source_role / 'tasks/enable.yml').read_text())
    names = {'Resolve the published public site layout',
             'Stage exact public assets in the same compensated nginx publication',
             'Stage hostname-bound public pages in the same compensated publication',
             'Stage removal of the exact retired security contact alongside the site'}
    tasks = [copy.deepcopy(value) for value in source if value.get('name') in names]
    assert len(tasks) == 4 and all('ansible.builtin.set_fact' in value and 'notify' not in value for value in tasks)
    _write(role / 'tasks/main.yml', tasks)
    variables = merge_render_vars()
    variables.pop('item', None)
    variables['nginx_transaction_files'] = []
    variables['public_site_canonical_url'] = 'https://new-origin.example.invalid'
    destination = root / 'candidate.json'
    _write(root / 'play.yml', [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
                              'vars': variables, 'tasks': [
                                  {'ansible.builtin.import_role': {'name': 'public-stage'}},
                                  {'ansible.builtin.copy': {'content': '{{ nginx_transaction_files | to_json }}', 'dest': str(destination), 'mode': '0600'}, 'no_log': True}]}])
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(destination.read_text())
    assert len(rows) == 15 and len({row['path'] for row in rows}) == 15
    assert rows[-1] == {'path': '/var/www/public-site/.well-known/security.txt', 'kind': 'absent'}
    for row in rows:
        assert row['path'].startswith('/var/www/public-site/')
        if row['kind'] == 'file':
            assert row['mode'] == '0644' and row['uid'] == row['gid'] == 0
    by_path = {row['path']: row for row in rows}
    for filename in ['favicon.svg', 'logo.svg', '404.html', 'assets/site.css']:
        assert base64.b64decode(by_path['/var/www/public-site/' + filename]['content_b64']) == (source_role / 'files/public-site' / filename).read_bytes()
    from urllib.parse import urlsplit
    canonical = urlsplit(_canonical_href(base64.b64decode(by_path['/var/www/public-site/index.html']['content_b64']).decode()))
    assert canonical.scheme == 'https' and canonical.netloc == 'new-origin.example.invalid'
    assert canonical.path == '/' and not canonical.query and not canonical.fragment
    # Candidate-only: no task in this producer can write /var/www or /etc/hosts.
    assert all('ansible.builtin.copy' not in value and 'ansible.builtin.template' not in value for value in tasks)
    enabled = (source_role / 'tasks/enable.yml').read_text()
    assert '/etc/hosts' not in enabled and 'unsafe_writes' not in enabled and 'getent' not in enabled


@pytest.mark.parametrize('committed', [False, True])
def test_rescue_rolls_forward_commit_and_never_compensates_after_lost_ack(tmp_path, committed):
    root, context = _fixture(tmp_path, 'none')
    # Run the production rescue resolver through Ansible and the real journal API.
    recovery = yaml.safe_load((ROOT / 'ansible/playbooks/tasks/transport-ingress-recover-commit.yml').read_text())
    recovery[0]['ansible.builtin.command'] = {
        'argv': [sys.executable, str(root / 'ingress_driver.py'), str(root), 'recover-commit', str(HELPER)]}
    _write(root / 'tasks/transport-ingress-recover-commit.yml', recovery)
    commit = yaml.safe_load((root / 'tasks/transport-ingress-commit.yml').read_text())
    if committed:
        # The helper completed but its response never reached the controller.
        commit = [commit[0], {'ansible.builtin.fail': {'msg': 'lost commit acknowledgement'}}]
    else:
        # The subprocess dies after deciding commit; retry must complete it.
        marker = "import json,sys;from pathlib import Path;p=Path(sys.argv[1]);v=json.loads(p.read_text());v.update(phase='committing',finish_egress=False,finish_firewall=True,revocation=None);p.write_text(json.dumps(v))"
        commit = [{'ansible.builtin.command': {'argv': [sys.executable, '-c', marker, str(root / 'nginx-state/nginx.service/site.json')]}, 'changed_when': False},
                  {'ansible.builtin.fail': {'msg': 'lost commit acknowledgement'}}]
    _write(root / 'tasks/transport-ingress-commit.yml', commit)
    result = _run(root)
    assert result.returncode != 0 and 'lost commit acknowledgement' in result.stdout
    events = (root / 'events').read_text().splitlines()
    assert 'quiesce' not in events and 'resume' not in events and 'ingress-restore' not in events
    assert all(Path(owner['paths'][0]).read_bytes() == (b'accepted ingress' if owner['owner'] == 'public-tls' else b'changed ingress') for owner in context['owners'])
    assert (root / 'frontend.conf').read_bytes() == b'changed frontend'
    assert (root / 'firewall-policy').read_bytes() == b'candidate firewall'
    assert not (root / 'nginx-state/nginx.service/site.json').exists()


def test_next_deploy_finishes_recorded_commit_before_staging(tmp_path):
    root, context = _fixture(tmp_path, 'none')
    _interrupt(root, 'open')
    journal = root / 'nginx-state/nginx.service/site.json'
    decision = json.loads(journal.read_text())
    decision.update(phase='committing', finish_egress=True, finish_firewall=False, revocation=None)
    journal.write_text(json.dumps(decision))
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (root / 'events').read_text().splitlines()
    assert 'quiesce' not in events and 'resume' not in events and 'ingress-restore' not in events
    assert events.index('ingress-begin') < events.index('stage')
    assert all(Path(owner['paths'][0]).read_bytes() == (b'accepted ingress' if owner['owner'] == 'public-tls' else b'changed ingress') for owner in context['owners'])
    assert not journal.exists() and not (root / 'outer-open').exists()
