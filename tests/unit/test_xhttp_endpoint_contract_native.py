"""Real pinned clients, peer attribution and owned HTTPS origin/rollback proof."""
from __future__ import annotations

from copy import deepcopy

import base64
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
import yaml

from liveness_profiles import build_profiles

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime
spec = importlib.util.spec_from_file_location(
    "xhttp_owned_native_fixture", ROOT / "tests/integration/transport_destination_boundary/fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def get(stack, port, path):
    deadline = time.monotonic() + 10
    while True:
        result = subprocess.run([
            "ip", "netns", "exec", stack.namespace, "curl", "--silent", "--show-error",
            "--noproxy", "*", "--max-time", "5", "--cacert", str(stack.cert),
            "--resolve", f"owned.example:{port}:192.0.2.90", "-D", "-",
            f"https://owned.example:{port}{path}",
        ], text=True, capture_output=True, timeout=8)
        if result.returncode == 7 and time.monotonic() < deadline:
            time.sleep(.1)
            continue
        assert result.returncode == 0, "owned HTTPS request failed"
        return result.stdout


def publish(stack, *, invalid=False):
    def row(path, body, mode):
        return {"path": str(path), "kind": "file", "content_b64": base64.b64encode(body).decode(),
                "mode": mode, "uid": 0, "gid": 0}
    document = {
        "owner": "xhttp-endpoint", "roots": [str(stack.ingress)],
        "files": [row(stack.nginx_config, stack.nginx_config.read_bytes(), "0600"),
                  row(stack.ingress / "certificate.pem", (stack.ingress / "certificate.pem").read_bytes(), "0644"),
                  row(stack.ingress / "private.pem", b"invalid candidate key" if invalid else
                      (stack.ingress / "private.pem").read_bytes(), "0600")],
        "validate_argv": [shutil.which("nginx"), "-t", "-c", str(stack.nginx_config), "-p", str(stack.library)],
        "unit": stack.token + "-nginx.service", "activation": "reload", "check": False,
        "credential_root": "", "runtime_directories": [], "activate_inactive": False,
        "desired_enabled": None,
    }
    return subprocess.run([
        sys.executable, str(ROOT / "ansible/roles/nginx-xhttp/files/nginx_transaction.py"),
    ], input=json.dumps(document), capture_output=True, text=True, timeout=70)


def exported_outbound(stack, endpoint="primary", *, native=False):
    """Synthetic provider metadata is input only; emission and client execution are real."""
    profile = ROOT / "ansible/group_vars" / ("vpn-" + stack.token + ".yml")
    metadata = ROOT / "tests/fixtures/tf-output-sample.json"
    previous = metadata.read_bytes()
    assert not profile.exists()
    document = {name: deepcopy(stack.values[name]) for name in ("xray", "nginx_xhttp", "hysteria", "transport_egress_secrets")}
    document["client_registry"] = {"native-device": {"status": "active"}}
    private = stack.file("emission.yaml", yaml.safe_dump(document))
    try:
        profile.write_text(yaml.safe_dump({
            "vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": True, "enable_hysteria": False,
                    "enable_amneziawg": False, "enable_snell": False, "enable_naive": False},
            "nginx_xhttp_public_port": stack.values["nginx_xhttp_public_port"],
            "nginx_xhttp_fallback_port": stack.values["nginx_xhttp_fallback_port"],
            "nginx_xhttp": {"fallback_enabled": stack.values["nginx_xhttp"].get("fallback_enabled", False)},
        }))
        selected = json.loads(previous)
        selected["server_ipv4"]["value"] = "192.0.2.90"
        metadata.write_text(json.dumps(selected))
        environment = {key: value for key, value in os.environ.items() if key not in {
            "VPN_SECRETS_FILE", "SOPS_FILES", "SOPS_FILE", "HOSTS", "COHORTS", "PROVIDER", "ENV"}}
        environment.update(VPN_SECRETS_FILE=str(private), HOSTS="upcloud:fixture", COHORTS=stack.token,
                           PATH=str(ROOT / "tests/stubs/bin") + ":" + environment["PATH"])
        unsupported = subprocess.run(["bash", str(ROOT / "scripts/emit-singbox.sh"), "native-device",
                                      "--profile-format", "sing-box"], env=environment,
                                     capture_output=True, text=True, timeout=30)
        assert unsupported.returncode != 0 and not unsupported.stdout
        assert stack.uuid not in unsupported.stderr
        result = subprocess.run(["bash", str(ROOT / "scripts/emit-singbox.sh"), "native-device",
                                 "--profile-format", "xray" if native else "ripdpi"], env=environment, capture_output=True,
                                text=True, timeout=30)
        assert result.returncode == 0, "canonical selected-client emission failed"
        emitted = json.loads(result.stdout)
        if native:
            return next(v for v in emitted["outbounds"] if v.get("protocol") == "vless"
                        and v["tag"].endswith(":alternate") == (endpoint == "alternate"))
        def no_key(_):
            raise AssertionError("unused AWG material was requested")
        profiles = build_profiles(None, emitted, document, "native-device", ["p1-xhttp"], None,
                                  None, None, no_key, str(stack.library), awg_defaults={}, awg_cohort={})
        outbounds = profiles["files"]["xray.json"]["outbounds"]
        outbound = next(v for v in outbounds if v["tag"].endswith(":alternate") == (endpoint == "alternate"))
        server = outbound["settings"]["vnext"][0]
        assert server["address"] == "192.0.2.90" and server["port"] == stack.values[
            "nginx_xhttp_fallback_port" if endpoint == "alternate" else "nginx_xhttp_public_port"]
        assert server["users"] == [{"id": stack.uuid, "encryption": "none"}]
        return outbound
    finally:
        metadata.write_bytes(previous)
        profile.unlink(missing_ok=True)


@pytest.mark.parametrize("primary_port", [443, 8443])
def test_pinned_endpoints_preserve_peer_origin_privacy_and_rejected_candidate(primary_port):
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    for binary in ("xray", "hysteria", "nginx", "curl", "ip", "systemctl", "openssl"):
        assert shutil.which(binary), "native endpoint prerequisite is unavailable"
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    for binary in ("xray", "hysteria"):
        assert pins[binary]["version"].lstrip("v") in fixture.command([binary, "version"])
    stack = fixture.NativeStack()
    publication = Path("/var/lib/vpn-nginx-publication") / (stack.token + "-nginx.service")
    assert not publication.exists()
    global_hosts = Path("/etc/hosts").read_bytes()
    try:
        stack.start()
        stack.start_frontend("p1", primary_port=primary_port, path="/native-sync/packet-v2", fallback=True)
        origin = "https://owned.example" + ("" if primary_port == 443 else f":{primary_port}")
        for port in (primary_port, 2083):
            page = get(stack, port, "/")
            assert re.search(r"HTTP/(?:1\.1|2) 200\b", page) and f'content="{origin}/"' in page
            assert "application/atom+xml" in get(stack, port, "/feed.xml")
            assert f"{origin}/" in get(stack, port, "/sitemap.xml")
            assert f"Sitemap: {origin}/sitemap.xml" in get(stack, port, "/robots.txt")
        redirected = fixture.command([
            "ip", "netns", "exec", stack.namespace, "curl", "--silent", "--noproxy", "*",
            "--max-time", "5", "--resolve", "owned.example:80:192.0.2.90", "-I", "http://owned.example/",
        ])
        assert f"Location: {origin}/" in redirected
        exported = exported_outbound(stack)
        access = stack.library / "logs/access.log"
        for port in (primary_port, 2083):
            for supplied in (False, True):
                before = access.stat().st_size
                headers = {"X-Forwarded-For": "198.51.100.201, 198.51.100.202",
                           "X-Real-IP": "198.51.100.203", "Forwarded": "for=198.51.100.204"} if supplied else None
                client = stack.start_client("p1", endpoint_port=port, headers=headers, source_address="192.0.2.81",
                                            outbound=exported if port == primary_port else None)
                time.sleep(.5)
                stack.run_driver(client)
                observed = access.read_text()[before:]
                accepted = [line for line in observed.splitlines() if "vless-xhttp-localhost" in line and "accepted" in line]
                assert accepted and all("192.0.2.81:0" in line for line in accepted), "actual peer attribution differs"
                assert not any(f"198.51.100.{suffix}" in observed for suffix in range(201, 205))
        rejected_client = stack.start_client("p1", True, source_address="192.0.2.81")
        time.sleep(.5)
        stack.run_driver(rejected_client, True)
        adopted = publish(stack)
        assert adopted.returncode == 0, "complete endpoint adoption failed"
        before = {str(path): path.read_bytes() for path in stack.ingress.rglob("*") if path.is_file()}
        rejected = publish(stack, invalid=True)
        assert rejected.returncode != 0 and "nginx publication failed" in rejected.stderr
        assert before == {str(path): path.read_bytes() for path in stack.ingress.rglob("*") if path.is_file()}
        stack.run_driver(client)
        assert re.search(r"HTTP/(?:1\.1|2) 200\b", get(stack, primary_port, "/"))
        # An actual unauthenticated QUIC exchange invokes Hysteria's owned proxy.
        # It must reach the verified primary HTTPS listener and keep ordinary 404 semantics.
        hosts = stack.file("masquerade-hosts", "127.0.0.1 localhost\n192.0.2.90 owned.example\n", "h")
        stack.start_hysteria(masquerade_origin=origin, hosts=hosts)
        stack.start_client("hysteria", True)
        deadline = time.monotonic() + 10
        public_log = stack.library / "vpn-xhttp.access.log"
        while time.monotonic() < deadline:
            content = public_log.read_text() if public_log.exists() else ""
            if re.search(r'"POST /auth HTTP/(?:1\.1|2\.0)" 404\b', content):
                break
            time.sleep(.1)
        else:
            pytest.fail("native Hysteria masquerade did not reach the served HTTPS origin")
        assert Path("/etc/hosts").read_bytes() == global_hosts
        ordinary = "\n".join(path.read_text(errors="replace") for path in stack.library.glob("vpn-xhttp*.log"))
        assert stack.values["xray"]["xhttp_path"] not in ordinary and stack.uuid not in ordinary
        assert stack.hys_password not in ordinary
    finally:
        stack.close()
        if publication.exists():
            shutil.rmtree(publication)


@pytest.mark.parametrize("mode", ["auto", "stream-up"])
def test_exported_distinct_alternate_survives_primary_outage_and_rejects_wrong_tls(mode):
    import copy
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend("p1", fallback=True, fallback_hostname="alternate.example", xhttp_mode=mode)
        primary = exported_outbound(stack)
        alternate = exported_outbound(stack, "alternate")
        assert alternate["streamSettings"]["tlsSettings"]["serverName"] == "alternate.example"
        assert alternate["streamSettings"]["xhttpSettings"]["mode"] == mode
        client = stack.start_client("p1", outbound=primary)
        other = stack.start_client("p1", outbound=alternate)
        time.sleep(.5)
        stack.run_driver(client)
        stack.run_driver(other)
        bad = copy.deepcopy(alternate)
        bad["streamSettings"]["tlsSettings"]["serverName"] = "unowned.example"
        wrong_tls = stack.start_client("p1", outbound=bad)
        time.sleep(.5)
        stack.run_driver(wrong_tls, True)
        rule = "table inet xhttp_outage {\n chain output {\n type filter hook output priority -100;\n tcp dport 8443 reject;\n }\n}\n"
        result = subprocess.run(["ip", "netns", "exec", stack.namespace, "nft", "-f", "-"],
                                input=rule, capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, "owned primary fault could not be installed"
        stack.run_driver(client, True)
        stack.run_driver(other)
        fixture.command(["ip", "netns", "exec", stack.namespace, "nft", "delete", "table", "inet", "xhttp_outage"])
        stack.run_driver(client)
    finally:
        stack.close()


def measurement(stack, client):
    # Unit startup acknowledgement precedes SOCKS bind. Admission is outside the
    # measured transfer; no authenticated request is retried or discarded.
    deadline = time.monotonic() + 5
    while not fixture.command(['ip', 'netns', 'exec', stack.namespace, 'ss', '-Hntl',
                               'sport', '=', str(client)]).strip():
        assert time.monotonic() < deadline, 'owned client listener did not become ready'
        time.sleep(.05)
    raw = fixture.command(['ip', 'netns', 'exec', stack.namespace, sys.executable,
                           str(ROOT / 'tests/integration/xhttp_delivery_matrix/measure.py'), str(client)], timeout=60)
    result = json.loads(raw)
    assert result['bytes_each_direction'] == 1048576
    assert result['mib_per_second'] >= .02 and result['latency_ms'] <= 2000
    return result


def client_resources(stack, unit, port):
    pid = int(fixture.command(['systemctl', 'show', unit, '--property=MainPID', '--value']).strip())
    status = (Path('/proc') / str(pid) / 'status').read_text()
    rss = int(re.search(r'^VmRSS:\s+(\d+)', status, re.M)[1])
    connections = fixture.command(['ip', 'netns', 'exec', stack.namespace, 'ss', '-Hnt', 'state', 'established',
                                   '(', 'dport', '=', str(port), ')']).splitlines()
    return dict(rss_kib=rss, connections=len(connections))


@pytest.mark.parametrize('connections', [1, 2, 4])
def test_exact_native_format_compares_bounded_pool_idle_reconnect_and_restoration(connections):
    mode = 'stream-up'
    assert sys.platform == 'linux' and os.geteuid() == 0 and os.environ.get('TRANSPORT_NATIVE_ISOLATED') == '1'
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend('p1', fallback=True, fallback_hostname='alternate.example', xhttp_mode=mode)
        baseline = exported_outbound(stack, native=True)
        baseline_client = stack.start_client('p1', outbound=baseline)
        baseline_unit = stack.units[-1]
        time.sleep(.5)
        stack.run_driver(baseline_client)
        baseline_measurement = measurement(stack, baseline_client)
        baseline_resources = client_resources(stack, baseline_unit, 8443)
        # Stop only the fixture-owned baseline client before measuring the candidate.
        fixture.command(['systemctl', 'stop', baseline_unit])
        stack.values['xray']['xhttp_tuning'] = dict(profile='bounded-pool', max_connections=connections)
        candidate = exported_outbound(stack, 'alternate', native=True)
        assert candidate['streamSettings']['xhttpSettings']['xmux'] == dict(
            maxConnections=connections, hMaxRequestTimes=0, hMaxReusableSecs=0, cMaxReuseTimes=0)
        candidate_client = stack.start_client('p1', outbound=candidate)
        candidate_unit = stack.units[-1]
        time.sleep(.5)
        stack.run_driver(candidate_client)
        measured = measurement(stack, candidate_client)
        time.sleep(3)  # An idle pool must deliver without replacing the process.
        idle = measurement(stack, candidate_client)
        # Delay only this disconnected namespace. Both profiles see the same fault.
        fixture.command(['ip', 'netns', 'exec', stack.namespace, 'tc', 'qdisc', 'add', 'dev', 'lo', 'root',
                         'netem', 'delay', '2ms', 'rate', '20mbit'])
        constrained = measurement(stack, candidate_client)
        fixture.command(['systemctl', 'start', baseline_unit])
        constrained_baseline = measurement(stack, baseline_client)
        fixture.command(['systemctl', 'stop', baseline_unit])
        fixture.command(['ip', 'netns', 'exec', stack.namespace, 'tc', 'qdisc', 'del', 'dev', 'lo', 'root'])
        resources = client_resources(stack, candidate_unit, 2083)
        assert resources['rss_kib'] <= 262144 and resources['connections'] <= connections
        assert measured['mib_per_second'] >= baseline_measurement['mib_per_second'] * .1
        assert constrained['mib_per_second'] >= constrained_baseline['mib_per_second'] * .1
        fixture.command(['systemctl', 'restart', candidate_unit])
        time.sleep(.5)
        reconnect = measurement(stack, candidate_client)
        # Real candidate parser refusal preserves the accepted baseline file.
        accepted = stack.library / 'frontend.json'
        before = accepted.read_bytes()
        invalid = json.loads(before)
        next(v for v in invalid['inbounds'] if v['tag'] == 'vless-xhttp-localhost')[
            'streamSettings']['xhttpSettings']['mode'] = 'unaccepted-mode'
        rejected = stack.file('rejected-tuning.json', json.dumps(invalid), 'x')
        result = subprocess.run([stack.xray, 'run', '-test', '-config', str(rejected)],
                                capture_output=True, text=True, timeout=10,
                                env={**os.environ, 'XRAY_LOCATION_ASSET': str(stack.assets)})
        assert result.returncode != 0 and accepted.read_bytes() == before
        fixture.command(['systemctl', 'stop', candidate_unit])
        stack.values['xray'].pop('xhttp_tuning')
        assert exported_outbound(stack, native=True) == baseline
        fixture.command(['systemctl', 'start', baseline_unit])
        time.sleep(.5)
        stack.run_driver(baseline_client)
        restored = measurement(stack, baseline_client)
        # Only technical aggregate observations are emitted, never profiles or credentials.
        print(json.dumps(dict(mode=mode, configured_connections=connections, baseline=baseline_measurement, candidate=measured,
                              baseline_resources=baseline_resources, candidate_resources=resources,
                              idle=idle, constrained=constrained, constrained_baseline=constrained_baseline,
                              reconnect=reconnect, restored=restored), sort_keys=True))
    finally:
        stack.close()


@pytest.mark.parametrize('mode', ['auto', 'packet-up', 'stream-up'])
def test_exact_native_format_modes_forward_without_tuning(mode):
    assert sys.platform == 'linux' and os.geteuid() == 0 and os.environ.get('TRANSPORT_NATIVE_ISOLATED') == '1'
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend('p1', xhttp_mode=mode)
        native = exported_outbound(stack, native=True)
        assert native['streamSettings']['xhttpSettings']['mode'] == mode
        client = stack.start_client('p1', outbound=native)
        time.sleep(.5)
        stack.run_driver(client)
        print(json.dumps(dict(mode=mode, untuned=measurement(stack, client))))
    finally:
        stack.close()
