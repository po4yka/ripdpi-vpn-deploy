"""Exact upstream acceptance in an explicitly disposable Linux runtime host.

Requires Xray plus its adjacent GeoIP, Hysteria, and the pinned AWG source trees
through AWG_NATIVE_GO_SOURCE and AWG_NATIVE_TOOLS_SOURCE. Build those sources
under the machine gate before selecting this lane; no fixture executable,
unsupported host or missing prerequisite may become a skipped success.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid

import pytest
import yaml

from template_render import merge_render_vars, render_template
from transport_semantics import awg_errors, cohort_errors, hysteria_errors

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def require_linux():
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.fail("transport native semantics require a disposable Linux root host")


def command(argv, *, data=None, env=None):
    result = subprocess.run(argv, input=data, capture_output=True, text=True,
                            env=env, timeout=20)
    if result.returncode:
        pytest.fail("exact native transport command rejected its accepted candidate")
    return result.stdout


def exact_awg_sources():
    require_linux()
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    outputs = []
    for variable, pin, artifact in (
        ("AWG_NATIVE_GO_SOURCE", "amneziawg_go_commit", "amneziawg-go"),
        ("AWG_NATIVE_TOOLS_SOURCE", "amneziawg_tools_commit", "src/wg"),
    ):
        raw = os.environ.get(variable)
        if not raw:
            pytest.fail("exact pinned AWG source fixture is unavailable")
        source = Path(raw)
        if command(["git", "-C", str(source), "rev-parse", "HEAD"]).strip() != pins[pin]:
            pytest.fail("AWG native source does not match the pinned immutable commit")
        binary = source / artifact
        if not binary.is_file() or not os.access(binary, os.X_OK):
            pytest.fail("AWG pinned native build output is unavailable")
        with binary.open("rb") as handle:
            if handle.read(4) != b"\x7fELF":
                pytest.fail("AWG native acceptance requires compiled ELF executables")
        outputs.append(binary)
    if not Path("/dev/net/tun").exists():
        pytest.fail("real AWG TUN prerequisite is unavailable")
    return outputs


def test_exact_awg_parser_accepts_host_and_explicit_routed_peers(tmp_path):
    go, tools = exact_awg_sources()
    interface = "sem" + uuid.uuid4().hex[:8]
    private = command([str(tools), "genkey"]).strip()
    client_private = command([str(tools), "genkey"]).strip()
    public = command([str(tools), "pubkey"], data=client_private).strip()
    psk = command([str(tools), "genpsk"]).strip()
    raw = {"server_private_key": private, "jc": 4, "jmin": 40, "jmax": 70,
           "s1": 50, "s2": 100, "h1": 11, "h2": 12, "h3": 13, "h4": 14,
           "peers": [{"name": "device", "public_key": public,
                      "preshared_key": psk, "allowed_ips": "10.66.66.2/32"}]}
    if awg_errors(raw, {"interface": interface}):
        pytest.fail("shared semantics refused valid generated native keys")
    process = subprocess.Popen([str(go), "-f", interface], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not Path("/run/amneziawg", interface + ".sock").exists():
            # Upstream platform IPC may use the WireGuard-compatible directory.
            if Path("/run/wireguard", interface + ".sock").exists():
                break
            if process.poll() is not None or time.monotonic() >= deadline:
                pytest.fail("exact AWG daemon did not establish its owned IPC interface")
            time.sleep(0.05)
        for kind, prefix in (("device", "10.66.66.2/32"), ("routed", "10.77.0.0/24")):
            raw["peers"][0].update(address_kind=kind, allowed_ips=prefix)
            if awg_errors(raw):
                pytest.fail("shared semantics refused a supported explicit native peer")
            config = tmp_path / "awg.conf"
            config.write_text("[Interface]\nPrivateKey = " + private + "\nListenPort = 51999\n" +
                              "Jc = 4\nJmin = 40\nJmax = 70\nS1 = 50\nS2 = 100\nH1 = 11\nH2 = 12\nH3 = 13\nH4 = 14\n" +
                              "[Peer]\nPublicKey = " + public + "\nPresharedKey = " + psk + "\nAllowedIPs = " + prefix + "\n")
            config.chmod(0o600)
            command([str(tools), "setconf", interface, str(config)])
            observed = command([str(tools), "show", interface, "allowed-ips"])
            if prefix not in observed:
                pytest.fail("native AWG did not retain the accepted peer prefix")
    finally:
        subprocess.run(["ip", "link", "delete", interface], capture_output=True, timeout=10)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        if subprocess.run(["ip", "link", "show", interface], capture_output=True, timeout=10).returncode == 0:
            pytest.fail("native AWG owned interface cleanup is unconfirmed")


def test_exact_xray_parser_accepts_explicit_known_cohort_members(tmp_path):
    require_linux()
    executable = shutil.which("xray")
    if not executable:
        pytest.fail("exact pinned Xray runtime is unavailable")
    values = merge_render_vars()
    logs = tmp_path / "logs"
    logs.mkdir(mode=0o700)
    values["xray_log_path"] = str(logs)
    values["xray_log_dir"] = str(logs)
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    if pins["xray"]["version"].lstrip("v") not in command([executable, "version"]):
        pytest.fail("Xray native runtime is not the selected exact pin")
    pair = command([executable, "x25519"])
    private = next((line.split(":", 1)[1].strip() for line in pair.splitlines() if line.startswith("PrivateKey:")), None)
    if not private:
        pytest.fail("Xray native key generator did not return the expected contract")
    values["xray"]["reality_private_key"] = private
    values["xray"]["target"] = "owned.example:443"
    values["xray"]["server_names"] = ["owned.example"]
    values["xray"]["clients"] = [{"name": "native-device",
                                  "uuid": "00000000-0000-4000-8000-000000000001",
                                  "short_id": "0011223344556677"}]
    values["xray"]["cohorts"] = [{"name": "technical", "port": 443,
                                      "flow_mode": "vision",
                                      "clients": [values["xray"]["clients"][0]["name"]]}]
    if cohort_errors(values["xray"]):
        pytest.fail("shared cohort semantics rejected native input")
    rendered = render_template(ROOT / "ansible/roles/xray/templates/config.json.j2", values)
    config = tmp_path / "xray.json"
    config.write_text(rendered)
    config.chmod(0o600)
    assets = str(Path(executable).resolve().parent)
    if not Path(assets, "geoip.dat").is_file():
        pytest.fail("exact Xray bundled GeoIP prerequisite is unavailable")
    command([executable, "run", "-test", "-config", str(config)],
            env={**os.environ, "XRAY_LOCATION_ASSET": assets})


def test_exact_hysteria_starts_accepted_owned_proxy_candidate(tmp_path):
    require_linux()
    executable = shutil.which("hysteria")
    if not executable:
        pytest.fail("exact pinned Hysteria runtime is unavailable")
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    if pins["hysteria"]["version"].lstrip("v") not in command([executable, "version"]):
        pytest.fail("Hysteria native runtime is not the selected exact pin")
    cert, key = tmp_path / "certificate.pem", tmp_path / "private.pem"
    command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
             "-out", str(cert), "-days", "2", "-subj", "/CN=owned.example"])
    key.chmod(0o600)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    values = merge_render_vars()
    values["hysteria_config_dir"] = str(tmp_path)
    values["hysteria_port"] = port
    shutil.copyfile(cert, tmp_path / "server.fullchain.pem")
    shutil.copyfile(key, tmp_path / "server.key")
    values["hysteria"].update(masquerade_type="proxy", masquerade_url="https://owned.example",
                               clients=[{"name": "native-device", "password": "native-fixture-strong-password"}])
    if hysteria_errors(values["hysteria"], "https://owned.example"):
        pytest.fail("shared Hysteria semantics rejected owned proxy")
    config = tmp_path / "config.yaml"
    config.write_text(render_template(ROOT / "ansible/roles/hysteria/templates/config.yaml.j2", values))
    config.chmod(0o600)
    command([sys.executable, str(ROOT / "ansible/roles/runtime-release/files/validate_yaml_mapping.py"),
             "--profile", "hysteria", str(config)])
    process = subprocess.Popen([executable, "server", "-c", str(config)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while True:
            listeners = command(["ss", "-lnup"])
            if any(re.search(rf":{port}(?:\s|$)", line) and f"pid={process.pid}," in line
                   for line in listeners.splitlines()):
                if process.poll() is not None:
                    pytest.fail("Hysteria candidate exited after binding")
                break
            if process.poll() is not None or time.monotonic() >= deadline:
                pytest.fail("exact Hysteria candidate failed its native startup")
            time.sleep(0.05)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        if any(re.search(rf":{port}(?:\s|$)", line) and f"pid={process.pid}," in line
               for line in command(["ss", "-lnup"]).splitlines()):
            pytest.fail("Hysteria owned socket cleanup is unconfirmed")
