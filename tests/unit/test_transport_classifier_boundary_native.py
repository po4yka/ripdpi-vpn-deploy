"""Actual classifier CLI and two disconnected interface paths, not scaffold activation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime

PEER = r'''
import json,pathlib,socket,sys,threading,time
root=pathlib.Path(sys.argv[1]);mode=sys.argv[2];lock=threading.Lock();counts={}
def serve(name,address,port,interface=None):
 s=socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET,socket.SOCK_STREAM)
 s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
 if interface:s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,interface.encode()+b'\0')
 s.bind((address,port));s.listen();counts[name]=0
 def loop():
  while True:
   c,_=s.accept()
   with lock:
    counts[name]+=1;p=root/(mode+'.new');p.write_text(json.dumps(counts));p.replace(root/(mode+'.json'))
   with c:
    data=c.recv(128)
    if data:c.sendall(data)
 threading.Thread(target=loop,daemon=True).start()
if mode=='peer':
 for name,address,port,interface in [('direct','192.0.2.80',9000,'pdirect'),('foreign','198.51.100.80',9000,'pforeign'),
                                     ('private','10.0.0.80',9000,'pdirect'),('own_control','203.0.113.80',9001,'pforeign'),
                                     ('own_web','203.0.113.80',9000,'pforeign'),('remote_control','198.51.100.80',9001,'pforeign')]:
  serve(name,address,port,interface)
else:
 serve('loopback4','127.0.0.2',9000);serve('loopback6','::1',9000)
(root/(mode+'.json')).write_text(json.dumps(counts));(root/(mode+'-ready')).touch()
while True:time.sleep(1)
'''

DRIVER = r'''
import ipaddress,json,pathlib,socket,struct,sys
c=json.load(sys.stdin)
def exact(s,n):
 b=bytearray()
 while len(b)<n:
  x=s.recv(n-len(b))
  if not x:raise EOFError
  b.extend(x)
 return bytes(b)
def probe(host,port,expected):
 with socket.create_connection(('127.0.0.1',10808),timeout=2) as s:
  s.sendall(b'\5\1\2');assert exact(s,2)==b'\5\2'
  user=b'cascade-xray';password=c['password'].encode()
  s.sendall(b'\1'+bytes([len(user)])+user+bytes([len(password)])+password)
  assert exact(s,2)==b'\1\0'
  ip=ipaddress.ip_address(host)
  s.sendall(b'\5\1\0'+bytes([1 if ip.version==4 else 4])+ip.packed+struct.pack('!H',port))
  h=exact(s,4);size=4 if h[3]==1 else 16;exact(s,size+2)
  assert h[:3]==(b'\5\0\0' if expected else b'\5\1\0')
  if expected:
   s.sendall(b'guarded-classifier');assert exact(s,18)==b'guarded-classifier'
result={}
for name,host,port,allowed in [('direct','192.0.2.80',9000,True),('foreign','198.51.100.80',9000,True),
                              ('private','10.0.0.80',9000,False),('loopback4','127.0.0.2',9000,False),
                              ('loopback6','::1',9000,False),('mapped_private','::ffff:127.0.0.2',9000,False),
                              ('mapped_owned','::ffff:203.0.113.80',9001,False),('own_control','203.0.113.80',9001,False),
                              ('own_web','203.0.113.80',9000,True),('remote_control','198.51.100.80',9001,True),
                              ('rewritten_public_refused','192.0.2.80',9010,False),('public_recovery','192.0.2.80',9000,True)]:
 probe(host,port,allowed);result[name]=True
 pathlib.Path(c['result']).write_text(json.dumps(result))
'''


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, "owned-classifier-prerequisite-failed"
    return result.stdout


def dataset():
    def varint(value):
        result = bytearray()
        while True:
            result.append((value & 127) | (128 if value > 127 else 0))
            value >>= 7
            if not value:
                return bytes(result)
    def field(number, data):
        return varint((number << 3) | 2) + varint(len(data)) + data
    entries = b""
    for address, prefix in (("192.0.2.0", 24), ("10.0.0.0", 8)):
        entries += field(2, field(1, socket.inet_aton(address)) + varint(2 << 3) + varint(prefix))
    return field(1, field(1, b"RU") + entries)


def test_actual_classifier_distinct_public_paths_and_private_management_refusal(tmp_path):
    if sys.platform != "linux" or os.geteuid() != 0 or os.environ.get("TRANSPORT_NATIVE_ISOLATED") != "1":
        pytest.fail("classifier acceptance requires owned isolated Linux root authority")
    for binary in ("ip", "nft", "tc", "ss", "runuser", "systemctl", "useradd", "userdel"):
        assert shutil.which(binary), "classifier acceptance requires actual namespace and service tooling"
    from transport_egress_config import build
    token = "tcl" + secrets.token_hex(4)
    classifier, peer = token + "c", token + "p"
    created, processes, users = [], [], []
    library = Path("/usr/local/libexec") / token
    state = Path("/var/lib") / token
    driver_state = Path("/var/lib") / (token+"-driver")
    unit = Path("/etc/systemd/system") / (token+".service")
    password = secrets.token_urlsafe(48)
    try:
        for directory, mode in ((library, 0o755), (state, 0o700), (driver_state, 0o700)):
            directory.mkdir(mode=mode);directory.chmod(mode)
        ids = {}
        for key in ("n", "g", "x", "c"):
            name = token+key
            command(["useradd", "--system", "--no-create-home", "--user-group", name]);users.append(name)
            ids[key] = int(command(["id", "-u", name]).strip())
        os.chown(driver_state, ids['x'], int(command(["id", "-g", token+'x']).strip()))
        for name in ('cascade-classifier-proxy.py', 'cascade_classifier_lib.py', 'transport_destination_policy.py', 'transport_private_authority.py'):
            shutil.copyfile(ROOT/'scripts'/name, library/name);(library/name).chmod(0o644)
        paths = {name: library/name for name in ('geoip.dat', 'peer.py', 'driver.py')}
        paths['geoip.dat'].write_bytes(dataset());paths['peer.py'].write_text(PEER);paths['driver.py'].write_text(DRIVER)
        for path in paths.values():path.chmod(0o644)
        context = {'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': False, 'enable_hysteria': False,
                           'enable_warp_outbound': False, 'enable_cascade_ingress': True},
                   'secrets': {name+'_password': 'synthetic '+name+' authority '+secrets.token_hex(16)
                               for name in ('direct_gateway', 'direct_xray', 'direct_hysteria', 'warp_xray', 'warp_gateway')},
                   'normalizer_uid': ids['n'], 'gateway_uid': ids['g'], 'classifier_uid': ids['c'],
                   'frontend_uids': {'xray': ids['x']}, 'owned_addresses': ['203.0.113.80'],
                   'management_tcp_ports': [9001], 'management_udp_ports': []}
        projection = build(context)['policy']
        (state/'password').write_text(password);(state/'password').chmod(0o600)
        (state/'policy').write_text(json.dumps({'policy': projection['policy']}));(state/'policy').chmod(0o600)
        for namespace in (classifier, peer):
            command(["ip", "netns", "add", namespace]);created.append(namespace)
            command(["ip", "-n", namespace, "link", "set", "lo", "up"])
        for index, network, local, remote in (("d", "192.0.2", "cdirect", "pdirect"), ("f", "198.51.100", "cforeign", "pforeign")):
            left, right = token+index+"a", token+index+"b"
            command(["ip", "link", "add", left, "type", "veth", "peer", "name", right])
            command(["ip", "link", "set", left, "netns", classifier]);command(["ip", "link", "set", right, "netns", peer])
            for namespace, original, renamed, suffix in ((classifier, left, local, "1"), (peer, right, remote, "80")):
                command(["ip", "-n", namespace, "link", "set", original, "name", renamed])
                command(["ip", "-n", namespace, "addr", "add", network+"."+suffix+"/24", "dev", renamed])
                command(["ip", "-n", namespace, "link", "set", renamed, "up"])
        for address, interface in (("10.0.0.80/24", "pdirect"), ("203.0.113.80/24", "pforeign")):
            command(["ip", "-n", peer, "addr", "add", address, "dev", interface])
        for network, gateway, interface in (("10.0.0.0/24", "192.0.2.80", "cdirect"), ("203.0.113.0/24", "198.51.100.80", "cforeign")):
            command(["ip", "-n", classifier, "route", "add", network, "via", gateway, "dev", interface])
        for namespace in created:
            links = json.loads(command(["ip", "-n", namespace, "-j", "link", "show"]))
            assert {link['ifname'] for link in links} == ({'lo', 'cdirect', 'cforeign'} if namespace == classifier else {'lo', 'pdirect', 'pforeign'})
        rewrite = ('table ip classifier_rewrite {\n chain output {\n'
                   ' type nat hook output priority -100; policy accept;\n'
                   ' ip daddr 192.0.2.80 tcp dport 9010 dnat to 10.0.0.80:9000;\n }\n}\n')
        result = subprocess.run(['ip', 'netns', 'exec', classifier, 'nft', '-f', '-'], input=rewrite, text=True, capture_output=True)
        assert result.returncode == 0, 'owned classifier rewrite prerequisite failed'
        kernel = ("import json,pathlib,sys;sys.path.insert(0,sys.argv[1]+'/scripts');import transport_egress_kernel as k;"
                  "k.STATE=pathlib.Path(sys.argv[2]);p=json.load(sys.stdin);k.run('apply',p);k.run('verify',p)")
        result = subprocess.run(['ip', 'netns', 'exec', classifier, sys.executable, '-c', kernel, str(ROOT), str(state)],
                                input=json.dumps(projection), text=True, capture_output=True, timeout=20)
        assert result.returncode == 0, 'actual classifier kernel authority was refused'
        for namespace, mode in ((classifier, 'local'), (peer, 'peer')):
            processes.append(subprocess.Popen(['ip', 'netns', 'exec', namespace, sys.executable, str(paths['peer.py']), str(state), mode],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        deadline = time.monotonic()+5
        while not all((state/(mode+'-ready')).exists() for mode in ('local', 'peer')):
            assert time.monotonic() < deadline, 'classifier receivers unavailable'
            time.sleep(.05)
        log = state/'classifier.log'
        argv = [sys.executable, '-Es', str(library/'cascade-classifier-proxy.py'), '--dataset', str(paths['geoip.dat']),
                '--password-file', '%d/password', '--policy-file', '%d/policy', '--direct-interface', 'cdirect',
                '--foreign-interface', 'cforeign', '--listen-port', '10808', '--connect-timeout', '1']
        import shlex
        unit.write_text('[Service]\nType=simple\nUser='+token+'c\nNetworkNamespacePath=/run/netns/'+classifier+
                        '\nNoNewPrivileges=yes\nCapabilityBoundingSet=CAP_NET_RAW\nAmbientCapabilities=CAP_NET_RAW\n'+
                        'LoadCredential=password:'+str(state/'password')+'\nLoadCredential=policy:'+str(state/'policy')+
                        '\nStandardOutput=append:'+str(log)+'\nStandardError=append:'+str(log)+'\nExecStart='+shlex.join(argv)+'\n')
        unit.chmod(0o644);command(['systemctl', 'daemon-reload']);command(['systemctl', 'start', token])
        deadline = time.monotonic()+10
        while not log.exists() or '\"state\": \"ready\"' not in log.read_text():
            assert time.monotonic() < deadline, 'actual unprivileged classifier unavailable'
            time.sleep(.05)
        actual_uid = command(['systemctl', 'show', token, '-p', 'User', '--value']).strip()
        assert actual_uid == token+'c' and ids['c'] != 0
        result_path = driver_state/'result.json'
        result = subprocess.run(['ip', 'netns', 'exec', classifier, 'runuser', '-u', token+'x', '--', sys.executable, str(paths['driver.py'])],
                                input=json.dumps({'password': password, 'result': str(result_path)}), text=True,
                                capture_output=True, timeout=25)
        evidence = json.loads(result_path.read_text()) if result_path.exists() else {'driver_started': False}
        assert result.returncode == 0, evidence
        assert evidence['rewritten_public_refused']
        counters = json.loads((state/'peer.json').read_text())
        assert counters['direct'] == 2 and counters['foreign'] == 1
        assert counters['own_web'] == counters['remote_control'] == 1
        assert counters['private'] == counters['own_control'] == 0
        assert all(value == 0 for value in json.loads((state/'local.json').read_text()).values())
        assert password not in log.read_text() and '203.0.113.80' not in log.read_text()
    finally:
        if unit.exists():
            subprocess.run(['systemctl', 'stop', token], capture_output=True)
            unit.unlink();subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
        for process in reversed(processes):
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
        for namespace in reversed(created):command(['ip', 'netns', 'delete', namespace])
        for user in reversed(users):subprocess.run(['userdel', user], capture_output=True)
        for directory in (library, state, driver_state):shutil.rmtree(directory, ignore_errors=True)
