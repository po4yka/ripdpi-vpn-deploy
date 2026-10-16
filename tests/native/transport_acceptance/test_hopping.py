"""Firewall-owned real QUIC hopping across both routed IP families."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest
import yaml

from native_common import ROOT, fixture
from template_render import render_template

pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize('family', [4, 6])
def test_native_hopping_no_net_admin_outbound_preserved_and_repeated_removal(family):
    stack = fixture.NativeStack()
    client_ns = stack.token + 'c'
    created = False
    try:
        stack.start()
        stack.start_frontend('hysteria')
        server_ns = stack.namespace
        fixture.command(['ip','netns','add',client_ns]); created = True
        fixture.command(['ip','-n',client_ns,'link','set','lo','up'])
        fixture.command(['ip','link','add',stack.token+'a','type','veth','peer','name',stack.token+'b'])
        for namespace, link, v4, v6 in ((server_ns,stack.token+'a','198.18.0.1/30','fd87::1/64'),
                                       (client_ns,stack.token+'b','198.18.0.2/30','fd87::2/64')):
            fixture.command(['ip','link','set',link,'netns',namespace])
            fixture.command(['ip','-n',namespace,'addr','add',v4,'dev',link])
            fixture.command(['ip','-n',namespace,'addr','add',v6,'dev',link,'nodad'])
            fixture.command(['ip','-n',namespace,'link','set',link,'up'])
        stack.values['vpn']['enable_hysteria'] = True
        stack.values['hysteria_port_range'] = '46000-46015'
        def run(*args, data=None):
            result = subprocess.run(['ip','netns','exec',server_ns,*args],input=data,text=True,capture_output=True,timeout=15)
            assert result.returncode == 0, 'owned-hopping-firewall-operation-refused'
            return result.stdout
        run('nft','add','table','inet','foreign_witness')
        foreign = run('nft','-j','list','table','inet','foreign_witness')
        run('nft','add','table','inet','owned_hops')
        run('nft','-f','-', data='add chain inet owned_hops prerouting { type nat hook prerouting priority dstnat; }\n')
        rendered = render_template(ROOT/'ansible/roles/firewall/templates/nftables.conf.j2', stack.values)
        redirect = [row.strip() for row in rendered.splitlines() if 'comment "hysteria-port-hopping"' in row]
        assert len(redirect) == 1
        rows = ''.join(f'add rule inet owned_hops prerouting meta nfproto ipv{family} udp dport {port} counter\n' for port in range(46000,46016))
        run('nft','-f','-',data=rows+'add rule inet owned_hops prerouting '+redirect[0]+'\n')
        def counters():
            doc = json.loads(run('nft','-j','list','table','inet','owned_hops'))
            return [part['counter']['packets'] for row in doc['nftables'] if 'rule' in row
                    for part in row['rule']['expr'] if 'counter' in part][:16]
        # Client lives across a veth, so requests traverse PREROUTING, never OUTPUT.
        stack.namespace = client_ns
        port = stack.start_client('hysteria')
        stack.namespace = server_ns
        path = stack.library / f'client-valid-{stack.client_count}.yaml'
        value = yaml.safe_load(path.read_text())
        host = '198.18.0.1' if family == 4 else '[fd87::1]'
        value['server'] = host + ':46000-46015'
        value['transport'] = {'udp':{'hopInterval':'5s'}}
        path.write_text(yaml.safe_dump(value))
        fixture.command(['systemctl','restart',stack.units[-1]])
        # The actual daemon must lack CAP_NET_ADMIN, independently of fixture root.
        unit = stack.token+'-hysteria'
        pid = int(fixture.command(['systemctl','show',unit,'-p','MainPID','--value']))
        status = (Path('/proc')/str(pid)/'status').read_text()
        caps = next(row.split()[1] for row in status.splitlines() if row.startswith('CapEff:'))
        assert not int(caps,16) & (1 << 12)
        deadline = time.monotonic()+75
        while True:
            stack.namespace = client_ns
            stack.run_driver(port)
            stack.namespace = server_ns
            if sum(count > 0 for count in counters()) >= 2:
                break
            assert time.monotonic() < deadline, 'two-native-hop-destinations-unobserved'
        # Outbound UDP to a range port must reach the actual foreign destination.
        echo = '''import socket,sys
s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET,socket.SOCK_DGRAM)
s.bind((sys.argv[1],46001));s.settimeout(10)
data,peer=s.recvfrom(4096);s.sendto(data,peer)
'''
        address = '198.18.0.2' if family == 4 else 'fd87::2'
        process = subprocess.Popen(['ip','netns','exec',client_ns,sys.executable,'-c',echo,address],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        stack.processes.append(process)
        time.sleep(.2)
        run(sys.executable,'-c',"import socket,sys;s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(5);s.sendto(b'foreign-destination',(sys.argv[1],46001));assert s.recv(4096)==b'foreign-destination'",address)
        assert process.wait(timeout=12) == 0
        stack.values['hysteria_port_range'] = ''
        without = render_template(ROOT/'ansible/roles/firewall/templates/nftables.conf.j2',stack.values)
        assert 'comment "hysteria-port-hopping"' not in without
        for _ in range(2):
            run('nft','flush','chain','inet','owned_hops','prerouting')
            assert run('nft','-j','list','table','inet','foreign_witness') == foreign
            value['server'] = host + ':443'
            value.pop('transport',None)
            path.write_text(yaml.safe_dump(value))
            fixture.command(['systemctl','restart',stack.units[-1]])
            stack.namespace = client_ns
            stack.run_driver(port)
            stack.namespace = server_ns
    finally:
        # Unit stop must precede namespace retirement.
        stack.namespace = stack.token
        stack.close()
        if created:
            fixture.command(['ip','netns','delete',client_ns])
