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
    result = subprocess.run(
        ["unshare", "--net", sys.executable, "-c", NATIVE],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
