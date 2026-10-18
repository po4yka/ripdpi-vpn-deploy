"""Actual forwarded source ports fit the stateless provider return domain."""
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
import json,os,pathlib,socket,subprocess,sys,tempfile,time
payload=json.load(sys.stdin)
def run(*args,check=True):
 result=subprocess.run(args,capture_output=True,text=True,timeout=15)
 if check and result.returncode: raise AssertionError(result.stdout+result.stderr)
 return result
def peer():
 process=subprocess.Popen(['unshare','--net',sys.executable,'-c','import time; time.sleep(180)'])
 for _ in range(100):
  if pathlib.Path('/proc/self/ns/net').readlink()!=pathlib.Path(f'/proc/{process.pid}/ns/net').readlink(): return process
  time.sleep(.01)
 raise AssertionError('namespace-not-ready')
# Docker can mount /proc/sys read-only while procps reports a successful
# ignored write. The caller owns a private mount namespace as well as netns.
# On a VM this can be a plain proc directory; bind it before remounting.
run('mount','--bind','/proc/sys','/proc/sys')
run('mount','-o','remount,rw','/proc/sys')
client=peer(); upstream=peer(); server=None
def inside(process,*args,check=True):
 return run('nsenter','--target',str(process.pid),'--net',*args,check=check)
try:
 for process in (client,upstream): inside(process,'ip','link','set','lo','up')
 run('ip','link','set','lo','up')
 for interface,process,network,v6 in [(payload['interface'],client,'10.201.0','fd00:201::'),('eth0',upstream,'192.0.2','2001:db8:201::')]:
  run('ip','link','add',interface,'type','veth','peer','name','other')
  run('ip','link','set','other','netns',str(process.pid))
  run('ip','addr','add',network+'.1/24','dev',interface)
  run('ip','-6','addr','add',v6+'1/64','dev',interface,'nodad')
  run('ip','link','set',interface,'up')
  inside(process,'ip','addr','add',network+'.2/24','dev','other')
  inside(process,'ip','-6','addr','add',v6+'2/64','dev','other','nodad')
  inside(process,'ip','link','set','other','up')
  inside(process,'ip','route','add','default','via',network+'.1')
  inside(process,'ip','-6','route','add','default','via',v6+'1')
 run('sysctl','-qw','net.ipv4.ip_forward=1')
 run('sysctl','-qw','net.ipv6.conf.all.forwarding=1')
 for key in ('net.ipv4.ip_forward','net.ipv6.conf.all.forwarding'):
  assert run('sysctl','-n',key).stdout.strip()=='1',key+'-not-effective'
 with tempfile.TemporaryDirectory() as temporary:
  directory=pathlib.Path(temporary)
  fragment=directory/'sources.nft'
  fragment.write_text('set vpn_tailnet_ssh_v4 { type ipv4_addr; flags interval; }\nset vpn_tailnet_ssh_v6 { type ipv6_addr; flags interval; }\n')
  policy=directory/'policy.nft'
  policy.write_text(payload['firewall'].replace('/etc/nftables.d/vpn-tailnet-ssh-sets.nft',str(fragment))+payload['split'])
  run('nft','-c','-f',str(policy)); run('nft','-f',str(policy))
  # The provider rejects outside-range replies before guest DNAT can change
  # their destination port. This is an actual packet filter, not a socket mock.
  provider=directory/'provider.nft'
  provider.write_text('table inet provider {\n chain ingress {\n type filter hook prerouting priority -150;\n iifname "eth0" meta l4proto { tcp, udp } th dport != 32768-60999 drop\n }\n}\n')
  run('nft','-f',str(provider))
  if payload['split']:
   state=run('nft','-j','list','table','inet','split_hop_egress').stdout
   checked=subprocess.run([sys.executable,'-c',payload['shape'],payload['interface'],'eth0','32768-60999'],input=state,text=True,capture_output=True,timeout=10)
   assert checked.returncode==0,checked.stderr+state
  echo=r'''
import json,socket,sys
family=int(sys.argv[1]); kind=int(sys.argv[2]); address=sys.argv[3]
s=socket.socket(family,kind); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind((address,28080)); s.settimeout(5)
if kind==socket.SOCK_STREAM: s.listen(1)
print('ready',flush=True)
if kind==socket.SOCK_STREAM:
 c,peer=s.accept(); c.recv(100); c.sendall(json.dumps(peer[1]).encode()); c.close()
else:
 data,peer=s.recvfrom(100); s.sendto(json.dumps(peer[1]).encode(),peer)
s.close()
'''
  probe=r'''
import json,socket,sys
family,kind,port=map(int,sys.argv[1:4]); source,destination=sys.argv[4:]
s=socket.socket(family,kind); s.settimeout(4); s.bind((source,port))
s.connect((destination,28080)); s.sendall(b'probe'); mapped=json.loads(s.recv(100))
assert 32768<=mapped<=60999 and mapped!=port,mapped
s.close(); print(mapped)
'''
  families=[(socket.AF_INET,'10.201.0.2','192.0.2.2')]
  if not payload['split']: families.append((socket.AF_INET6,'fd00:201::2','2001:db8:201::2'))
  for family,source,destination in families:
   for kind in (socket.SOCK_STREAM,socket.SOCK_DGRAM):
    for port in (3074,62000):
     server=subprocess.Popen(['nsenter','--target',str(upstream.pid),'--net',sys.executable,'-c',echo,str(family),str(kind),destination],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
     assert server.stdout.readline().strip()=='ready'
     result=inside(client,sys.executable,'-c',probe,str(family),str(kind),str(port),source,destination,check=False)
     if result.returncode:
      print('failed-probe',payload['interface'],family,kind,port,flush=True)
      print(run('nft','list','chain','inet','filter','forward').stdout,flush=True)
      print(run('nft','list','table','inet','nat',check=False).stdout,flush=True)
      print(run('ip','-6','neigh').stdout,flush=True)
      print(run('ip','-6','route').stdout,flush=True)
      print(inside(client,'ip','-6','neigh').stdout,flush=True)
      print(inside(client,'ip','-6','route').stdout,flush=True)
      print(run('nft','list','chain','inet','filter','input').stdout,flush=True)
      print(run('nft','list','chain','inet','filter','output').stdout,flush=True)
      raise AssertionError(result.stderr)
     assert server.wait(timeout=6)==0,server.stderr.read()
     server=None
  # The guest still refuses unsolicited management traffic on the client side.
  listener=socket.socket(); listener.bind(('10.201.0.1',22)); listener.listen(1)
  denied=inside(client,sys.executable,'-c',"import socket; socket.create_connection(('10.201.0.1',22),.3)",check=False)
  assert denied.returncode!=0
  listener.close()
finally:
 if server is not None:
  server.terminate(); server.wait(timeout=5)
 for process in (client,upstream): process.terminate(); process.wait(timeout=5)
"""


def native_payload(mode):
    variables = merge_render_vars()
    variables["vpn"] = {key: False for key in variables["vpn"] if key.startswith("enable_")}
    variables["vpn"]["enable_amneziawg" if mode == "awg" else "enable_split_hop_egress"] = True
    variables["terraform_nat_source_port_range"] = "32768-60999"
    variables["firewall_awg_uplink_interface"] = "eth0"
    variables["firewall_effective_ssh_ports"] = [22]
    variables["allowed_ssh_cidrs"] = ["203.0.113.42/32"]
    variables["amneziawg_secrets"]["instances"] = [{"name": "awg0", "peers": [{"allowed_ips": {"ipv4": "10.201.0.2/32", "ipv6": "fd00:201::2/128"}}]}]
    variables["split_hop_egress"] = {**variables["split_hop_egress"], "wg_interface": "shop0", "forward_iface": "eth0"}
    firewall = render_template(ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", variables)
    split = ""
    shape = ""
    if mode == "split-hop":
        import yaml
        split = render_template(ROOT / "ansible/roles/split-hop-egress/templates/split-hop-egress.nft.j2", variables)
        tasks = yaml.safe_load((ROOT / "ansible/roles/split-hop-egress/tasks/enable.yml").read_text())
        shape = next(task for task in tasks if task["name"] == "Check exact split-hop egress policy shape")["ansible.builtin.command"]["argv"][2]
    return {"firewall": firewall, "split": split, "shape": shape, "interface": "awg0" if mode == "awg" else "shop0"}


@pytest.mark.parametrize("mode", ["awg", "split-hop"])
def test_forwarded_nat_return_domain_preserves_low_high_client_ports(mode):
    assert sys.platform == "linux" and os.geteuid() == 0
    assert os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    result = subprocess.run(["unshare", "--net", "--mount", "--propagation", "private", sys.executable, "-c", NATIVE], input=json.dumps(native_payload(mode)), text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
