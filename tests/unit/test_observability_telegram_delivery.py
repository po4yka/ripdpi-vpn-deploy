"""Focused contracts for the bounded primary Telegram relay."""

from __future__ import annotations

from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib import error, request

import pytest
import yaml

from scripts.template_render import render_template
from tests.unit.test_observability_control_plane_alerting import (
    _contract as complete_contract,
)

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
RELAY_PATH = ROLE / "files/observability-telegram-relay.py"


def _relay():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "observability_telegram_relay", RELAY_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract() -> dict[str, object]:
    return {
        "config_root": "/etc/observability-control-plane",
        "alerting": {
            "group_wait": "30s",
            "group_interval": "5m",
            "critical_repeat_interval": "1h",
            "warning_repeat_interval": "6h",
            "recovery_stability": "3m",
            "telegram": {
                "relay_url": "http://127.0.0.1:19095/alert",
                "relay_auth_credential": (
                    "/run/credentials/observability-alertmanager.service/"
                    "telegram-relay-auth-token"
                ),
                "webhook_timeout": "20s",
                "max_alerts": 5,
            },
            "deadman": {
                "enabled": False,
                "receiver_url": "http://127.0.0.1:19093/alerts",
                "repeat_interval": "1m",
            },
        },
    }


def _alert(status: str, suffix: str = "") -> dict[str, object]:
    return {
        "status": status,
        "labels": {
            "environment": "stage" + suffix,
            "node": "node" + suffix,
            "component": "control" + suffix,
        },
        "annotations": {
            "summary": "summary <unsafe>" + suffix,
            "evidence_class": "fixture&" + suffix,
            "runbook": "docs/runbook>" + suffix,
            "description": "must never be rendered",
        },
        "startsAt": "2026-09-05T00:00:00Z",
        "endsAt": "2026-09-05T00:01:00Z",
        "generatorURL": "",
        "fingerprint": "a" * 16,
    }


def _payload(status: str = "firing", alerts: int = 1) -> dict[str, object]:
    return {
        "version": "4",
        "groupKey": "fixture-group",
        "truncatedAlerts": 0,
        "status": status,
        "receiver": "telegram-primary",
        "groupLabels": {"alertname": "Alert<&"},
        "commonLabels": {"alertname": "Alert<&"},
        "commonAnnotations": {"source_generation": "a" * 40},
        "externalURL": "",
        "alerts": [_alert(status, str(index)) for index in range(alerts)],
    }


def test_alertmanager_routes_to_authenticated_bounded_webhooks() -> None:
    rendered = render_template(
        ROLE / "templates/observability-alertmanager.yml.j2",
        {"observability_control_plane": _contract()},
    )
    parsed = yaml.safe_load(rendered)

    assert parsed["route"]["group_wait"] == "30s"
    assert parsed["route"]["group_interval"] == "5m"
    assert parsed["route"]["routes"] == [
        {
            "receiver": "telegram-critical",
            "matchers": ['severity="critical"'],
            "repeat_interval": "1h",
        },
        {
            "receiver": "telegram-primary",
            "matchers": ['severity="warning"'],
            "repeat_interval": "6h",
        },
    ]
    webhooks = [
        receiver["webhook_configs"][0]
        for receiver in parsed["receivers"]
        if receiver["name"] in {"telegram-primary", "telegram-critical"}
    ]
    assert len(webhooks) == 2
    for webhook in webhooks:
        assert webhook == {
            "url": "http://127.0.0.1:19095/alert",
            "send_resolved": True,
            "max_alerts": 5,
            "timeout": "20s",
            "http_config": {
                "authorization": {
                    "type": "Bearer",
                    "credentials_file": (
                        "/run/credentials/observability-alertmanager.service/"
                        "telegram-relay-auth-token"
                    ),
                }
            },
        }
    assert "telegram_configs" not in rendered
    assert "telegram-bot-token" not in rendered


@pytest.mark.parametrize("status", ["firing", "resolved"])
def test_relay_renders_escaped_capped_firing_and_resolved_messages(status: str) -> None:
    relay = _relay()
    payload = _payload(status, alerts=5)
    payload["alerts"][0]["labels"].update(
        {"environment": "stage<&", "node": "node>", "component": "control&"}
    )
    payload["truncatedAlerts"] = 2
    message = relay.render_message(payload, max_alerts=5)

    assert message.startswith("FIRING" if status == "firing" else "RESOLVED")
    assert message.count("\n- ") == 5
    assert "... omitted 2 alerts" in message
    assert "&lt;unsafe&gt;" in message
    assert "Alert&lt;&amp;" in message
    assert "stage&lt;&amp;" in message
    assert "must never be rendered" not in message
    assert len(message) <= 4096


def test_relay_requires_authenticated_loopback_webhook_before_delivery() -> None:
    relay = _relay()
    delivered: list[str] = []
    relay.deliver = lambda **values: delivered.append(values["message"])
    server = relay.RelayServer(
        ("127.0.0.1", 0),
        relay.handler(
            {
                "api_url": "https://api.telegram.org",
                "bot_token": "123456789:fixture-token-not-real",
                "auth_token": "a" * 64,
                "chat_id": "-100000000001",
                "topic_id": 42,
            }
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/alert"
        body = json.dumps(_payload()).encode()
        with pytest.raises(error.HTTPError) as refused:
            request.urlopen(
                request.Request(endpoint, data=body, method="POST"), timeout=2
            )
        assert refused.value.code == 401
        with pytest.raises(error.HTTPError) as refused_type:
            request.urlopen(
                request.Request(
                    endpoint,
                    data=body,
                    headers={"Authorization": "Bearer " + "a" * 64},
                    method="POST",
                ),
                timeout=2,
            )
        assert refused_type.value.code == 400
        with request.urlopen(
            request.Request(
                endpoint,
                data=body,
                headers={
                    "Authorization": "Bearer " + "a" * 64,
                    "Content-Type": "application/json",
                },
                method="POST",
            ),
            timeout=2,
        ) as response:
            assert response.status == 200
            assert json.loads(response.read()) == {"status": "delivered"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert len(delivered) == 1
    assert delivered[0].startswith("FIRING: Alert")


def test_relay_rejects_oversize_or_unbounded_payloads() -> None:
    relay = _relay()
    with pytest.raises(relay.Refusal, match="payload-contract"):
        relay.parse_payload(json.dumps(_payload(alerts=51)).encode(), 65536)
    with pytest.raises(relay.Refusal, match="payload-size"):
        relay.parse_payload(b"{" * 65, 64)


def test_relay_rejects_invalid_delivery_identity_before_serving() -> None:
    relay = _relay()
    with pytest.raises(relay.Refusal, match="delivery-contract"):
        relay.validate_delivery_contract(
            "http://api.telegram.org",
            "123456789:fixture-token-not-real",
            "-100000000001",
            42,
        )
    with pytest.raises(relay.Refusal, match="delivery-contract"):
        relay.validate_delivery_contract(
            "https://api.telegram.org", "invalid", "-100000000001", 42
        )


def test_relay_delivery_constructs_the_exact_validated_telegram_origin() -> None:
    relay = _relay()
    captured: list[str] = []

    def opener(outbound, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 5
        captured.append(outbound.full_url)
        return _Response(200, b'{"ok":true}')

    relay.deliver(
        api_url="https://api.telegram.org",
        token="123456789:fixture-token-not-real",
        chat_id="-100000000001",
        topic_id=42,
        message="bounded",
        opener=opener,
    )

    assert captured == [
        "https://api.telegram.org/bot123456789:fixture-token-not-real/sendMessage"
    ]


def test_relay_reads_only_single_line_ascii_systemd_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relay = _relay()
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    (tmp_path / "valid").write_bytes(b"a" * 64 + b"\n")
    assert relay._credential("valid") == "a" * 64
    for index, content in enumerate((b"", b" value", b"a\nb", b"\xff")):
        name = f"invalid-{index}"
        (tmp_path / name).write_bytes(content)
        with pytest.raises((relay.Refusal, UnicodeError)):
            relay._credential(name)
    with pytest.raises(relay.Refusal, match="credential-path"):
        relay._credential("../valid")


def test_repeated_firing_payload_is_a_deterministic_reminder() -> None:
    relay = _relay()
    payload = _payload("firing")
    assert relay.render_message(payload) == relay.render_message(payload)


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.headers = Message()

    def read(self, maximum: int) -> bytes:
        return self._body[:maximum]

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _http_error(status: int, retry_after: str | None = None) -> error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return error.HTTPError(
        "https://api.telegram.org/redacted",
        status,
        "fixture",
        headers,
        io.BytesIO(b'{"ok":false}'),
    )


@pytest.mark.parametrize(
    ("first", "expected_sleep"),
    [(_http_error(429, "99"), 5), (_http_error(503), 1), (TimeoutError(), 1)],
)
def test_relay_retries_only_transient_failures_with_bounded_delay(
    first: BaseException, expected_sleep: int
) -> None:
    relay = _relay()
    attempts: list[object] = [first, _Response(200, b'{"ok":true}')]
    sleeps: list[int] = []

    def opener(outbound, timeout):  # type: ignore[no-untyped-def]
        assert outbound.full_url.startswith("https://api.telegram.org/bot")
        assert timeout == 5
        result = attempts.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    relay.deliver(
        api_url="https://api.telegram.org",
        token="123456789:fixture-token-not-real",
        chat_id="-100000000001",
        topic_id=42,
        message="bounded",
        opener=opener,
        sleeper=sleeps.append,
    )

    assert attempts == []
    assert sleeps == [expected_sleep]


@pytest.mark.parametrize(
    "failure",
    [
        _http_error(301),
        _http_error(302),
        _http_error(303),
        _http_error(307),
        _http_error(308),
        _http_error(400),
        _Response(200, b"not-json"),
    ],
)
def test_relay_does_not_retry_semantic_or_malformed_responses(failure: object) -> None:
    relay = _relay()
    calls = 0

    def opener(_outbound, timeout):  # type: ignore[no-untyped-def]
        nonlocal calls
        assert timeout == 5
        calls += 1
        if isinstance(failure, BaseException):
            raise failure
        return failure

    with pytest.raises(relay.DeliveryFailure):
        relay.deliver(
            api_url="https://api.telegram.org",
            token="123456789:fixture-token-not-real",
            chat_id="-100000000001",
            topic_id=0,
            message="bounded",
            opener=opener,
            sleeper=lambda _seconds: None,
        )
    assert calls == 1


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_relay_opener_never_forwards_telegram_body_across_redirects(
    status: int,
) -> None:
    relay = _relay()
    source_requests: list[bytes] = []
    redirected_requests: list[bytes] = []

    class RedirectTarget(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            redirected_requests.append(b"GET")
            self.send_response(200)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            redirected_requests.append(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTarget)

    class RedirectSource(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            source_requests.append(self.rfile.read(length))
            self.send_response(status)
            self.send_header(
                "Location", f"http://127.0.0.1:{target.server_port}/captured"
            )
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectSource)
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (target, source)
    ]
    for server, thread in zip((target, source), threads, strict=True):
        thread.start()
    outbound = request.Request(
        f"http://127.0.0.1:{source.server_port}/sendMessage",
        data=b'{"secret":"must-not-forward"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with pytest.raises(error.HTTPError) as refused:
            relay._open_without_redirect(outbound, timeout=1)
        assert refused.value.code == status
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=1)
    assert source_requests == [b'{"secret":"must-not-forward"}']
    assert redirected_requests == []


def test_relay_auth_is_a_distinct_private_secret_and_not_sender_derived() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/alerting-authority.yml").read_text())
    activation = next(
        task["block"]
        for task in tasks
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    materialize = next(
        task
        for task in activation
        if task["name"] == "Materialize primary Telegram relay credentials for systemd"
    )
    relay_item = materialize["loop"][1]
    assert relay_item["content"] == "{{ observability_secrets.telegram.relay_auth_token }}"
    assert "sender_token" not in relay_item["content"]
    assert "hash('sha256')" not in relay_item["content"]

    secret_contract = (ROLE / "tasks/alerting-secret-contract.yml").read_text()
    assert "observability_secrets.telegram.relay_auth_token" in secret_contract
    assert "silence_gateway.sender_token" in secret_contract
    assert "silence_gateway.operators" in secret_contract


@pytest.mark.parametrize("duplicate", ["sender", "operator", "bot"])
def test_duplicate_relay_auth_refuses_before_any_write(
    tmp_path: Path, duplicate: str
) -> None:
    contract = complete_contract()
    if duplicate == "sender":
        relay_auth = contract["alerting"]["silence_gateway"]["sender_token"]
    elif duplicate == "operator":
        relay_auth = contract["alerting"]["silence_gateway"]["operators"][0]["token"]
    else:
        contract["alerting"]["telegram"]["bot_token"] = "f" * 64
        relay_auth = contract["alerting"]["telegram"]["bot_token"]
    marker = tmp_path / "must-not-write"
    playbook = tmp_path / "secret-contract.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "secret authority refusal",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {
                        "observability_control_plane": contract,
                        "observability_secrets": {
                            "telegram": {"relay_auth_token": relay_auth}
                        },
                    },
                    "tasks": [
                        {
                            "name": "Exercise private relay authority contract",
                            "ansible.builtin.include_tasks": str(
                                ROLE / "tasks/alerting-secret-contract.yml"
                            ),
                        },
                        {
                            "name": "Forbidden write after invalid authority",
                            "ansible.builtin.copy": {
                                "content": "forbidden",
                                "dest": str(marker),
                            },
                        },
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    completed = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode != 0
    assert "changed=0" in completed.stdout
    assert not marker.exists()
    assert relay_auth not in completed.stdout + completed.stderr


def test_distinct_relay_auth_contract_passes_without_changes(tmp_path: Path) -> None:
    contract = complete_contract()
    relay_auth = "d4" * 32
    playbook = tmp_path / "secret-contract.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "secret authority acceptance",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {
                        "observability_control_plane": contract,
                        "observability_secrets": {
                            "telegram": {"relay_auth_token": relay_auth}
                        },
                    },
                    "tasks": [
                        {
                            "name": "Exercise private relay authority contract",
                            "ansible.builtin.include_tasks": str(
                                ROLE / "tasks/alerting-secret-contract.yml"
                            ),
                        }
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    completed = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "changed=0" in completed.stdout
    assert relay_auth not in completed.stdout + completed.stderr


def test_alerting_contract_refuses_a_noncanonical_webhook_timeout(
    tmp_path: Path,
) -> None:
    contract = complete_contract()
    contract["alerting"]["telegram"]["webhook_timeout"] = "0s"
    playbook = tmp_path / "contract.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "timeout refusal",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {
                        "observability_control_plane": contract,
                        "role_path": str(ROLE),
                    },
                    "tasks": [
                        {
                            "name": "Exercise production alerting contract",
                            "ansible.builtin.include_tasks": str(
                                ROLE / "tasks/alerting-contract.yml"
                            ),
                        }
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    completed = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode != 0
    assert "changed=0" in completed.stdout


def test_relay_is_in_authority_snapshot_rollback_and_disable_boundaries() -> None:
    snapshot = _load_python(
        "observability_authority_snapshot",
        ROLE / "files/observability-authority-snapshot.py",
    )
    assert "observability-telegram-relay.service" in snapshot.SERVICES
    assert (
        "etc/observability-control-plane/credentials/telegram-relay-auth-token"
        in snapshot.FIXED
    )
    assert "etc/systemd/system/observability-telegram-relay.service" in snapshot.FIXED
    assert "usr/local/libexec/observability-telegram-relay" in snapshot.FIXED

    authority = (ROLE / "tasks/alerting-authority.yml").read_text()
    for expected in (
        "Materialize primary Telegram relay credentials for systemd",
        "Install bounded primary Telegram relay",
        "Require authenticated loopback Telegram relay readiness",
        "Require restored authenticated Telegram relay readiness",
        "observability-telegram-relay.service",
    ):
        assert expected in authority
    for source in (ROLE / "tasks/alerting-disable.yml", ROLE / "tasks/disable.yml"):
        text = source.read_text()
        assert "observability-telegram-relay.service" in text
        assert "/usr/local/libexec/observability-telegram-relay" in text


def test_relay_systemd_unit_has_only_credentials_and_bounded_network_authority() -> (
    None
):
    unit = (ROLE / "templates/observability-telegram-relay.service.j2").read_text()
    assert "DynamicUser=yes" in unit
    assert "LoadCredential=telegram-bot-token:" in unit
    assert "LoadCredential=telegram-relay-auth-token:" in unit
    assert "Environment=" not in unit
    assert "127.0.0.1:19095" in unit
    assert "TimeoutStopSec=20s" in unit
    for boundary in (
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "PrivateDevices=true",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet=",
    ):
        assert boundary in unit


def _load_python(name: str, path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_alertmanager_v0281_enforces_the_webhook_request_timeout(
    tmp_path: Path,
) -> None:
    binary_value = os.environ.get("ALERTMANAGER_BIN", "")
    if not binary_value:
        pytest.skip("ALERTMANAGER_BIN is required for the native notifier test")
    binary = Path(binary_value)
    amtool = binary.with_name("amtool")
    version = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True, check=True
    )
    assert "version 0.28.1" in version.stdout + version.stderr

    request_started = threading.Event()
    deadline_observed = threading.Event()
    received: list[dict[str, object]] = []

    class WebhookStub(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            assert self.headers["Authorization"] == "Bearer relay-fixture-token"
            assert self.headers["Content-Type"] == "application/json"
            length = int(self.headers.get("Content-Length", "0"))
            received.append(json.loads(self.rfile.read(length)))
            request_started.set()
            time.sleep(5)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    stub = ThreadingHTTPServer(("127.0.0.1", 0), WebhookStub)
    stub.daemon_threads = True
    stub_thread = threading.Thread(target=stub.serve_forever, daemon=True)
    stub_thread.start()
    alertmanager_port = _free_port()
    credential = tmp_path / "relay-auth"
    credential.write_text("relay-fixture-token")
    contract = _contract()
    contract["alerting"]["telegram"].update(
        {
            "relay_url": f"http://127.0.0.1:{stub.server_port}/alert",
            "relay_auth_credential": str(credential),
            "webhook_timeout": "1s",
        }
    )
    config = yaml.safe_load(
        render_template(
            ROLE / "templates/observability-alertmanager.yml.j2",
            {"observability_control_plane": contract},
        )
    )
    config["route"]["group_wait"] = "0s"
    config_path = tmp_path / "alertmanager.yml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    checked = subprocess.run(
        [str(amtool), "check-config", str(config_path)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr

    process = subprocess.Popen(
        [
            str(binary),
            f"--config.file={config_path}",
            f"--storage.path={tmp_path / 'data'}",
            f"--web.listen-address=127.0.0.1:{alertmanager_port}",
            "--cluster.listen-address=",
            "--log.level=info",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_lines: list[str] = []

    def capture_logs() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            log_lines.append(line)
            if "configured webhook timeout reached (1s)" in line:
                deadline_observed.set()

    log_thread = threading.Thread(target=capture_logs, daemon=True)
    log_thread.start()
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(
                    "Alertmanager exited before ready: " + "".join(log_lines)
                )
            try:
                with request.urlopen(
                    f"http://127.0.0.1:{alertmanager_port}/-/ready", timeout=0.2
                ) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("Alertmanager did not become ready")
        alert = json.dumps(
            [
                {
                    "labels": {
                        "alertname": "FixtureTimeout",
                        "environment": "staging",
                        "node": "fixture-node",
                        "instance": f"fixture-{index}",
                        "component": "control-plane",
                        "policy": "none",
                        "profile": "none",
                        "vantage": "control",
                        "severity": "warning",
                    },
                    "annotations": {
                        "summary": "fixture",
                        "evidence_class": "fixture",
                        "runbook": "docs/OBSERVABILITY-OPERATIONS.md",
                        "source_generation": "c" * 40,
                    },
                }
                for index in range(7)
            ]
        ).encode()
        with request.urlopen(
            request.Request(
                f"http://127.0.0.1:{alertmanager_port}/api/v2/alerts",
                data=alert,
                headers={"Content-Type": "application/json"},
            ),
            timeout=2,
        ) as response:
            assert response.status == 200
        assert request_started.wait(timeout=2)
        started = time.monotonic()
        assert deadline_observed.wait(timeout=3)
        assert 0.5 <= time.monotonic() - started < 3
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        log_thread.join(timeout=1)
        stub.shutdown()
        stub.server_close()
        stub_thread.join(timeout=1)
    output = "".join(log_lines)
    assert received
    assert all(len(payload["alerts"]) == 5 for payload in received)
    capped = next(payload for payload in received if payload["truncatedAlerts"] == 2)
    relay = _relay()
    parsed = relay.parse_payload(json.dumps(capped).encode())
    assert len(relay.render_message(parsed)) <= 4096
    assert "relay-fixture-token" not in output
