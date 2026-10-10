"""Real SSH key authentication with fixed command and denied PTY/forwarding."""

from __future__ import annotations
import base64
import importlib.util
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import time
import uuid
import pytest

from template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def run(*argv, check=True):
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def test_explicit_account_authenticates_only_the_forced_key_command():
    assert os.geteuid() == 0 and shutil.which("sshd")
    suffix = uuid.uuid4().hex[:10]
    user = "vpnptest" + suffix
    base = Path("/var/lib") / ("vpn-p2-ssh-" + suffix)
    base.mkdir(mode=0o755)
    process = None
    created = False
    try:
        home = base / "home"
        run(
            "useradd",
            "--no-create-home",
            "--home-dir",
            str(home),
            "--shell",
            "/bin/sh",
            user,
        )
        created = True
        run("usermod", "--password", "*", user)
        identity = pwd.getpwnam(user)
        home.mkdir(mode=0o750)
        os.chown(home, identity.pw_uid, identity.pw_gid)
        sshdir = home / ".ssh"
        sshdir.mkdir(mode=0o700)
        os.chown(sshdir, identity.pw_uid, identity.pw_gid)
        private = base / "client_key"
        host = base / "host_key"
        for key in (private, host):
            run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key))
        source = (
            ROOT / "ansible/roles/real-vps-awg-nat/templates/server-authorized-key.j2"
        ).read_text()
        assert (
            'command="/usr/bin/sudo -n /usr/local/libexec/ripdpi-real-vps-awg-nat-server --forced"'
            in source
        )
        authorized = source.replace(
            "{{ real_vps_awg_nat_secrets.sentinel_ssh_public_key }}",
            private.with_suffix(".pub").read_text().strip(),
        ).replace(
            "/usr/bin/sudo -n /usr/local/libexec/ripdpi-real-vps-awg-nat-server --forced",
            "/usr/bin/printf authorized",
        )
        path = sshdir / "authorized_keys"
        path.write_text(authorized)
        path.chmod(0o600)
        os.chown(path, identity.pw_uid, identity.pw_gid)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        cfg = base / "config"
        cfg.mkdir(mode=0o755)
        fragments = cfg / "sshd_config.d"
        fragments.mkdir(mode=0o755)
        (cfg / "sshd_config").write_text(
            f"HostKey {host}\nListenAddress 127.0.0.1\nUsePAM no\nPidFile {base}/sshd.pid\nInclude {fragments}/*.conf\nSubsystem sftp /usr/lib/openssh/sftp-server\n"
        )
        (fragments / "10-cloud-init-hardening.conf").write_text(
            f"Port {port}\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\n"
        )
        (fragments / "20-ansible-hardening.conf").write_text("X11Forwarding no\n")
        spec = importlib.util.spec_from_file_location(
            "sshd_ownership", ROOT / "ansible/roles/baseline/files/sshd_ownership.py"
        )
        planner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(planner)

        intent = render_template(
            ROOT / "ansible/roles/baseline/templates/sshd_config.d-hardening.conf.j2",
            dict(
                ansible_user="deploy",
                baseline_ssh_extra_allowed_users=[user],
                security_controls={"ssh_allow_tcp_forwarding": True},
            ),
        ).encode()
        context = {
            "user": user,
            "host": "sentinel.example.test",
            "addr": "127.0.0.1",
            "laddr": "127.0.0.1",
            "lport": port,
        }
        plan = planner.build_baseline_plan(cfg, contexts=[context], hardening=intent)
        for relative, pair in plan["files"].items():
            (cfg / relative).write_bytes(base64.b64decode(pair["after"]["data_b64"]))
        planner.assert_effective(plan, cfg, phase="after")
        process = subprocess.Popen(
            ["/usr/sbin/sshd", "-D", "-e", "-f", str(cfg / "sshd_config")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        args = [
            "ssh",
            "-i",
            str(private),
            "-p",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + str(base / "known_hosts"),
            user + "@127.0.0.1",
        ]
        (base / "known_hosts").write_text(
            f"[127.0.0.1]:{port} " + host.with_suffix(".pub").read_text()
        )
        shell = run(*args, "printf unauthorized")
        assert shell.stdout == "authorized" and "unauthorized" not in shell.stdout
        terminal = run(*args[:-1], "-tt", args[-1], "printf unauthorized", check=False)
        assert (
            "PTY allocation request failed" in terminal.stderr
            and "unauthorized" not in terminal.stdout
        )
        forwarding = run(*args[:-1], "-W", "127.0.0.1:9", args[-1], check=False)
        assert (
            forwarding.returncode != 0
            and "administratively prohibited" in forwarding.stderr
        )
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
        if created:
            run("userdel", user, check=False)
        shutil.rmtree(base)
