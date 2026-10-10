"""Actual common helper/NSS/Xray behavior in an owned, disconnected Linux namespace."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

import pytest
import yaml

from test_transport_destination_boundary import config

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime

PEER = r'''
import json,os,pathlib,socket,struct,sys,threading,time
root=pathlib.Path(sys.argv[1]);stop=threading.Event();lock=threading.Lock()
counts={'public_tcp':0,'public_udp':0,'private_tcp':0,'private_udp':0,'queries':0,'late':0}
def failure(kind,value,trace):
 while trace.tb_next:trace=trace.tb_next
 with lock:
  (root/'peer-failure.json').write_text(json.dumps({'kind':kind.__name__,'line':trace.tb_lineno,
                                                'errno':value.errno if isinstance(value,OSError) else None}))
threading.excepthook=lambda value:failure(value.exc_type,value.exc_value,value.exc_traceback)
sys.excepthook=failure
def record(key):
 with lock:
  counts[key]+=1
  temporary=root/'counts.new';temporary.write_text(json.dumps(counts));temporary.replace(root/'counts.json')
def echo(ip, family, private, udp):
 s=socket.socket(family,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
 s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((ip,9000));s.settimeout(.2)
 if not udp:s.listen()
 def loop():
  while not stop.is_set():
   try:
    if udp:
     data,peer=s.recvfrom(4096);received=time.monotonic()
     record('private_udp' if private else 'public_udp');s.sendto(data,peer)
     if data.startswith(b'active-') and data[7:].isdigit():
      sent=time.monotonic()
      with lock:
       temporary=root/'active-peer.new';temporary.write_text(json.dumps({'sequence':int(data[7:]),'received':received,'sent':sent}));temporary.replace(root/'active-peer.json')
     if data==b'late-start':
      def late(peer=peer):
       until=time.monotonic()+20
       while time.monotonic()<until:
        time.sleep(.5);s.sendto(b'late-retired',peer);record('late')
      threading.Thread(target=late,daemon=True).start()
    else:
     c,_=s.accept();record('private_tcp' if private else 'public_tcp')
     def connection(c=c):
      with c:
       while True:
        data=c.recv(4096)
        if not data:return
        c.sendall(data)
     threading.Thread(target=connection,daemon=True).start()
   except socket.timeout:pass
 threading.Thread(target=loop,daemon=True).start()
for ip,family,private in [('192.0.2.80',socket.AF_INET,False),('192.0.2.81',socket.AF_INET,False),
                          ('2001:db8::80',socket.AF_INET6,False),('127.0.0.2',socket.AF_INET,True),
                          ('::1',socket.AF_INET6,True)]:
 for udp in (False,True):echo(ip,family,private,udp)
d=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);d.bind(('192.0.2.53',53));d.settimeout(.2)
while True:
 try:request,peer=d.recvfrom(4096)
 except socket.timeout:continue
 try:
  offset=12;labels=[]
  while request[offset]:
   length=request[offset];labels.append(request[offset+1:offset+1+length].decode('ascii'));offset+=length+1
  offset+=1;qtype,qclass=struct.unpack('!HH',request[offset:offset+4]);end=offset+4;name='.'.join(labels)
  record('queries');answers=[]
  if name=='drop.test':continue
  changed=(root/'private-answer').exists()
  if qtype==1:
   if name in ('public.test','mixed4.test'):answers=['127.0.0.2','192.0.2.80'] if name.startswith('mixed') else ['127.0.0.2' if changed else '192.0.2.80']
   if name in ('fresh4.test','recovered.test'):answers=['192.0.2.81']
   if name=='private4.test':answers=['127.0.0.2']
  elif qtype==28:
   if name in ('mixed6.test','fresh6.test'):answers=['::1','2001:db8::80'] if name.startswith('mixed') else ['2001:db8::80']
   if name=='private6.test':answers=['::1']
   if name=='mapped.test':answers=['::ffff:127.0.0.2','::ffff:192.0.2.80']
  response=request[:2]+struct.pack('!HHHHH',0x8180,1,len(answers),0,0)+request[12:end]
  for answer in answers:
   packed=socket.inet_pton(socket.AF_INET if qtype==1 else socket.AF_INET6,answer)
   response+=b'\xc0\x0c'+struct.pack('!HHIH',qtype,1,0,len(packed))+packed
  d.sendto(response,peer)
 except (IndexError,ValueError,struct.error):pass
'''

DRIVER = r'''
import json,pathlib,socket,struct,sys,time
sys.path.insert(0,sys.argv[1])
import transport_socks as w
from transport_egress_normalizer import _frame,_expected
data=json.load(sys.stdin);listener=data['listener'];root=pathlib.Path(data['state'])
def auth():
 c=socket.create_connection(('127.0.0.1',listener['port']),timeout=3)
 c.sendall(b'\x05\x01\x02');_frame(c,lambda b:_expected(b,b'\x05\x02'))
 c.sendall(w.upstream_auth(listener['username'],listener['password']));_frame(c,lambda b:_expected(b,b'\x01\x00'));return c
def tcp(name):
 c=auth();n=name.encode();c.sendall(b'\x05\x01\0\3'+bytes([len(n)])+n+struct.pack('!H',9000));_frame(c,w.upstream_reply);c.settimeout(3);return c
def payload(connection,expected):
 # Handshake budgets are cumulative within a handshake, never across application probes.
 deadline=time.monotonic()+3;received=bytearray()
 try:
  while len(received)<len(expected):
   remaining=deadline-time.monotonic()
   if remaining<=0:raise TimeoutError
   connection.settimeout(remaining);value=connection.recv(len(expected)-len(received))
   if not value:raise EOFError
   received.extend(value)
  return bytes(received)==expected
 finally:connection.settimeout(3)
def associate():
 c=auth();c.sendall(w.upstream_request(3,'0.0.0.0',0));_,ip,p=_frame(c,w.upstream_reply)
 u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);u.settimeout(.7);return c,u,(ip,p)
def packet(u,relay,name,marker):
 global last_udp_sent,last_udp_marker
 last_udp_marker=marker;last_udp_sent=time.monotonic()
 n=name.encode();u.sendto(bytes(3)+bytes([3,len(n)])+n+struct.pack('!H',9000)+marker,relay)
 ip,p,payload=w.datagram(u.recv(4096),4096);assert payload==marker;return ip
def controls():
 result={}
 for line in pathlib.Path('/proc/self/net/tcp').read_text().splitlines()[1:]:
  fields=line.split()
  if int(fields[7])==data['normalizer_uid'] and int(fields[2].split(':')[1],16)==12090:
   result[int(fields[1].split(':')[1],16)]=fields[3]
 return result
def tuples():
 result={}
 for line in pathlib.Path('/proc/self/net/udp').read_text().splitlines()[1:]:
  fields=line.split();port=int(fields[1].split(':')[1],16)
  if int(fields[7])==data['normalizer_uid'] and (13000<=port<=13001 or 16000<=port<=16001):
   result[port]=int(fields[9])
 return result
results={'both_families':False,'binding':False,'fresh_private_refused':False,'capacity':False,
         'quiet_reuse':False,'quiet_guard':False,'late_reply_dropped':False,'active_over_300':False,'resolver_timeout':False}
diagnostic_started=time.monotonic();stage='initial';stage_times={}
def mark(value):
 global stage
 stage=value;stage_times[value]=round(time.monotonic()-diagnostic_started,3)
def evidence():
 (root/'driver-result.json').write_text(json.dumps(results))
def failure(kind, value, trace):
 while trace.tb_next:trace=trace.tb_next
 results['driver_failure']={'kind':kind.__name__,'line':trace.tb_lineno,'stage':stage,
                          'elapsed_seconds':round(time.monotonic()-diagnostic_started,3),'stage_times':stage_times,
                          'retired_front_port':old_relay[1] if 'old_relay' in globals() else None,
                          'retired_tuples':retired_tuples if 'retired_tuples' in globals() else {},
                          'current_tuples':tuples(),'original_active_tuples':original_tuples if 'original_tuples' in globals() else {},
                          'active_backend_control':{port:controls().get(port,'absent') for port in active_backend_control} if 'active_backend_control' in globals() else {},
                          'last_udp_sent':last_udp_sent if 'last_udp_sent' in globals() else None,
                          'failed_udp_sequence':active_sequence if stage=='active-udp' and 'active_sequence' in globals() else None}
 if 'control' in globals():
  readable=bool(__import__('select').select([control],[],[],0)[0])
  results['driver_failure']['active_front_control_readable']=readable
  results['driver_failure']['active_front_control_eof']=readable and control.recv(1,socket.MSG_PEEK)==b''
 if 'u' in globals():
  timeout=u.gettimeout();u.settimeout(0)
  try:
   frame=u.recv(4096,socket.MSG_PEEK);_,_,queued=w.datagram(frame,4096)
   results['driver_failure']['queued_reply_matches_failed_packet']=queued==last_udp_marker
  except (OSError,ValueError):results['driver_failure']['queued_reply_matches_failed_packet']=False
  finally:u.settimeout(timeout)
 evidence()
sys.excepthook=failure
evidence()
control,u,relay=associate();active_backend_control=list(controls());stream=tcp('public.test')
for name,expected in [('mixed4.test','192.0.2.80'),('fresh4.test','192.0.2.81'),
                      ('mixed6.test','2001:db8::80'),('fresh6.test','2001:db8::80'),('mapped.test','192.0.2.80')]:
 assert packet(u,relay,name,('shape-'+name).encode())==expected
for name in ('private4.test','private6.test'):
 try:packet(u,relay,name,b'private-forbidden');raise AssertionError('private-destination-replied')
 except socket.timeout:pass
assert packet(u,relay,'public.test',b'binding-start')=='192.0.2.80';results['both_families']=True;evidence()
(root/'private-answer').touch()
assert packet(u,relay,'public.test',b'same-public-binding')=='192.0.2.80';results['binding']=True;evidence()
new_tcp=auth();n=b'public.test';new_tcp.sendall(b'\x05\x01\0\3'+bytes([len(n)])+n+struct.pack('!H',9000))
assert _frame(new_tcp,lambda b:_expected(b,w.FAILURE))==len(w.FAILURE);new_tcp.close();results['fresh_private_refused']=True;evidence()
started=time.monotonic();u.settimeout(1.5)
try:packet(u,relay,'drop.test',b'dropped-dns');raise AssertionError('unexpected-dns-reply')
except socket.timeout:pass
assert time.monotonic()-started<2;u.settimeout(.7)
assert packet(u,relay,'recovered.test',b'post-timeout-recovery')=='192.0.2.81'
results['resolver_timeout']=True;evidence()
(root/'private-answer').unlink()
original_tuples=tuples()
retired,old,old_relay=associate();retired_tuples={port:inode for port,inode in tuples().items() if original_tuples.get(port)!=inode}
assert len(retired_tuples)==2 and old_relay[1] in retired_tuples
assert packet(old,old_relay,'public.test',b'late-start')=='192.0.2.80'
retired.close();began=time.monotonic();checked=False;reused=False;quiet_checked=False;late_frontend=False;active_sequence=0
while time.monotonic()-began<305:
 mark('active-tcp');stream.sendall(b'active');assert payload(stream,b'active')
 mark('active-udp');assert packet(u,relay,'public.test',b'active-'+str(active_sequence).encode())=='192.0.2.80';active_sequence+=1
 elapsed=time.monotonic()-began
 if elapsed>5 and not checked:
  c=auth();c.sendall(w.upstream_request(3,'0.0.0.0',0));assert _frame(c,lambda b:_expected(b,w.FAILURE))==len(w.FAILURE);c.close();results['capacity']=True;evidence()
  old.settimeout(.2)
  try:old.recv(4096);raise AssertionError('retired-recipient-replied')
  except socket.timeout:results['late_reply_dropped']=True;evidence()
  checked=True
 if elapsed>20 and not late_frontend:
  mark('late-frontend-sent');n=b'public.test';old.sendto(bytes(3)+bytes([3,len(n)])+n+struct.pack('!H',9000)+b'late-frontend',old_relay)
  late_frontend=True
 if elapsed>245 and not quiet_checked:
  mark('quiet-guard');assert all(tuples().get(port)==inode for port,inode in retired_tuples.items());c=auth();c.sendall(w.upstream_request(3,'0.0.0.0',0))
  assert _frame(c,lambda b:_expected(b,w.FAILURE))==len(w.FAILURE);c.close()
  results['quiet_guard']=True;evidence();quiet_checked=True
 if elapsed>280 and not reused:
  mark('quiet-reuse');c,new,new_relay=associate();assert new_relay==old_relay
  assert all(port in tuples() and tuples()[port]!=inode for port,inode in retired_tuples.items())
  assert packet(new,new_relay,'public.test',b'new-recipient')=='192.0.2.80'
  results['quiet_reuse']=True;evidence();c.close();new.close();reused=True
 time.sleep(.5)
results['active_over_300']=True;evidence()
control.close();u.close();old.close();stream.close()
(root/'driver-result.json').write_text(json.dumps(results))
'''


def command(argv, *, environment=None, timeout=20):
    result = subprocess.run(argv, capture_output=True, text=True, env=environment, timeout=timeout)
    assert result.returncode == 0, "owned-native-command-failed"
    return result.stdout


def test_actual_sealed_normalizer_named_udp_long_stream_and_quarantine(tmp_path):
    if sys.platform != "linux" or os.geteuid() != 0 or os.environ.get("TRANSPORT_NATIVE_ISOLATED") != "1":
        pytest.fail("owned native normalizer requires explicit isolated Linux root authority")
    for binary in ("ip", "nft", "tc", "ss", "systemctl", "useradd", "userdel", "runuser", "xray"):
        if not shutil.which(binary):
            pytest.fail("owned native normalizer prerequisite is unavailable")
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    assert pins["xray"]["version"].lstrip("v") in command([shutil.which("xray"), "version"])
    import importlib.util
    specification = importlib.util.spec_from_file_location("owned_common_transport_fixture", ROOT / "tests/integration/transport_destination_boundary/fixture.py")
    fixture = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(fixture)
    stack = fixture.NativeStack()
    driver_process = None
    try:
        stack.start(common=True, peer_source=PEER)
        driver = stack.library / "driver.py"
        driver.write_text(DRIVER);driver.chmod(0o644)
        driver_process = subprocess.Popen(["ip", "netns", "exec", stack.namespace, "runuser", "-u", stack.users["x"], "--",
                                           sys.executable, str(driver), str(stack.library)],
                                          stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stack.processes.append(driver_process)
        pressure_start = {name: Path("/proc/pressure", name).read_text().strip() for name in ("cpu", "io", "memory")}
        driver_process.stdin.write(json.dumps({"listener": stack.config["listeners"][0], "state": str(stack.driver_state), "normalizer_uid": stack.uids["n"]}).encode())
        driver_process.stdin.close()
        status = driver_process.wait(timeout=330)
        result_path = stack.driver_state / "driver-result.json"
        result = json.loads(result_path.read_text()) if result_path.exists() else {"driver_started": False}
        if status:
            peer_failure = stack.driver_state / "peer-failure.json"
            counts_file = stack.driver_state / "counts.json"
            result["native_failure_context"] = {
                "peer_exception": json.loads(peer_failure.read_text()) if peer_failure.exists() else None,
                "packet_counts": json.loads(counts_file.read_text()) if counts_file.exists() else {},
                "peer_process_status": stack.processes[0].poll(),
                "normalizer_active": command(["systemctl", "show", stack.token + "-normalizer", "--property=ActiveState", "--value"]).strip() == "active",
                "last_peer_active_packet": json.loads((stack.driver_state / "active-peer.json").read_text()) if (stack.driver_state / "active-peer.json").exists() else None,
                "guest_pressure_start": pressure_start,
                "guest_pressure_failure": {name: Path("/proc/pressure", name).read_text().strip() for name in ("cpu", "io", "memory")},
                "guest_load_average": os.getloadavg(),
            }
        if status:
            (tmp_path / "native-failure.json").write_text(json.dumps(result, indent=2, sort_keys=True))
        assert status == 0, json.dumps(result, sort_keys=True)
        assert result and all(result.values())
        counts = json.loads((stack.driver_state / "counts.json").read_text())
        assert counts["private_tcp"] == counts["private_udp"] == 0
        assert counts["public_tcp"] > 0 and counts["public_udp"] > 300 and counts["late"] > 0
        logs = command(["journalctl", "--unit", stack.token + "-normalizer", "--no-pager", "-o", "cat"])
        assert stack.config["backends"]["direct"]["password"] not in logs
        assert stack.config["listeners"][0]["password"] not in logs
        assert "192.0.2.80" not in logs and "public.test" not in logs
    finally:
        stack.close()
