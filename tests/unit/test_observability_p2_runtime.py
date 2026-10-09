"""Native read-only role preflight and recovery-pointer behavior; no fleet access."""

from __future__ import annotations

import copy
import hashlib
import os
import pwd
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLES = ROOT / "ansible/roles"
TLS = ROLES / "observability_control_plane/files/observability-tls-preflight.py"


def _run(argv, **kwargs):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60, **kwargs)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def authority(tmp_path):
    _run(
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
            "/CN=fixture-ca",
            "-keyout",
            str(tmp_path / "ca.key"),
            "-out",
            str(tmp_path / "ca.crt"),
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        ]
    )
    _run(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=node-fixture",
            "-keyout",
            str(tmp_path / "client.key"),
            "-out",
            str(tmp_path / "client.csr"),
        ]
    )
    extensions = tmp_path / "extensions"
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n"
    )
    _run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(tmp_path / "client.csr"),
            "-CA",
            str(tmp_path / "ca.crt"),
            "-CAkey",
            str(tmp_path / "ca.key"),
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            str(extensions),
            "-out",
            str(tmp_path / "client.crt"),
        ]
    )
    return {
        name: (tmp_path / name).read_text()
        for name in ("ca.crt", "client.crt", "client.key")
    }


@pytest.mark.native_runtime
@pytest.mark.parametrize("existing", [False, True])
def test_complete_agent_check_mode_never_publishes_private_candidates(
    tmp_path, authority, existing
):
    assert sys.platform == "linux" and os.geteuid() == 0
    owned = Path("/etc/observability-agent")
    queue = Path("/var/lib/observability-agent")
    assert (
        not owned.exists() and not queue.exists()
    ), "requires disposable empty role namespace"
    created_account = False
    if existing:
        try:
            account = pwd.getpwnam("observability-agent")
        except KeyError:
            _run(
                [
                    "useradd",
                    "--system",
                    "--no-create-home",
                    "--shell",
                    "/usr/sbin/nologin",
                    "observability-agent",
                ]
            )
            created_account = True
            account = pwd.getpwnam("observability-agent")
        (owned / "credentials/generations").mkdir(parents=True)
        (queue / "queue").mkdir(parents=True, mode=0o700)
        os.chown(queue / "queue", account.pw_uid, account.pw_gid)
        (owned / "queue-receiver.url").write_text(
            "https://10.23.0.2:9443/remote-write/v1/nodes/node-fixture\n"
        )
        (owned / "queue-receiver.url").chmod(0o600)
        (owned / "retained-fixture").write_text("must survive check mode")

    def snapshot():
        return {
            str(path): (
                path.lstat().st_mode,
                (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else None
                ),
            )
            for directory in (owned, queue)
            for path in (
                [directory, *directory.rglob("*")] if directory.exists() else []
            )
        }

    before = snapshot()
    values = yaml.safe_load(
        (ROLES / "observability_agent/defaults/main.yml").read_text()
    )
    values["observability_agent"].update(
        enabled=True,
        version="v1.153.0",
        release_urls={
            "amd64": "https://github.com/VictoriaMetrics/VictoriaMetrics/releases/download/v1.153.0/vmutils-linux-amd64-v1.153.0.tar.gz",
            "arm64": "https://github.com/VictoriaMetrics/VictoriaMetrics/releases/download/v1.153.0/vmutils-linux-arm64-v1.153.0.tar.gz",
        },
        linux_amd64_sha256="85aea24a4829cf26033d810aceb7888070bd4eaff321357168ff6db24bf7c00c",
        linux_arm64_sha256="8153c4feb73564215950a299c803d5c1e974772cd34b8c162d43ea2c5b516df5",
        node_id="node-fixture",
        environment="ci",
        receiver_origin="https://10.23.0.2:9443",
        receiver_address="10.23.0.2",
    )
    values.update(
        observability_contract={"schema_version": 1, "credential_mode": "systemd"},
        observability_alert_policy=yaml.safe_load(
            (ROOT / "ansible/group_vars/all.yml").read_text()
        )["observability_alert_policy"],
        node_manifest_source_revision="a" * 40,
        node_manifest_deployable_digest="b" * 64,
        observability_push={
            "node_id": "node-fixture",
            "origin": "https://10.23.0.2:9444",
            "kinds": ["node"],
            "services": ["observability-agent.service"],
            "expected_nodes": ["node-fixture"],
            "prometheus_origin": "http://127.0.0.1:9090",
            "relay_origin": "http://127.0.0.1:19095",
            "relay_auth_path": "/etc/observability-control-plane/credentials/telegram-relay-auth-token",
            "textfile_dir": "/var/lib/node_exporter/textfile",
        },
        observability_kuma_secrets={
            "schema_version": 1,
            "tls": {"ca_pem": authority["ca.crt"]},
            "push_monitors": [
                {
                    "node_id": "node-fixture",
                    "kind": "node",
                    "token": "NodeFixtureToken00000000000000001",
                }
            ],
        },
        observability_secrets={
            "receiver_ca_pem": authority["ca.crt"],
            "senders": [
                {
                    "node_id": "node-fixture",
                    "certificate_pem": authority["client.crt"],
                    "private_key_pem": authority["client.key"],
                }
            ],
        },
        ansible_python_interpreter=sys.executable,
    )
    play = tmp_path / "check.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": values,
                    "roles": [{"role": "observability_agent"}],
                }
            ]
        )
    )
    play.chmod(0o600)
    environment = dict(
        os.environ,
        ANSIBLE_ROLES_PATH=str(ROLES),
        ANSIBLE_CONFIG=str(ROOT / "ansible/ansible.cfg"),
    )
    try:
        result = _run(
            ["ansible-playbook", "-i", "localhost,", "--check", str(play)],
            env=environment,
        )
        assert (
            "Validate sender TLS authority without filesystem candidates"
            in result.stdout
        )
        candidate = result.stdout.split(
            "Create private observability credential candidate]", 1
        )[1].split("TASK [", 1)[0]
        assert "skipping: [localhost]" in candidate
        assert snapshot() == before
        for private in authority.values():
            assert private not in result.stdout + result.stderr
    finally:
        for directory in (owned, queue):
            if directory.exists():
                shutil.rmtree(directory)
        if created_account:
            _run(["userdel", "observability-agent"])


def test_unchanged_collector_generation_preserves_prior_pointer(tmp_path):
    tasks = yaml.safe_load(
        (ROLES / "observability_control_plane/tasks/enable.yml").read_text()
    )

    def flatten(rows):
        for row in rows:
            yield row
            for key in ("block", "rescue", "always"):
                yield from flatten(row.get(key, []))

    task = copy.deepcopy(
        next(
            row
            for row in flatten(tasks)
            if row.get("name")
            == "Preserve ready control-plane generation before activation"
        )
    )
    # Alternate filesystem ownership is test isolation only; the role remains root-owned.
    task["ansible.builtin.file"].update(
        owner=str(os.geteuid()), group=str(os.getegid())
    )
    generations = tmp_path / "generations"
    generations.mkdir()
    old = generations / ("a" * 64 + ".yml")
    current = generations / ("b" * 64 + ".yml")
    old.write_text("old")
    current.write_text("current")
    previous = tmp_path / "previous.yml"
    previous.symlink_to(old)
    before = previous.lstat().st_ino
    values = {
        "ansible_python_interpreter": sys.executable,
        "observability_control_plane": {
            "config_root": str(tmp_path),
            "service_group": str(os.getegid()),
        },
        "_observability_current": {
            "stat": {"exists": True, "lnk_source": str(current)}
        },
        "_observability_generation": "b" * 64,
    }
    play = tmp_path / "pointer.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": values,
                    "tasks": [task],
                }
            ]
        )
    )
    result = _run(["ansible-playbook", "-i", "localhost,", str(play)])
    assert "failed=0" in result.stdout
    assert previous.readlink() == old and previous.lstat().st_ino == before


@pytest.mark.native_runtime
@pytest.mark.parametrize("mutation", [None, "identity", "purpose", "private_key"])
def test_memory_only_tls_preflight_validates_actual_authority(
    tmp_path, authority, mutation
):
    import json

    request = {
        "certificate": authority["client.crt"],
        "private_key": authority["client.key"],
        "ca": authority["ca.crt"],
        "purpose": "sslclient",
        "identity": "node-fixture",
    }
    if mutation == "identity":
        request["identity"] = "different-node"
    elif mutation == "purpose":
        request["purpose"] = "sslserver"
    elif mutation == "private_key":
        request["private_key"] = (tmp_path / "ca.key").read_text()
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    result = subprocess.run(
        [sys.executable, str(TLS)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == (0 if mutation is None else 2)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    assert "Traceback" not in result.stderr
    assert all(
        value not in result.stdout + result.stderr for value in authority.values()
    )


@pytest.mark.native_runtime
def test_real_policy_daemon_idle_heartbeat_and_enabled_disabled_idempotence(tmp_path):
    import re
    import time

    assert sys.platform == "linux" and os.geteuid() == 0
    unit = Path("/etc/systemd/system/policy-ratelimit.service")
    script = Path("/usr/local/bin/policy-ratelimit.py")
    metrics = Path("/var/lib/node_exporter/textfile/vpn_policy_ratelimit.prom")
    log = Path("/var/log/xray/access.log")
    assert all(
        not path.exists() for path in (unit, script, metrics, log)
    ), "requires disposable policy namespace"
    metrics.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    log.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    log.write_text("")
    values = yaml.safe_load((ROLES / "policy-ratelimit/defaults/main.yml").read_text())
    # Direct role invocation enables the daemon; no firewall mutation is needed
    # for this idle-source publication/lifecycle case.
    values.update(
        ansible_python_interpreter=sys.executable,
        vpn={"enable_policy_ratelimit": False},
    )
    play = tmp_path / "policy.yml"
    environment = dict(
        os.environ,
        ANSIBLE_ROLES_PATH=str(ROLES),
        ANSIBLE_CONFIG=str(ROOT / "ansible/ansible.cfg"),
    )

    def converge(enabled):
        values["policy_ratelimit_role_enabled"] = enabled
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": values,
                        "roles": [{"role": "policy-ratelimit"}],
                    }
                ]
            )
        )
        return _run(
            ["ansible-playbook", "-i", "localhost,", str(play)], env=environment
        )

    def timestamp():
        if not metrics.exists():
            return None
        content = metrics.read_text()
        assert "vpn_policy_ratelimit_input_available 1" in content
        assert "vpn_policy_ratelimit_input_progress_total 0" in content
        return int(
            re.search(
                r"^vpn_policy_ratelimit_last_success_timestamp_seconds (\d+)$",
                content,
                re.MULTILINE,
            ).group(1)
        )

    try:
        converge(True)
        first = None
        deadline = time.monotonic() + 10
        while first is None and time.monotonic() < deadline:
            first = timestamp()
            time.sleep(0.2)
        assert first is not None
        latest = first
        deadline = time.monotonic() + 20
        while latest == first and time.monotonic() < deadline:
            latest = timestamp()
            time.sleep(0.2)
        assert latest > first
        _run(["systemctl", "is-active", "--quiet", "policy-ratelimit.service"])
        converge(False)
        assert all(not path.exists() for path in (unit, script, metrics))
        assert (
            subprocess.run(
                ["systemctl", "is-active", "--quiet", "policy-ratelimit.service"]
            ).returncode
            != 0
        )
        repeated = converge(False)
        assert "changed=0" in repeated.stdout
    finally:
        if unit.exists():
            subprocess.run(
                ["systemctl", "stop", "policy-ratelimit.service"], capture_output=True
            )
            subprocess.run(
                ["systemctl", "disable", "policy-ratelimit.service"],
                capture_output=True,
            )
        for path in (unit, script, metrics, log):
            path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)


@pytest.mark.native_runtime
@pytest.mark.parametrize("existing", [False, True])
def test_retained_receiver_complete_check_mode_never_mutates_authority(
    tmp_path, authority, existing
):
    import ssl

    assert sys.platform == "linux" and os.geteuid() == 0
    owned = Path("/etc/observability-deadman")
    assert not owned.exists(), "requires disposable retained-receiver namespace"
    extensions = tmp_path / "server-extensions"
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:deadman.fixture.invalid\n"
    )
    for name, subject, extension_file in (
        ("pulse", "deadman.fixture.invalid", extensions),
        ("control", "deadman-control", tmp_path / "extensions"),
    ):
        _run(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                "/CN=" + subject,
                "-keyout",
                str(tmp_path / (name + ".key")),
                "-out",
                str(tmp_path / (name + ".csr")),
            ]
        )
        _run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(tmp_path / (name + ".csr")),
                "-CA",
                str(tmp_path / "ca.crt"),
                "-CAkey",
                str(tmp_path / "ca.key"),
                "-CAcreateserial",
                "-days",
                "1",
                "-extfile",
                str(extension_file),
                "-out",
                str(tmp_path / (name + ".crt")),
            ]
        )
    control = (tmp_path / "control.crt").read_text()
    fingerprint = lambda certificate: hashlib.sha256(
        ssl.PEM_cert_to_DER_cert(certificate)
    ).hexdigest()
    values = yaml.safe_load(
        (ROLES / "observability_deadman/defaults/main.yml").read_text()
    )
    receiver = values["observability_deadman"]
    receiver.update(
        enabled=True,
        source_generation="a" * 40,
        reverse_health_url="https://control.fixture.invalid:9443/observability/v1/deadman/reverse",
    )
    receiver["pulse_tls"]["server_name"] = "deadman.fixture.invalid"
    receiver["telegram"].update(chat_id="123456789", topic_id=0)
    receiver["reverse_health_tls"].update(
        ca_pem=authority["ca.crt"],
        client_cert_pem=control,
        client_key_pem=(tmp_path / "control.key").read_text(),
        client_cn="deadman-control",
        client_cert_fingerprint_sha256=fingerprint(control),
        ca_fingerprint_sha256=fingerprint(authority["ca.crt"]),
    )
    values.update(
        ansible_python_interpreter=sys.executable,
        observability_contract={"schema_version": 1, "credential_mode": "systemd"},
        observability_deadman_secrets={
            "schema_version": 1,
            "pulse_token": "PulseFixtureToken00000000000000001",
            "telegram": {"bot_token": "TelegramFixtureToken00000000000000002"},
            "pulse_tls": {
                "ca_pem": authority["ca.crt"],
                "server_cert_pem": (tmp_path / "pulse.crt").read_text(),
                "server_key_pem": (tmp_path / "pulse.key").read_text(),
            },
        },
    )
    if existing:
        (owned / "credentials").mkdir(parents=True, mode=0o700)
        (owned / "credentials/pulse-token").write_text(
            "prior authority remains untouched"
        )
        (owned / "credentials/pulse-token").chmod(0o600)

    def snapshot():
        return {
            str(path): (
                path.lstat().st_mode,
                path.lstat().st_uid,
                path.lstat().st_gid,
                path.lstat().st_ino,
                path.lstat().st_mtime_ns,
                (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else None
                ),
            )
            for path in ([owned, *owned.rglob("*")] if owned.exists() else [])
        }

    before = snapshot()
    play = tmp_path / "receiver-check.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": values,
                    "roles": [{"role": "observability_deadman"}],
                }
            ]
        )
    )
    play.chmod(0o600)
    environment = dict(
        os.environ,
        ANSIBLE_ROLES_PATH=str(ROLES),
        ANSIBLE_CONFIG=str(ROOT / "ansible/ansible.cfg"),
    )
    try:
        result = _run(
            ["ansible-playbook", "-i", "localhost,", "--check", str(play)],
            env=environment,
        )
        assert "Read pulse TLS server certificate before host mutation" in result.stdout
        assert snapshot() == before
        assert all(
            value not in result.stdout + result.stderr for value in authority.values()
        )
    finally:
        if owned.exists():
            shutil.rmtree(owned)
