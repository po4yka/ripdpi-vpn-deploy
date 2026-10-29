"""Bounded real frontend traffic; credentials stay in private files and pipes."""
from __future__ import annotations

import base64
import ctypes
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit



class ProbeRefused(RuntimeError):
    pass


def parent_death(parent):
    """Linux foreground children cannot outlive the invoking publisher."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        os._exit(126)
    if os.getppid() != parent:
        os.kill(os.getpid(), signal.SIGKILL)


def foreground_options():
    parent = os.getpid()
    return {'preexec_fn': lambda: parent_death(parent)} if sys.platform == 'linux' else {}


def run(argv, timeout, *, data=None, env=None):
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(argv, stdin=subprocess.PIPE if data else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=env or {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'},
                               start_new_session=True, **foreground_options())
    output = bytearray()
    pending = memoryview(data or b'')
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            if data:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProbeRefused('native-command-timeout')
                for key, _events in selector.select(remaining):
                    if key.fileobj is process.stdout:
                        chunk = os.read(process.stdout.fileno(), min(65536, 1048577 - len(output)))
                        if not chunk:
                            selector.unregister(process.stdout)
                            continue
                        output.extend(chunk)
                        if len(output) > 1048576:
                            raise ProbeRefused('native-command-output-limit')
                    else:
                        try:
                            count = os.write(process.stdin.fileno(), pending[:65536])
                            pending = pending[count:]
                        except BrokenPipeError:
                            pending = memoryview(b'')
                        if not pending:
                            selector.unregister(process.stdin)
                            process.stdin.close()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeRefused('native-command-timeout')
            if process.wait(timeout=remaining):
                raise ProbeRefused('native-command-refused')
        return bytes(output)
    except subprocess.TimeoutExpired:
        raise ProbeRefused('native-command-timeout') from None
    finally:
        try:
            cleanup_process(process)
        finally:
            process.stdout.close()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()


def cleanup_process(process):
    """Retire the invocation-owned foreground process group on every outcome."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        # An already-exited process group needs no signal; still reap the child.
        pass
    process.wait(timeout=5)
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise ProbeRefused('native-cleanup-unconfirmed')


@contextmanager
def child(argv, env=None):
    process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env=env or {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'},
                               start_new_session=True, **foreground_options())
    try:
        yield process
    finally:
        cleanup_process(process)


def private_file(directory, name, content):
    path = directory / name
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content if isinstance(content, bytes) else content.encode())
    return path


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def public_key(private, timeout=5):
    raw = base64.urlsafe_b64decode(private + '=' * (-len(private) % 4))
    if len(raw) != 32:
        raise ProbeRefused('reality-key-invalid')
    encoded = bytes.fromhex('302e020100300506032b656e04220420') + raw
    public = run(['/usr/bin/openssl', 'pkey', '-inform', 'DER', '-pubout', '-outform', 'DER'], timeout, data=encoded)
    if len(public) != 44:
        raise ProbeRefused('reality-key-invalid')
    return base64.urlsafe_b64encode(public[-32:]).decode().rstrip('=')


def stream_is_xhttp(inbound):
    return inbound.get('streamSettings', {}).get('network') == 'xhttp'


def xray_clients(document, port, client_name, timeout=30):
    deadline = time.monotonic() + timeout
    if not isinstance(document.get('inbounds'), list) or not 1 <= len(document['inbounds']) <= 16:
        raise ProbeRefused('frontend-shape-unsupported')
    candidates = []
    for inbound in document['inbounds']:
        if inbound.get('protocol') != 'vless':
            continue
        tag = inbound.get('tag', '')
        email = client_name + ('-' + tag[len('vless-reality-'):] if tag.startswith('vless-reality-') else '-xhttp' if stream_is_xhttp(inbound) else '')
        configured = inbound['settings']['clients']
        users = [user for user in configured if user.get('email') == email]
        if len(users) != 1:
            raise ProbeRefused('frontend-credentials-empty')
        user = {key: users[0][key] for key in ('id', 'flow') if key in users[0]}
        user['encryption'] = 'none'
        stream = inbound['streamSettings']
        if stream.get('security') == 'reality':
            server = stream['realitySettings']
            short_ids = server['shortIds']
            if len(short_ids) != len(configured):
                raise ProbeRefused('frontend-credential-tuple-invalid')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeRefused('native-command-timeout')
            stream = {'network': stream['network'], 'security': 'reality', 'realitySettings': {
                'serverName': server['serverNames'][0], 'fingerprint': 'chrome',
                'password': public_key(server['privateKey'], timeout=min(5, remaining)),
                'shortId': short_ids[configured.index(users[0])]}}
        elif stream['network'] == 'xhttp':
            stream = {'network': 'xhttp', 'security': 'none', 'xhttpSettings': stream['xhttpSettings']}
        else:
            raise ProbeRefused('frontend-shape-unsupported')
        if stream.get('security') == 'reality' and 'finalmask' in inbound['streamSettings']:
            stream['finalmask'] = deepcopy(inbound['streamSettings']['finalmask'])
        candidates.append({'log': {'loglevel': 'none'}, 'inbounds': [{
            'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'udp': True}}],
            'outbounds': [{'protocol': 'vless', 'mux': {'enabled': stream.get('security') == 'reality' and not user.get('flow')},
                          'settings': {'vnext': [{
                'address': '127.0.0.1', 'port': inbound['port'], 'users': [user]}]}, 'streamSettings': stream}]})
    if not candidates:
        raise ProbeRefused('frontend-shape-unsupported')
    return candidates


def hysteria_client(document, port, ca, client_name, *, tls_server_name=None):
    if document['auth']['type'] != 'userpass' or not document['auth']['userpass']:
        raise ProbeRefused('frontend-credentials-empty')
    if client_name not in document['auth']['userpass']:
        raise ProbeRefused('dedicated-probe-client-required')
    name, password = client_name, document['auth']['userpass'][client_name]
    listen = document['listen']
    host, server_port = listen.rsplit(':', 1)
    host = '127.0.0.1' if host in ('', '0.0.0.0', '[::]') else host
    sni = tls_server_name or (document['acme']['domains'][0] if 'acme' in document
                             else urlsplit(document['masquerade']['proxy']['url']).hostname)
    # ACME startup can outlast the client's first dial. Keep SOCKS alive while
    # request() checks real TLS, authentication and traffic under one deadline.
    client = {'server': host + ':' + server_port, 'auth': name + ':' + password, 'lazy': True,
              'tls': {'sni': sni, 'insecure': False},
              'socks5': {'listen': '127.0.0.1:' + str(port)}}
    if ca is not None:
        client['tls']['ca'] = str(ca)
    if 'ech' in document:
        import importlib.util
        # Ansible can execute this source inline without the installed library
        # on sys.path. Select its prepared companion, not an ambient module.
        shared = Path(__file__).with_name('transport_semantics.py')
        if not shared.is_file():
            shared = Path(__file__).resolve().parents[4] / 'scripts/transport_semantics.py'
        spec = importlib.util.spec_from_file_location('transport_semantics', shared)
        semantics = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(semantics)
        client['tls']['ech'] = semantics.ech_keys_config(Path(document['ech']['keyPath']).read_text())
    if 'congestion' in document:
        client['congestion'] = document['congestion']
    if 'obfs' in document:
        client['obfs'] = document['obfs']
    return client


def request(port, url, expected, process, deadline):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or any(ord(ch) < 32 for ch in url):
        raise ProbeRefused('canary-invalid')
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeRefused('client-exited')
        remaining = deadline - time.monotonic()
        config = ('silent\nshow-error\noutput = "/dev/null"\nwrite-out = "%{http_code}"\n'
                  + 'proxy = ' + json.dumps('socks5h://127.0.0.1:' + str(port)) + '\n'
                  + 'url = ' + json.dumps(url) + '\n' + 'max-time = ' + str(max(.01, remaining)) + '\n')
        try:
            output = run(['/usr/bin/curl', '--config', '-'], max(.01, remaining), data=config.encode())
        except ProbeRefused as error:
            if str(error) not in {'native-command-refused', 'native-command-timeout'}:
                raise
            output = None
        if output == str(expected).encode() and process.poll() is None:
            return
        time.sleep(min(.1, max(0, deadline - time.monotonic())))
    raise ProbeRefused('authenticated-traffic-refused')


def probe(binary, config, *, asset_dir=None, url, client_name, expected=204, timeout=30, tls_server_name=None):
    deadline = time.monotonic() + timeout
    raw = Path(config).read_bytes()
    if asset_dir is None:
        import yaml
    document = json.loads(raw) if asset_dir is not None else yaml.safe_load(raw)
    with tempfile.TemporaryDirectory(prefix='ripdpi-transport-client-') as temporary:
        directory = Path(temporary)
        port = free_port()
        if asset_dir is not None:
            clients = xray_clients(document, port, client_name, timeout=max(.01, deadline - time.monotonic()))
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'XRAY_LOCATION_ASSET': str(asset_dir)}
            for index, client in enumerate(clients):
                path = private_file(directory, 'client-' + str(index) + '.json', json.dumps(client))
                with child([str(binary), 'run', '-config', str(path)], env) as process:
                    request(port, url, expected, process, deadline)
        else:
            client = hysteria_client(document, port, document.get('tls', {}).get('cert'), client_name,
                                     tls_server_name=tls_server_name)
            path = private_file(directory, 'client.yaml', yaml.safe_dump(client))
            with child([str(binary), 'client', '--config', str(path)]) as process:
                request(port, url, expected, process, deadline)
