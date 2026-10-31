"""Owned disconnected native fixture; never registers a vendor or reads inventory."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import yaml

from scripts.template_render import merge_render_vars, render_template
from transport_egress_config import build

ROOT = Path(__file__).resolve().parents[3]
AREA = Path(__file__).resolve().parent


def command(argv, timeout=20):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError("owned-native-command-failed")
    return result.stdout


class NativeStack:
    def __init__(self):
        self.token = "tdf" + secrets.token_hex(4)
        self.namespace = self.token
        self.library = Path("/usr/local/libexec") / self.token
        self.state = Path("/var/lib") / self.token
        self.users = {key: self.token + key for key in ("n", "g", "x", "h")}
        self.units = []
        self.created_users = []
        self.processes = []
        self.client_count = 0
        self.created_namespace = False
        self.unit_files = []
        self.xray = shutil.which("xray")
        self.hysteria = shutil.which("hysteria")
        self.assets = next((path for path in (Path("/usr/local/share/xray"), Path("/opt/artifacts/xray"),
                                              Path(self.xray).resolve().parent)
                            if (path / "geoip.dat").is_file()), None)
        if self.assets is None:
            raise RuntimeError("native-xray-assets-unavailable")

    def file(self, name, value, group=None):
        path = self.library / name
        fd, temporary = tempfile.mkstemp(prefix=".owned-config-", dir=self.library)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(value)
                stream.flush()
                if group:
                    os.fchown(stream.fileno(), 0, self.gids[group])
                os.fchmod(stream.fileno(), 0o640 if group else 0o600)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path

    def unit(self, name, argv, user=None, properties=()):
        unit = self.token + "-" + name
        # A real unit file expands %d exactly like the deployed unit. The
        # transient systemd-run command deliberately escapes argument specifiers.
        path = Path("/etc/systemd/system") / (unit + ".service")
        lines = ["[Unit]", "Description=Owned native transport fixture", "[Service]", "Type=simple",
                 "NetworkNamespacePath=/run/netns/" + self.namespace,
                 "Environment=XRAY_LOCATION_ASSET=" + str(self.assets),
                 "Environment=XRAY_RUNTIME_BINARY=" + self.xray]
        if user:
            lines.append("User=" + self.users[user])
        lines.extend(properties)
        lines.append("ExecStart=" + " ".join(shlex.quote(argument) for argument in argv))
        with path.open("x") as stream:
            stream.write("\n".join(lines) + "\n")
        path.chmod(0o644)
        self.unit_files.append(path)
        command(["systemctl", "daemon-reload"])
        # Retain ownership before a start acknowledgement can fail or time out.
        self.units.append(unit)
        command(["systemctl", "start", unit])
        return unit

    def start(self, common=False, peer_source=None):
        # A fresh disposable host may lack the shared parent; never rely on an earlier suite creating it.
        self.library.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        self.library.mkdir(mode=0o755)
        self.library.chmod(0o755)
        binary = self.library / "xray"
        shutil.copyfile(self.xray, binary)
        binary.chmod(0o555)
        assert hashlib.sha256(binary.read_bytes()).digest() == hashlib.sha256(Path(self.xray).read_bytes()).digest()
        self.xray = str(binary)
        assets = self.library / "assets"
        assets.mkdir(mode=0o755)
        assets.chmod(0o755)
        for name in ("geoip.dat", "geosite.dat"):
            source = self.assets / name
            if source.is_file():
                target = assets / name
                shutil.copyfile(source, target)
                target.chmod(0o444)
                assert hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(source.read_bytes()).digest()
        assets.chmod(0o555)
        self.assets = assets
        if self.hysteria:
            # The verified fixture cache may have root-private ancestors.
            # Copy the exact bytes into this owned executable directory.
            target = self.library / "hysteria"
            shutil.copyfile(self.hysteria, target);target.chmod(0o555)
            architecture = "arm64" if os.uname().machine == "aarch64" else "amd64"
            expected = json.loads((ROOT / "scripts/hysteria-runtimes.json").read_text())[
                "hysteria"]["sha256"]["linux-" + architecture]
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise RuntimeError("native-hysteria-digest-mismatch")
            self.hysteria = str(target)
        self.state.mkdir(mode=0o700)
        self.driver_state = Path("/run") / (self.token + "-driver")
        self.driver_state.mkdir(mode=0o700)
        self.uids, self.gids = {}, {}
        for key, user in self.users.items():
            command(["useradd", "--system", "--no-create-home", "--user-group", user])
            self.created_users.append(user)
            self.uids[key] = int(command(["id", "-u", user]).strip())
            self.gids[key] = int(command(["id", "-g", user]).strip())
        os.chown(self.driver_state, self.uids["x"], self.gids["x"])
        command(["ip", "netns", "add", self.namespace])
        self.created_namespace = True
        command(["ip", "-n", self.namespace, "link", "set", "lo", "up"])
        for address in ("192.0.2.53/32", "192.0.2.80/32", "192.0.2.81/32", "192.0.2.90/32", "2001:db8::80/128"):
            command(["ip", "-n", self.namespace, "address", "add", address, "dev", "lo"])
        links = command(["ip", "-n", self.namespace, "-json", "link", "show"])
        assert {item["ifname"] for item in json.loads(links)} == {"lo"}
        for name in ("transport_destination_policy.py", "transport_socks.py", "transport_egress_normalizer.py", "transport_private_authority.py"):
            shutil.copyfile(ROOT / "scripts" / name, self.library / name)
            (self.library / name).chmod(0o644)
        peer_path = AREA / "peer.py"
        if peer_source is not None:
            peer_path = self.library / "peer.py"
            peer_path.write_text(peer_source);peer_path.chmod(0o644)
        self.processes.append(subprocess.Popen(["ip", "netns", "exec", self.namespace, sys.executable,
                                               str(peer_path), str(self.driver_state)],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        secret_values = {name + "_password": "synthetic " + name + " authority " + secrets.token_hex(16)
                         for name in ("direct_xray", "direct_hysteria", "direct_gateway", "warp_xray", "warp_gateway")}
        context = {"vpn": {"enable_xray_reality": True, "enable_nginx_xhttp": True,
                             "enable_hysteria": not common, "enable_warp_outbound": False},
                   "secrets": secret_values, "normalizer_uid": self.uids["n"], "gateway_uid": self.uids["g"],
                   "frontend_uids": {"xray": self.uids["x"], "hysteria": self.uids["h"]},
                   "owned_addresses": ["192.0.2.90"], "management_tcp_ports": [22, 10086], "management_udp_ports": []}
        built = build(context)
        value, projection = built["normalizer"], built["policy"]
        value["resolver"]["nameservers"] = projection["resolver"]["nameservers"] = ["192.0.2.53"]
        if common:
            value["limits"]["max_associations"] = 2
            value["listeners"][0]["udp_port_max"] = projection["listeners"][0]["udp_port_max"] = 13001
            value["backends"]["direct"]["udp_source_port_max"] = projection["backends"]["direct"]["udp_source_port_max"] = 16001
            value["resolver"]["lookup_timeout_seconds"] = 1
        kernel = ("import json,pathlib,sys;sys.path.insert(0,sys.argv[1]+'/scripts');"
                  "import transport_egress_kernel as k;k.STATE=pathlib.Path(sys.argv[2]);"
                  "p=json.load(sys.stdin);k.run('apply',p);k.run('verify',p)")
        result = subprocess.run(["ip", "netns", "exec", self.namespace, sys.executable, "-c", kernel, str(ROOT), str(self.state)],
                                input=json.dumps(projection), text=True, capture_output=True, timeout=20)
        assert result.returncode == 0, "production-kernel-projection-rejected"
        private = self.state / "config.json"
        private.write_text(json.dumps(value));private.chmod(0o600)
        resolver = value["resolver"]
        for name, body in (("resolv.conf", f"nameserver 192.0.2.53\noptions timeout:{resolver['timeout_seconds']} attempts:{resolver['attempts']}\n"),
                           ("nsswitch.conf", "hosts: dns\n"), ("hosts", "")):
            (self.state / name).write_text(body);(self.state / name).chmod(0o644)
        backend = value["backends"]["direct"]
        gateway = {"log": {"loglevel": "none"}, "inbounds": [{"listen": "127.0.0.1", "port": 12090,
                   "protocol": "socks", "settings": {"auth": "password", "udp": True,
                   "accounts": [{"user": backend["username"], "pass": backend["password"]}]}}],
                   "outbounds": [{"protocol": "freedom", "settings": {"domainStrategy": "ForceIP"}}]}
        path = self.file("gateway.json", json.dumps(gateway), "g")
        command([self.xray, "run", "-test", "-config", str(path)])
        self.unit("gateway", [self.xray, "run", "-config", str(path)], "g")
        properties = ["RestrictAddressFamilies=AF_INET AF_INET6", "NoNewPrivileges=yes",
                      "UnsetEnvironment=LOCALDOMAIN RES_OPTIONS HOSTALIASES PYTHONPATH PYTHONHOME",
                      "LoadCredential=config:" + str(private)]
        properties += [f"BindReadOnlyPaths={self.state / name}:/etc/{name}" for name in ("resolv.conf", "nsswitch.conf", "hosts")]
        normalizer = self.unit("normalizer", [sys.executable, "-Es", str(self.library / "transport_egress_normalizer.py"),
                                               "--config", "%d/config"], "n", properties)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if "normalizer-ready" in command(["journalctl", "--unit", normalizer, "--no-pager", "-o", "cat"]):
                break
            time.sleep(.2)
        else:
            lines = command(["journalctl", "--unit", normalizer, "--no-pager", "-o", "cat"]).splitlines()
            categories = [line for line in lines if line.startswith("normalizer-unavailable")]
            raise RuntimeError("sealed-normalizer-unavailable:" + ",".join(categories))
        self.config = value
        self.policy = projection
        self.cert = self.library / "certificate.pem"
        self.key = self.library / "private.pem"
        command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(self.key),
                 "-out", str(self.cert), "-days", "2", "-subj", "/CN=owned.example",
                 "-addext", "subjectAltName=DNS:owned.example,DNS:alternate.example", "-addext", "basicConstraints=critical,CA:TRUE"])
        self.cert.chmod(0o644)
        self.key.chmod(0o640);os.chown(self.key, 0, self.gids["h"])
        self.values = merge_render_vars()
        self.values["transport_egress_secrets"] = secret_values
        # The lab reads peer attribution and rotation from the access log, which
        # production renders as `none` unless the policy rate-limiter consumes it.
        self.values.update(xray_runtime_binary=self.xray, xray_runtime_bundled_asset_dir=str(self.assets),
                           xray_asset_dir=str(self.assets), xray_access_log_enabled=True)
        self.uuid = str(uuid.uuid4())
        self.short = secrets.token_hex(8)
        self.hys_password = "synthetic-native-hysteria-secret-" + secrets.token_hex(12)

    def start_frontend(self, profile, *, primary_port=8443, path="/native-sync", fallback=False, cohorts=None, fallback_hostname="owned.example", xhttp_mode="auto"):
        values = self.values
        values["vpn"].update(enable_xray_reality=profile == "p0", enable_nginx_xhttp=profile == "p1",
                              enable_warp_outbound=False, enable_cascade_ingress=False)
        logs = self.library / "logs"
        logs.mkdir(mode=0o750)
        command([sys.executable, str(ROOT / "ansible/roles/xray/files/xray_log_setup.py"),
                 "--directory", str(logs), "--user", self.users["x"], "--group", self.users["x"]])
        self.diagnostic_logs = {"frontend": logs / "error.log"}
        values.update(xray_port=443, xray_fallback_port=0, xray_api_listen="127.0.0.1:10086",
                      xray_log_path=str(logs), xray_log_dir=str(logs), nginx_xhttp_port=10085,
                      nginx_xhttp_public_port=primary_port, xray_block_quic_outbound=False)
        pair = command([self.xray, "x25519"])
        fields = {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in pair.splitlines() if ":" in line}
        assert "PrivateKey" in fields and "Password (PublicKey)" in fields
        self.reality_password = fields["Password (PublicKey)"]
        values["xray"].update(target="192.0.2.90:8444", server_names=["owned.example"], reality_private_key=fields["PrivateKey"],
                              clients=[{"name": "native-device", "uuid": self.uuid, "short_id": self.short}],
                              cohorts=cohorts or [], xhttp_path=path, xhttp_mode=xhttp_mode)
        if profile in ("p0", "p1"):
            path = self.file("frontend.json", render_template(ROOT / "ansible/roles/xray/templates/config.json.j2", values), "x")
            listener = next(item for item in self.config["listeners"] if item["name"] == "direct_xray")
            server = next(item for item in json.loads(path.read_text())["outbounds"] if item["tag"] == "direct")["settings"]["servers"][0]
            authority = {"address": server["address"] == listener["address"], "port": server["port"] == listener["port"],
                         "username": server["users"][0]["user"] == listener["username"],
                         "password": server["users"][0]["pass"] == listener["password"],
                         "frontend_uid": listener["frontend_uid"] == self.uids["x"]}
            normalizer_pid = int(command(["systemctl", "show", self.token + "-normalizer", "--property=MainPID", "--value"]).strip())
            private = Path("/proc") / str(normalizer_pid) / "root/run/credentials" / (self.token + "-normalizer.service") / "config"
            authority["running_normalizer_config"] = json.loads(private.read_text()) == self.config
            assert all(authority.values()), "native-outbound-authority-mismatch:" + json.dumps(authority, sort_keys=True)
            command(["env", "XRAY_LOCATION_ASSET=" + str(self.assets), self.xray, "run", "-test", "-config", str(path)])
            self.unit("frontend", [self.xray, "run", "-config", str(path)], "x",
                      ("AmbientCapabilities=CAP_NET_BIND_SERVICE", "CapabilityBoundingSet=CAP_NET_BIND_SERVICE"))
        if profile == "p0":
            self.unit("target", ["openssl", "s_server", "-accept", "192.0.2.90:8444", "-tls1_3", "-alpn", "h2",
                                  "-cert", str(self.cert), "-key", str(self.key), "-quiet"])
        elif profile == "p1":
            values["nginx_xhttp"].update(server_name="owned.example", fallback_enabled=fallback)
            if fallback_hostname != "owned.example":
                values["nginx_xhttp"].update(fallback_server_name=fallback_hostname,
                                           fallback_cert_pem=self.cert.read_text(), fallback_key_pem=self.key.read_text())
            values["public_site_canonical_url"] = "https://owned.example" + ("" if primary_port == 443 else ":" + str(primary_port))
            self.ingress = self.library / "ingress"
            self.ingress.mkdir(mode=0o755);self.ingress.chmod(0o755)
            self.site = self.ingress / "site"
            shutil.copytree(ROOT / "ansible/roles/nginx-xhttp/files/public-site", self.site)
            for item in [self.site, *self.site.rglob("*")]:
                item.chmod(0o755 if item.is_dir() else 0o644)
            for template in (ROOT / "ansible/roles/nginx-xhttp/templates/public-site").glob("*.j2"):
                if template.name.startswith("_"):
                    continue
                target = self.site / template.name.removesuffix(".j2")
                target.write_text(render_template(template, values));target.chmod(0o644)
            for name, source in (("certificate.pem", self.cert), ("private.pem", self.key)):
                shutil.copyfile(source, self.ingress / name)
                (self.ingress / name).chmod(0o644 if name == "certificate.pem" else 0o600)
            body = render_template(ROOT / "ansible/roles/nginx-xhttp/templates/site.conf.j2", values)
            body = body.replace("/etc/nginx/tls/owned.example.fullchain.pem", str(self.ingress / "certificate.pem")).replace(
                "/etc/nginx/tls/owned.example.key", str(self.ingress / "private.pem")).replace("/var/log/nginx/", str(self.library) + "/")
            body = body.replace("/etc/nginx/tls/" + fallback_hostname + ".fullchain.pem", str(self.ingress / "certificate.pem"))
            body = body.replace("/etc/nginx/tls/" + fallback_hostname + ".key", str(self.ingress / "private.pem"))
            body = body.replace("/var/www/public-site", str(self.site))
            nginx = self.ingress / "nginx.conf"
            nginx.write_text("worker_processes 1;\npid " + str(self.library / "nginx.pid") +
                             ";\nevents { worker_connections 128; }\nhttp {\n" + body + "\n}\n")
            nginx.chmod(0o600)
            self.nginx_config = nginx
            command(["nginx", "-t", "-c", str(nginx), "-p", str(self.library)])
            self.unit("nginx", ["nginx", "-c", str(nginx), "-p", str(self.library), "-g", "daemon off;"],
                      properties=("ExecReload=/bin/kill -HUP $MAINPID",))
        else:
            self.start_hysteria()

    def start_hysteria(self, *, masquerade_origin="https://owned.example", hosts=None, salamander=False):
        values = self.values
        values["hysteria"].update(clients=[{"name": "native-device", "password": self.hys_password}],
                                  masquerade_type="proxy", masquerade_url=masquerade_origin,
                                  salamander_enabled=salamander, salamander_password="synthetic-native-salamander-authority")
        values.update(hysteria_port=443, hysteria_config_dir=str(self.library))
        shutil.copyfile(self.cert, self.library / "server.fullchain.pem")
        shutil.copyfile(self.key, self.library / "server.key")
        for name in ("server.fullchain.pem", "server.key"):
            (self.library / name).chmod(0o640);os.chown(self.library / name, 0, self.gids["h"])
        path = self.file("hysteria-server.yaml", render_template(ROOT / "ansible/roles/hysteria/templates/config.yaml.j2", values), "h")
        properties = ["AmbientCapabilities=CAP_NET_BIND_SERVICE", "CapabilityBoundingSet=CAP_NET_BIND_SERVICE"]
        if hosts:
            properties += ["BindReadOnlyPaths=" + str(hosts) + ":/etc/hosts", "Environment=SSL_CERT_FILE=" + str(self.cert)]
        self.unit("hysteria", [self.hysteria, "server", "--config", str(path)], "h",
                  properties)

    def start_client(self, profile, invalid=False, *, endpoint_port=None, headers=None, source_address=None, outbound=None):
        port = 18180 + self.client_count
        self.client_count += 1
        suffix = ("invalid" if invalid else "valid") + "-" + str(self.client_count)
        if profile in ("p0", "p1"):
            user = {"id": str(uuid.uuid4()) if invalid else self.uuid, "encryption": "none"}
            if profile == "p0":
                user["flow"] = "xtls-rprx-vision"
                stream = {"network": "raw", "security": "reality", "realitySettings": {
                          "serverName": "owned.example", "fingerprint": "chrome", "password": self.reality_password,
                          "shortId": self.short}}
            else:
                stream = {"network": "xhttp", "security": "tls", "tlsSettings": {"serverName": "owned.example",
                          "allowInsecure": False, "certificates": [{"certificateFile": str(self.cert), "usage": "verify"}]},
                          "xhttpSettings": {"host": "owned.example", "path": self.values["xray"]["xhttp_path"], "mode": "auto"}}
                if headers:
                    stream["xhttpSettings"]["headers"] = headers
            logs = self.library / ("client-logs-" + suffix)
            logs.mkdir(mode=0o750)
            command([sys.executable, str(ROOT / "ansible/roles/xray/files/xray_log_setup.py"),
                     "--directory", str(logs), "--user", self.users["x"], "--group", self.users["x"]])
            self.diagnostic_logs["client-" + suffix] = logs / "error.log"
            document = {"log": {"loglevel": "warning", "error": str(logs / "error.log")}, "inbounds": [{"listen": "127.0.0.1", "port": port,
                        "protocol": "socks", "settings": {"udp": True}}],
                        "outbounds": [{"protocol": "vless", "settings": {"vnext": [{"address": "192.0.2.90",
                        "port": 443 if profile == "p0" else (endpoint_port or self.values["nginx_xhttp_public_port"]), "users": [user]}]}, "streamSettings": stream}]}
            if outbound is not None:
                document["outbounds"] = [copy.deepcopy(outbound)]
                selected = document["outbounds"][0]
                selected["streamSettings"]["tlsSettings"]["certificates"] = [
                    {"certificateFile": str(self.cert), "usage": "verify"}]
                assert selected["streamSettings"]["tlsSettings"]["allowInsecure"] is False
                if headers:
                    selected["streamSettings"]["xhttpSettings"]["headers"] = headers
                if invalid:
                    selected["settings"]["vnext"][0]["users"][0]["id"] = user["id"]
            if source_address:
                document["outbounds"][0]["sendThrough"] = source_address
            path = self.file("client-" + suffix + ".json", json.dumps(document), "x")
            command([self.xray, "run", "-test", "-config", str(path)])
            self.unit("client-" + suffix, [self.xray, "run", "-config", str(path)], "x")
        else:
            document = {"server": "192.0.2.90:443", "auth": "native-device:" + ("wrong" if invalid else self.hys_password),
                        "tls": {"sni": "owned.example", "ca": str(self.cert), "insecure": False},
                        "socks5": {"listen": "127.0.0.1:" + str(port)}}
            path = self.file("client-" + suffix + ".yaml", yaml.safe_dump(document), "h")
            self.unit("client-" + suffix, [self.hysteria, "client", "--config", str(path)], "h")
        return port

    def run_driver(self, port, negative=False, *, socket_timeout=3):
        assert 0 < socket_timeout <= self.values["watchdog"]["reality_probe_timeout"]
        result = self.driver_state / ("negative-result.json" if negative else "result.json")
        process = subprocess.Popen(["ip", "netns", "exec", self.namespace, sys.executable, str(AREA / "driver.py")],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append(process)
        process.stdin.write(json.dumps({"port": port, "result": str(result), "negative_auth": negative,
                                        "socket_timeout": socket_timeout}).encode())
        process.stdin.close()
        status = process.wait(timeout=90)
        if not result.is_file():
            raise RuntimeError("native-driver-result-unavailable")
        values = json.loads(result.read_text())
        rejected = [name for name, accepted in values.items() if not accepted]
        diagnostic = {}
        if status or rejected:
            for name, path in self.diagnostic_logs.items():
                content = path.read_text(errors="replace")[:131072] if path.is_file() else ""
                diagnostic[name] = {phrase: phrase.lower() in content.lower() for phrase in (
                    "authentication", "handshake", "rejected", "connection refused", "timeout",
                    "account", "failed to read", "failed to write", "failed to process outbound",
                    "proxy/socks", "proxy/vless", "REALITY", "TLS", "HTTP", "invalid", "EOF")}
        assert status == 0 and values and not rejected, ("native-case-rejected:" + ",".join(rejected)
                                                       + ":categories:" + json.dumps(diagnostic, sort_keys=True))
        return values

    def close(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        for unit in reversed(self.units):
            stopped = subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=15)
            observed = command(["systemctl", "show", unit, "--property=ActiveState,MainPID"]).splitlines()
            if (stopped.returncode != 0 or "MainPID=0" not in observed
                    or not ({"ActiveState=inactive", "ActiveState=failed"} & set(observed))):
                raise RuntimeError("owned-native-unit-cleanup-unconfirmed")
            subprocess.run(["systemctl", "reset-failed", unit], capture_output=True, timeout=15)
        for path in self.unit_files:
            path.unlink()
        if self.unit_files:
            command(["systemctl", "daemon-reload"])
        if self.created_namespace:
            command(["ip", "netns", "delete", self.namespace])
        for user in reversed(self.created_users):
            command(["userdel", user])
        for path in (self.library, self.state, getattr(self, "driver_state", self.state)):
            if path.exists():
                shutil.rmtree(path)
