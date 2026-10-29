"""Current rendered firewall runs in a disposable native network namespace."""

from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime
NATIVE = r"""
import sys,json
PAYLOAD=json.load(sys.stdin)
import ipaddress,json,pathlib,subprocess,tempfile,time

def run(*args,check=True):
 result=subprocess.run(list(args),check=False,capture_output=True,text=True,timeout=15)
 if check and result.returncode: raise RuntimeError(result.stderr)
 return result
def nft(*args): return run('/usr/sbin/nft',*args).stdout
def values(name):
 data=json.loads(nft('-j','list','set','inet','filter',name))
 return next(row['set'] for row in data['nftables'] if 'set' in row)
def expiry(name,address):
 for item in values(name)['elem']:
  entry=item['elem']
  if ipaddress.ip_address(entry['val'])==ipaddress.ip_address(address): return entry['expires']
 raise AssertionError('membership-lost')
with tempfile.TemporaryDirectory(prefix='vpn-p2-nft-') as temporary:
 directory=pathlib.Path(temporary)
 fragment=directory/'sources.nft'
 fragment.write_text('set vpn_tailnet_ssh_v4 { type ipv4_addr; flags interval; elements = { 198.51.100.21/32 }; }\nset vpn_tailnet_ssh_v6 { type ipv6_addr; flags interval; }\n')
 candidate=directory/'candidate.nft'
 def load(name):
  candidate.write_text(PAYLOAD['variants'][name].replace('/etc/nftables.d/vpn-tailnet-ssh-sets.nft',str(fragment)))
  nft('-c','-f',str(candidate)); nft('-f',str(candidate))
 load('host')
 selected=[('f2b_sshd4','198.51.100.22'),('f2b_sshd6','2001:db8::22'),('policy_offenders','198.51.100.23'),('policy_offenders6','2001:db8::23')]
 for name,address in selected: nft('add','element','inet','filter',name,'{',address,'timeout','90s','}')
 before={name:expiry(name,address) for name,address in selected}
 time.sleep(1.1)
 for variant in ['xhttp','snell','host']:
  load(variant)
  for name,address in selected:
   current=expiry(name,address)
   print(json.dumps({'before':before[name],'remaining':current}))
   assert 0<current<before[name]
  output=nft('list','chain','inet','filter','output')
  assert ('tcp accept' in output)==(variant!='host')
  assert ('udp accept' in output)==(variant!='host')
 fragment.write_text('set vpn_tailnet_ssh_v4 { type ipv4_addr; flags interval; elements = { 203.0.113.21/32 }; }\nset vpn_tailnet_ssh_v6 { type ipv6_addr; flags interval; }\n')
 load('host')
 source=nft('list','set','inet','filter','vpn_tailnet_ssh_v4')
 assert '203.0.113.21' in source and '198.51.100.21' not in source
 load('collector')
 rules=json.loads(nft('-j','list','chain','inet','filter','input'))['nftables']
 rule=next(row['rule'] for row in rules if row.get('rule',{}).get('comment')=='private-collector-ingress')
 assert rule['expr']==[
  {'match':{'op':'==','left':{'meta':{'key':'iifname'}},'right':'tailscale0'}},
  {'match':{'op':'==','left':{'payload':{'protocol':'ip','field':'daddr'}},'right':'100.64.0.2'}},
  {'match':{'op':'==','left':{'payload':{'protocol':'ip','field':'saddr'}},'right':{'set':['100.64.0.3','100.64.0.4']}}},
  {'match':{'op':'==','left':{'payload':{'protocol':'tcp','field':'dport'}},'right':9443}},
  {'accept':None}]
 load('host')
 assert 'private-collector-ingress' not in nft('list','chain','inet','filter','input')
 helper=directory/'helper.py'; helper.write_text(PAYLOAD['helper'])
 for address in ['198.51.100.24','2001:db8::24']:
  for operation in ['ban','ban','unban','unban']:
   argv=['/usr/bin/python3',str(helper),operation,address]
   if operation=='ban': argv.append('30')
   result=run(*argv,check=False)
   assert result.returncode==0,(operation,result.stderr)
 nft('flush','table','inet','filter'); nft('destroy','set','inet','filter','f2b_sshd4')
 result=run('/usr/bin/python3',str(helper),'ban','198.51.100.24','30',check=False)
 assert result.returncode==1 and result.stderr=='Fail2Ban nft enforcement failed\n'
 print(json.dumps({"fresh_reload_and_profile_egress":True,"v4_v6_timed_membership_and_expiry_preserved":True,"static_sources_replaced":True,"native_ban_unban_races":True,"missing_set_fails":True}))
"""


def test_fresh_reload_timed_sets_static_sources_and_proxy_egress_native():
    assert os.geteuid() == 0
    variants = {}
    for name, toggle in [
        ("host", None),
        ("xhttp", "enable_nginx_xhttp"),
        ("snell", "enable_snell"),
    ]:
        variables = merge_render_vars()
        variables["vpn"] = {
            key: False for key in variables["vpn"] if key.startswith("enable_")
        }
        variables["vpn"]["enable_policy_ratelimit"] = True
        if toggle:
            variables["vpn"][toggle] = True
        variables["security_controls"] = {"fail2ban": True}
        variables["firewall_egress_policy"] = "strict"
        variants[name] = render_template(
            ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", variables
        )
    payload = {
        "variants": variants,
        "helper": (
            ROOT / "ansible/roles/intrusion_prevention/files/vpn-fail2ban-nft.py"
        ).read_text(),
    }
    variables['firewall_tailnet_collector_ingress'] = {
        'address': '100.64.0.2', 'sources': ['100.64.0.3', '100.64.0.4']}
    variants['collector'] = render_template(
        ROOT / 'ansible/roles/firewall/templates/nftables.conf.j2', variables)
    result = subprocess.run(
        ["unshare", "--net", sys.executable, "-c", NATIVE],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


IPV6_CONTROL = r'''
import json,pathlib,socket,subprocess,sys,tempfile,time
payload=json.load(sys.stdin)
def run(*argv,check=True):
 result=subprocess.run(argv,check=False,capture_output=True,text=True,timeout=15)
 if check and result.returncode: raise AssertionError(result.stderr)
 return result
peer=subprocess.Popen(['unshare','--net',sys.executable,'-c','import time; time.sleep(60)'])
server=None
try:
 for _ in range(100):
  if pathlib.Path('/proc/self/ns/net').readlink()!=pathlib.Path(f'/proc/{peer.pid}/ns/net').readlink(): break
  time.sleep(.01)
 else: raise AssertionError('peer namespace did not start')
 def inside(*argv): return run('nsenter','--target',str(peer.pid),'--net',*argv)
 run('ip','link','set','lo','up'); inside('ip','link','set','lo','up')
 run('ip','link','add','audit-left','type','veth','peer','name','audit-right')
 run('ip','link','set','audit-right','netns',str(peer.pid))
 run('ip','link','set','audit-left','up'); inside('ip','link','set','audit-right','up')
 run('ip','-6','address','add','fd42:abcd::1/64','dev','audit-left','nodad')
 inside('ip','-6','address','add','fd42:abcd::2/64','dev','audit-right','nodad')
 with tempfile.TemporaryDirectory() as temp:
  directory=pathlib.Path(temp)
  fragment=directory/'sources.nft'
  fragment.write_text('set vpn_tailnet_ssh_v4 { type ipv4_addr; flags interval; }\nset vpn_tailnet_ssh_v6 { type ipv6_addr; flags interval; }\n')
  candidate=directory/'candidate.nft'
  candidate.write_text(payload.replace('/etc/nftables.d/vpn-tailnet-ssh-sets.nft',str(fragment)))
  run('nft','-c','-f',str(candidate)); run('nft','-f',str(candidate))
  code="""import socket
s=socket.socket(socket.AF_INET6); s.bind(('fd42:abcd::2',443)); s.listen(); print('ready',flush=True)
for _ in range(2):
 c,_=s.accept(); c.sendall(b'ok'); c.close()
"""
  server=subprocess.Popen(['nsenter','--target',str(peer.pid),'--net',sys.executable,'-c',code],stdout=subprocess.PIPE,text=True)
  assert server.stdout.readline().strip()=='ready'
  for _ in range(2):
   run('ip','-6','neigh','flush','dev','audit-left')
   inside('ip','-6','neigh','flush','dev','audit-right')
   with socket.socket(socket.AF_INET6) as client:
    client.settimeout(3); client.connect(('fd42:abcd::2',443)); assert client.recv(2)==b'ok'
  server.wait(timeout=5)
  # An unrelated outbound ICMPv6 echo still fails the strict policy.
  assert run('ping','-6','-c','1','-W','1','fd42:abcd::2',check=False).returncode!=0
  assert 'policy drop' in run('nft','list','chain','inet','filter','output').stdout
finally:
 if server is not None and server.poll() is None: server.terminate(); server.wait(timeout=5)
 peer.terminate(); peer.wait(timeout=5)
'''


def test_strict_ipv6_neighbor_resolution_survives_empty_caches():
    assert os.geteuid() == 0
    variables = merge_render_vars()
    variables["firewall_egress_policy"] = "strict"
    variables["vpn"] = {key: False for key in variables["vpn"] if key.startswith("enable_")}
    rendered = render_template(ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", variables)
    result = subprocess.run(["unshare", "--net", sys.executable, "-c", IPV6_CONTROL],
                            input=json.dumps(rendered), capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


SSH_ROTATION = r'''
import base64,json,os,pathlib,subprocess,sys,time,types
p=json.load(sys.stdin)
for name in ('transport_runtime_transaction','firewall_consumer'):
 module=types.ModuleType(name);module.__file__=str(pathlib.Path(p['root'])/(name+'.py'));sys.modules[name]=module
 exec(compile(p[name],module.__file__,'exec'),module.__dict__)
tx=sys.modules['transport_runtime_transaction'];fw=sys.modules['firewall_consumer']
root=pathlib.Path(p['root']);fw.STATE=root/'state';fw.STATE.mkdir(mode=0o700);fw.CONFIG=root/'candidate.nft'
before=fw.HEADER+b'table inet filter;\nflush table inet filter\ndestroy set inet filter f2b_sshd4\ntable inet filter {\n chain input {\n  type filter hook input priority 0; policy drop;\n  tcp dport 22 ip saddr { 1.1.1.1/32, 9.9.9.9/32 } accept\n }\n}\n'
fw.CONFIG.write_bytes(before);fw.CONFIG.chmod(0o644)
subprocess.run(['nft','-f',str(fw.CONFIG)],check=True)
subprocess.run(['nft','add','set','inet','filter','f2b_sshd4','{','type','ipv4_addr',';','flags','timeout',';','}'],check=True)
subprocess.run(['nft','add','element','inet','filter','f2b_sshd4','{','8.8.4.4','timeout','90s','}'],check=True)
subprocess.run(['nft','add','table','inet','foreign'],check=True)
def timed():
 data=json.loads(subprocess.check_output(['nft','-j','list','set','inet','filter','f2b_sshd4']))
 value=next(v['set'] for v in data['nftables'] if 'set' in v)
 entry=value['elem'][0]['elem'];assert entry['val']=='8.8.4.4'
 return value['handle'],entry['expires']
handle,remaining=timed()
with tx.Transaction(fw.STATE,uid=0) as active:
 active.record('accepted.json',{'schema':1,'nodes':{str(fw.CONFIG):tx.node(fw.CONFIG,0)},'previous':None,'units':{}})
request={'old_source':'1.1.1.1','new_source':'208.67.222.222','port':22}
plan=fw.operate('rotate-ssh',{**request,'check':True})['plan']
time.sleep(1.1)
fw.operate('rotate-ssh',{**request,'plan':plan})
assert fw.CONFIG.read_bytes()==before.replace(b'1.1.1.1',b'208.67.222.222')
current,expiry=timed();assert current==handle and 0<expiry<remaining
fw.operate('restore',{'owner':'site'})
assert fw.CONFIG.read_bytes()==before
current,expiry=timed();assert current==handle and 0<expiry<remaining
assert any(row.get('table',{}).get('name')=='foreign' for row in fw.live_policy()['nftables'])
plan=fw.operate('rotate-ssh',{**request,'check':True})['plan']
fw.operate('rotate-ssh',{**request,'plan':plan})
fw.operate('finish',{'owner':'site'})
assert not (fw.STATE/'consumer.json').exists() and not (fw.STATE/'ssh-rotation.json').exists()
assert timed()[0]==handle
print(json.dumps({'native_single_rule_apply_restore':True,'timed_set_identity_and_expiry_preserved':True,'foreign_table_preserved':True,'finish':True}))
'''


def test_exact_ssh_rotation_preserves_native_timed_sets(private_authority_path):
    assert os.geteuid() == 0
    payload = {'root': str(private_authority_path)}
    for name, path in (
        ('transport_runtime_transaction', 'runtime-release/files/transport_runtime_transaction.py'),
        ('firewall_consumer', 'firewall/files/firewall_consumer.py'),
    ):
        payload[name] = (ROOT / 'ansible/roles' / path).read_text()
    result = subprocess.run(
        ['unshare', '--net', sys.executable, '-c', SSH_ROTATION],
        input=json.dumps(payload), text=True, capture_output=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
