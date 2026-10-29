"""Exercise native probe startup without changing the owned lab's live units."""
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import yaml


def main():
    library, binary, url, parent = sys.argv[1:]
    sys.path.insert(0, library)
    from transport_runtime_probe import (
        ProbeRefused, cleanup_process, foreground_options, private_file, probe,
    )

    with tempfile.TemporaryDirectory(prefix='hysteria-probe-startup-', dir=parent) as temporary:
        directory = Path(temporary)
        cert, key = directory / 'server.pem', directory / 'server.key'
        foreign = directory / 'foreign.pem'
        for name, public, private in (
            ('owned.example', cert, key),
            ('foreign.example', foreign, directory / 'foreign.key'),
        ):
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt',
                'ec_paramgen_curve:prime256v1', '-nodes', '-days', '1', '-subj', '/CN=' + name,
                '-addext', 'subjectAltName=DNS:' + name, '-out', str(public), '-keyout', str(private)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            public.chmod(0o600)
            private.chmod(0o600)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(('127.0.0.1', 0))
            document = {
                'listen': '127.0.0.1:' + str(reservation.getsockname()[1]),
                'tls': {'cert': str(cert), 'key': str(key)},
                'auth': {'type': 'userpass', 'userpass': {'probe': 'owned-test-password'}},
                'masquerade': {'type': 'proxy', 'proxy': {'url': 'https://owned.example'}},
            }
            server = private_file(directory, 'server.yaml', yaml.safe_dump(document))
            # Hold the UDP socket until just before exec: cold TLS startup can
            # accept a process/port check before it can complete a handshake.
            launcher = ('import os,sys,time;time.sleep(8);os.close(int(sys.argv[1]));'
                        'os.execv(sys.argv[2],sys.argv[2:])')
            process = subprocess.Popen([sys.executable, '-c', launcher, str(reservation.fileno()),
                binary, 'server', '--config', str(server)], pass_fds=(reservation.fileno(),),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, **foreground_options())
        try:
            probe(binary, server, url=url, client_name='probe', timeout=15)
            refused = {}
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as unavailable:
                unavailable.bind(('127.0.0.1', 0))
                for case in ('ca', 'name', 'auth', 'unavailable'):
                    candidate = deepcopy(document)
                    options = {}
                    if case == 'ca':
                        candidate['tls']['cert'] = str(foreign)
                    elif case == 'name':
                        options['tls_server_name'] = 'foreign.example'
                    elif case == 'auth':
                        candidate['auth']['userpass']['probe'] = 'wrong-test-password'
                    else:
                        candidate['listen'] = '127.0.0.1:' + str(unavailable.getsockname()[1])
                    path = private_file(directory, case + '.yaml', yaml.safe_dump(candidate))
                    started = time.monotonic()
                    try:
                        probe(binary, path, url=url, client_name='probe', timeout=2, **options)
                    except ProbeRefused as error:
                        if str(error) not in {'authenticated-traffic-refused', 'client-exited'}:
                            raise
                        refused[case] = str(error)
                    else:
                        raise RuntimeError('native-probe-accepted-' + case)
                    if time.monotonic() - started > 8:
                        raise RuntimeError('native-probe-deadline-' + case)
            print(json.dumps({'delayed_native_start': 'passed',
                'refused_within_deadline': refused}))
        finally:
            cleanup_process(process)


if __name__ == '__main__':
    main()
