"""Actual pinned native issue/revoke probes in an explicitly disposable Linux host.

Run the complete file under the existing isolated systemd native lane. Missing
tools, TUN, systemd, source receipts or positive traffic fail instead of skipping.
No inventory, deployed credential or network outside the owned lab is used.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4

import pytest

import device_lifecycle_probe as renderer
import device_lifecycle_probe_worker as worker
from template_render import render_template
from test_device_lifecycle_probe import HttpsOrigin, authority, certificate, request, settings
from test_snell_native import snell_binary
from test_transport_semantics_native import exact_awg_sources

ROOT = Path(__file__).resolve().parents[2]
ADDRESS = "203.0.113.239"
pytestmark = pytest.mark.native_runtime


def command(argv, *, data=None):
    result = subprocess.run([str(value) for value in argv], input=data, capture_output=True, timeout=20)
    assert result.returncode == 0, "native lifecycle command failed: " + Path(argv[0]).name
    return result.stdout


def free_port(network=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, network) as connection:
        connection.bind((ADDRESS, 0))
        return connection.getsockname()[1]


@pytest.fixture(scope="module")
def native_tools(snell_binary):
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    assert Path("/run/systemd/system").is_dir(), "native lifecycle needs the owned systemd lane"
    go, awg = exact_awg_sources()
    quick = Path(os.environ["AWG_NATIVE_TOOLS_SOURCE"]) / "src/wg-quick/linux.bash"
    assert quick.is_file()
    xray = Path(shutil.which("xray") or "/missing")
    hysteria = Path(os.environ.get("HYSTERIA_NATIVE_BINARY", str(ROOT / ".cache/native-transport-semantics/bin/hysteria")))
    naive = Path(os.environ.get("NAIVE_NATIVE_BINARY", str(ROOT / ".cache/p2-native-caddy/caddy")))
    for binary in (xray, hysteria, naive):
        assert binary.is_file(), "missing admitted native lifecycle runtime"
    assert b"26.3.27" in command([xray, "version"])
    assert b"v2.13.0" in command([hysteria, "version"])
    info = command([naive, "build-info"])
    assert b"v2.11.7" in info and b"c096d6a00cb2" in info
    directory = Path("/usr/local/libexec") / ("device-probe-test-" + uuid4().hex)
    directory.mkdir(mode=0o700)
    binaries = {name: shutil.which(name) for name in ("ip", "curl", "systemctl")}
    try:
        for name, source in {"xray": xray, "hysteria": hysteria, "snell": snell_binary,
                             "awg": awg, "awg-go": go, "awg-quick": quick, "naive": naive}.items():
            target = directory / name
            shutil.copyfile(source, target)
            target.chmod(0o500)
            assert target.read_bytes() == source.read_bytes()
            binaries[name] = str(target)
        yield binaries
    finally:
        shutil.rmtree(directory)


@pytest.fixture
def owned_origin(tmp_path, native_tools):
    interface = "dpt" + uuid4().hex[:10]
    current = json.loads(command(["ip", "-j", "address", "show"]))
    assert not any(entry.get("local") == ADDRESS for device in current for entry in device.get("addr_info", []))
    command(["ip", "link", "add", interface, "type", "dummy"])
    origin = None
    try:
        command(["ip", "address", "add", ADDRESS + "/32", "dev", interface])
        command(["ip", "link", "set", interface, "up"])
        cert, key = certificate(tmp_path)
        origin = HttpsOrigin(cert, key, address=ADDRESS)
        yield origin, cert, key
    finally:
        if origin:
            origin.close()
        command(["ip", "link", "delete", interface])


@contextmanager
def service(binary, args, config_path, cert):
    name = "device-probe-test-" + uuid4().hex + ".service"
    # systemd-run owns the actual process, so worker witness reads the real PID
    # and health. A fixture executable is never substituted for this service.
    command(["systemd-run", "--quiet", "--unit", name, "--property=Type=simple",
             "--property=RuntimeMaxSec=180", "--property=StandardOutput=null", "--property=StandardError=null",
             "--setenv=SSL_CERT_FILE=" + str(cert), str(binary), *args, str(config_path)])
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ready = subprocess.run(["systemctl", "is-active", "--quiet", name], capture_output=True, timeout=3)
            if ready.returncode == 0:
                break
            time.sleep(0.05)
        else:
            pytest.fail("actual native server failed startup")
        yield name
    finally:
        stopped = subprocess.run(["systemctl", "stop", name], capture_output=True, timeout=10)
        if stopped.returncode:
            state = subprocess.run(["systemctl", "show", name, "--property=LoadState,ActiveState"], capture_output=True, timeout=5)
            assert b"LoadState=not-found" in state.stdout and b"ActiveState=inactive" in state.stdout
        subprocess.run(["systemctl", "reset-failed", name], capture_output=True, timeout=5)


def write(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def selected_profiles(monkeypatch, source, config):
    monkeypatch.setattr(renderer, "context", lambda _: copy.deepcopy(config))
    return renderer.render_profiles(source, "", "device0", "upcloud:fixture", ADDRESS)


class MeasuredRuntime(worker.Runtime):
    """Keep categorical native request diagnostics separate from probe receipts."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.measurements = []

    def http(self, control, timeout, directory, **kwargs):
        result = super().http(control, timeout, directory, **kwargs)
        self.measurements.append({
            "route": next((name for name in ("proxy", "namespace", "naive") if kwargs.get(name)), "control"),
            "exit": result["exit"], "accepted": result["accepted"],
            "elapsed_ms": round(result["elapsed"] * 1000),
        })
        return result


def wait_for_native_access(runtime, profile, origin, directory):
    """Admit actual payload readiness before testing the operation receipt."""
    control = request([profile], origin.url)["control"]
    deadline = time.monotonic() + 15
    while True:
        remaining = deadline - time.monotonic()
        assert remaining > 0, "native fixture did not reach authenticated readiness"
        measured = runtime.stream(profile, control, min(5, remaining), directory)
        assert measured["setup_ok"] and measured["cleanup_ok"], "native readiness resources were not reclaimed"
        assert time.monotonic() < deadline, "native fixture exceeded authenticated readiness deadline"
        if measured["accepted"]:
            return
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))


def assert_access(runtime, profile, origin, state):
    runtime.measurements.clear()
    value = request([profile], origin.url)
    value["mode"] = "deny" if state == "denied" else "accept"
    value["timeout_seconds"] = 5
    result = worker.run_request(value, runtime=runtime)
    row = result["profiles"][0]
    assert row["state"] == state, {"result": result, "requests": runtime.measurements}
    assert all(row[key] for key in ("control_ok", "setup_ok", "cleanup_ok", "runtime_healthy")), result
    if state == "denied":
        assert row["peer_absent"], result
    assert result["cleanup"] == "confirmed"
    assert "private-" not in json.dumps(result) and profile["witness"]["credential"] not in json.dumps(result)
    return row


@pytest.mark.parametrize("shape", ["vision", "mux", "sudoku", "xhttp"])
def test_actual_xray_profile_issue_revoke_and_last_device(native_tools, owned_origin, tmp_path, monkeypatch, shape):
    origin, cert, key = owned_origin
    source, config = authority(), settings()
    config["vpn"] = {name: False for name in config["vpn"]}
    config["vpn"].update(enable_xray_reality=shape != "xhttp", enable_nginx_xhttp=shape == "xhttp")
    port = free_port()
    config.update(xray_port=port, xray_fallback_port=0, nginx_xhttp_public_port=port)
    source["nginx_xhttp"]["fallback_enabled"] = False
    pair = command([native_tools["xray"], "x25519"]).decode()
    values = dict(line.split(": ", 1) for line in pair.splitlines() if ": " in line)
    source["xray"]["reality_public_key"] = values["Password (PublicKey)"]
    if shape in {"mux", "sudoku"}:
        config["vpn"]["xray_flow_mode"] = "mux"
        config["vpn"]["xray_finalmask"] = shape == "sudoku"
    profile = selected_profiles(monkeypatch, source, config)[0]
    client = source["xray"]["clients"][0]
    user = {"id": client["uuid"], "email": "device0"}
    if shape == "vision":
        user["flow"] = "xtls-rprx-vision"
    stream = ({"network": "xhttp", "security": "tls", "xhttpSettings": {"path": "/app-sync", "mode": "auto"},
               "tlsSettings": {"certificates": [{"certificateFile": str(cert), "keyFile": str(key)}]}}
              if shape == "xhttp" else {"network": "raw", "security": "reality", "realitySettings": {
                  "target": ADDRESS + ":" + str(origin.server.server_port), "serverNames": ["localhost"],
                  "privateKey": values["PrivateKey"], "shortIds": [client["short_id"]], "xver": 0}})
    if shape == "sudoku":
        stream["finalmask"] = {"tcp": [{"type": "sudoku", "settings": {}}]}
    server = {"log": {"loglevel": "none"}, "inbounds": [{"listen": ADDRESS, "port": port, "protocol": "vless",
              "settings": {"clients": [user], "decryption": "none"}, "streamSettings": stream}],
              "outbounds": [{"protocol": "freedom"}]}
    path = tmp_path / "server.json"
    write(path, server)
    runtime = MeasuredRuntime(binaries=native_tools, ca_file=cert)
    with service(native_tools["xray"], ["run", "-config"], path, cert) as unit:
        profile["witness"].update(config_path=str(path), unit=unit)
        # Type=simple is active before REALITY's asynchronous target discovery.
        wait_for_native_access(runtime, profile, origin, tmp_path)
        assert_access(runtime, profile, origin, "accepted")
        survivor_id = str(uuid4())
        survivor = copy.deepcopy(profile)
        survivor["config"]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = survivor_id
        survivor["witness"]["credential"] = survivor_id
        server["inbounds"][0]["settings"]["clients"] = [{"id": survivor_id, "email": "survivor", **({"flow": user["flow"]} if "flow" in user else {})}]
        write(path, server)
        command(["systemctl", "restart", unit])
        wait_for_native_access(runtime, survivor, origin, tmp_path)
        assert_access(runtime, survivor, origin, "accepted")
        assert_access(runtime, profile, origin, "denied")
        command(["systemctl", "stop", unit])
        path.unlink()
        assert assert_access(runtime, profile, origin, "denied")["inactive_confirmed"]


def test_actual_hysteria_issue_revoke_and_last_device(native_tools, owned_origin, tmp_path, monkeypatch):
    origin, cert, key = owned_origin
    source, config = authority(), settings()
    config["vpn"] = {name: False for name in config["vpn"]}
    config["vpn"]["enable_hysteria"] = True
    port = free_port(socket.SOCK_DGRAM)
    config["hysteria_port"] = port
    profile = selected_profiles(monkeypatch, source, config)[0]
    server = {"listen": ADDRESS + ":" + str(port), "tls": {"cert": str(cert), "key": str(key)},
              "auth": {"type": "userpass", "userpass": {"device0": "private-hy-password", "survivor": "survivor-hy-password"}},
              "bandwidth": {"up": "100 mbps", "down": "200 mbps"}}
    path = tmp_path / "server.yaml"
    # The authority reader consumes the exact canonical YAML mapping shape.
    def publish():
        import yaml
        text = yaml.safe_dump({name: value for name, value in server.items() if name != "auth"}, sort_keys=False)
        text += "auth:\n  type: userpass\n  userpass:\n" + "".join("    " + json.dumps(name) + ": " + json.dumps(value) + "\n" for name, value in server["auth"]["userpass"].items())
        path.write_text(text)
        path.chmod(0o600)
    publish()
    runtime = MeasuredRuntime(binaries=native_tools, ca_file=cert)
    with service(native_tools["hysteria"], ["server", "-c"], path, cert) as unit:
        profile["witness"].update(config_path=str(path), unit=unit)
        assert_access(runtime, profile, origin, "accepted")
        del server["auth"]["userpass"]["device0"]
        publish()
        command(["systemctl", "restart", unit])
        assert_access(runtime, profile, origin, "denied")
        command(["systemctl", "stop", unit])
        path.unlink()
        assert assert_access(runtime, profile, origin, "denied")["inactive_confirmed"]


@pytest.mark.parametrize("variant", ["v4-stream", "v6-default", "v6-unshaped"])
def test_actual_snell_fresh_reuse_and_revoked_user(native_tools, owned_origin, tmp_path, monkeypatch, variant):
    origin, cert, _ = owned_origin
    source, config = authority(), settings()
    config["vpn"] = {name: False for name in config["vpn"]}
    config["vpn"]["enable_snell"] = True
    selected = next(value for value in config["snell"]["variants"] if value["id"] == variant)
    selected["listen_port"] = free_port()
    config["snell"]["variants"] = [selected]
    profiles = selected_profiles(monkeypatch, source, config)
    secret = next(value for value in source["snell_secrets"]["variants"] if value["id"] == variant)
    inbound = {"type": "snell", "listen": ADDRESS, "listen_port": selected["listen_port"], "version": selected["server_version"],
               "psk": secret["psk"], "users": [*secret["users"], {"name": "survivor", "userkey": "STUB_SURVIVOR_USER_KEY"}]}
    inbound.update({"obfs_mode": "none"} if selected["server_version"] == 5 else {"mode": selected["mode"]})
    server = {"log": {"disabled": True}, "inbounds": [inbound], "outbounds": [{"type": "direct"}]}
    path = tmp_path / "server.json"
    write(path, server)
    runtime = MeasuredRuntime(binaries=native_tools, ca_file=cert)
    with service(native_tools["snell"], ["run", "-c"], path, cert) as unit:
        for profile in profiles:
            profile["witness"].update(config_path=str(path), unit=unit)
            assert_access(runtime, profile, origin, "accepted")
        inbound["users"] = [inbound["users"][-1]]
        write(path, server)
        command(["systemctl", "restart", unit])
        for profile in profiles:
            assert_access(runtime, profile, origin, "denied")
        command(["systemctl", "stop", unit])
        path.unlink()
        assert assert_access(runtime, profiles[0], origin, "denied")["inactive_confirmed"]


def test_actual_naive_issue_revoke_and_last_handler(native_tools, owned_origin, tmp_path, monkeypatch):
    origin, cert, key = owned_origin
    source, config = authority(), settings()
    config["vpn"] = {name: False for name in config["vpn"]}
    config["vpn"]["enable_naive"] = True
    config["naive_bind_port"] = free_port()
    profile = selected_profiles(monkeypatch, source, config)[0]
    path = tmp_path / "caddy.json"
    shutil.copyfile(cert, tmp_path / "server.fullchain.pem")
    shutil.copyfile(key, tmp_path / "server.key")
    values = {"naive": {"bind_port": config["naive_bind_port"], "config_dir": str(tmp_path), "log_dir": str(tmp_path), "decoy_root": str(tmp_path)},
              "naive_secrets": {**source["naive_secrets"], "probe_resistance_secret": "owned-native-probe"}}
    def publish():
        path.write_text(render_template(ROOT / "ansible/roles/naive/templates/caddy.json.j2", values))
        path.chmod(0o600)
    publish()
    runtime = MeasuredRuntime(binaries=native_tools, ca_file=cert)
    with service(native_tools["naive"], ["run", "--config"], path, cert) as unit:
        profile["witness"].update(config_path=str(path), unit=unit)
        assert_access(runtime, profile, origin, "accepted")
        values["naive_secrets"]["clients"] = []
        publish()
        command(["systemctl", "restart", unit])
        assert_access(runtime, profile, origin, "denied")


@contextmanager
def revocation_service(engine, binaries):
    """Own exact canonical barrier surfaces only inside the admitted native lab."""
    unit = "snell.service" if engine == "snell" else "caddy-naive.service"
    binary = Path("/usr/local/bin") / ("sing-box-snell" if engine == "snell" else "caddy-naive")
    helper = Path("/usr/local/libexec/ripdpi-consumer/device_revocation_barrier.py")
    unit_path = Path("/etc/systemd/system") / unit
    state = Path("/var/lib/ripdpi/device-revocation") / unit
    naive_state = Path("/var/lib/ripdpi/naive-activation")
    directory = Path("/etc") / ("device-revocation-test-" + uuid4().hex)
    assert not any(os.path.lexists(path) for path in (unit_path, state, directory))
    prior = subprocess.run(["systemctl", "show", unit, "--property=LoadState"], capture_output=True, timeout=20, check=False)
    assert prior.returncode in {0, 1} and prior.stdout.strip() == b"LoadState=not-found"
    if engine == "naive":
        assert not os.path.lexists(naive_state)
    created_files, created_directories = [], []

    def ensure_directory(path):
        if not path.exists():
            ensure_directory(path.parent)
            path.mkdir(mode=0o755)
            created_directories.append(path)
        assert not path.is_symlink() and path.stat().st_uid == 0 and not path.stat().st_mode & 0o022

    def install(source, target):
        ensure_directory(target.parent)
        if os.path.lexists(target):
            assert target.is_file() and not target.is_symlink()
            assert target.stat().st_uid == 0 and target.stat().st_nlink == 1 and not target.stat().st_mode & 0o022
            with target.open("rb") as installed, source.open("rb") as admitted:
                assert hashlib.file_digest(installed, "sha256").digest() == hashlib.file_digest(admitted, "sha256").digest()
        else:
            shutil.copyfile(source, target)
            target.chmod(0o500)
            created_files.append(target)

    try:
        ensure_directory(state.parent)
        install(Path(binaries[engine]), binary)
        for name in ("device_revocation_barrier.py", "transport_runtime_transaction.py"):
            install(ROOT / "ansible/roles/runtime-release/files" / name, helper.parent / name)
        if engine == "naive":
            install(ROOT / "ansible/roles/naive/files/naive_activate.py", Path("/usr/local/libexec/vpn-naive-activate.py"))
        directory.mkdir(mode=0o700)
        config = directory / ("config.json" if engine == "snell" else "caddy.json")
        args = "run -c" if engine == "snell" else "run --config"
        unit_path.write_text("[Unit]\nDescription=Owned device revocation native test\n"
            "[Service]\nType=simple\nExecStartPre=/usr/bin/python3 -BEs " + str(helper) + " admit " + unit +
            "\nExecStart=" + str(binary) + " " + args + " " + str(config) +
            "\nStandardOutput=null\nStandardError=null\n[Install]\nWantedBy=multi-user.target\n")
        unit_path.chmod(0o644)
        command(["systemctl", "daemon-reload"])
        yield unit, unit_path, config, helper, state
    finally:
        if unit_path.exists():
            command(["systemctl", "stop", unit])
            assert b"MainPID=0" in command(["systemctl", "show", unit, "--property=MainPID"])
            subprocess.run(["systemctl", "disable", unit], capture_output=True, timeout=20, check=False)
            unit_path.unlink()
            command(["systemctl", "daemon-reload"])
            subprocess.run(["systemctl", "reset-failed", unit], capture_output=True, timeout=10, check=False)
        for path in (state, directory, *([naive_state] if engine == "naive" else [])):
            if path.exists():
                shutil.rmtree(path)
        for path in reversed(created_files):
            path.unlink()
        for path in reversed(created_directories):
            path.rmdir()


def barrier_call(helper, action, unit, payload, *, killed=False):
    if killed:
        # Execute real activation, then SIGKILL the controller before its barrier
        # receipt. No binary, unit state, credential result or receipt is mocked.
        source = ("import os,signal,sys;sys.path.insert(0," + repr(str(helper.parent)) + ")\n"
                  "import device_revocation_barrier as barrier\n"
                  "original=barrier.run\n"
                  "def interrupted(argv):\n"
                  " result=original(argv)\n"
                  " if argv[:2]==['systemctl','restart'] or argv[:2]==['/usr/bin/python3','/usr/local/libexec/vpn-naive-activate.py']:\n"
                  "  os.kill(os.getpid(),signal.SIGKILL)\n"
                  " return result\n"
                  "barrier.run=interrupted\nbarrier.main()\n")
        argv = ["/usr/bin/python3", "-I", "-B", "-S", "-c", source, action, unit]
    else:
        argv = ["/usr/bin/python3", "-BEs", str(helper), action, unit]
    return subprocess.run(argv, input=json.dumps(payload).encode(), capture_output=True, timeout=60, check=False)


@pytest.mark.parametrize("engine", ["snell", "naive"])
@pytest.mark.parametrize("interruption", ["after-begin", "after-publication", "after-activation"])
def test_actual_native_revocation_interruption_fences_restart_and_resumes(
    native_tools, owned_origin, monkeypatch, engine, interruption,
):
    origin, cert, key = owned_origin
    source, config = authority(), settings()
    config["vpn"] = {name: False for name in config["vpn"]}
    config["vpn"]["enable_" + engine] = True
    port = free_port()
    if engine == "snell":
        variant = next(row for row in config["snell"]["variants"] if row["id"] == "v6-default")
        variant["listen_port"] = port
        config["snell"]["variants"] = [variant]
    else:
        config["naive_bind_port"] = port
    old = selected_profiles(monkeypatch, source, config)[0]
    survivor = copy.deepcopy(old)
    if engine == "snell":
        survivor["config"]["outbounds"][0]["userkey"] = "STUB_SURVIVOR_NATIVE_KEY"
        survivor["witness"]["credential"] = "STUB_SURVIVOR_NATIVE_KEY"
    else:
        survivor["config"].update(username="survivor", password="survivor-native-password")
        survivor["witness"]["credential"] = "survivor:survivor-native-password"
    runtime = MeasuredRuntime(binaries=native_tools, ca_file=cert)
    with revocation_service(engine, native_tools) as (unit, unit_path, path, helper, state):
        if engine == "snell":
            secret = next(row for row in source["snell_secrets"]["variants"] if row["id"] == "v6-default")
            users = [*secret["users"], {"name": "survivor", "userkey": "STUB_SURVIVOR_NATIVE_KEY"}]
            server = {"log": {"disabled": True}, "inbounds": [{"type": "snell", "listen": ADDRESS,
                "listen_port": port, "version": config["snell"]["variants"][0]["server_version"],
                "mode": config["snell"]["variants"][0]["mode"],
                "psk": secret["psk"], "users": users}], "outbounds": [{"type": "direct"}]}
            before = json.dumps(server).encode()
            server["inbounds"][0]["users"] = users[-1:]
            after = json.dumps(server).encode()
        else:
            shutil.copyfile(cert, path.parent / "server.fullchain.pem")
            shutil.copyfile(key, path.parent / "server.key")
            for filename in ("server.fullchain.pem", "server.key"):
                (path.parent / filename).chmod(0o600)
            users = [*source["naive_secrets"]["clients"],
                     {"name": "survivor", "username": "survivor", "password": "survivor-native-password"}]
            values = {"naive": {"bind_port": port, "config_dir": str(path.parent), "log_dir": str(path.parent),
                       "decoy_root": str(path.parent)}, "naive_secrets": {**source["naive_secrets"],
                       "clients": users, "probe_resistance_secret": "owned-native-probe"}}
            template = ROOT / "ansible/roles/naive/templates/caddy.json.j2"
            before = render_template(template, values).encode()
            values["naive_secrets"]["clients"] = users[-1:]
            after = render_template(template, values).encode()
        path.write_bytes(before)
        path.chmod(0o600)
        for profile in (old, survivor):
            profile["witness"].update(config_path=str(path), unit=unit)
        command(["systemctl", "start", unit])
        assert_access(runtime, old, origin, "accepted")
        assert_access(runtime, survivor, origin, "accepted")
        plan = {str(unit_path): hashlib.sha256(unit_path.read_bytes()).hexdigest(),
                str(path): hashlib.sha256(after).hexdigest()}
        payload = {"authority": {"operation_id": str(uuid4()), "intent_sha256": "a" * 64}, "plan": plan}
        if engine == "naive":
            for filename in ("server.fullchain.pem", "server.key"):
                plan[str(path.parent / filename)] = hashlib.sha256((path.parent / filename).read_bytes()).hexdigest()
            payload["activation"] = {"server_name": "localhost", "port": port}
        assert barrier_call(helper, "begin", unit, payload).returncode == 0
        if interruption != "after-begin":
            path.write_bytes(after)
        if interruption == "after-activation":
            assert barrier_call(helper, "activate", unit, payload, killed=True).returncode == -9
            assert_access(runtime, old, origin, "denied")
            assert_access(runtime, survivor, origin, "accepted")
        fence = json.loads((state / "revocation.json").read_bytes())
        assert fence["receipt"] is None
        # A fresh unattended start cannot reactivate even the retained old file.
        command(["systemctl", "stop", unit])
        restarted = subprocess.run(["systemctl", "start", unit], capture_output=True, timeout=20, check=False)
        assert restarted.returncode != 0
        assert b"MainPID=0" in command(["systemctl", "show", unit, "--property=MainPID"])
        probe = worker.run_request(request([old], origin.url), runtime=runtime)
        assert probe["control"] == "passed" and probe["cleanup"] == "confirmed"
        assert probe["profiles"][0]["state"] != "accepted"
        changed = copy.deepcopy(payload)
        changed["authority"]["operation_id"] = str(uuid4())
        assert barrier_call(helper, "begin", unit, changed).returncode != 0
        assert barrier_call(helper, "guard", unit, {}).returncode != 0
        path.write_bytes(after)
        command(["systemctl", "reset-failed", unit])
        resumed = barrier_call(helper, "activate", unit, payload)
        assert resumed.returncode == 0, "native revocation resume failed"
        assert json.loads((state / "revocation.json").read_bytes())["receipt"] is not None
        assert_access(runtime, old, origin, "denied")
        assert_access(runtime, survivor, origin, "accepted")
        assert json.loads(barrier_call(helper, "activate", unit, payload).stdout) == {"changed": False}
        command(["systemctl", "restart", unit])
        assert_access(runtime, old, origin, "denied")
        assert_access(runtime, survivor, origin, "accepted")


def test_actual_awg_issued_peer_revoked_peer_and_ambiguous_controls(native_tools, owned_origin, tmp_path, monkeypatch):
    origin, cert, _ = owned_origin
    source, config = authority(), settings()
    config["vpn"] = {name: False for name in config["vpn"]}
    config["vpn"]["enable_amneziawg"] = True
    instance = source["amneziawg_secrets"]["instances"][0]
    instance["name"] = "dps" + uuid4().hex[:10]
    source["client_registry"]["device0"]["awg_binding"]["instance"] = instance["name"]
    instance["listen_port"] = free_port(socket.SOCK_DGRAM)
    profile = selected_profiles(monkeypatch, source, config)[0]
    interface = instance["name"]
    peer = instance["peers"][0]
    config_path = tmp_path / (interface + ".conf")
    lines = ["[Interface]", "PrivateKey = " + instance["server_private_key"], "ListenPort = " + str(instance["listen_port"])]
    lines += [name.capitalize() + " = " + str(instance[name]) for name in ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4")]
    lines += ["[Peer]", "PublicKey = " + peer["public_key"], "PresharedKey = " + peer["preshared_key"],
              "AllowedIPs = " + ", ".join(peer["allowed_ips"].values())]
    config_path.write_text("\n".join(lines) + "\n")
    config_path.chmod(0o600)
    # A direct real foreground TUN owner is registered with systemd. The worker
    # still creates its independent client TUN and namespace for every attempt.
    with service(native_tools["awg-go"], ["-f"], Path(interface), cert) as unit:
        deadline = time.monotonic() + 5
        while subprocess.run(["ip", "link", "show", interface], capture_output=True).returncode:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        command([native_tools["awg"], "setconf", interface, config_path])
        for name in ("address_v4", "address_v6"):
            command(["ip", "address", "add", instance[name], "dev", interface])
        command(["ip", "link", "set", interface, "up"])
        profile["witness"].update(config_path=str(config_path), unit=unit)
        runtime = MeasuredRuntime(binaries=native_tools, ca_file=cert, namespace_root=tmp_path / "netns")
        # ip-netns consumes /etc/netns; use the real owned namespace resolver
        # location rather than an injected fixture path for native traffic.
        runtime.namespace_root = Path("/etc/netns")
        assert assert_access(runtime, profile, origin, "accepted")["fresh_handshake"]
        command([native_tools["awg"], "set", interface, "peer", peer["public_key"], "remove"])
        denied = assert_access(runtime, profile, origin, "denied")
        assert not denied["fresh_handshake"]
        broken = request([profile], origin.url)
        broken["control"]["body_sha256"] = "0" * 64
        assert worker.run_request(broken, runtime=runtime)["profiles"][0]["state"] == "unknown"
        command([native_tools["awg"], "setconf", interface, config_path])
        # Retained old authority must be observed accepted, never denied by a
        # synthetic local removal document or an earlier failed attempt.
        assert_access(runtime, profile, origin, "accepted")
        wrong = copy.deepcopy(profile)
        wrong["config"]["text"] = wrong["config"]["text"].replace(
            source["client_registry"]["device0"]["awg_private_key"],
            source["client_registry"]["device1"]["awg_private_key"])
        retained = worker.run_request(request([wrong], origin.url), runtime=runtime)
        assert retained["profiles"][0]["state"] == "unknown" and not retained["profiles"][0]["peer_absent"]
        command(["systemctl", "stop", unit])
        assert worker.run_request(request([profile], origin.url), runtime=runtime)["profiles"][0]["state"] == "unknown"
    assert subprocess.run(["ip", "link", "show", interface], capture_output=True).returncode == 1
