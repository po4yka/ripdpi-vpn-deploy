"""Probe target absence always reaches shared recovery without starting nginx."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import ssl
import subprocess
import sys
import time
import uuid

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DISABLE = ROOT / "ansible/roles/probe-matrix-target/tasks/disable.yml"


def test_disabled_caller_has_unconditional_nginx_only_recovery_contract():
    tasks = yaml.safe_load(DISABLE.read_text())
    transaction = next(
        task
        for task in tasks
        if task.get("ansible.builtin.include_role", {}).get("tasks_from")
        == "transaction"
    )
    assert "when" not in transaction
    assert transaction["vars"]["nginx_transaction_roots"] == ["/etc/nginx"]
    assert transaction["vars"]["nginx_transaction_activate_inactive"] is False
    assert transaction["vars"]["nginx_transaction_desired_enabled"] is None
    assert {row["path"] for row in transaction["vars"]["nginx_transaction_files"]} == {
        "/etc/nginx/sites-enabled/probe-matrix-tls.conf",
        "/etc/nginx/sites-available/probe-matrix-tls.conf",
    }
    assert not any(
        task.get("register") == "_probe_matrix_retire_nginx" for task in tasks
    )


def run(argv, *, data=None, check=True):
    result = subprocess.run(
        argv, input=data, capture_output=True, text=True, timeout=90
    )
    if check:
        assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-1000:]
    return result


def disabled_role(base):
    play = base / "disabled.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {"probe_matrix_target_role_enabled": False},
                    "roles": [
                        {"role": str(ROOT / "ansible/roles/probe-matrix-target")}
                    ],
                }
            ]
        )
    )
    return run(["ansible-playbook", "-i", "localhost,", str(play)])


def unit_state():
    return run(
        ["systemctl", "show", "nginx.service", "--property=ActiveState,UnitFileState"]
    ).stdout


def prerequisites():
    assert os.geteuid() == 0 and sys.platform == "linux"
    for name in ("probe-matrix-xray.service", "probe-matrix-mtg.service"):
        assert (
            run(
                ["systemctl", "show", name, "--property=LoadState", "--value"]
            ).stdout.strip()
            == "not-found"
        )
    for path in (
        "/etc/nginx/sites-enabled/probe-matrix-tls.conf",
        "/etc/nginx/sites-available/probe-matrix-tls.conf",
        "/etc/probe-matrix",
    ):
        assert not os.path.lexists(
            path
        ), "fixture cannot overwrite retained probe authority"


@pytest.mark.native_runtime
def test_sigkill_after_both_vhosts_removed_then_actual_unchanged_disable_recovers_listener(
    tmp_path,
):
    prerequisites()
    before_fixture = unit_state()
    was_active = "ActiveState=active\n" in before_fixture
    suffix = uuid.uuid4().hex[:12]
    base = Path("/var/lib") / ("vpn-p2-probe-retire-" + suffix)
    base.mkdir(mode=0o700)
    key, certificate = base / "key.pem", base / "cert.pem"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-subj",
            "/CN=probe.example.test",
            "-addext",
            "subjectAltName=DNS:probe.example.test",
            "-days",
            "1",
        ]
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    available = Path("/etc/nginx/sites-available/probe-matrix-tls.conf")
    enabled = Path("/etc/nginx/sites-enabled/probe-matrix-tls.conf")
    helper = ROOT / "ansible/roles/nginx-xhttp/files/nginx_transaction.py"
    rows = [
        {
            "path": str(available),
            "kind": "file",
            "mode": "0644",
            "uid": 0,
            "gid": 0,
            "content_b64": base64.b64encode(
                f'server {{ listen 127.0.0.1:{port} ssl; ssl_certificate {certificate}; ssl_certificate_key {key}; location / {{ return 200 "probe-control"; }} }}\n'.encode()
            ).decode(),
        },
        {
            "path": str(enabled),
            "kind": "link",
            "target": str(available),
            "mode": "0777",
            "uid": 0,
            "gid": 0,
        },
    ]
    document = {
        "owner": "probe-matrix-target",
        "roots": ["/etc/nginx"],
        "files": rows,
        "validate_argv": ["/usr/sbin/nginx", "-t"],
        "unit": "nginx.service",
        "activation": "reload",
        "check": False,
        "credential_root": "",
        "runtime_directories": [],
        "activate_inactive": True,
        "desired_enabled": None,
        "prune_releases": None,
    }
    removal = {
        **document,
        "files": [
            {"path": str(enabled), "kind": "absent"},
            {"path": str(available), "kind": "absent"},
        ],
        "activate_inactive": False,
    }
    process = None

    def probe():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", port), timeout=2) as plain:
            with context.wrap_socket(
                plain, server_hostname="probe.example.test"
            ) as connection:
                connection.sendall(
                    b"GET / HTTP/1.1\r\nHost: probe.example.test\r\nConnection: close\r\n\r\n"
                )
                return b"200 OK" in connection.recv(4096)

    try:
        run([sys.executable, str(helper)], data=json.dumps(document))
        assert probe()
        prior_enabled = unit_state().split("UnitFileState=", 1)[1].splitlines()[0]
        barrier = base / "barrier"
        wrapper = base / "interrupt.py"
        wrapper.write_text(
            "import importlib.util,json,os,signal,sys\nfrom pathlib import Path\n"
            + f"s=importlib.util.spec_from_file_location('tx',{str(helper)!r});m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=m.apply\ndef apply(path,row,created):\n original(path,row,created)\n"
            + f" if str(path)=={str(available)!r} and row.get('kind')=='absent':\n  Path({str(barrier)!r}).write_text('removed');os.kill(os.getpid(),signal.SIGSTOP)\n"
            + "m.apply=apply\nprint(json.dumps(m.publish(json.load(sys.stdin))))\n"
        )
        process = subprocess.Popen(
            [sys.executable, str(wrapper)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.stdin.write(json.dumps(removal))
        process.stdin.close()
        deadline = time.monotonic() + 20
        while not barrier.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert not available.exists() and not enabled.exists()
        assert probe(), "fixture must retain real cached listener before adoption"
        pending = Path("/var/lib/vpn-nginx-publication/nginx.service/pending.json")
        assert pending.exists()
        process.kill()
        process.wait(timeout=5)
        process = None
        disabled_role(base)
        assert not pending.exists()
        assert not available.exists() and not enabled.exists()
        assert (
            unit_state().split("UnitFileState=", 1)[1].splitlines()[0] == prior_enabled
        )
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            except OSError:
                break
            assert time.monotonic() < deadline, "recovered disable kept listener"
            time.sleep(0.02)
        result = disabled_role(base)
        assert "changed=0" in result.stdout
    finally:
        if process is not None:
            process.kill()
            process.wait(timeout=5)
        try:
            disabled_role(base)
        finally:
            run(["systemctl", "start" if was_active else "stop", "nginx.service"])
            shutil.rmtree(base)
        assert unit_state() == before_fixture


@pytest.mark.native_runtime
def test_actual_fresh_disabled_caller_preserves_inactive_shared_nginx(tmp_path):
    prerequisites()
    was_active = "ActiveState=active\n" in unit_state()
    try:
        run(["systemctl", "stop", "nginx.service"])
        before = unit_state()
        result = disabled_role(tmp_path)
        assert unit_state() == before
        assert "ActiveState=inactive\n" in unit_state()
        assert "failed=0" in result.stdout
        assert not Path("/etc/probe-matrix").exists()
    finally:
        if was_active:
            run(["systemctl", "start", "nginx.service"])
