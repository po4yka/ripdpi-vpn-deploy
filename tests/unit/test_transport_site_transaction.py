"""Actual localhost Ansible composition failures; no native runtime claim."""
import copy
from html.parser import HTMLParser
import importlib.util
import json
import os
from pathlib import Path
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
    return copy.deepcopy(yaml.safe_load(SITE.read_text())[0]['tasks'][0])


def test_site_closes_complete_protected_block_before_unrelated_roles():
    play = yaml.safe_load(SITE.read_text())[0]
    assert [value['role'] for value in play['roles']] == ['baseline', 'package_updates', 'firewall', 'intrusion_prevention', 'geodata', 'tailnet-management']
    block = protected()
    names = [value.get('ansible.builtin.import_role', {}).get('name') for value in block['block']]
    assert [name for name in names if name] == ['transport-egress', 'xray', 'reality-self-steal', 'nginx-xhttp', 'hysteria']
    assert block['block'][0]['ansible.builtin.import_tasks'] == 'tasks/transport-ingress-begin.yml'
    assert block['block'][-2]['ansible.builtin.import_tasks'] == 'tasks/transport-egress-activate.yml'
    assert block['block'][-1]['ansible.builtin.import_tasks'] == 'tasks/transport-ingress-commit.yml'
    assert play['tasks'][1]['ansible.builtin.import_role']['name'] == 'cdn-front'
    assert 'post_tasks' not in play
    assert block['rescue'][0]['ansible.builtin.include_role']['tasks_from'] == 'quiesce'
    assert block['rescue'][1]['ansible.builtin.include_tasks'] == 'tasks/transport-ingress-restore.yml'
    assert block['rescue'][2]['ansible.builtin.include_role']['tasks_from'] == 'rollback'
    assert all(value['ansible.builtin.import_role']['public'] for value in block['block'] if 'ansible.builtin.import_role' in value)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def _prestep(root):
    source = yaml.safe_load(BEGIN.read_text())
    names = [value['name'] for value in source]
    steps = copy.deepcopy(source[names.index(DECLARE) + 1:names.index(CAPTURE)])
    stat_paths = {JOURNAL: str(root / 'nginx-state/nginx.service/site.json'), PENDING: str(root / 'nginx-state/nginx.service/pending.json'),
                  OUTER_HELPER: str(root / 'libexec/transport_runtime_outer.py')}
    for step in steps:
        if 'ansible.builtin.stat' in step:
            step['ansible.builtin.stat']['path'] = stat_paths[step['ansible.builtin.stat']['path']]
        elif 'ansible.builtin.command' in step:
            assert step['ansible.builtin.command']['argv'] == ['/usr/bin/python3', '-Es', OUTER_HELPER, 'status']
            step['ansible.builtin.command']['argv'] = [sys.executable, str(root / 'outer_status.py'), str(root)]
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


def _fixture(tmp_path, failure):
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
                                        for owner in ['nginx-xhttp', 'reality-self-steal']]}
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
tx.command=lambda argv:'';tx.restore_enabled=lambda *args:None
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
elif action=='pend':
 value=next(v for v in tx.site_request(context) if v['owner']=='nginx-xhttp')
 value['files']=[dict(path=value['files'][0]['path'],kind='file',uid=os.geteuid(),gid=os.getegid(),mode=0o640,content_b64=base64.b64encode(b'changed ingress').decode())]
 path=Path(value['files'][0]['path'])
 tx.persist(state/'pending.json',dict(schema=2,phase='prepared',candidate='candidate-'+'0'*32,request=value,files={str(path):tx.capture(path)},active=False,
  service=dict(active=False,exists=True,unit_file_state='disabled'),owner='nginx-xhttp',receipt=tx.capture(state/'nginx-xhttp.activated.json'),next_receipt=tx.receipt_row(tx.owned_receipt(value))))
else:tx.site_transaction(action,context)
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
    for role in ['transport-egress', 'xray', 'hysteria', 'nginx-xhttp', 'reality-self-steal']:
        _write(roles / role / 'defaults/main.yml', {role.replace('-', '_') + '_parse_visible': True})
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
    _write(roles / 'transport-egress/tasks/rollback.yml', [event('resume'), {'ansible.builtin.copy': {'src': str(root / 'previous.conf'), 'dest': str(accepted), 'mode': '0640'}},
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
    _write(root / 'tasks/transport-ingress-begin.yml', _prestep(root) + [invoke('begin'), {'ansible.builtin.set_fact': {'transport_site_transaction_active': True}}])
    _write(root / 'tasks/transport-ingress-restore.yml', [{**invoke('restore'), 'when': 'transport_site_transaction_active | default(false) | bool'}])
    _write(root / 'tasks/transport-ingress-commit.yml', [invoke('commit'), {'ansible.builtin.set_fact': {'transport_site_transaction_active': False, '_transport_egress_transaction_started': False}}])
    (root / 'tasks/transport-egress-activate.yml').write_bytes((ROOT / 'ansible/playbooks/tasks/transport-egress-activate.yml').read_bytes())
    block = protected()
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


def _interrupt(root, outer):
    """Leave the on-node state of a protected deploy killed after staging began."""
    driver = root / 'ingress_driver.py'
    for action, owner in [('begin', None), ('publish', 'nginx-xhttp'), ('publish', 'reality-self-steal')]:
        argv = [sys.executable, str(driver), str(root), action, str(HELPER)] + ([owner] if owner else [])
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
    (root / 'events').write_text('')
    if outer != 'no-helper':
        helper = root / 'libexec/transport_runtime_outer.py'
        helper.write_text('')
        helper.chmod(0o755)
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
    for owner in context['owners']:
        assert Path(owner['paths'][0]).read_bytes() == b'accepted ingress'
    events = (root / 'events').read_text().splitlines()
    assert events.index('quiesce') < events.index('ingress-restore') < events.index('resume')
    assert not (root / 'nginx-state/nginx.service/site.json').exists()


def test_later_unrelated_failure_keeps_once_activated_committed_generation(tmp_path):
    root, context = _fixture(tmp_path, 'unrelated')
    result = _run(root)
    assert result.returncode != 0 and 'controlled unrelated failure' in result.stdout
    assert (root / 'frontend.conf').read_bytes() == b'changed frontend'
    assert (root / 'state').read_text() == 'candidate-running'
    assert all(Path(value['paths'][0]).read_bytes() == b'changed ingress' for value in context['owners'])
    events = (root / 'events').read_text().splitlines()
    assert events.count('activate') == 1 and 'resume' not in events
    assert events.index('activate') < events.index('ingress-commit')
    assert not (root / 'nginx-state/nginx.service/site.json').exists()


def _journal_state(root):
    state = root / 'nginx-state/nginx.service'
    return {path: path.read_bytes() for path in sorted(state.glob('*.json'))}


@pytest.mark.parametrize('outer', ['open', 'closed', 'no-helper'])
def test_interrupted_prior_site_transaction_is_compensated_in_rescue_order_then_next_run_converges(tmp_path, outer):
    root, context = _fixture(tmp_path, 'none')
    receipts = {path: data for path, data in _journal_state(root).items() if path.name.endswith('.activated.json')}
    _interrupt(root, outer)
    assert (root / 'nginx-state/nginx.service/site.json').exists()
    result = _run(root)
    assert result.returncode != 0
    assert 'interrupted-protected-ingress-transaction' in result.stdout
    assert 'accepted-generation recovery was attempted when available' in result.stdout
    assert (root / 'status-ran').exists() == (outer != 'no-helper')
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
    assert all(Path(value['paths'][0]).read_bytes() == b'changed ingress' for value in context['owners'])


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
    assert all(Path(value['paths'][0]).read_bytes() == b'changed ingress' for value in context['owners'])
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
    assert all(Path(value['paths'][0]).read_bytes() == b'changed ingress' for value in context['owners'])


@pytest.mark.parametrize('tamper', ['symlink', 'group-writable', 'hardlink', 'writable-directory'])
def test_unsafe_outer_helper_is_refused_before_status_runs_and_the_journal_is_retained(tmp_path, tamper):
    root, context = _fixture(tmp_path, 'none')
    _interrupt(root, 'open')
    helper = root / 'libexec/transport_runtime_outer.py'
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
    assert all(Path(value['paths'][0]).read_bytes() == b'changed ingress' for value in context['owners'])
    assert (root / 'events').read_text() == ''


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
    assert all(Path(value['paths'][0]).read_bytes() == b'changed ingress' for value in context['owners'])
    assert (root / 'events').read_text() == ''


@pytest.mark.parametrize('outer', ['no-helper', 'open'])
def test_malformed_prior_site_journal_fails_closed_before_capture_and_is_retained(tmp_path, outer):
    root, context = _fixture(tmp_path, 'none')
    _interrupt(root, outer)
    journal = root / 'nginx-state/nginx.service/site.json'
    journal.write_text('{"schema": 99}')
    before = _journal_state(root)
    result = _run(root)
    assert result.returncode != 0 and 'interrupted-protected-ingress-transaction' in result.stdout
    assert _journal_state(root) == before
    assert all(Path(value['paths'][0]).read_bytes() == b'changed ingress' for value in context['owners'])
    events = (root / 'events').read_text().splitlines()
    assert 'ingress-restore' not in events and 'ingress-begin' not in events and 'stage' not in events
    # With the outer route open the rescue stops the candidates, cannot restore, and never resumes the accepted generation.
    assert events == (['quiesce'] if outer == 'open' else [])
    assert (root / 'state').read_text() == ('stopped' if outer == 'open' else 'accepted-running')


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
        'Read the interrupted egress outer route ownership',
        'Refuse adoption when the egress outer route ownership cannot be read',
        "Adopt the interrupted transaction as this block's sole compensation owner",
        'Refuse to capture while an interrupted protected ingress transaction awaits compensation']
    detect, pending, pending_refuse, admit, locate, outer, unreadable, adopt, refuse = steps
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
    finish = next(value for value in commit if value['name'].startswith('Commit the complete native consumer'))
    assert finish['ansible.builtin.command']['argv'][2] == OUTER_HELPER
    assert locate['ansible.builtin.stat'] == {'path': OUTER_HELPER, 'follow': False}
    # The status helper runs as root only after the role's one shared admission of its ancestry and file.
    assert admit['ansible.builtin.include_role'] == {'name': 'transport-egress', 'tasks_from': 'helper-authority'}
    assert admit['when'] == ['_transport_ingress_interrupted.stat.exists', 'not ansible_check_mode']
    prepare = yaml.safe_load((EGRESS_TASKS / 'runtime-prepare.yml').read_text())
    assert prepare[0]['ansible.builtin.import_tasks'] == 'helper-authority.yml' and 'consumer-helper-authority-refused' not in (EGRESS_TASKS / 'runtime-prepare.yml').read_text()
    shared = yaml.safe_load((EGRESS_TASKS / 'helper-authority.yml').read_text())
    assert len(shared) == 1 and shared[0]['check_mode'] is False and shared[0]['changed_when'] is False
    assert any('transport_runtime_' in part and "'outer'" in part for part in shared[0]['ansible.builtin.command']['argv'])
    assert outer['ansible.builtin.command']['argv'] == ['/usr/bin/python3', '-Es', OUTER_HELPER, 'status']
    assert outer['no_log'] is True and outer['failed_when'] is False and outer['changed_when'] is False
    for step in (locate, outer, adopt):
        assert 'not ansible_check_mode' in step['when'] and '_transport_ingress_interrupted.stat.exists' in step['when']
    # Dry-run reports the category only; adoption never happens in check mode.
    assert set(adopt['ansible.builtin.set_fact']) == {'transport_site_transaction_active', '_transport_egress_transaction_started'}
    assert unreadable['when'] == '_transport_ingress_interrupted_outer.rc | default(0) != 0'
    assert 'regex_findall' in unreadable['ansible.builtin.fail']['msg'] and 'no_log' not in unreadable
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
                              'tasks': source + [{'ansible.builtin.assert': {'that': ["_transport_ingress_request.owners[0].paths | sort == expected_xhttp", "_transport_ingress_request.owners[1].paths | sort == expected_self"]}, 'no_log': True}]}])
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
    names = {'Stage exact public assets in the same compensated nginx publication',
             'Stage hostname-bound public pages in the same compensated publication',
             'Stage removal of the exact retired security contact alongside the site'}
    tasks = [copy.deepcopy(value) for value in source if value.get('name') in names]
    assert len(tasks) == 3 and all('ansible.builtin.set_fact' in value and 'notify' not in value for value in tasks)
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
