"""Field-report ingest on the subscription host (SEC-1795086333272606).

The service runs as a subprocess on loopback with the shared contract
validator, so status codes, metrics output and logs are observed directly.
"""
from __future__ import annotations

import copy
import http.client
import importlib.util
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/subscription-host"
SERVICE = ROLE / "files/vpn-field-report.py"
GOLDEN = json.loads((ROOT / "contract/client-field-report.golden.json").read_text())
TOKEN = "cohortTokenCurrent_0000000001"
PREVIOUS = "cohortTokenPrevious_000000002"
FIELD_REPORT_PATH = "/v1/field-report"


def _config(tmp_path: Path, **overrides) -> dict:
    textfile_dir = tmp_path / "textfile"
    textfile_dir.mkdir(exist_ok=True)
    config = {
        "path": FIELD_REPORT_PATH,
        "max_body_bytes": 65536,
        "min_attempts": 5,
        "max_attempts_per_report": 1000,
        "top_n_min_reports": 3,
        "asn_top_n": 20,
        "operator_top_n": 20,
        "country_top_n": 10,
        "window_seconds": 3600,
        "max_series": 400,
        "server_refs": ["p0-reality-upcloud-prod", "p2-hysteria2-upcloud-prod"],
        "textfile": str(textfile_dir / "vpn_field_report.prom"),
        "schema": str(ROOT / "contract/client-field-report.schema.json"),
        "validator": str(ROOT / "scripts/validate-field-report.py"),
    }
    config.update(overrides)
    return config


# Hands the service its listening socket as systemd does: fd 3 with LISTEN_FDS=1 and LISTEN_PID set to the
# service's own PID (exec keeps it).
SOCKET_ACTIVATION = ("import os, sys\n"
                     "fd = int(sys.argv[1])\n"
                     "if fd != 3:\n"
                     "    os.dup2(fd, 3)\n"
                     "    os.close(fd)\n"
                     "os.environ.update(LISTEN_FDS='1', LISTEN_PID=str(os.getpid()))\n"
                     "os.execv(sys.argv[2], sys.argv[2:])\n")


# The same hand-over, then the service runs in this process with every non-Unix socket refused as the unit's
# RestrictAddressFamilies=AF_UNIX seccomp filter refuses it (EAFNOSUPPORT), so creating one fails the start.
UNIX_ONLY_ACTIVATION = ("import errno, os, runpy, socket, sys\n"
                        "fd = int(sys.argv[1])\n"
                        "if fd != 3:\n"
                        "    os.dup2(fd, 3)\n"
                        "    os.close(fd)\n"
                        "os.environ.update(LISTEN_FDS='1', LISTEN_PID=str(os.getpid()))\n"
                        "class UnixOnly(socket.socket):\n"
                        "    def __init__(self, family=-1, type=-1, proto=-1, fileno=None):\n"
                        "        if fileno is None and family != socket.AF_UNIX:\n"
                        "            raise OSError(errno.EAFNOSUPPORT, 'address family not allowed')\n"
                        "        super().__init__(family, type, proto, fileno)\n"
                        "socket.socket = UnixOnly\n"
                        "sys.argv, sys.dont_write_bytecode = sys.argv[2:], True\n"
                        "runpy.run_path(sys.argv[0], run_name='__main__')\n")


def _service_command(listener: socket.socket, tmp_path: Path, activation: str = SOCKET_ACTIVATION) -> list[str]:
    launcher = [sys.executable, "-I", "-B"] if activation is SOCKET_ACTIVATION else []
    return [sys.executable, "-I", "-c", activation, str(listener.fileno()), *launcher,
            str(SERVICE), "--config", str(tmp_path / "config.json"), "--tokens", str(tmp_path / "tokens.json")]


def _write_config(tmp_path: Path, config: dict, tokens: dict | None = None) -> None:
    # port is where the tests connect; the service never binds and gets no port.
    (tmp_path / "config.json").write_text(json.dumps({key: value for key, value in config.items() if key != "port"}))
    (tmp_path / "tokens.json").write_text(json.dumps(tokens or {"current": TOKEN}))


def _tcp_listener() -> socket.socket:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    return listener


@pytest.fixture
def ingest(tmp_path):
    processes = []

    def start(tokens: dict | None = None, **overrides):
        # A loopback TCP socket stands in for the unit's Unix socket, so the HTTP helpers stay simple;
        # test_the_ingest_serves_an_inherited_unix_socket covers the real family.
        with _tcp_listener() as listener:
            config = _config(tmp_path, port=listener.getsockname()[1], **overrides)
            _write_config(tmp_path, config, tokens)
            process = subprocess.Popen(_service_command(listener, tmp_path), pass_fds=(listener.fileno(),),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(process)
        deadline = time.monotonic() + 10
        while not Path(config["textfile"]).exists():
            assert process.poll() is None, process.stderr.read()
            assert time.monotonic() < deadline
            time.sleep(0.05)
        return process, config

    yield start
    for process in processes:
        process.terminate()
        process.wait(timeout=5)


def _post(config: dict, body: bytes, token: str | None = TOKEN, length: int | None = None, path: str = FIELD_REPORT_PATH) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", config["port"], timeout=5)
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body) if length is None else length)}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    try:
        connection.request("POST", path, body=body if length is None else b"", headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


def _metrics(config: dict) -> str:
    return Path(config["textfile"]).read_text()


def _samples(text: str) -> dict[str, float]:
    return {line.rsplit(" ", 1)[0]: float(line.rsplit(" ", 1)[1]) for line in text.splitlines() if line and not line.startswith("#")}


def test_status_codes_and_only_an_accepted_report_changes_metrics(ingest):
    _, config = ingest()
    empty = _metrics(config)
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    accepted = _metrics(config)
    assert accepted != empty
    assert _samples(accepted)['vpn_field_report_attempts_total{protocol="vless-reality",network="other",country="other"}'] == 49

    extra = copy.deepcopy(GOLDEN)
    extra["device_id"] = "x"
    assert _post(config, json.dumps(extra).encode()) == 400
    assert _post(config, json.dumps(GOLDEN).encode(), token="wrongTokenValue_00000000000") == 401
    assert _post(config, b"", length=config["max_body_bytes"] + 1) == 413
    assert _post(config, b"{}", path="/other") == 404


def test_unauthenticated_requests_never_starve_a_valid_report(ingest):
    _, config = ingest()
    for _ in range(300):
        assert _post(config, json.dumps(GOLDEN).encode(), token="wrongTokenValue_00000000000") == 401
    assert _post(config, json.dumps(GOLDEN).encode()) == 202


def test_a_slow_connection_cannot_hold_the_ingest_past_its_deadline(ingest):
    _, config = ingest()
    slow = socket.create_connection(("127.0.0.1", config["port"]), timeout=5)
    try:
        # Each byte arrives well inside the per-read timeout, so only a total deadline ends this request.
        slow.sendall(b"POST ")
        started = time.monotonic()
        connection = http.client.HTTPConnection("127.0.0.1", config["port"], timeout=20)
        body = json.dumps(GOLDEN).encode()
        connection.putrequest("POST", FIELD_REPORT_PATH)
        for name, value in (("Content-Type", "application/json"), ("Content-Length", str(len(body))),
                            ("Authorization", f"Bearer {TOKEN}")):
            connection.putheader(name, value)
        connection.endheaders(body)
        for _ in range(14):
            try:
                slow.sendall(b"/")
            except OSError:
                break
            time.sleep(1)
        assert connection.getresponse().status == 202
        assert time.monotonic() - started < 12
        connection.close()
    finally:
        slow.close()


def test_the_ingest_serves_an_inherited_unix_socket(tmp_path):
    import tempfile

    # macOS limits a socket path to 104 bytes, more than pytest's tmp_path leaves.
    with tempfile.TemporaryDirectory(dir="/tmp") as short, socket.socket(socket.AF_UNIX) as listener:
        listener.bind(f"{short}/ingest.sock")
        listener.listen()
        config = _config(tmp_path)
        _write_config(tmp_path, config)
        process = subprocess.Popen(_service_command(listener, tmp_path, UNIX_ONLY_ACTIVATION),
                                   pass_fds=(listener.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(5)
                client.connect(f"{short}/ingest.sock")
                body = json.dumps(GOLDEN).encode()
                client.sendall(b"POST /v1/field-report HTTP/1.1\r\nHost: sub\r\nAuthorization: Bearer " + TOKEN.encode()
                               + b"\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
                assert client.recv(64).startswith(b"HTTP/1.0 202 ")
            assert _samples(_metrics(config))["vpn_field_report_reports_total"] == 1
        finally:
            process.terminate()
            _, stderr = process.communicate(timeout=5)
    assert stderr == ""


def test_the_ingest_refuses_to_start_without_its_socket_unit(tmp_path):
    config = _config(tmp_path)
    _write_config(tmp_path, config)
    # Run directly: no LISTEN_FDS, so there is no socket to serve and nothing may bind one.
    result = subprocess.run([sys.executable, "-I", "-B", str(SERVICE), "--config", str(tmp_path / "config.json"),
                             "--tokens", str(tmp_path / "tokens.json")], capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert result.stderr == "vpn-field-report: expected exactly one listening socket from vpn-field-report.socket\n"
    assert not Path(config["textfile"]).exists()


def test_rejections_leave_metrics_unchanged(ingest):
    _, config = ingest()
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    accepted = _metrics(config)
    bad_histogram = copy.deepcopy(GOLDEN)
    bad_histogram["buckets"][0]["latency_ms_histogram"][0] += 1
    for body, token in ((b"not json", TOKEN), (json.dumps(bad_histogram).encode(), TOKEN),
                        (json.dumps(GOLDEN).encode(), None), (json.dumps(GOLDEN).encode(), PREVIOUS)):
        assert _post(config, body, token=token) in (400, 401)
    assert _metrics(config) == accepted


def test_no_address_or_token_reaches_logs_metrics_or_state(ingest, tmp_path):
    process, config = ingest()
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    assert _post(config, b"{", token=TOKEN) == 400
    assert _post(config, json.dumps(GOLDEN).encode(), token="wrongTokenValue_00000000000") == 401
    process.terminate()
    stdout, stderr = process.communicate(timeout=5)
    textfile_dir = Path(config["textfile"]).parent
    stored = "".join(path.read_text() for path in textfile_dir.iterdir())
    for needle in ("127.0.0.1", TOKEN, "wrongTokenValue"):
        assert needle not in stdout + stderr
        assert needle not in stored
    assert [path.name for path in textfile_dir.iterdir()] == ["vpn_field_report.prom"]


def test_previous_token_is_accepted_only_during_its_overlap(ingest):
    _, config = ingest({"current": TOKEN, "previous": PREVIOUS, "previous_valid_until": "2999-01-01T00:00:00Z"})
    assert _post(config, json.dumps(GOLDEN).encode(), token=PREVIOUS) == 202
    assert _post(config, json.dumps(GOLDEN).encode(), token=TOKEN) == 202


def test_previous_token_is_rejected_after_its_overlap(ingest):
    _, config = ingest({"current": TOKEN, "previous": PREVIOUS, "previous_valid_until": "2000-01-01T00:00:00Z"})
    assert _post(config, json.dumps(GOLDEN).encode(), token=PREVIOUS) == 401
    assert _post(config, json.dumps(GOLDEN).encode(), token=TOKEN) == 202


def _bucket(attempts: int, protocol: str = "xhttp") -> dict:
    return {"server_ref": "p0-reality-upcloud-prod", "protocol": protocol, "outcome": "success", "attempts": attempts,
            "latency_ms_histogram": [attempts, 0, 0, 0, 0, 0, 0, 0]}


def test_buckets_under_the_configured_floor_are_dropped_and_counted(ingest):
    _, config = ingest(min_attempts=10)
    report = copy.deepcopy(GOLDEN)
    report["buckets"] = [_bucket(7), _bucket(10)]
    assert _post(config, json.dumps(report).encode()) == 202
    samples = _samples(_metrics(config))
    assert samples['vpn_field_report_attempts_total{protocol="xhttp",network="other",country="other"}'] == 10
    assert samples['vpn_field_report_endpoint_attempts_total{protocol="xhttp",server_ref="p0-reality-upcloud-prod"}'] == 10
    assert samples["vpn_field_report_dropped_buckets_total"] == 1
    assert samples["vpn_field_report_reports_total"] == 1


@pytest.mark.parametrize("buckets", [[_bucket(4), _bucket(5)], [_bucket(4)]], ids=["mixed", "all-under"])
def test_a_bucket_under_the_contract_floor_rejects_the_report_without_counting(ingest, buckets):
    _, config = ingest()
    before = _metrics(config)
    report = copy.deepcopy(GOLDEN)
    report["buckets"] = buckets
    assert _post(config, json.dumps(report).encode()) == 400
    assert _metrics(config) == before


@pytest.mark.parametrize("field", ["country", "server_ref", "protocol", "failure_stage"])
@pytest.mark.parametrize("suffix", ["\n", '"'])
def test_label_strings_with_a_newline_or_quote_are_rejected(ingest, field, suffix):
    _, config = ingest()
    before = _metrics(config)
    report = copy.deepcopy(GOLDEN)
    target = report["network"] if field == "country" else report["buckets"][1]
    target[field] += suffix
    assert _post(config, json.dumps(report).encode()) == 400
    assert _metrics(config) == before


def test_rendered_label_values_are_escaped(tmp_path):
    aggregate = _module().Aggregate(_config(tmp_path), [50, 100, 250, 500, 1000, 2500, 5000, "+Inf"])
    aggregate.attempts[("xhttp", "as64500", 'Z"\\\n')] = 5
    assert 'vpn_field_report_attempts_total{protocol="xhttp",network="as64500",country="Z\\"\\\\\\n"} 5' in aggregate.render()


def _module():
    spec = importlib.util.spec_from_file_location("vpn_field_report_service", SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_labels_stay_bounded_for_many_networks_and_unknown_endpoints(tmp_path):
    module = _module()
    max_series = 120
    config = _config(tmp_path, max_series=max_series)
    aggregate = module.Aggregate(config, [50, 100, 250, 500, 1000, 2500, 5000, "+Inf"])
    protocols = ["vless-reality", "xhttp", "hysteria2", "amneziawg", "naiveproxy", "local-desync"]
    for window in (0, 3600):
        # One large report: the most attempts of any network, but too few reports to earn its own label.
        report = copy.deepcopy(GOLDEN)
        report["network"] = {"source": "server_hint", "asn": 63999, "country": "ZX", "network_type": "wifi"}
        report["buckets"] = [{"server_ref": "unknown", "protocol": "xhttp", "outcome": "success", "attempts": 100000,
                              "latency_ms_histogram": [100000, 0, 0, 0, 0, 0, 0, 0]}]
        aggregate.add(report, window)
        for index in range(1000):
            report = copy.deepcopy(GOLDEN)
            report["network"] = {"source": "server_hint", "asn": 64000 + index, "country": "ZZ" if index % 2 else "ZY",
                                 "network_type": "wifi"}
            report["buckets"] = [
                {"server_ref": f"unknown-{index}", "protocol": protocols[index % 6], "outcome": "failure",
                 "failure_stage": "tcp_reset", "attempts": 5 + index, "latency_ms_histogram": [0, 0, 0, 0, 0, 0, 0, 5 + index]},
            ]
            for _ in range(3 + index % 2 if index >= 980 else 1):
                aggregate.add(copy.deepcopy(report), window + index * 0.001)
    samples = _samples(aggregate.render())
    networks = {key.split('network="')[1].split('"')[0] for key in samples if 'network="' in key}
    # The 20 networks that sent at least three reports in the first window, and "other".
    assert networks == {f"as{64000 + index}" for index in range(980, 1000)} | {"other"}
    assert {key.split('server_ref="')[1].split('"')[0] for key in samples if "server_ref=" in key} == {"other"}
    # Label-bearing counters: the budget plus one overflow set per protocol for
    # attempts, failures per stage and both endpoint families; then 6 latency
    # series of 9 samples and the two unlabelled counters.
    counters = [key for key in samples if "latency" not in key and "{" in key]
    assert len(counters) <= max_series + 6 * (1 + 11 + 2 + 1)
    assert len(samples) <= max_series + 6 * (1 + 11 + 2 + 1) + 6 * 9 + 3


SIM = {"source": "sim", "operator": {"mcc": "001", "mnc": "01"}, "network_type": "cellular"}


def test_network_label_follows_the_report_source_and_operators_rank_apart_from_asns(tmp_path):
    aggregate = _module().Aggregate(_config(tmp_path, asn_top_n=1, operator_top_n=1),
                                    [50, 100, 250, 500, 1000, 2500, 5000, "+Inf"])
    sources = [SIM, {**SIM, "operator": {"mcc": "001", "mnc": "010"}},
               {"source": "server_hint", "asn": 64500, "country": "ZZ", "network_type": "wifi"},
               {"source": "none", "network_type": "other"}]
    for window in (0, 3600):
        # Three reports from each source in each window; a three-digit MNC is a different operator.
        for index, network in enumerate(sources * 3):
            report = copy.deepcopy(GOLDEN)
            report["network"] = copy.deepcopy(network)
            aggregate.add(report, window + index)
    samples = _samples(aggregate.render())
    networks = {key.split('network="')[1].split('"')[0] for key in samples if "network_reports_total" in key}
    # One ASN and one operator earned their own label although asn_top_n and operator_top_n are both 1: the
    # rankings are separate. The other operator ties and loses on order, and a none report is "unknown".
    assert networks == {"001-01", "as64500", "other", "unknown"}
    second_window = 'vpn_field_report_network_reports_total{protocol="hysteria2",network="%s"}'
    assert samples[second_window % "001-01"] == 3
    assert samples[second_window % "unknown"] == 6
    # Only the server_hint report carries a country; the others have none to label.
    assert samples['vpn_field_report_attempts_total{protocol="hysteria2",network="001-01",country="unknown"}'] == 15
    assert samples['vpn_field_report_failures_total{protocol="hysteria2",failure_stage="quic_handshake",network="as64500"}'] == 15


def test_sim_and_none_reports_are_accepted_and_a_report_with_two_identities_is_not(ingest):
    _, config = ingest()
    for network, status in ((SIM, 202), ({"source": "none", "network_type": "wifi"}, 202),
                            ({**SIM, "asn": 64500}, 400), ({"source": "none", "asn": 64500, "network_type": "wifi"}, 400)):
        report = copy.deepcopy(GOLDEN)
        report["network"] = network
        assert _post(config, json.dumps(report).encode()) == status
    assert _samples(_metrics(config))["vpn_field_report_reports_total"] == 2


def test_one_report_adds_at_most_the_attempts_cap(tmp_path):
    aggregate = _module().Aggregate(_config(tmp_path, max_attempts_per_report=1000), [50, 100, 250, 500, 1000, 2500, 5000, "+Inf"])
    report = copy.deepcopy(GOLDEN)
    report["network"] = {"source": "server_hint", "asn": 64500, "country": "ZZ", "network_type": "wifi"}
    report["buckets"] = [
        {"server_ref": "p0-reality-upcloud-prod", "protocol": "xhttp", "outcome": "failure", "failure_stage": "tcp_reset",
         "attempts": 3000, "latency_ms_histogram": [0, 0, 0, 0, 0, 0, 0, 3000]},
        {"server_ref": "p0-reality-upcloud-prod", "protocol": "xhttp", "outcome": "success", "attempts": 1000,
         "latency_ms_histogram": [1000, 0, 0, 0, 0, 0, 0, 0]},
    ]
    aggregate.add(report, 0)
    aggregate.add(copy.deepcopy(GOLDEN), 1)
    samples = _samples(aggregate.render())
    # 4000 attempts scale by 1000/4000: 750 failures and 250 successes, in the same proportion.
    assert samples['vpn_field_report_attempts_total{protocol="xhttp",network="other",country="other"}'] == 1000
    assert samples['vpn_field_report_failures_total{protocol="xhttp",failure_stage="tcp_reset",network="other"}'] == 750
    assert samples['vpn_field_report_latency_seconds_count{protocol="xhttp"}'] == 1000
    assert samples["vpn_field_report_capped_reports_total"] == 1
    # The golden report holds 49 vless-reality attempts and stays under the cap.
    assert samples['vpn_field_report_attempts_total{protocol="vless-reality",network="other",country="other"}'] == 49
    # Each report counts once for each protocol it holds, whatever its size or bucket count.
    assert samples['vpn_field_report_network_reports_total{protocol="xhttp",network="other"}'] == 1
    assert samples['vpn_field_report_network_reports_total{protocol="vless-reality",network="other"}'] == 1
    assert samples['vpn_field_report_network_reports_total{protocol="hysteria2",network="other"}'] == 1


def _rendered(name: str, _inventory: dict | None = None, **field_report) -> str:
    spec = importlib.util.spec_from_file_location("field_report_renderer", ROOT / "scripts/check-templates-render.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    variables = {**renderer.merge_render_vars(), **(_inventory or {})}
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["subscription_field_report"]
    variables["subscription_field_report"] = {**defaults, "enabled": True, **field_report}
    return renderer.render_template(ROLE / "templates" / name, variables)


def test_nginx_location_limits_size_and_rate_and_keeps_body_in_memory():
    vhost = _rendered("subscription.conf.j2", max_body_bytes=32768)
    location = vhost.split("location = /v1/field-report {", 1)[1].split("\n    }", 1)[0]
    assert "limit_except POST { deny all; }" in location
    assert "limit_req zone=vpn_field_report_per_ip burst=20 nodelay;" in location
    assert "limit_req_status 429;" in location
    assert "client_max_body_size 32768;" in location
    assert "client_body_buffer_size 32768;" in location
    assert "access_log /var/log/nginx/vpn-sub.categorical.log vpn_sub_category;" in location
    assert "error_log /dev/null crit;" in location
    assert "remote_addr" not in location and "X-Real-IP" not in location and "X-Forwarded-For" not in location
    assert "proxy_pass http://unix:/run/vpn-field-report.sock:;" in location and "127.0.0.1" not in location
    # An unknown token or a refused method gets the vhost's uniform not-found answer, so a probe cannot tell the route exists.
    assert "proxy_intercept_errors on;\n        error_page 401 403 = @vpn_sub_not_found;" in location
    assert "location @vpn_sub_not_found {\n        return 404;\n    }" in vhost
    assert "limit_req_zone $binary_remote_addr zone=vpn_field_report_per_ip:10m rate=30r/m;" in _rendered("rate-limit.conf.j2")
    assert "field-report" not in _rendered("subscription.conf.j2", enabled=False)


def test_unit_delivers_tokens_as_credential_and_keeps_the_hardening_floor():
    unit = _rendered("vpn-field-report.service.j2")
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "LoadCredential=cohort-tokens:/etc/vpn-field-report/cohort-tokens.json" in unit
    assert "--tokens %d/cohort-tokens" in exec_start and "Environment=" not in unit
    for directive in ("User=vpn-field-report", "NoNewPrivileges=true", "ProtectSystem=strict", "PrivateTmp=true",
                      "ProtectHome=true", "ProtectKernelTunables=true", "ProtectKernelModules=true",
                      "ProtectControlGroups=true", "RestrictNamespaces=true", "LockPersonality=true",
                      "RestrictRealtime=true", "RestrictSUIDSGID=true", "SystemCallArchitectures=native",
                      "CapabilityBoundingSet=\n", "IPAddressDeny=any\n", "PrivateNetwork=true\n",
                      "RestrictAddressFamilies=AF_UNIX\n", "Requires=vpn-field-report.socket\n",
                      "StateDirectory=vpn-field-report\n", "StateDirectoryMode=0755\n", "LimitCORE=0\n"):
        assert directive in unit
    # The ingest writes only its own state directory; it is no member of the shared textfile writer group.
    assert "SupplementaryGroups=" not in unit and "ReadWritePaths=" not in unit and "IPAddressAllow=" not in unit
    # Only the nginx user can connect: a loopback TCP port would be open to every local process.
    listen = [line for line in _rendered("vpn-field-report.socket.j2").splitlines() if line and not line.startswith("#")]
    assert [line for line in listen if line.split("=", 1)[0] in {"ListenStream", "SocketUser", "SocketGroup", "SocketMode"}] == \
        ["ListenStream=/run/vpn-field-report.sock", "SocketUser=www-data", "SocketGroup=www-data", "SocketMode=0600"]
    assert not any(line.startswith(("ListenDatagram=", "ListenSequentialPacket=")) for line in listen)
    config = json.loads(_rendered("vpn-field-report.json.j2", server_refs=["p0-reality-upcloud-prod"]))
    assert config["textfile"] == "/var/lib/vpn-field-report/vpn_field_report.prom"
    assert "listen" not in config and "port" not in config
    assert config["server_refs"] == ["p0-reality-upcloud-prod"]


def test_role_links_the_private_aggregate_into_the_textfile_directory():
    tasks = yaml.safe_load((ROLE / "tasks/field-report.yml").read_text())
    links = [task["ansible.builtin.file"] for task in tasks
             if task.get("ansible.builtin.file", {}).get("state") == "link"]
    assert links == [{"src": "/var/lib/vpn-field-report/vpn_field_report.prom",
                      "dest": "{{ (monitoring | default({})).node_exporter_textfile_dir | default('/var/lib/node_exporter/textfile') }}/vpn_field_report.prom",
                      "state": "link", "owner": "root", "group": "root", "force": True, "follow": False}]
    retired = yaml.safe_load((ROLE / "tasks/field-report-disable.yml").read_text())
    removed = next(task for task in retired if task["name"] == "Remove field-report ingest files and aggregate textfile")
    assert "/var/lib/vpn-field-report" in removed["loop"]


def _settings_assert_holds(**changes) -> bool:
    """Evaluate the role's real settings assert with the pinned ansible-core templar."""
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    tasks = yaml.safe_load((ROLE / "tasks/field-report.yml").read_text())
    task = next(task for task in tasks if task["name"] == "Require bounded field-report ingest settings and cohort tokens")
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["subscription_field_report"]
    field_report = {"cohort_token": TOKEN, "previous_cohort_token": PREVIOUS,
                    "previous_cohort_token_valid_until": "2999-01-01T00:00:00Z"}
    settings = {**defaults, "server_refs": ["p0-reality-upcloud-prod"]}
    for key, value in changes.items():
        (field_report if key in field_report else settings)[key] = value
    templar = Templar(loader=DataLoader(), variables={"subscription_field_report": settings, "field_report": field_report})
    return all(templar.template(trust_as_template("{{ " + condition + " }}")) for condition in task["ansible.builtin.assert"]["that"])


@pytest.mark.parametrize("key", ["path", "cohort_token", "previous_cohort_token", "previous_cohort_token_valid_until",
                                 "server_refs"])
def test_settings_assert_refuses_a_trailing_newline(key):
    assert _settings_assert_holds()
    value = {"path": FIELD_REPORT_PATH, "cohort_token": TOKEN, "previous_cohort_token": PREVIOUS,
             "previous_cohort_token_valid_until": "2999-01-01T00:00:00Z", "server_refs": "p0-reality-upcloud-prod"}[key]
    assert not _settings_assert_holds(**{key: [value + "\n"] if key == "server_refs" else value + "\n"})


@pytest.mark.parametrize(("release", "package"), [("trixie", "python3-jsonschema=4.19.2-6"),
                                                  ("noble", "python3-jsonschema=4.10.3-2ubuntu1")])
def test_validator_package_is_pinned_for_each_supported_release(release, package):
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    tasks = yaml.safe_load((ROLE / "tasks/field-report.yml").read_text())
    install = next(task for task in tasks if task["name"] == "Install the field-report contract validator package")
    guard = next(task for task in tasks if task["name"] == "Require a pinned validator package for this release")
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["subscription_field_report"]
    for facts, admitted in (({"distribution_release": release}, True), ({"distribution_release": "bookworm"}, False)):
        templar = Templar(loader=DataLoader(), variables={"subscription_field_report": defaults, "ansible_facts": facts})
        assert all(templar.template(trust_as_template("{{ " + condition + " }}"))
                   for condition in guard["ansible.builtin.assert"]["that"]) is admitted
    templar = Templar(loader=DataLoader(), variables={"subscription_field_report": defaults,
                                                      "ansible_facts": {"distribution_release": release}})
    assert templar.template(trust_as_template(install["ansible.builtin.apt"]["name"])) == package


DATASET_ROWS = (b"1.0.0.0\t1.0.0.255\t0\tNone\tNot routed\n"
                b"192.0.2.0\t192.0.2.255\t64500\tZZ\tTEST-NET-ONE \xc3\xa9\n"
                b"198.51.100.0\t198.51.100.255\t0\tNone\tNot routed\n"
                b"203.0.113.0\t203.0.113.255\t64502\tNone\tNo country\n"
                b"2001:db8::\t2001:db8::ffff\t64501\tZY\tTEST-SIX\n"
                b"2001:db8:1::\t2001:db8:1::ffff\t64501\tZY\tTEST-SIX\n")
HINT_PATH = "/v1/network-hint"


def _dataset(tmp_path: Path, rows: bytes = DATASET_ROWS, fleet_addresses: list[str] | None = None) -> dict:
    import gzip
    import hashlib

    path = tmp_path / "ip2asn-combined.tsv.gz"
    path.write_bytes(gzip.compress(rows))
    return {"path": HINT_PATH, "ttl_seconds": 21600, "database": str(path),
            "database_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "fleet_addresses": fleet_addresses or []}


def _get(config: dict, peer: str | None, token: str | None = TOKEN, path: str = HINT_PATH) -> tuple[int, bytes, dict]:
    connection = http.client.HTTPConnection("127.0.0.1", config["port"], timeout=5)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if peer is not None:
        headers["X-Network-Hint-Peer"] = peer
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        connection.close()


def test_network_hint_answers_from_the_peer_header_and_never_keeps_the_address(ingest, tmp_path):
    spec = importlib.util.spec_from_file_location("validate_field_report_for_hint_test", ROOT / "scripts/validate-field-report.py")
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    checker = contract.validator(json.loads((ROOT / "contract/client-network-hint.schema.json").read_text()))
    # 192.0.2.10 and 2001:db8:1::10 stand for fleet nodes: a fetch through the tunnel arrives from one of them,
    # or from another address in the node's IPv6 /64.
    process, config = ingest(network_hint=_dataset(tmp_path, fleet_addresses=["192.0.2.10", "2001:db8:1::10"]))
    before = _metrics(config)
    assert _samples(before)["vpn_field_report_network_hint_available"] == 1

    # The socket peer is loopback; only the header that nginx sets names the client address.
    status, body, headers = _get(config, "192.0.2.77")
    hint = json.loads(body)
    assert status == 200 and headers["Content-Type"] == "application/json" and headers["Cache-Control"] == "no-store"
    assert list(checker.iter_errors(hint)) == []
    assert (hint["asn"], hint["country"], hint["ttl_seconds"]) == (64500, "ZZ", 21600)
    assert hint["observed_at"].endswith(":00:00Z") and b"192.0.2.77" not in body
    assert json.loads(_get(config, "2001:db8::1")[1])["asn"] == 64501
    assert json.loads(_get(config, "::ffff:192.0.2.1")[1])["asn"] == 64500
    # A fleet address, not routed, no country, outside every range, malformed or missing: no hint. A fleet
    # node's own ASN would name the hosting network, never the device's.
    for peer in ("192.0.2.10", "::ffff:192.0.2.10", "2001:db8:1::10", "2001:db8:1::abcd", "198.51.100.9", "203.0.113.9", "10.0.0.1",
                 "192.0.2.1, 203.0.113.9", "not-an-address", None):
        assert _get(config, peer)[:2] == (204, b"")
    assert _get(config, "192.0.2.77", token="wrongTokenValue_00000000000")[:2] == (401, b"")
    assert _get(config, "192.0.2.77", token=None)[0] == 401
    assert _get(config, "192.0.2.77", path=FIELD_REPORT_PATH)[0] == 404
    # The hint changes no report counter.
    assert _metrics(config) == before

    process.terminate()
    stdout, stderr = process.communicate(timeout=5)
    stored = "".join(path.read_text() for path in Path(config["textfile"]).parent.iterdir())
    for needle in ("192.0.2.77", "2001:db8::1", TOKEN):
        assert needle not in stdout + stderr and needle not in stored


def test_network_hint_route_is_absent_without_a_dataset(ingest):
    _, config = ingest()
    assert _get(config, "192.0.2.77")[0] == 404
    assert "vpn_field_report_network_hint_available" not in _metrics(config)


@pytest.mark.parametrize("rows,pin_matches", [
    (DATASET_ROWS, False),
    (DATASET_ROWS + b"192.0.2.128\t192.0.2.200\t64503\tZZ\toverlaps\n", True),
    (DATASET_ROWS + b"203.0.114.0\t203.0.114.255\tAS64503\tZZ\tnot a number\n", True),
    (DATASET_ROWS + b"203.0.114.9\t203.0.114.0\t64503\tZZ\treversed\n", True),
    (DATASET_ROWS + b"203.0.114.0\n", True),
    (b"2001:db8::\t2001:db8::ffff\t64501\tZY\tno IPv4\n", True),
    (None, True),
], ids=["pin-mismatch", "overlap", "asn-text", "reversed", "short-line", "no-ipv4", "truncated-gzip"])
def test_a_damaged_or_unpinned_dataset_turns_off_only_the_hint(ingest, tmp_path, rows, pin_matches):
    hint = _dataset(tmp_path, rows or DATASET_ROWS)
    if rows is None:
        # A truncated gzip stream whose pin matches its bytes.
        import hashlib
        data = Path(hint["database"]).read_bytes()[:-12]
        Path(hint["database"]).write_bytes(data)
        hint["database_sha256"] = hashlib.sha256(data).hexdigest()
    if not pin_matches:
        hint["database_sha256"] = "0" * 64
    process, config = ingest(network_hint=hint)
    # A damaged dataset never answers, and report intake keeps working.
    assert _get(config, "192.0.2.77")[0] == 404
    assert _samples(_metrics(config))["vpn_field_report_network_hint_available"] == 0
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    assert _samples(_metrics(config))["vpn_field_report_reports_total"] == 1
    process.terminate()
    _, stderr = process.communicate(timeout=5)
    assert "network hint dataset" in stderr and "network hint is off" in stderr and "Traceback" not in stderr


def test_a_malformed_fleet_address_turns_off_only_the_hint(ingest, tmp_path):
    process, config = ingest(network_hint=_dataset(tmp_path, fleet_addresses=["192.0.2.0/24"]))
    assert _get(config, "192.0.2.77")[0] == 404
    assert _samples(_metrics(config))["vpn_field_report_network_hint_available"] == 0
    process.terminate()
    _, stderr = process.communicate(timeout=5)
    assert stderr == "vpn-field-report: network hint fleet address list has a malformed entry; the network hint is off\n"


def test_a_gzip_bomb_line_is_refused_inside_the_unit_memory_limit(tmp_path):
    import gzip
    import hashlib

    # 256 MiB of digits with no line break compress to well under 1 MiB; the unit allows 128M.
    path = tmp_path / "ip2asn-combined.tsv.gz"
    path.write_bytes(gzip.compress(b"1" * (256 << 20), compresslevel=1))
    hint = {"path": HINT_PATH, "ttl_seconds": 21600, "database": str(path),
            "database_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "fleet_addresses": []}
    config = _config(tmp_path, network_hint=hint)
    _write_config(tmp_path, config)
    # A wrapper runs the service as its only child until the first aggregate is written, so the
    # child peak RSS is the service's own, measured after the dataset load.
    wrapper = ("import os, resource, subprocess, sys, time\n"
               "textfile, command = sys.argv[1], sys.argv[2:]\n"
               "child = subprocess.Popen(command, pass_fds=(int(command[4]),), stderr=subprocess.PIPE, text=True)\n"
               "deadline = time.monotonic() + 30\n"
               "while not os.path.exists(textfile) and child.poll() is None and time.monotonic() < deadline:\n"
               "    time.sleep(0.05)\n"
               "child.terminate()\n"
               "_, stderr = child.communicate(timeout=10)\n"
               "peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss\n"
               "print(int(os.path.exists(textfile)), peak if sys.platform == 'darwin' else peak * 1024)\n"
               "sys.stderr.write(stderr)\n")
    with _tcp_listener() as listener:
        result = subprocess.run([sys.executable, "-I", "-c", wrapper, config["textfile"],
                                 *_service_command(listener, tmp_path)], pass_fds=(listener.fileno(),),
                                capture_output=True, text=True, timeout=60)
    served, peak = (int(value) for value in result.stdout.split())
    assert served == 1 and "network hint dataset has an over-long line" in result.stderr
    assert peak < 128 << 20


def test_a_dataset_over_the_decompressed_size_cap_is_refused(tmp_path, monkeypatch):
    module = _module()
    hint = _dataset(tmp_path)
    module.AsnTable(hint["database"], hint["database_sha256"])
    monkeypatch.setattr(module, "MAX_DATASET_BYTES", len(DATASET_ROWS) - 1)
    with pytest.raises(ValueError, match="network hint dataset exceeds its decompressed size limit"):
        module.AsnTable(hint["database"], hint["database_sha256"])


def test_nginx_hint_location_uses_only_the_peer_address_and_refuses_forwarding_headers():
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["subscription_field_report"]["network_hint"]
    vhost = _rendered("subscription.conf.j2", network_hint={**defaults, "enabled": True})
    location = vhost.split(f"location = {HINT_PATH} {{", 1)[1].split("\n    }", 1)[0]
    assert "limit_except GET { deny all; }" in location
    assert "if ($vpn_network_hint_forwarded) {\n            return 400;\n        }" in location
    assert "limit_req zone=vpn_network_hint_per_ip burst=10 nodelay;" in location
    assert "proxy_set_header X-Network-Hint-Peer $remote_addr;" in location
    for header in ("X-Forwarded-For", "Forwarded", "X-Real-IP"):
        assert f'proxy_set_header {header} "";' in location
    assert "proxy_pass_request_body off;" in location
    assert "proxy_pass http://unix:/run/vpn-field-report.sock:;" in location
    assert "proxy_intercept_errors on;\n        error_page 401 403 = @vpn_sub_not_found;" in location
    assert "access_log /var/log/nginx/vpn-sub.categorical.log vpn_sub_category;" in location
    assert "error_log /dev/null crit;" in location
    # A real_ip setting would let a client choose the address that the hint looks up.
    assert "set_real_ip_from" not in vhost and "real_ip_header" not in vhost
    limits = _rendered("rate-limit.conf.j2", network_hint={**defaults, "enabled": True})
    assert "limit_req_zone $binary_remote_addr zone=vpn_network_hint_per_ip:10m rate=30r/m;" in limits
    assert ('map "$http_x_forwarded_for$http_forwarded$http_x_real_ip$http_x_network_hint_peer" '
            '$vpn_network_hint_forwarded {\n    ""      0;\n    default 1;\n}') in limits
    assert "network-hint" not in _rendered("subscription.conf.j2")
    assert "vpn_network_hint" not in _rendered("rate-limit.conf.j2")
    inventory = {"groups": {"all": ["vpn-a", "vpn-b", "sub-only"]},
                 "hostvars": {"vpn-a": {"vpn_service_address": "192.0.2.10", "server_ipv6": "2001:db8::10",
                                        "honeypot_listen_addr": "192.0.2.11"},
                              "vpn-b": {"vpn_service_address": "198.51.100.20"},
                              "sub-only": {"vpn_service_address": "192.0.2.10", "server_ipv6": ""}}}
    config = json.loads(_rendered("vpn-field-report.json.j2", _inventory=inventory, network_hint={**defaults, "enabled": True}))
    assert config["network_hint"] == {"path": HINT_PATH, "ttl_seconds": 21600,
                                      "database": "/usr/local/lib/vpn-field-report/ip2asn-combined.tsv.gz",
                                      "database_sha256": defaults["dataset_sha256"],
                                      "fleet_addresses": ["192.0.2.10", "192.0.2.11", "198.51.100.20", "2001:db8::10"]}
    assert json.loads(_rendered("vpn-field-report.json.j2"))["network_hint"] is None


def _hint_assert_holds(**changes) -> bool:
    """Evaluate the network-hint settings assert as the assert module does, with the pinned ansible-core templar."""
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    tasks = yaml.safe_load((ROLE / "tasks/field-report.yml").read_text())
    task = next(task for task in tasks if task["name"] == "Require bounded network-hint settings and a pinned dataset")
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["subscription_field_report"]
    settings = {**defaults, "network_hint": {**defaults["network_hint"], "enabled": True, **changes}}
    templar = Templar(loader=DataLoader(), variables={"subscription_field_report": settings})
    return all(templar.evaluate_conditional(trust_as_template(condition)) for condition in task["ansible.builtin.assert"]["that"])


@pytest.mark.parametrize("change", [{"path": FIELD_REPORT_PATH}, {"path": HINT_PATH + "\n"}, {"ttl_seconds": 299},
                                    {"ttl_seconds": 86401}, {"dataset_version": "latest"},
                                    {"dataset_version": "20261101T093850Z\n"}, {"dataset_sha256": ""},
                                    {"dataset_sha256": "A" * 64}, {"nginx_rate": "30r/m\n"}],
                         ids=lambda change: repr(change))
def test_hint_settings_assert_refuses_unbounded_or_unpinned_values(change):
    assert _hint_assert_holds()
    assert not _hint_assert_holds(**change)


def test_role_copies_only_the_pinned_controller_dataset():
    tasks = {task["name"]: task for task in yaml.safe_load((ROLE / "tasks/field-report.yml").read_text())}
    probe = tasks["Verify the pinned network-hint dataset on the controller"]
    assert probe["delegate_to"] == "localhost" and probe["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"
    assert probe["ansible.builtin.stat"]["path"].endswith(
        "/.cache/ip-asn/ip2asn-combined-{{ subscription_field_report.network_hint.dataset_version }}.tsv.gz")
    assert tasks["Require the controller dataset to match its pin"]["ansible.builtin.assert"]["that"][1] == \
        "_subscription_network_hint_dataset.stat.checksum == subscription_field_report.network_hint.dataset_sha256"
    copy_task = tasks["Install the pinned network-hint dataset"]["ansible.builtin.copy"]
    assert copy_task["src"] == "{{ _subscription_network_hint_dataset.stat.path }}"
    assert not any("get_url" in str(task) or "uri" in task for task in tasks.values())


def test_refresh_script_pins_only_a_dataset_the_ingest_can_load(tmp_path):
    import gzip

    good = tmp_path / "good.tsv.gz"
    good.write_bytes(gzip.compress(DATASET_ROWS))
    bad = tmp_path / "bad.tsv.gz"
    bad.write_bytes(gzip.compress(DATASET_ROWS + b"192.0.2.128\t192.0.2.200\t64503\tZZ\toverlaps\n"))
    stub = tmp_path / "bin"
    stub.mkdir()
    # The stub stands in for the download: it writes the chosen file and a Last-Modified header.
    (stub / "curl").write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do case "$1" in --dump-header) h="$2"; shift;; '
                               '--output) o="$2"; shift;; esac; shift; done\n'
                               'printf "HTTP/2 200\\r\\nlast-modified: Sun, 01 Nov 2026 09:38:50 GMT\\r\\n\\r\\n" > "$h"\n'
                               'cp "$STUB_DATASET" "$o"\n')
    (stub / "curl").chmod(0o755)
    cache = tmp_path / "cache"
    script = ROOT / "scripts/refresh-ip-asn-dataset.sh"
    env = {"PATH": f"{stub}:/usr/bin:/bin", "IP_ASN_CACHE_DIR": str(cache), "TMPDIR": str(tmp_path)}
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30,
                            env={**env, "STUB_DATASET": str(good)})
    assert result.returncode == 0, result.stderr
    import hashlib
    stored = cache / "ip2asn-combined-20261101T093850Z.tsv.gz"
    assert stored.read_bytes() == good.read_bytes()
    assert f'dataset_sha256: "{hashlib.sha256(good.read_bytes()).hexdigest()}"' in result.stdout
    assert 'dataset_version: "20261101T093850Z"' in result.stdout
    # A second build with the same version must not replace the copy that a committed pin names.
    other = tmp_path / "other.tsv.gz"
    other.write_bytes(gzip.compress(DATASET_ROWS + b"203.0.114.0\t203.0.114.255\t64503\tZZ\tnewer build\n"))
    clobber = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30,
                             env={**env, "STUB_DATASET": str(other)})
    assert clobber.returncode == 1 and "already exists" in clobber.stderr
    assert stored.read_bytes() == good.read_bytes() and sorted(cache.iterdir()) == [stored]
    stored.unlink()
    refused = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30,
                             env={**env, "STUB_DATASET": str(bad)})
    assert refused.returncode != 0 and not list(cache.iterdir())
    assert subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30,
                          env={**env, "STUB_DATASET": str(good), "IP_ASN_DATASET_URL": "http://iptoasn.com/x"}).returncode == 1
