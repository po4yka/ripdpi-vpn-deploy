"""Canonical nftables plus exact AWG clients on constrained dual-stack paths."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from awg_client import config, export
from awg_device_binding import resolve_binding
from template_render import merge_render_vars, render_template
from test_awg_device_binding import document
from test_awg_device_binding_native import native_config
from test_transport_semantics_native import command, exact_awg_sources

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]

# Independent actual sockets terminate only inside the owned uplink namespace.
ECHO = r'''
import socket, struct, sys, threading
family = socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET
address = sys.argv[1]
def udp(port):
    s = socket.socket(family, socket.SOCK_DGRAM); s.bind((address, port))
    while True:
        data, peer = s.recvfrom(65535)
        if port == 53:
            kind = struct.unpack('!H', data[-4:-2])[0]
            value = socket.inet_pton(socket.AF_INET6 if kind == 28 else socket.AF_INET,
                                     'fd88::2' if kind == 28 else '198.18.1.2')
            data = data[:2] + b'\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00' + data[12:] + b'\xc0\x0c' + struct.pack('!HHIH',kind,1,30,len(value)) + value
        s.sendto(data, peer)
for port in (32000, 53): threading.Thread(target=udp, args=(port,), daemon=True).start()
s = socket.socket(family); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind((address,32000)); s.listen()
def stream(c):
    with c:
        while data := c.recv(65535): c.sendall(data)
while True:
    c,_ = s.accept(); threading.Thread(target=stream,args=(c,),daemon=True).start()
'''
PROBE = r'''
import json, os, socket, struct, sys, time
address = sys.argv[1]; family = socket.AF_INET6 if ':' in address else socket.AF_INET
bind = sys.argv[2] if len(sys.argv)>2 else None
started=time.monotonic(); received=0
for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
    with socket.socket(family,kind) as s:
        s.settimeout(2)
        if bind: s.bind((bind,0))
        s.connect((address,32000))
        for i in range(24):
            payload=os.urandom(4096 if kind==socket.SOCK_STREAM else 1200)
            s.sendall(payload); response=b''
            while len(response)<len(payload):
                part=s.recv(65535)
                if not part: raise SystemExit(2)
                response+=part
            assert response==payload
            received+=len(response)
for qtype in (1,28):
    with socket.socket(family,socket.SOCK_DGRAM) as s:
        s.settimeout(2); s.connect((address,53))
        query=b'\x17\x42\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x05owned\x07example\x00'+struct.pack('!HH',qtype,1)
        s.send(query); response=s.recv(4096)
        value=socket.inet_pton(socket.AF_INET6 if qtype==28 else socket.AF_INET,'fd88::2' if qtype==28 else '198.18.1.2')
        assert response[:2]==query[:2] and response[6:8]==b'\x00\x01' and response.endswith(value)
print(json.dumps({'bytes':received,'seconds':time.monotonic()-started,'udp_sent':24,'udp_received':24,'dns_types':[1,28]}))
'''


@pytest.mark.parametrize('members', [1, 2])
def test_owned_uplink_nat_mtu_dns_reconnect_revocation_and_no_native_bypass(tmp_path, members):
    go, tools = exact_awg_sources()
    token = uuid.uuid4().hex[:7]
    namespaces, processes = [], []
    server, uplink = 'as'+token, 'au'+token
    clients = ['ac'+token+str(i) for i in range(members)]
    interfaces = ['a7'+token, 'a9'+token][:members]
    doc = document()
    doc['amneziawg_secrets']['instances'] = doc['amneziawg_secrets']['instances'][:members]
    doc['client_registry'] = {name: entry for name, entry in doc['client_registry'].items()
                              if name in [f'device{i}' for i in range(members)]}
    for i, item in enumerate(doc['amneziawg_secrets']['instances']):
        item.update(name=interfaces[i], mtu=1280, jc=0, s1=0, s2=0)
        doc['client_registry'][f'device{i}']['awg_binding']['instance'] = interfaces[i]
    def run(ns, argv, data=None):
        return command(['ip','netns','exec',ns,*map(str,argv)], data=data)
    def link(ns, name, address):
        command(['ip','-n',ns,'address','add',address,'dev',name,'nodad'] if ':' in address
                else ['ip','-n',ns,'address','add',address,'dev',name])
    def veth(left_ns, right_ns, left, right):
        command(['ip','link','add',left,'type','veth','peer','name',right])
        command(['ip','link','set',left,'netns',left_ns])
        command(['ip','link','set',right,'netns',right_ns])
        for ns, iface in ((left_ns,left),(right_ns,right)):
            command(['ip','-n',ns,'link','set',iface,'mtu','1380','up'])
    def start(ns, argv):
        process = subprocess.Popen(['ip','netns','exec',ns,*map(str,argv)],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        processes.append(process)
        return process
    def configure(ns, iface, text, addresses):
        candidate=tmp_path/(iface+'.conf'); candidate.write_text(native_config(text)); candidate.chmod(0o600)
        run(ns,[tools,'setconf',iface,candidate])
        for address in addresses: link(ns,iface,address)
        command(['ip','-n',ns,'link','set',iface,'mtu','1280','up'])
        assert json.loads(command(['ip','-n',ns,'-j','link','show',iface]))[0]['mtu']==1280
    def probe(i, address, *, source=None, accepted=True):
        result=subprocess.run(['ip','netns','exec',clients[i],sys.executable,'-c',PROBE,address,
                               *([source] if source else [])],capture_output=True,text=True,timeout=12)
        assert (result.returncode==0)==accepted, 'authenticated constrained-path result disagrees with policy'
        if accepted:
            measured=json.loads(result.stdout)
            assert measured['bytes']==24*(4096+1200) and measured['seconds']>0
            assert measured['udp_sent']==measured['udp_received'] and measured['dns_types']==[1,28]
            print(json.dumps({'members':members,'client':i,'family':6 if ':' in address else 4,'mtu':1280,**measured}))
    try:
        for ns in (server,uplink,*clients):
            command(['ip','netns','add',ns]); namespaces.append(ns)
            command(['ip','-n',ns,'link','set','lo','up'])
        veth(server,uplink,'up0','echo0')
        for ns,iface,addresses in ((server,'up0',('198.18.1.1/30','fd88::1/64')),
                                   (uplink,'echo0',('198.18.1.2/30','fd88::2/64'))):
            for address in addresses: link(ns,iface,address)
        for name,value in (('net.ipv4.ip_forward','1'),('net.ipv6.conf.all.forwarding','1')):
            run(server,['sysctl','-qw',name+'='+value])
        # Preserve a foreign table through both canonical publication and revocation.
        run(server,['nft','-f','-'],'table inet foreign_owned {\n chain retained {\n counter comment "foreign-retained";\n }\n}\n')
        for i,ns in enumerate(clients):
            left,right='us'+str(i),'uc'+str(i)
            veth(server,ns,left,right)
            endpoint=f'192.0.2.{4*i+1}'
            link(server,left,endpoint+'/30'); link(ns,right,f'192.0.2.{4*i+2}/30')
            # Native fallback routes exist so the kill-switch is exercised after tunnel failure.
            command(['ip','-n',ns,'route','add','default','via',endpoint,'dev',right,'metric','200'])
            link(server,left,f'fd90:{i+1}::1/64'); link(ns,right,f'fd90:{i+1}::2/64')
            command(['ip','-n',ns,'-6','route','add','default','via',f'fd90:{i+1}::1','dev',right,'metric','200'])
            ci='c'+token+str(i)
            for space,iface in ((server,interfaces[i]),(ns,ci)):
                process=start(space,[go,'-f',iface]); deadline=time.monotonic()+10
                while subprocess.run(['ip','-n',space,'link','show',iface],capture_output=True).returncode:
                    assert process.poll() is None and time.monotonic()<deadline
                    time.sleep(.05)
            selected=resolve_binding(doc,{},f'device{i}','upcloud:fixture',interfaces[i])
            block=export(doc,{},f'device{i}','upcloud:fixture',interfaces[i],endpoint)
            values=merge_render_vars(); values['_inst']=selected.instance
            configure(server,interfaces[i],render_template(ROOT/'ansible/roles/amneziawg/templates/awg0.conf.j2',values),
                      [selected.instance['address_v4'],selected.instance['address_v6']])
            configure(ns,ci,config(block).replace('<CLIENT_PRIVATE_KEY>',doc['client_registry'][f'device{i}']['awg_private_key']),block['address'])
            for family in ('-4','-6'):
                command(['ip','-n',ns,family,'route','add','default','dev',ci,'metric','10'])
            run(ns,['nft','-f','-'],f'''table inet lockdown {{ chain output {{ type filter hook output priority 100; policy drop;
              oifname "lo" accept
              oifname "{ci}" accept
              oifname "{right}" ip daddr {endpoint} udp dport {selected.instance['listen_port']} accept
              meta l4proto ipv6-icmp icmpv6 type {{ nd-neighbor-solicit, nd-neighbor-advert }} ip6 hoplimit 255 accept
              counter drop comment "native-bypass-denied"
            }}\n }}\n''')
        values=merge_render_vars()
        values.update(amneziawg_secrets=doc['amneziawg_secrets'],firewall_awg_uplink_interface='up0',
                      security_controls={'fail2ban':False},public_listener_contract=[
                          {'name':name,'protocol':'udp','port':51820+i,'port_range':None} for i,name in enumerate(interfaces)],
                      _firewall_effective_check_mode=True,_firewall_tailnet_ssh_sets_was_absent=True,
                      _firewall_tailnet_initial_fragment=(ROOT/'ansible/roles/firewall/files/vpn-tailnet-ssh-sets.empty.nft').read_text())
        values['vpn']={key:False for key in values['vpn'] if key.startswith('enable_')}
        values['vpn']['enable_amneziawg']=True
        def publish():
            text=render_template(ROOT/'ansible/roles/firewall/templates/nftables.conf.j2',values)
            run(server,['nft','-c','-f','-'],text)
            run(server,['nft','-f','-'],text)
            assert 'foreign-retained' in run(server,['nft','list','table','inet','foreign_owned'])
        publish()
        for address in ('198.18.1.2','fd88::2'): start(uplink,[sys.executable,'-c',ECHO,address])
        time.sleep(.2)
        for cycle in range(3):
            for i,ns in enumerate(clients):
                ci='c'+token+str(i)
                if cycle:
                    command(['ip','-n',ns,'link','set',ci,'down'])
                    command(['ip','-n',ns,'link','set',ci,'up'])
                for address in ('198.18.1.2','fd88::2'): probe(i,address)
        counters=json.loads(run(server,['nft','-j','list','chain','inet','nat','postrouting']))
        for iface in interfaces:
            rules=[entry['rule'] for entry in counters['nftables'] if entry.get('rule',{}).get('comment')=='awg-nat-'+iface]
            assert len(rules)==1
            assert sum(expression.get('counter',{}).get('packets',0) for expression in rules[0]['expr'])>0
        # Spoofed family identities must not be admitted by the server's peer key.
        for address in ('10.70.0.6/32','fd42:10::6/128'): link(clients[0],'c'+token+'0',address)
        probe(0,'198.18.1.2',source='10.70.0.6',accepted=False)
        probe(0,'fd88::2',source='fd42:10::6',accepted=False)
        if members==2:
            for address in ('10.71.0.2','fd42:11::2'):
                start(clients[1],[sys.executable,'-c',ECHO,address])
            time.sleep(.2)
            for address in ('10.71.0.2','fd42:11::2'):
                probe(1,address)
                probe(0,address,accepted=False)
            for address in ('198.18.1.2','fd88::2'): probe(1,address)
        # Removing a key and both source claims denies both families even with retained conntrack.
        revoked_key=doc['amneziawg_secrets']['instances'][0]['peers'][0]['public_key']
        values['amneziawg_secrets']['instances'][0]['peers']=[]
        publish()
        for address in ('198.18.1.2','fd88::2'): probe(0,address,accepted=False)
        run(server,[tools,'set',interfaces[0],'peer',revoked_key,'remove'])
        for address in ('198.18.1.2','fd88::2'): probe(0,address,accepted=False)
        if members==2:
            for address in ('198.18.1.2','fd88::2'): probe(1,address)
        # A missing TUN cannot fall through to either pre-existing native default route.
        command(['ip','-n',clients[0],'link','delete','c'+token+'0'])
        for address in ('198.18.1.2','fd88::2'): probe(0,address,accepted=False)
        lockdown=json.loads(run(clients[0],['nft','-j','list','table','inet','lockdown']))
        denied=[entry['rule'] for entry in lockdown['nftables'] if entry.get('rule',{}).get('comment')=='native-bypass-denied']
        assert sum(expression.get('counter',{}).get('packets',0) for expression in denied[0]['expr'])>0
    finally:
        for process in reversed(processes):
            if process.poll() is None: process.terminate()
        for process in reversed(processes):
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        for ns in reversed(namespaces): command(['ip','netns','delete',ns])
        remaining=command(['ip','netns','list'])
        assert all(ns not in remaining for ns in namespaces)
