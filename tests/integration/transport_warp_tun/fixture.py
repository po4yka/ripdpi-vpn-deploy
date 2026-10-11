"""Disconnected IP-frame TUN pump; no vendor account or replacement proxy."""
from __future__ import annotations
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT/'scripts'))
import transport_egress_kernel as kernel
from transport_egress_config import build


def run(*args, data=None):
    result = subprocess.run(list(args), input=data, text=True, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError('owned-warp-tun-command-failed')
    return result.stdout


def tun(namespace, name):
    original = os.open('/proc/self/ns/net', os.O_RDONLY)
    selected = os.open('/run/netns/'+namespace, os.O_RDONLY)
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        if libc.setns(selected, 0x40000000):
            raise OSError(ctypes.get_errno(), 'owned-setns-failed')
        fd = os.open('/dev/net/tun', os.O_RDWR | os.O_NONBLOCK)
        fcntl.ioctl(fd, 0x400454ca, struct.pack('16sH', name.encode(), 0x1001))
        return fd
    finally:
        if libc.setns(original, 0x40000000):
            raise OSError(ctypes.get_errno(), 'owned-setns-restore-failed')
        os.close(original); os.close(selected)


PEER = r'''
import socket,threading,time
for udp in (False,True):
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
 s.bind(('192.0.2.80',9000))
 if not udp:s.listen()
 def serve(s=s,udp=udp):
  while True:
   if udp:
    data,peer=s.recvfrom(65535);s.sendto(data,peer)
   else:
    c,_=s.accept()
    with c:
     data=c.recv(65535);c.sendall(data)
 threading.Thread(target=serve,daemon=True).start()
while True:time.sleep(1)
'''

CLIENT = r'''
import json,os,socket,struct,sys
p=json.load(sys.stdin);os.setgroups([]);os.setgid(p['uid']);os.setuid(p['uid'])
def exact(c,n):
 out=b''
 while len(out)<n:
  value=c.recv(n-len(out))
  if not value:raise OSError('closed')
  out+=value
 return out
try:
 with socket.create_connection(('10.250.254.2',12091),timeout=2) as c:
  c.sendall(b'\x05\x01\x02');assert exact(c,2)==b'\x05\x02'
  u=b'gateway-warp';pw=p['password'].encode()
  c.sendall(bytes([1,len(u)])+u+bytes([len(pw)])+pw);assert exact(c,2)==b'\x01\x00'
  udp=p['network']=='udp';command=3 if udp else 1
  c.sendall(bytes([5,command,0,1])+socket.inet_aton('0.0.0.0' if udp else '192.0.2.80')+struct.pack('!H',0 if udp else 9000))
  h=exact(c,4);assert h[:3]==b'\x05\x00\x00'
  exact(c,4 if h[3]==1 else 16);exact(c,2)
  payload=b'actual-warp-tun-'+p['network'].encode()
  if udp:
   with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as d:
    d.settimeout(2);d.bind(('10.250.254.1',p['source_port']))
    frame=b'\0\0\0\1'+socket.inet_aton('192.0.2.80')+struct.pack('!H',9000)+payload
    d.sendto(frame,('10.250.254.2',12091));reply,_=d.recvfrom(65535);assert reply[10:]==payload
  else:
   c.sendall(payload);assert exact(c,len(payload))==payload
except (OSError,AssertionError):sys.exit(1)
'''


def main():
    if os.geteuid() != 0 or not Path('/dev/net/tun').exists():
        raise RuntimeError('owned-native-tun-required')
    work = Path(tempfile.mkdtemp(prefix='rdb-two-tun-')); work.chmod(0o755)
    gateway_ns, peer_ns = 'ripdpi-warp', 'rdb-tun-'+uuid.uuid4().hex[:8]
    names = {key: 'rdbt'+uuid.uuid4().hex[:8]+key for key in ('n','g','w','x')}
    processes, users, namespaces, descriptors = [], [], [], []
    pump_stop = threading.Event(); capture_stop = threading.Event()
    counts = {'tun_frames':0, 'recipient_tun_frames':0, 'underlay_recipient_frames':0}
    gateway = None
    try:
        for key,name in names.items():
            run('useradd','--system','--no-create-home','--user-group',name);users.append(name)
        uids = {key:int(run('id','-u',name)) for key,name in names.items()}
        gids = {key:int(run('id','-g',name)) for key,name in names.items()}
        for name in (gateway_ns,peer_ns):
            run('ip','netns','add',name);namespaces.append(name)
            run('ip','-n',name,'link','set','lo','up')
        run('ip','link','add','rpd-warp-host','type','veth','peer','name','rpd-warp-ns')
        run('ip','link','set','rpd-warp-ns','netns',gateway_ns)
        run('ip','address','add','10.250.254.1/30','dev','rpd-warp-host')
        run('ip','link','set','rpd-warp-host','up')
        run('ip','-n',gateway_ns,'address','add','10.250.254.2/30','dev','rpd-warp-ns')
        run('ip','-n',gateway_ns,'link','set','rpd-warp-ns','up')
        run('ip','-n',gateway_ns,'route','add','default','via','10.250.254.1')
        gateway_fd, peer_fd = tun(gateway_ns,'CloudflareWARP'), tun(peer_ns,'rdb-peer-tun')
        descriptors.extend([gateway_fd,peer_fd])
        for ns,name,address in [(gateway_ns,'CloudflareWARP','192.0.2.2/24'),(peer_ns,'rdb-peer-tun','192.0.2.80/24')]:
            run('ip','-n',ns,'address','add',address,'dev',name);run('ip','-n',ns,'link','set',name,'up')
        secret = {name+'_password': 'owned-tun-'+name+'-'+uuid.uuid4().hex for name in ('direct_xray','direct_gateway','warp_xray','warp_gateway')}
        context = {'vpn':{'enable_xray_reality':True,'enable_nginx_xhttp':False,'enable_hysteria':False,'enable_warp_outbound':True},
                   'secrets':secret,'normalizer_uid':uids['n'],'gateway_uid':uids['g'],'warp_gateway_uid':uids['w'],
                   'frontend_uids':{'xray':uids['x']},'owned_addresses':['192.0.2.2'],'management_tcp_ports':[22],'management_udp_ports':[]}
        policy = build(context)['policy']
        def admit():
            info = json.loads(run('ip','-n',gateway_ns,'-j','-d','link','show','CloudflareWARP'))[0]
            policy['warp']['tunnel_ifindex'] = info['ifindex']
            kernel.run('apply',policy);kernel.run('apply',policy,True)
            kernel.run('verify',policy);kernel.run('verify',policy,True)
        kernel.STATE = work/'policy-state';kernel.STATE.mkdir(mode=0o700)
        admit()
        binary = Path(shutil.which('xray') or '')
        if not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != '8255dd939c34cf966cc91517b6324dd3c8d0bcf49ffac8beca049a38c46845ed':
            raise RuntimeError('exact-native-xray-required')
        target = work/'xray';shutil.copyfile(binary,target);target.chmod(0o555)
        cfg = work/'gateway.json'
        cfg.write_text(json.dumps({'log':{'loglevel':'none'},'inbounds':[{'listen':'10.250.254.2','port':12091,'protocol':'socks',
            'settings':{'auth':'password','udp':True,'ip':'10.250.254.2','accounts':[{'user':'gateway-warp','pass':secret['warp_gateway_password']}]}}],
            'outbounds':[{'protocol':'freedom','settings':{'domainStrategy':'ForceIP'}}]}))
        cfg.chmod(0o640);os.chown(cfg,0,gids['w'])
        def start_gateway():
            def demote():
                os.setgroups([]);os.setgid(gids['w']);os.setuid(uids['w'])
            # Enter namespace while privileged, then drop identity before the genuine binary.
            script = 'import os,sys;os.setgroups([]);os.setgid(int(sys.argv[1]));os.setuid(int(sys.argv[2]));os.execv(sys.argv[3],sys.argv[3:])'
            result = subprocess.Popen(['ip','netns','exec',gateway_ns,sys.executable,'-c',script,str(gids['w']),str(uids['w']),str(target),'run','-config',str(cfg)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            processes.append(result);time.sleep(.3)
            if result.poll() is not None:raise RuntimeError('native-gateway-start-failed')
            return result
        peer = subprocess.Popen(['ip','netns','exec',peer_ns,sys.executable,'-c',PEER],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(peer)
        time.sleep(.2);gateway = start_gateway()
        def pump(a,b):
            while not pump_stop.is_set():
                try:ready=select.select([a,b],[],[],.05)[0]
                except (OSError,ValueError):return
                for source in ready:
                    try:
                        frame=os.read(source,65535)
                        if not frame:continue
                        os.write(b if source==a else a,frame);counts['tun_frames']+=1
                        if len(frame)>=20 and frame[0]>>4==4 and frame[16:20]==socket.inet_aton('192.0.2.80'):
                            counts['recipient_tun_frames']+=1
                    except (OSError,BlockingIOError):
                        if pump_stop.is_set():return
                        pump_stop.wait(.005)
        thread=threading.Thread(target=pump,args=(gateway_fd,peer_fd),daemon=True);thread.start()
        capture=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));capture.bind(('rpd-warp-host',0));capture.settimeout(.1)
        def monitor():
            while not capture_stop.is_set():
                try:frame=capture.recv(65535)
                except socket.timeout:continue
                if len(frame)>34 and frame[12:14]==b'\x08\0' and frame[30:34]==socket.inet_aton('192.0.2.80'):
                    counts['underlay_recipient_frames']+=1
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        def client(network,port):
            data={'uid':uids['n'],'password':secret['warp_gateway_password'],'network':network,'source_port':port}
            result=subprocess.run([sys.executable,'-c',CLIENT],input=json.dumps(data),text=True,capture_output=True,timeout=8)
            return result.returncode==0
        assert client('tcp',18000) and client('udp',18001),'native-tun-public-completion-failed'
        before=counts['tun_frames'];assert before>0
        old_index=policy['warp']['tunnel_ifindex']
        run('ip','-n',gateway_ns,'link','delete','CloudflareWARP')
        assert not client('tcp',18002) and not client('udp',18003),'plaintext-underlay-admitted'
        assert counts['underlay_recipient_frames']==0,'recipient-packet-reached-underlay'
        pump_stop.set();thread.join(1);os.close(gateway_fd);descriptors.remove(gateway_fd)
        gateway_fd=tun(gateway_ns,'CloudflareWARP');descriptors.append(gateway_fd)
        run('ip','-n',gateway_ns,'address','add','192.0.2.2/24','dev','CloudflareWARP')
        run('ip','-n',gateway_ns,'link','set','CloudflareWARP','up')
        new_index=json.loads(run('ip','-n',gateway_ns,'-j','link','show','CloudflareWARP'))[0]['ifindex']
        assert new_index!=old_index
        pump_stop.clear();thread=threading.Thread(target=pump,args=(gateway_fd,peer_fd),daemon=True);thread.start()
        before_stale=counts['recipient_tun_frames']
        assert not client('tcp',18004) and not client('udp',18007),'stale-tun-authority-admitted'
        assert counts['recipient_tun_frames']==before_stale,'stale-policy-sent-recipient-frame'
        gateway.terminate();gateway.wait(timeout=3)
        admit();gateway=start_gateway()
        assert client('tcp',18005) and client('udp',18006),'native-tun-recovery-failed'
        assert counts['tun_frames']>before and counts['underlay_recipient_frames']==0
        capture_stop.set();watcher.join(1);capture.close()
        print(json.dumps({'actual_tcp_udp':True,'two_native_tuns':True,'underlay_recipient_frames':0,
                          'tun_loss_denied':True,'stale_ifindex_denied':True,'fresh_policy_and_generation_recovered':True,
                          'registered_vendor_acceptance':False}))
    finally:
        pump_stop.set();capture_stop.set()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for fd in descriptors:
            os.close(fd)
        for namespace in reversed(namespaces):
            subprocess.run(['ip','netns','delete',namespace],capture_output=True)
        for name in users:
            subprocess.run(['userdel',name],capture_output=True)
        shutil.rmtree(work)


if __name__=='__main__':
    main()
