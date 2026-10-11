"""Actual final nftables packet boundary in disconnected Linux namespaces."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_transport_egress_kernel import context
from transport_egress_config import build

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime

NATIVE = r'''
import json,os,pathlib,subprocess,sys,tempfile,time,socket,threading,uuid
sys.path.insert(0,sys.argv[1]+'/scripts')
import transport_egress_kernel as k
p=json.load(sys.stdin)
p['normalizer_uid']=21001;p['gateway_uid']=21002
for item in p['listeners']:item['frontend_uid']=21003 if item['name']=='direct_xray' else 21004

def run(*args,data=None,check=True):
 r=subprocess.run(list(args),input=data,text=True,capture_output=True,timeout=15)
 if check and r.returncode:raise RuntimeError(r.stderr)
 return r
name='rdb-peer-'+uuid.uuid4().hex[:10]
root=pathlib.Path(tempfile.mkdtemp(prefix='rdb-kernel-'));k.STATE=root;peer=None
PEER=r"""
import socket,sys,threading,json,pathlib,time
root=pathlib.Path(sys.argv[1]);counts={'public_tcp':0,'public_udp':0,'remote_ssh':0,'private_tcp':0,'private_udp':0};lock=threading.Lock()
def record(name):
 with lock:
  counts[name]+=1;(root/'counts.new').write_text(json.dumps(counts));(root/'counts.new').replace(root/'counts.json')
def serve(addr,port,kind,udp=False):
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((addr,port));s.settimeout(.2)
 if not udp:s.listen()
 def loop():
  while True:
   try:
    if udp:
     data,client=s.recvfrom(2048);record(kind);s.sendto(data,client)
    else:
     c,_=s.accept();record(kind)
     with c:c.sendall(c.recv(2048))
   except socket.timeout:pass
 threading.Thread(target=loop,daemon=True).start()
serve('192.0.2.80',9000,'public_tcp');serve('192.0.2.80',9000,'public_udp',True);serve('192.0.2.80',2222,'remote_ssh')
serve('10.0.0.1',9000,'private_tcp');serve('10.0.0.1',9000,'private_udp',True)
(root/'ready').write_text('ready')
while True:time.sleep(1)
"""
DIAL=r"""
import os,socket,sys
os.setgroups([]);os.setgid(int(sys.argv[1]));os.setuid(int(sys.argv[1]))
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if sys.argv[4]=='udp' else socket.SOCK_STREAM);s.settimeout(.5)
try:
 if sys.argv[4]=='udp':s.sendto(b'boundary-positive',(sys.argv[2],int(sys.argv[3])));r=s.recv(2048)
 else:s.connect((sys.argv[2],int(sys.argv[3])));s.sendall(b'boundary-positive');r=s.recv(2048)
 assert r==b'boundary-positive';sys.exit(0)
except (OSError,AssertionError):sys.exit(1)
"""
local_counts={'admin':0,'web':0}
def local(port,key):
 s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('203.0.113.1',port));s.listen();s.settimeout(.2)
 def loop():
  while True:
   try:
    c,_=s.accept();local_counts[key]+=1
    with c:c.sendall(c.recv(2048))
   except socket.timeout:pass
   except OSError:return
 threading.Thread(target=loop,daemon=True).start()
 return s
locals=[]
try:
 run('ip','link','set','lo','up');run('ip','address','add','203.0.113.1/32','dev','lo')
 run('ip','netns','add',name);run('ip','link','add','rdb-host','type','veth','peer','name','rdb-peer');run('ip','link','set','rdb-peer','netns',name)
 run('ip','address','add','192.0.2.1/24','dev','rdb-host');run('ip','link','set','rdb-host','up')
 for args in [('link','set','lo','up'),('address','add','192.0.2.80/24','dev','rdb-peer'),('link','set','rdb-peer','up'),('address','add','10.0.0.1/32','dev','lo')]:run('ip','-n',name,*args)
 run('ip','route','add','10.0.0.1/32','via','192.0.2.80')
 peer=subprocess.Popen(['ip','netns','exec',name,sys.executable,'-c',PEER,str(root)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 until=time.monotonic()+10
 while not (root/'ready').exists() and time.monotonic()<until:time.sleep(.05)
 assert (root/'ready').exists(),'peer-not-ready'
 locals=[local(2222,'admin'),local(8080,'web')]
 p['policy']={'owned_addresses':['203.0.113.1'],'management_tcp_ports':[2222],'management_udp_ports':[]}
 assert json.loads(k.run('apply',p))=={'changed':True}
 assert json.loads(k.run('apply',p))=={'changed':False};k.run('verify',p)
 def dial(address,port=9000,network='tcp'):
  return run(sys.executable,'-c',DIAL,str(p['gateway_uid']),address,str(port),network,check=False).returncode==0
 assert dial('192.0.2.80') and dial('192.0.2.80',network='udp')
 assert dial('192.0.2.80',2222) and dial('203.0.113.1',8080)
 assert not dial('10.0.0.1') and not dial('10.0.0.1',network='udp') and not dial('203.0.113.1',2222)
 # An earlier ACCEPT is not terminal across independent base chains. DNAT runs before the final destination boundary.
 rewrites="""table inet rewrites { chain early { type filter hook output priority 0; policy accept; meta skuid 21002 accept; }
chain change { type nat hook output priority -100; policy accept; ip daddr 192.0.2.80 tcp dport 9010 dnat to 10.0.0.1:9000; ip daddr 192.0.2.80 udp dport 9010 dnat to 10.0.0.1:9000; ip daddr 192.0.2.80 tcp dport 9011 dnat to 203.0.113.1:2222; }
}"""
 run('nft','-f','-',data=rewrites);k.run('verify',p)
 assert not dial('192.0.2.80',9010) and not dial('192.0.2.80',9010,'udp') and not dial('192.0.2.80',9011)
 assert dial('192.0.2.80') and dial('192.0.2.80',network='udp')
 # Unsupported late authority refuses activation while retaining the accepted guard.
 run('nft','-f','-',data='table inet unsupported { chain late { type route hook output priority 301; policy accept; }; }')
 try:k.run('apply',p);raise AssertionError('late-authority-admitted')
 except k.BoundaryError:pass
 assert not dial('10.0.0.1')
 run('nft','delete','table','inet','unsupported')
 # Postrouting jumps/gotos inherit late mutation authority even in ordinary chains.
 for transfer in ['jump','goto']:
  rule=f"table inet unsupported {{ chain helper {{ ip daddr set 10.0.0.1; }}; chain post {{ type filter hook postrouting priority 0; policy accept; {transfer} helper; }}; }}"
  run('nft','-f','-',data=rule)
  try:k.run('apply',p);raise AssertionError('indirect-late-mutation-admitted')
  except k.BoundaryError:pass
  run('nft','delete','table','inet','unsupported')
 assert dial('192.0.2.80') and not dial('10.0.0.1')
 # A malformed candidate cannot replace or weaken the accepted table.
 bad=json.loads(json.dumps(p));bad['gateway_uid']=0
 try:k.run('apply',bad);raise AssertionError('invalid-policy-admitted')
 except k.BoundaryError:pass
 k.run('verify',p);assert dial('192.0.2.80')
 counts=json.loads((root/'counts.json').read_text())
 assert counts['private_tcp']==counts['private_udp']==local_counts['admin']==0,counts
 assert counts['public_tcp']>=3 and counts['public_udp']>=2 and counts['remote_ssh']==1 and local_counts['web']==1
 print(json.dumps({'public_tcp_udp':True,'remote_ssh_and_own_web':True,'private_and_own_admin_contacts':0,'after_accept_dnat_guard':True,'late_authority_refused':True,'accepted_policy_preserved':True}))
finally:
 for s in locals:s.close()
 if peer is not None:
  peer.terminate()
  try:peer.wait(timeout=3)
  except subprocess.TimeoutExpired:peer.kill();peer.wait()
 run('ip','netns','delete',name,check=False)
 import shutil;shutil.rmtree(root)
'''


def test_final_kernel_addresses_public_plumbing_and_candidate_preservation_native():
    assert sys.platform == 'linux' and os.geteuid() == 0
    assert os.environ.get('TRANSPORT_NATIVE_ISOLATED') == '1', 'owned disconnected Linux runner required'
    policy = build(context())['policy']
    result = subprocess.run(['unshare', '--net', '--mount', '--propagation', 'private', sys.executable, '-c', NATIVE, str(ROOT)], input=json.dumps(policy), text=True, capture_output=True, timeout=75)
    assert result.returncode == 0, result.stdout+result.stderr
    receipt = json.loads(result.stdout.splitlines()[-1])
    assert receipt['private_and_own_admin_contacts'] == 0
    assert all(value is True for key, value in receipt.items() if key != 'private_and_own_admin_contacts')
