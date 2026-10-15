"""Positive ECH wire/traffic and failures with actual released recipient engines."""

from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import socketserver
import subprocess
import threading
import time

import pytest
import yaml
from hysteria_ech import generate
from template_render import merge_render_vars, render_template
from test_emit_singbox_roundtrip import _secrets_as_json, _build_env, SCRIPT

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "ech_native_lab", ROOT / "tests/integration/hysteria_ech.py"
)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
pytestmark = pytest.mark.native_runtime


@pytest.fixture(scope="module")
def runtimes(pytestconfig):
    return lab.binaries(Path(str(pytestconfig.cache.makedir("hysteria-ech-artifacts"))))


@pytest.mark.parametrize(
    "profile", ["bandwidth-capped", "bbr-conservative", "bbr-standard"]
)
def test_actual_ech_clients_traffic_privacy_trust_and_resources(
    tmp_path, runtimes, profile
):
    baseline = merge_render_vars()
    with lab.socket_ceilings(
        baseline["baseline_udp_receive_buffer_max"], baseline["baseline_udp_send_buffer_max"]
    ) as socket_ceilings, lab.namespace(), ExitStack() as resources:

        def receive_errors():
            rows = Path("/proc/net/snmp").read_text().splitlines()
            for index, row in enumerate(rows[:-1]):
                if row.startswith("Udp:") and "RcvbufErrors" in row:
                    return int(
                        dict(zip(row.split()[1:], rows[index + 1].split()[1:]))[
                            "RcvbufErrors"
                        ]
                    )
            raise AssertionError("UDP-drop-observation-unavailable")

        initial_drops = receive_errors()
        payload = b"native-authenticated-payload-" * 32768

        class HTTP(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.recv(4096)
                self.request.sendall(
                    b"HTTP/1.0 200 OK\r\nContent-Length: "
                    + str(len(payload)).encode()
                    + b"\r\n\r\n"
                    + payload
                )

        class UDP(socketserver.BaseRequestHandler):
            def handle(self):
                packet, sock = self.request
                # Exercise a real DNS question/answer boundary in addition to arbitrary UDP.
                response = (
                    packet[:2] + b"\x81\x80" + packet[4:]
                    if len(packet) >= 12 and packet[2:4] == b"\x01\x00"
                    else packet
                )
                sock.sendto(response, self.client_address)

        http = socketserver.ThreadingTCPServer(("127.0.0.1", 0), HTTP)
        udp = socketserver.ThreadingUDPServer(("127.0.0.1", 0), UDP)
        for server in (http, udp):
            thread = threading.Thread(target=server.serve_forever)
            thread.start()

            def stop(server=server, thread=thread):
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                assert not thread.is_alive()

            resources.callback(stop)
        cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
        lab.command(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=inner.example",
                "-addext",
                "subjectAltName=DNS:inner.example",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ]
        )
        key.chmod(0o600)
        ech = generate(runtimes["hysteria"], "outer.example", "inner.example")
        authority = lab.private(tmp_path / "ech.key", ech["keys_pem"])
        variables = merge_render_vars()
        port = lab.free_port()
        variables["hysteria_port"] = port
        variables["hysteria"].update(
            version="v2.13.0",
            ech=ech,
            resource_profile=profile,
            cert_pem=cert.read_text(),
            key_pem=key.read_text(),
            masquerade_url="https://inner.example",
            clients=[
                {"name": "device-a", "password": "fixture-device-a-password"},
                {"name": "device-b", "password": "fixture-device-b-password"},
                {"name": "laptop", "password": "fixture-laptop-password"},
            ],
        )
        doc = yaml.safe_load(
            render_template(
                ROOT / "ansible/roles/hysteria/templates/config.yaml.j2", variables
            )
        )
        doc["tls"].update(cert=str(cert), key=str(key))
        doc["ech"]["keyPath"] = str(authority)
        server_path = lab.private(tmp_path / "server.yaml", yaml.safe_dump(doc))
        gateway = lab.private(
            tmp_path / "gateway.json",
            json.dumps(
                {
                    "inbounds": [
                        {
                            "type": "socks",
                            "listen": "127.0.0.1",
                            "listen_port": 12081,
                            "users": [
                                {
                                    "username": "normalizer-direct-hysteria",
                                    "password": variables["transport_egress_secrets"][
                                        "direct_hysteria_password"
                                    ],
                                }
                            ],
                        }
                    ],
                    "outbounds": [{"type": "direct"}],
                }
            ),
        )
        resources.enter_context(
            lab.process(
                [str(runtimes["sing_box"]), "run", "-c", str(gateway)],
                tmp_path,
                "gateway",
            )
        )
        server, server_log = resources.enter_context(
            lab.process(
                [str(runtimes["hysteria"]), "--log-level", "debug", "server", "-c", str(server_path)],
                tmp_path,
                "server",
            )
        )
        socks_ports = []
        for i, name in enumerate(("device-a", "device-b")):
            local, local_udp = (
                lab.free_port(),
                lab.free_port(socketserver.socket.SOCK_DGRAM),
            )
            client = {
                "server": "127.0.0.1:" + str(port),
                "auth": name + ":fixture-" + name + "-password",
                "tls": {
                    "sni": "inner.example",
                    "ca": str(cert),
                    "insecure": False,
                    "ech": ech["config_list"],
                },
                "tcpForwarding": [
                    {
                        "listen": "127.0.0.1:" + str(local),
                        "remote": "127.0.0.1:" + str(http.server_address[1]),
                    }
                ],
                "udpForwarding": [
                    {
                        "listen": "127.0.0.1:" + str(local_udp),
                        "remote": "127.0.0.1:" + str(udp.server_address[1]),
                    }
                ],
            }
            if profile.startswith("bbr-"):
                client["congestion"] = {"type": "bbr", "bbrProfile": profile[4:]}
            path = lab.private(tmp_path / (name + ".yaml"), yaml.safe_dump(client))
            process, log = resources.enter_context(
                lab.process(
                    [str(runtimes["hysteria"]), "--log-level", "debug", "client", "-c", str(path)],
                    tmp_path,
                    name,
                )
            )
            lab.tcp_transfer(local, payload)
            assert (
                lab.udp_transfer(local_udp, b"authenticated-udp")
                == b"authenticated-udp"
            )
            dns = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
            assert lab.udp_transfer(local_udp, dns) == dns[:2] + b"\x81\x80" + dns[4:]
            assert (
                b'"ech": true' in log.read_bytes() or b'"ech":true' in log.read_bytes()
            ), "negotiated-ech-telemetry-required"
            socks_ports.append(local)

        # Simultaneous bounded transfers measure both clients on the identical netem path.
        def measured(local):
            start = time.monotonic()
            transferred = 0
            while time.monotonic() - start < 5:
                lab.tcp_transfer(local, payload)
                transferred += len(payload)
            return transferred / (time.monotonic() - start)

        with lab.lossy_measurement(), ThreadPoolExecutor(max_workers=2) as pool:
            rates = list(pool.map(measured, socks_ports))
        assert min(rates) > 0 and max(rates) / min(rates) < 10, (
            "multi-client-fairness-regression"
        )
        for local in socks_ports:
            lab.tcp_transfer(
                local, payload
            )  # A new native stream after the concurrent transfer.
        assert receive_errors() == initial_drops, "UDP-receive-drop-regression"
        assert [int(value) for value in socket_ceilings] == [
            baseline["baseline_udp_receive_buffer_max"],
            baseline["baseline_udp_send_buffer_max"],
        ]
        status = Path("/proc", str(server.pid), "status").read_text()
        rss = int(
            next(
                line.split()[1]
                for line in status.splitlines()
                if line.startswith("VmRSS:")
            )
        )
        assert rss < 262144, "runtime-memory-budget-exceeded"
        assert len(list(Path("/proc", str(server.pid), "fd").iterdir())) < 1024
        # Parse the actual canonical emitter with the supported official recipient.
        source = _secrets_as_json(tmp_path)
        secret = json.loads(source.read_text())
        secret["hysteria"].update(variables["hysteria"])
        secret["nginx_xhttp"]["server_name"] = "inner.example"
        source.write_text(json.dumps(secret))
        emitted = subprocess.run(
            ["bash", str(SCRIPT), "laptop"],
            env=_build_env(tmp_path, source),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert emitted.returncode == 0
        full = json.loads(emitted.stdout)
        outbound = next(x for x in full["outbounds"] if x["type"] == "hysteria2")
        outbound.update(server="127.0.0.1", server_port=port)
        outbound.pop("server_ports", None)
        outbound.pop("hop_interval", None)
        outbound["tls"]["certificate"] = [cert.read_text()]
        local = lab.free_port()
        # Keep complete emitted canonical profile for actual parser validation.
        complete = lab.private(tmp_path / "complete.json", json.dumps(full))
        lab.command([str(runtimes["sing_box"]), "check", "-c", str(complete)])
        official_udp = lab.free_port(socketserver.socket.SOCK_DGRAM)
        recipient = {
            "inbounds": [
                {
                    "type": "direct",
                    "listen": "127.0.0.1",
                    "listen_port": local,
                    "override_address": "127.0.0.1",
                    "override_port": http.server_address[1],
                    "network": "tcp",
                },
                {
                    "type": "direct",
                    "listen": "127.0.0.1",
                    "listen_port": official_udp,
                    "override_address": "127.0.0.1",
                    "override_port": udp.server_address[1],
                    "network": "udp",
                },
            ],
            "outbounds": [outbound],
        }
        path = lab.private(tmp_path / "recipient.json", json.dumps(recipient))
        capture = tmp_path / "handshake.pcap"
        lab.private(capture, "")
        cap, _ = resources.enter_context(
            lab.process(
                [
                    "tcpdump",
                    "-Z",
                    "root",
                    "-i",
                    "lo",
                    "-U",
                    "-w",
                    str(capture),
                    "udp",
                    "port",
                    str(port),
                ],
                tmp_path,
                "capture",
            )
        )
        time.sleep(0.2)
        assert cap.poll() is None
        resources.enter_context(
            lab.process(
                [str(runtimes["sing_box"]), "run", "-c", str(path)],
                tmp_path,
                "recipient",
            )
        )
        lab.tcp_transfer(local, payload)
        assert (
            lab.udp_transfer(official_udp, b"official-recipient-udp")
            == b"official-recipient-udp"
        )
        assert lab.udp_transfer(official_udp, dns) == dns[:2] + b"\x81\x80" + dns[4:]
        bare = dict(doc)
        bare.pop("ech")
        bare_port = lab.free_port()
        bare["listen"] = ":" + str(bare_port)
        bare_path = lab.private(tmp_path / "server-no-ech.yaml", yaml.safe_dump(bare))
        resources.enter_context(
            lab.process(
                [str(runtimes["hysteria"]), "--log-level", "debug", "server", "-c", str(bare_path)],
                tmp_path,
                "server-no-ech",
            )
        )
        # Every bad identity, trust, credential and generation fails actual forwarding.
        for label in (
            "wrong-san",
            "untrusted",
            "stale-config",
            "wrong-auth",
            "ech-disabled",
        ):
            bad = json.loads(json.dumps(recipient))
            bad["inbounds"][0]["listen_port"] = lab.free_port()
            bad["inbounds"][1]["listen_port"] = lab.free_port(
                socketserver.socket.SOCK_DGRAM
            )
            target = bad["outbounds"][0]
            if label == "wrong-san":
                target["tls"]["server_name"] = "wrong.example"
            elif label == "untrusted":
                target["tls"].pop("certificate")
            elif label == "wrong-auth":
                target["password"] = "wrong:password"
            elif label == "ech-disabled":
                target["server_port"] = bare_port
            else:
                fresh = generate(runtimes["hysteria"], "outer.example", "inner.example")
                target["tls"]["ech"]["config"][1] = fresh["config_list"]
            path = lab.private(tmp_path / (label + ".json"), json.dumps(bad))
            with lab.process(
                [str(runtimes["sing_box"]), "run", "-c", str(path)], tmp_path, label
            ) as (bad_process, _bad_log):
                time.sleep(0.15)
                assert bad_process.poll() is None, "negative-recipient-start-required"
                with pytest.raises(AssertionError, match="authenticated-tcp"):
                    lab.tcp_transfer(
                        bad["inbounds"][0]["listen_port"], payload, timeout=1
                    )
        cap.terminate()
        cap.wait(timeout=5)
        names = lab.command(
            [
                "tshark",
                "-r",
                str(capture),
                "-d",
                "udp.port==" + str(port) + ",quic",
                "-Y",
                "tls.handshake.type == 1",
                "-T",
                "fields",
                "-e",
                "tls.handshake.extensions_server_name",
            ]
        ).decode()
        assert "outer.example" in names and "inner.example" not in names, (
            "encrypted-clienthello-wire-proof-required"
        )
        logs = (
            b"".join(path.read_bytes() for path in tmp_path.glob("*.log"))
            + emitted.stdout.encode()
            + emitted.stderr.encode()
        )
        assert (
            b"ECH KEYS" not in logs
            and authority.read_text().splitlines()[1].encode() not in logs
        )
        # Metrics are observed results, never a claim of improvement over the other modes.
        print(
            json.dumps(
                {
                    "profile": profile,
                    "tcp_bytes_per_second": rates,
                    "rss_kib": rss,
                    "transfer_seconds": [len(payload) / rate for rate in rates],
                    "udp_receive_drops": receive_errors() - initial_drops,
                    "socket_ceilings": [int(value) for value in socket_ceilings],
                    "packet_outer_sni": True,
                }
            )
        )
