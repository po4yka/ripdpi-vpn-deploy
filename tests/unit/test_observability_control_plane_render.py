"""Static receiver-contract regression tests for the observability control plane."""

from pathlib import Path
import io
import os
import socket
import ssl
import subprocess
import threading

import pytest
import yaml

from scripts.template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"


def _fixture_client_namespace() -> dict[str, object]:
    prepare = yaml.safe_load((ROLE / "molecule/enabled/prepare.yml").read_text())
    client = next(
        task
        for task in prepare[0]["tasks"]
        if task["name"] == "Install bounded direct mTLS fixture client"
    )
    namespace: dict[str, object] = {"__name__": "fixture_client"}
    exec(client["ansible.builtin.copy"]["content"], namespace)
    return namespace


def _values() -> dict:
    return {
        "observability_control_plane": {
            "ingress_port": 9443,
            "ingress_sni": "ingest.example.test",
            "control_plane_dns_san": "control.example.test",
            "prometheus_listen": "127.0.0.1:9090",
            "remote_write_path_prefix": "/remote-write/v1/nodes",
            "request_body_limit": "8m",
            "request_concurrency": 4,
            "request_rate": "20r/s",
            "request_rate_burst": 40,
            "config_root": "/etc/observability-control-plane",
            "data_dir": "/var/lib/observability-prometheus",
            "service_user": "prometheus",
            "service_group": "prometheus",
            "binary_link": "/usr/local/libexec/observability-prometheus",
            "tsdb_retention_time": "30d",
            "tsdb_retention_size": "20GB",
            "ingest_identities": [
                {"node_id": "vpn-p0"},
                {"node_id": "vpn-p2"},
            ],
        }
    }


def test_ingress_is_only_the_bounded_authenticated_write_path() -> None:
    rendered = render_template(
        ROLE / "templates/observability-remote-write.conf.j2", _values()
    )

    for required in (
        "listen 9443 ssl http2 default_server;",
        "ssl_reject_handshake on;",
        "listen 9443 ssl http2;",
        "ssl_client_certificate /etc/observability-control-plane/tls/client-ca.crt;",
        "ssl_crl /etc/observability-control-plane/tls/client.crl;",
        "ssl_verify_client on;",
        "client_max_body_size 8m;",
        "limit_conn observability_remote_write_conn 4;",
        "rate=20r/s;",
        "burst=40 nodelay;",
        'location ~ "^/remote-write/v1/nodes/',
        "if ($request_method != POST) { return 405; }",
        "if ($observability_remote_write_node != $1) { return 403; }",
        "rewrite ^ /api/v1/write break;",
        "proxy_pass http://127.0.0.1:9090;",
        "X-Prometheus-Remote-Write-Version $http_x_prometheus_remote_write_version;",
        "location / { return 404; }",
    ):
        assert required in rendered

    for forbidden in ("/api/v1/query", "/-/reload", "proxy_set_header Authorization"):
        assert forbidden not in rendered


def test_ingress_binds_each_certificate_subject_to_exact_node_path() -> None:
    rendered = render_template(
        ROLE / "templates/observability-remote-write.conf.j2", _values()
    )

    assert '"CN=vpn-p0" vpn-p0;' in rendered
    assert '"CN=vpn-p2" vpn-p2;' in rendered
    assert 'default "";' in rendered


def test_prometheus_service_is_loopback_only_and_storage_is_bounded() -> None:
    rendered = render_template(
        ROLE / "templates/observability-prometheus.service.j2", _values()
    )

    for required in (
        "--web.listen-address=127.0.0.1:9090",
        "--web.enable-remote-write-receiver",
        "--storage.tsdb.retention.time=30d",
        "--storage.tsdb.retention.size=20GB",
        "ProtectSystem=strict",
        "NoNewPrivileges=true",
        "PrivateDevices=true",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "ProtectKernelLogs=yes",
        "ProtectClock=yes",
        "LockPersonality=yes",
        "RestrictNamespaces=yes",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "ReadWritePaths=/var/lib/observability-prometheus",
    ):
        assert required in rendered
    assert "0.0.0.0:9090" not in rendered


def test_role_defaults_and_tasks_fail_closed_before_host_writes() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_control_plane"
    ]
    enabled = (ROLE / "tasks/enable.yml").read_text()

    assert defaults["enabled"] is False
    assert defaults["prometheus"]["version"] == ""
    assert defaults["tls"]["server_key_pem"] == ""
    assert "requires exact bounded receiver settings" in enabled
    assert "- sslclient" in enabled
    assert "- -crl_check_all" in enabled
    assert "ingress_sni != observability_control_plane.control_plane_dns_san" in enabled


def test_enabled_role_refuses_missing_pins_and_mtls_before_mutation(
    tmp_path: Path,
) -> None:
    playbook = tmp_path / "missing-control-plane-contract.yml"
    playbook.write_text("""---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    observability_control_plane:
      enabled: true
  roles:
    - observability_control_plane
""")

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    # The failed assert is intentionally no_log because it checks credential
    # material; its recap proves the refusal happened before any host mutation.
    assert "changed=0" in result.stdout


def test_enabled_molecule_archive_matches_runtime_release_strip_contract() -> None:
    prepare = (ROLE / "molecule/enabled/prepare.yml").read_text()
    converge = (ROLE / "molecule/enabled/converge.yml").read_text()

    assert (
        'tar -C "$fixture" -czf "$fixture/prometheus.tar.gz" prometheus-fixture/prometheus'
        in prepare
    )
    assert (
        "archive_members: {amd64: prometheus-fixture/prometheus, arm64: prometheus-fixture/prometheus}"
        in converge
    )
    assert (
        "runtime_release_archive_strip_components: 1"
        in (ROLE / "tasks/enable.yml").read_text()
    )


def test_disabled_molecule_seeds_retained_tsdb_once_before_idempotence() -> None:
    converge = (ROLE / "molecule/default/converge.yml").read_text()
    prepare = (ROLE / "molecule/default/prepare.yml").read_text()

    assert "Seed historical TSDB marker" not in converge
    assert "Create historical TSDB directory" in prepare
    assert "Seed historical TSDB marker" in prepare


def test_prometheus_restart_is_conditional_on_published_runtime_changes() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    nested = [
        child
        for task in tasks
        for section in ("block", "rescue", "always")
        for child in task.get(section, [])
    ]
    by_name = {task["name"]: task for task in [*tasks, *nested]}

    assert by_name["Install Prometheus service unit"]["register"] == (
        "_observability_prometheus_unit"
    )
    assert (
        by_name["Point current configuration at candidate generation"]["register"]
        == "_observability_prometheus_activation"
    )
    service = by_name["Start or restart Prometheus for the published generation"][
        "ansible.builtin.systemd_service"
    ]
    assert service["state"] == (
        "{{ 'restarted' if (_observability_prometheus_unit.changed or "
        "_observability_prometheus_activation.changed) else 'started' }}"
    )


def test_enabled_receiver_waits_for_the_exact_get_refusal_before_red_path_checks() -> (
    None
):
    verify = yaml.safe_load((ROLE / "molecule/enabled/verify.yml").read_text())
    tasks = verify[0]["tasks"]
    by_name = {task["name"]: task for task in tasks}
    readiness = by_name[
        "Wait for the receiver and assert the authenticated GET refusal"
    ]
    command = readiness["ansible.builtin.command"]["argv"]

    assert command[0] == "/var/tmp/observability-control-plane-fixture/mtls-client.py"
    assert command[command.index("--server-name") + 1] == "ingest.fixture.test"
    assert command[command.index("--path") + 1] == "/remote-write/v1/nodes/vpn-p0"
    assert readiness["failed_when"] is False
    assert readiness["retries"] == 10
    assert readiness["delay"] == 1
    assert readiness["until"] == "get_request.stdout == '405'"

    names = [task["name"] for task in tasks]
    for red_path in (
        "Assert remote-write receiver rejects a missing or wrong SNI",
        "Assert remote-write receiver rejects a CN path mismatch",
        "Submit an oversized request and require exact server-side 413",
        "Assert valid mTLS remote write reaches only loopback Prometheus",
    ):
        assert names.index(readiness["name"]) < names.index(red_path)


def test_enabled_receiver_checks_use_the_bounded_direct_fixture_client() -> None:
    verify = yaml.safe_load((ROLE / "molecule/enabled/verify.yml").read_text())
    client_tasks = [
        task
        for task in verify[0]["tasks"]
        if task.get("ansible.builtin.command", {}).get("argv", [None])[0]
        == "/var/tmp/observability-control-plane-fixture/mtls-client.py"
    ]

    assert len(client_tasks) == 5
    for task in client_tasks:
        command = task["ansible.builtin.command"]["argv"]
        assert (
            command[0] == "/var/tmp/observability-control-plane-fixture/mtls-client.py"
        )
        assert "--server-name" in command
        assert "--path" in command

    readiness_name = "Wait for the receiver and assert the authenticated GET refusal"
    for task in client_tasks:
        if task["name"] == readiness_name:
            continue
        result = task["register"]
        assert task["retries"] == 2
        assert task["delay"] == 1
        if result == "oversized_request":
            assert task["until"] == (
                "oversized_request.stdout == '413' and oversized_request.rc == 0"
            )
        else:
            assert task["until"] == (
                f"({result}.msg | default('')) != 'Error executing command.'"
            )


def test_enabled_receiver_fixture_normalizes_tls_rejections_only() -> None:
    verify = yaml.safe_load((ROLE / "molecule/enabled/verify.yml").read_text())
    client_tasks = [
        task
        for task in verify[0]["tasks"]
        if task.get("ansible.builtin.command", {}).get("argv", [None])[0]
        == "/var/tmp/observability-control-plane-fixture/mtls-client.py"
    ]
    prepare = (ROLE / "molecule/enabled/prepare.yml").read_text(encoding="utf-8")

    assert "except ssl.SSLError:\n                  return 60" in prepare
    assert (
        "except (OSError, http.client.HTTPException, ValueError):\n                  return 2"
        in prepare
    )

    wrong_sni = next(
        task
        for task in client_tasks
        if task["name"] == "Assert remote-write receiver rejects a missing or wrong SNI"
    )
    assert wrong_sni["failed_when"] == "wrong_sni.rc != 60"

    mismatched_cn = next(
        task
        for task in client_tasks
        if task["name"] == "Assert remote-write receiver rejects a CN path mismatch"
    )
    mismatch_command = mismatched_cn["ansible.builtin.command"]["argv"]
    assert mismatch_command[mismatch_command.index("--method") + 1] == "POST"
    assert mismatched_cn["failed_when"] == (
        "mismatched_cn.stdout != '403' and mismatched_cn.rc != 60"
    )
    assert mismatch_command[mismatch_command.index("--cert") + 1].endswith(
        "client-vpn-p0.crt"
    )
    assert mismatch_command[mismatch_command.index("--path") + 1].endswith("/vpn-p1")

    prepare = yaml.safe_load((ROLE / "molecule/enabled/prepare.yml").read_text())
    client = next(
        task
        for task in prepare[0]["tasks"]
        if task["name"] == "Install bounded direct mTLS fixture client"
    )
    content = client["ansible.builtin.copy"]["content"]
    assert (
        "socket.create_connection((DIRECT_ADDRESS, DIRECT_PORT), timeout=5)" in content
    )
    assert "load_cert_chain" in content
    assert "server_hostname=self.host" in content
    assert "response.read()" not in content
    assert 'parser.add_argument("--body-size", type=int)' in content
    assert "def send_declared_length_request" not in content
    assert "connection.sock.sendall(request)" not in content
    assert "MAX_BODY_SIZE = 8 * 1024 * 1024 + 1" in content
    assert "args.body_size > MAX_BODY_SIZE" in content
    assert "def send_streaming_request" in content
    assert "threading.Thread(target=read_response, daemon=True)" in content
    assert "while remaining and not completed.is_set()" in content
    assert "if send_error is not None and status != 413" in content
    assert "deadline = time.monotonic() + response_timeout" in content
    assert "sock.shutdown(socket.SHUT_RDWR)" in content
    assert "reader.join(timeout=0.1)" in content
    assert "ssl.SSLEOFError" in content
    assert '"Expect: 100-continue"' not in content
    assert '"Content-Length: {}".format(args.body_size)' in content
    assert "def read_response_status" in content
    assert "BoundedBody" not in content
    assert "except ssl.SSLError:" in content
    assert "connection.request(" in content
    assert "status = connection.getresponse().status" in content
    assert 'body=args.body.encode("utf-8")' in content
    assert "urllib" not in content

    oversized = next(
        task for task in client_tasks if task["name"].startswith("Submit an oversized")
    )
    oversized_command = oversized["ansible.builtin.command"]["argv"]
    assert "--body-file" not in oversized_command
    assert "--content-length" not in oversized_command
    assert oversized_command[oversized_command.index("--body-size") + 1] == "8388609"
    assert oversized["failed_when"] == (
        "oversized_request.stdout != '413' or oversized_request.rc != 0"
    )
    assert oversized["until"] == (
        "oversized_request.stdout == '413' and oversized_request.rc == 0"
    )
    verify_text = (ROLE / "molecule/enabled/verify.yml").read_text()
    assert "observability-remote-write.error.log" not in verify_text
    assert "oversized_request.rc != 60" not in verify_text
    converge = (ROLE / "molecule/enabled/converge.yml").read_text()
    assert "request_body_limit: 8m" in converge


def test_enabled_fixture_parses_413_before_a_request_body_is_sent() -> None:
    namespace = _fixture_client_namespace()
    read_response_status = namespace["read_response_status"]

    assert callable(read_response_status)
    assert (
        read_response_status(
            io.BytesIO(
                b"HTTP/1.1 413 Request Entity Too Large\r\nConnection: close\r\n\r\n"
            )
        )
        == 413
    )
    with pytest.raises(ValueError, match="interim response"):
        read_response_status(io.BytesIO(b"HTTP/1.1 100 Continue\r\n\r\n"))


def _fixture_request(size: int) -> bytes:
    return (
        b"POST /remote-write/v1/nodes/fixture HTTP/1.1\r\n"
        b"Host: ingest.fixture.test\r\n" + f"Content-Length: {size}\r\n\r\n".encode()
    )


def _read_headers(connection: socket.socket) -> bytes:
    received = b""
    while b"\r\n\r\n" not in received:
        received += connection.recv(4096)
    return received.split(b"\r\n\r\n", 1)[1]


def test_enabled_fixture_accepts_413_returned_during_streaming_upload() -> None:
    namespace = _fixture_client_namespace()
    send_streaming_request = namespace["send_streaming_request"]
    client, server = socket.socketpair()
    response = b"HTTP/1.1 413 Request Entity Too Large\r\nConnection: close\r\n\r\n"

    def reject_after_headers() -> None:
        try:
            _read_headers(server)
            server.sendall(response)
            server.shutdown(socket.SHUT_WR)
        finally:
            server.close()

    thread = threading.Thread(target=reject_after_headers)
    thread.start()
    try:
        assert send_streaming_request(client, _fixture_request(65537), 65537) == 413
    finally:
        client.close()
        thread.join(timeout=1)


def test_enabled_fixture_accepts_413_returned_after_streaming_body() -> None:
    namespace = _fixture_client_namespace()
    send_streaming_request = namespace["send_streaming_request"]
    client, server = socket.socketpair()
    body_size = 65537
    response = b"HTTP/1.1 413 Request Entity Too Large\r\nConnection: close\r\n\r\n"

    def reject_after_body() -> None:
        try:
            received = _read_headers(server)
            while len(received) < body_size:
                received += server.recv(body_size - len(received))
            server.sendall(response)
        finally:
            server.close()

    thread = threading.Thread(target=reject_after_body)
    thread.start()
    try:
        assert (
            send_streaming_request(client, _fixture_request(body_size), body_size)
            == 413
        )
    finally:
        client.close()
        thread.join(timeout=1)


def test_enabled_fixture_refuses_a_streaming_upload_without_response() -> None:
    namespace = _fixture_client_namespace()
    send_streaming_request = namespace["send_streaming_request"]
    readers: list[threading.Thread] = []

    class TrackingThread(threading.Thread):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            readers.append(self)

    class TrackingThreading:
        Event = staticmethod(threading.Event)
        Thread = TrackingThread

    namespace["threading"] = TrackingThreading
    client, server = socket.socketpair()
    hold_open = threading.Event()

    def receive_without_response() -> None:
        try:
            _read_headers(server)
            server.recv(1)
            hold_open.wait(1)
        finally:
            server.close()

    thread = threading.Thread(target=receive_without_response)
    thread.start()
    try:
        with pytest.raises(TimeoutError, match="response timeout"):
            send_streaming_request(
                client, _fixture_request(1), 1, response_timeout=0.01
            )
    finally:
        hold_open.set()
        client.close()
        thread.join(timeout=1)
    assert readers and all(not reader.is_alive() for reader in readers)


def test_enabled_fixture_accepts_413_from_an_abrupt_tls_peer_close(
    tmp_path: Path,
) -> None:
    namespace = _fixture_client_namespace()
    send_streaming_request = namespace["send_streaming_request"]
    certificate = tmp_path / "certificate.pem"
    private_key = tmp_path / "private-key.pem"
    subprocess.run(
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
            "/CN=fixture.test",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        capture_output=True,
        check=True,
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate, private_key)
    client_context = ssl.create_default_context()
    client_context.check_hostname = False
    client_context.verify_mode = ssl.CERT_NONE
    response = b"HTTP/1.1 413 Request Entity Too Large\r\nConnection: close\r\n\r\n"
    response_sent = threading.Event()

    def reject_and_close_tls() -> None:
        connection, _ = listener.accept()
        tls_connection = server_context.wrap_socket(connection, server_side=True)
        try:
            _read_headers(tls_connection)
            tls_connection.sendall(response)
            response_sent.set()
            tls_connection.close()
        finally:
            listener.close()

    thread = threading.Thread(target=reject_and_close_tls)
    thread.start()
    raw = socket.create_connection(listener.getsockname(), timeout=1)
    client = client_context.wrap_socket(raw, server_hostname="fixture.test")

    class PeerClosedTLSSocket:
        def __init__(self, delegate: ssl.SSLSocket) -> None:
            self.delegate = delegate
            self.send_calls = 0

        def sendall(self, data: bytes) -> None:
            self.send_calls += 1
            if self.send_calls == 2:
                assert response_sent.wait(1)
                raise ssl.SSLEOFError("peer closed during body upload")
            self.delegate.sendall(data)

        def makefile(self, *args: object, **kwargs: object) -> object:
            return self.delegate.makefile(*args, **kwargs)

        def settimeout(self, timeout: float) -> None:
            self.delegate.settimeout(timeout)

        def shutdown(self, how: int) -> None:
            self.delegate.shutdown(how)

        def close(self) -> None:
            self.delegate.close()

    peer_closed_client = PeerClosedTLSSocket(client)
    try:
        assert (
            send_streaming_request(peer_closed_client, _fixture_request(65537), 65537)
            == 413
        )
        assert peer_closed_client.send_calls == 2
    finally:
        client.close()
        thread.join(timeout=1)
