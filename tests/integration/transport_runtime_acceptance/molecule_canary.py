"""Owned HTTPS canary and TLS peer for disposable native Molecule scenarios."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
import json
from pathlib import Path
import subprocess
import ssl
import sys

NAMESPACE = 'molecule-transport-canary'
HOST_LINK, PEER_LINK = 'mtc-host', 'mtc-peer'


def run(*argv):
    return subprocess.run(argv, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout


def prepare():
    if Path('/run/netns', NAMESPACE).exists():
        addresses = json.loads(run('ip', '-j', '-n', NAMESPACE, 'addr', 'show', 'dev', 'lo'))
        selected = {item['local'] for entry in addresses for item in entry['addr_info']}
        if not {'192.0.2.80', '192.0.2.90'} <= selected:
            raise RuntimeError('canary-namespace-unconfirmed')
        return
    run('ip', 'netns', 'add', NAMESPACE)
    run('ip', 'link', 'add', HOST_LINK, 'type', 'veth', 'peer', 'name', PEER_LINK)
    run('ip', 'link', 'set', PEER_LINK, 'netns', NAMESPACE)
    run('ip', 'addr', 'add', '10.247.0.1/30', 'dev', HOST_LINK)
    run('ip', 'link', 'set', HOST_LINK, 'up')
    run('ip', '-n', NAMESPACE, 'addr', 'add', '10.247.0.2/30', 'dev', PEER_LINK)
    run('ip', '-n', NAMESPACE, 'link', 'set', PEER_LINK, 'up')
    run('ip', '-n', NAMESPACE, 'link', 'set', 'lo', 'up')
    for address in ('192.0.2.80/32', '192.0.2.90/32'):
        run('ip', '-n', NAMESPACE, 'addr', 'add', address, 'dev', 'lo')
    run('ip', 'route', 'add', '192.0.2.0/24', 'via', '10.247.0.2', 'dev', HOST_LINK)
    run('ip', '-n', NAMESPACE, 'route', 'add', 'default', 'via', '10.247.0.1')


class Canary(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args):
        pass


class CanaryServer(HTTPServer):
    def server_bind(self):
        # The owned numeric endpoint must not wait on disconnected reverse DNS.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


def serve(directory):
    with subprocess.Popen(['openssl', 's_server', '-accept', '192.0.2.90:8444',
            '-tls1_3', '-alpn', 'h2', '-cert', str(directory / 'cert.pem'),
            '-key', str(directory / 'key.pem'), '-quiet'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as peer:
        try:
            server = CanaryServer(('192.0.2.80', 18080), Canary)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(directory / 'canary.pem', directory / 'canary.key')
            server.socket = context.wrap_socket(server.socket, server_side=True)
            server.serve_forever()
        finally:
            peer.terminate()
            peer.wait(timeout=5)


if __name__ == '__main__':
    if sys.argv[1] == '--prepare':
        prepare()
    else:
        serve(Path(sys.argv[1]))
