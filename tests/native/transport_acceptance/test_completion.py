"""Real positive byte completion followed by independent credential/TLS refusals."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest
import yaml

from native_common import ROOT, fixture
from template_render import render_template

pytestmark = pytest.mark.native_runtime
HTTPS = '''from http.server import BaseHTTPRequestHandler,HTTPServer
import ssl,sys
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length']))
  self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args): pass
server=HTTPServer(('192.0.2.80',18443),Handler)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(sys.argv[1],sys.argv[2])
server.socket=context.wrap_socket(server.socket,server_side=True);server.serve_forever()
'''


def rewrite_client(stack, mutate):
    unit = stack.units[-1]
    path = sorted(stack.library.glob('client-*.*'), key=lambda p:p.stat().st_mtime_ns)[-1]
    value = json.loads(path.read_text()) if path.suffix == '.json' else yaml.safe_load(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value) if path.suffix == '.json' else yaml.safe_dump(value))
    fixture.command(['systemctl', 'restart', unit])
    time.sleep(.5)


def salamander(stack):
    stack.values['hysteria'].update(salamander_enabled=True, salamander_password='owned-salamander-authority')
    path = stack.library / 'hysteria-server.yaml'
    path.write_text(render_template(ROOT / 'ansible/roles/hysteria/templates/config.yaml.j2', stack.values))
    fixture.command(['systemctl', 'restart', stack.token + '-hysteria'])


def client(stack, profile, invalid=False, obfs=False):
    port = stack.start_client(profile, invalid)
    if obfs:
        rewrite_client(stack, lambda value:value.update(obfs={'type':'salamander','salamander':{'password':'owned-salamander-authority'}}))
    return port


@pytest.mark.parametrize('profile,obfs', [('p0', False), ('p1', False), ('hysteria', False), ('hysteria', True)])
def test_https_upload_download_tcp_udp_dns_and_independent_rejection(profile, obfs):
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend(profile)
        if obfs:
            salamander(stack)
        worker = subprocess.Popen(['ip','netns','exec',stack.namespace,sys.executable,'-c',HTTPS,str(stack.cert),str(stack.key)],
                                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        stack.processes.append(worker)
        port = client(stack, profile, obfs=obfs)
        time.sleep(.5)
        stack.run_driver(port)
        payload = stack.file('upload', 'native-bidirectional-payload\n' * 8192)
        response = fixture.command(['ip','netns','exec',stack.namespace,'curl','--silent','--show-error',
            '--noproxy','','--max-time','30','--proxy',f'socks5h://127.0.0.1:{port}',
            '--connect-to','owned.example:18443:192.0.2.80:18443','--cacert',str(stack.cert),
            '--data-binary','@'+str(payload),'https://owned.example:18443/'], timeout=35)
        assert response.encode() == payload.read_bytes(), 'authenticated-HTTPS-byte-completion-refused'
        # Meaningful bidirectional TCP/UDP, beyond handshakes or activity counters.
        source = (ROOT / 'tests/integration/transport_destination_boundary/driver.py').read_text()
        source = source.replace('import ipaddress', 'import ipaddress\nimport os')
        source = source.replace('b"public-probe"', 'os.urandom(65536)').replace('b"udp-probe"', 'os.urandom(1200)').replace('("packet-" + str(index)).encode()', 'os.urandom(1200)')
        result = stack.driver_state / 'bulk-result.json'
        observed = subprocess.run(['ip','netns','exec',stack.namespace,sys.executable,'-c',source],
            input=json.dumps({'port':port,'result':str(result)}),capture_output=True,text=True,timeout=90)
        assert observed.returncode == 0 and all(json.loads(result.read_text()).values())
        rejected = client(stack, profile, invalid=True, obfs=obfs)
        time.sleep(.5)
        stack.run_driver(rejected, True)
        wrong_tls = client(stack, profile, obfs=obfs)
        def mismatch(value):
            if profile == 'hysteria':
                value['tls']['sni'] = 'wrong.example'
            else:
                stream = value['outbounds'][0]['streamSettings']
                stream['realitySettings' if profile == 'p0' else 'tlsSettings']['serverName'] = 'wrong.example'
        rewrite_client(stack, mismatch)
        stack.run_driver(wrong_tls, True)
        stack.run_driver(port)
    finally:
        stack.close()
