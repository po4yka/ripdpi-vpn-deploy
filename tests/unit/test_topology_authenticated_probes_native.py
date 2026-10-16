"""Owned exact-client TLS/authentication and per-surface outage acceptance.

All traffic stays in the disconnected namespace. Portable control-flow tests
remain separate from these actual Xray, nginx and QUIC observations.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest
import yaml

from template_render import render_fragment, render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime
spec = importlib.util.spec_from_file_location(
    "topology_probe_native", ROOT / "tests/integration/transport_destination_boundary/fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def require_native():
    assert os.uname().sysname == "Linux" and os.geteuid() == 0
    assert os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    for binary in ("xray", "hysteria", "nginx", "curl", "systemctl", "ip", "openssl"):
        assert shutil.which(binary), "exact native probe prerequisite missing"
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    for binary in ("xray", "hysteria"):
        assert pins[binary]["version"].lstrip("v") in fixture.command([binary, "version"])


def canary(stack):
    cert, key = stack.library / "canary.pem", stack.library / "canary.key"
    fixture.command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                     "-keyout", str(key), "-out", str(cert), "-subj", "/CN=owned-canary",
                     "-addext", "subjectAltName=IP:192.0.2.81"])
    key.chmod(0o600)
    stack.unit("canary", ["openssl", "s_server", "-accept", "192.0.2.81:9445", "-www",
                           "-cert", str(cert), "-key", str(key), "-quiet"])
    return cert


def request(stack, cert, port=None, *, healthy=True):
    args = ["ip", "netns", "exec", stack.namespace, "curl", "--silent", "--show-error",
            "--max-time", "4", "--cacert", str(cert), "--output", "/dev/null", "--write-out", "%{http_code}"]
    args += ["--noproxy", "", "--proxy", f"socks5h://127.0.0.1:{port}"] if port else ["--noproxy", "*"]
    args += ["https://192.0.2.81:9445/"]
    deadline = time.monotonic() + 8
    while True:
        result = subprocess.run(args, capture_output=True, text=True, timeout=6,
                                env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"})
        delivered = result.returncode == 0 and result.stdout == "200"
        if delivered or time.monotonic() >= deadline:
            assert delivered is healthy, "native authenticated delivery boundary violated"
            return
        time.sleep(.1)


@pytest.mark.parametrize("salamander", [False, True])
def test_secure_smoke_and_watchdog_hysteria_auth_sni_ca_and_obfs(salamander):
    require_native()
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_hysteria(salamander=salamander)
        cert = canary(stack)
        request(stack, cert)  # Direct control is independent of transport proof.
        values = copy.deepcopy(stack.values)
        values.update(vpn_service_address="192.0.2.90", hysteria_config_dir=str(stack.library))
        values["watchdog"].update(hysteria_probe_client="native-device", hysteria_probe_socks_port=31110)
        values["hysteria"]["server_name"] = "owned.example"
        private = yaml.safe_load(render_template(
            ROOT / "ansible/roles/watchdog/templates/hysteria-probe.yaml.j2", values))
        assert private["tls"]["insecure"] is False
        # Render the actual smoke task's private client as well.
        play = yaml.safe_load((ROOT / "ansible/playbooks/smoke-test.yml").read_text())[0]
        def find(tasks):
            for task in tasks:
                if task.get("name") == "Render Hysteria client config":
                    return task["ansible.builtin.copy"]["content"]
                found = find(task.get("block", []))
                if found:
                    return found
        smoke = yaml.safe_load(render_fragment("native-smoke.yaml", find(play["tasks"]), values))
        smoke["server"] = "192.0.2.90:443"
        assert smoke["tls"] == private["tls"]
        assert smoke.get("obfs") == private.get("obfs")
        for index, failure in enumerate((None, "credential", "san", "trust", "obfs", "smoke")):
            candidate = copy.deepcopy(smoke if failure == "smoke" else private)
            port = 31110 + index
            candidate["socks5"]["listen"] = f"127.0.0.1:{port}"
            if failure == "credential":
                candidate["auth"] = "native-device:wrong-private-password"
            elif failure == "san":
                candidate["tls"]["sni"] = "different.example"
            elif failure == "trust":
                candidate["tls"]["ca"] = str(cert)
            elif failure == "obfs":
                candidate["obfs"] = {"type": "salamander", "salamander": {"password": "wrong-obfs-authority"}}
            path = stack.file(f"health-{index}.yaml", yaml.safe_dump(candidate), "h")
            stack.unit(f"health-{index}", [stack.hysteria, "client", "-c", str(path)], "h")
            request(stack, cert, port, healthy=failure in (None, "smoke"))
            request(stack, cert)
    finally:
        stack.close()


def test_xhttp_all_frontends_authentication_and_backend_outage():
    require_native()
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend("p1", primary_port=8443, fallback=True)
        cert = canary(stack)
        values = copy.deepcopy(stack.values)
        values.update(vpn_service_address="192.0.2.90", watchdog_reality_probes=[])
        values["watchdog"]["reality_probe_client"] = "native-device"
        document = json.loads(render_template(
            ROOT / "ansible/roles/watchdog/templates/reality-probe.json.j2", values))
        path = stack.file("health-xhttp.json", json.dumps(document), "x")
        stack.unit("health-xhttp", [stack.xray, "run", "-config", str(path)], "x",
                   ["Environment=SSL_CERT_FILE=" + str(stack.cert)])
        ports = [item["port"] for item in document["inbounds"]]
        assert len(ports) == 2
        for port in ports:
            request(stack, cert, port)
        nginx = stack.token + "-nginx.service"
        before = fixture.command(["systemctl", "show", nginx, "--property=MainPID", "--value"])
        fixture.command(["systemctl", "stop", stack.token + "-frontend.service"])
        for port in ports:
            request(stack, cert, port, healthy=False)
        request(stack, cert)
        assert fixture.command(["systemctl", "show", nginx, "--property=MainPID", "--value"]) == before
    finally:
        stack.close()


def test_cohort_only_reality_delivers_every_listener_and_rejects_wrong_uuid():
    require_native()
    stack = fixture.NativeStack()
    try:
        stack.start()
        cohorts = [{'name': name, 'port': port, 'flow_mode': 'vision', 'clients': ['native-device']}
                   for name, port in [('first', 2443), ('second', 2444)]]
        stack.start_frontend('p0', cohorts=cohorts)
        cert = canary(stack)
        values = copy.deepcopy(stack.values)
        values.update(vpn_service_address='192.0.2.90', watchdog_reality_probes=[
            {'name': cohort['name'], 'port': cohort['port'], 'p0_reality_shape_input': cohort}
            for cohort in cohorts])
        values['watchdog']['reality_probe_client'] = 'native-device'
        values['xray']['reality_public_key'] = stack.reality_password
        document = json.loads(render_template(
            ROOT / 'ansible/roles/watchdog/templates/reality-probe.json.j2', values))
        assert [outbound['settings']['vnext'][0]['port'] for outbound in document['outbounds']] == [2443, 2444]
        path = stack.file('health-reality.json', json.dumps(document), 'x')
        stack.unit('health-reality', [stack.xray, 'run', '-config', str(path)], 'x')
        for inbound in document['inbounds']:
            request(stack, cert, inbound['port'])
        # A real invalid identity must fail despite a positive direct control.
        for index, outbound in enumerate(document['outbounds']):
            outbound['settings']['vnext'][0]['users'][0]['id'] = '11111111-2222-4333-8444-555555555555'
            document['inbounds'][index]['port'] += 100
        path = stack.file('health-reality-invalid.json', json.dumps(document), 'x')
        stack.unit('health-reality-invalid', [stack.xray, 'run', '-config', str(path)], 'x')
        for inbound in document['inbounds']:
            request(stack, cert, inbound['port'], healthy=False)
        request(stack, cert)
    finally:
        stack.close()


def test_stopped_exact_client_times_out_and_watchdog_cleanup_kills_its_owner():
    import signal
    require_native()
    stack = fixture.NativeStack()
    process = None
    try:
        stack.start()
        stack.start_hysteria(salamander=True)
        cert = canary(stack)
        values = copy.deepcopy(stack.values)
        values.update(vpn_service_address='192.0.2.90', hysteria_config_dir=str(stack.library))
        values['watchdog'].update(hysteria_probe_client='native-device', hysteria_probe_socks_port=31180)
        values['hysteria']['server_name'] = 'owned.example'
        client = stack.file('stalled-health.yaml', render_template(
            ROOT / 'ansible/roles/watchdog/templates/hysteria-probe.yaml.j2', values))
        source = (ROOT / 'ansible/roles/watchdog/templates/vpn-watchdog.sh.j2').read_text()
        # Execute the unchanged production cleanup and request functions against
        # the exact live QUIC client, not a process pretending to be a client.
        cleanup = source[source.index('cleanup_reality_client()'):source.index('# A stable private directory')]
        round_trip = source[source.index('socks_listener_ready()'):source.index('probe_reality_listeners()')]
        script = 'set -euo pipefail\n' + cleanup + round_trip + '''
"$HYSTERIA_BIN" client -c "$CLIENT_CONFIG" >/dev/null 2>&1 &
xray_probe_pid=$!
owned_pid=$xray_probe_pid
trap cleanup_reality_client EXIT
deadline=$(( SECONDS + 8 ))
while ! socks_listener_owned 31180; do
  kill -0 "$xray_probe_pid"
  (( SECONDS < deadline ))
  sleep .1
done
reality_canary_round_trip 31180
kill -STOP "$xray_probe_pid"
if reality_canary_round_trip 31180; then exit 41; fi
cleanup_reality_client
if kill -0 "$owned_pid" 2>/dev/null; then exit 42; fi
'''
        started = time.monotonic()
        process = subprocess.Popen(['ip', 'netns', 'exec', stack.namespace, 'bash', '-c', script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
            env={**os.environ, 'HYSTERIA_BIN': stack.hysteria, 'CLIENT_CONFIG': str(client),
                 'XRAY_REALITY_PROBE_TIMEOUT': '2', 'XRAY_REALITY_PROBE_EXPECTED_STATUS': '200',
                 'XRAY_REALITY_PROBE_URL': 'https://192.0.2.81:9445/', 'CURL_CA_BUNDLE': str(cert)})
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, 'actual stopped-client request/cleanup boundary failed'
        assert time.monotonic() - started < 20
        assert not stdout and stack.hys_password not in stderr
        request(stack, cert)
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        stack.close()
