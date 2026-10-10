"""Real nginx/systemd TLS publication, boot ownership and compensation proof."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import pathlib
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def run(*args, check=True):
    result = subprocess.run(
        list(args), check=False, capture_output=True, text=True, timeout=45
    )
    if check and result.returncode:
        raise AssertionError(result.stderr)
    return result


def test_real_nginx_complete_tls_boot_and_failed_activation_compensation():
    assert (
        sys.platform == "linux" and os.geteuid() == 0
    ), "requires disposable native Linux root/systemd lane"
    assert shutil.which("nginx") and shutil.which(
        "openssl"
    ), "requires native nginx and openssl"
    HELPER = (ROOT / "ansible/roles/nginx-xhttp/files/nginx_transaction.py").read_text()
    suffix = uuid.uuid4().hex[:12]
    unit = "vpn-p2-nginx-" + suffix + ".service"
    unit_file = pathlib.Path("/etc/systemd/system") / unit
    base = pathlib.Path("/var/lib") / ("vpn-p2-nginx-" + suffix)
    assert not base.exists() and not unit_file.exists()
    base.mkdir(mode=0o700)
    config = base / "config"
    config.mkdir(mode=0o750)
    logs = base / "logs"
    logs.mkdir(mode=0o750)
    tls = config / "tls"
    tls.mkdir(mode=0o750)
    helper = base / "helper.py"
    helper.write_text(HELPER)
    helper.chmod(0o750)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    run(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(tls / "server.key"),
        "-out",
        str(tls / "server.crt"),
        "-subj",
        "/CN=transaction.example.test",
        "-addext",
        "subjectAltName=IP:127.0.0.1",
        "-days",
        "1",
    )
    certificate = (tls / "server.crt").read_bytes()
    key = (tls / "server.key").read_bytes()
    (tls / "server.crt").unlink()
    (tls / "server.key").unlink()
    runtime = "/run/vpn-p2-nginx-" + suffix
    unit_text = f'[Unit]\nDescription=Owned nginx transaction regression\n[Service]\nType=simple\nLoadCredential=server.crt:{tls}/server.crt\nLoadCredential=server.key:{tls}/server.key\nRuntimeDirectory=vpn-p2-nginx-{suffix}\nExecStart=/usr/sbin/nginx -c {config}/nginx.conf -g "daemon off;"\nPrivateTmp=true\nProtectSystem=strict\nNoNewPrivileges=true\nRestrictNamespaces=true\nReadWritePaths={logs}\n[Install]\nWantedBy=multi-user.target\n'

    def configuration(body):
        return f'pid {runtime}/nginx.pid;\nerror_log {logs}/error.log;\nevents {{}}\nhttp {{ access_log {logs}/access.log; server {{ listen 127.0.0.1:{port} ssl; ssl_certificate /run/credentials/{unit}/server.crt; ssl_certificate_key /run/credentials/{unit}/server.key; location / {{ return 200 "{body}"; }} }} }}\n'

    def file(path, data, mode):
        return {
            "path": str(path),
            "kind": "file",
            "content_b64": base64.b64encode(
                data if isinstance(data, bytes) else data.encode()
            ).decode(),
            "mode": mode,
            "uid": 0,
            "gid": 0,
        }

    def request(body, private_key=key, unit_data=unit_text, check=False):
        return {
            "owner": "native-regression",
            "roots": [str(config)],
            "files": [
                file(config / "nginx.conf", configuration(body), "0640"),
                file(tls / "server.crt", certificate, "0644"),
                file(tls / "server.key", private_key, "0600"),
                file(unit_file, unit_data, "0644"),
            ],
            "validate_argv": [
                "/usr/sbin/nginx",
                "-t",
                "-c",
                str(config / "nginx.conf"),
            ],
            "unit": unit,
            "activation": "restart",
            "check": check,
            "credential_root": str(tls),
            "runtime_directories": [runtime],
            "activate_inactive": True,
            "desired_enabled": True,
        }

    def publish(document):
        return subprocess.run(
            ["/usr/bin/python3", str(helper)],
            input=json.dumps(document),
            text=True,
            capture_output=True,
            timeout=90,
        )

    def body():
        context = ssl.create_default_context(cafile=str(tls / "server.crt"))
        for attempt in range(30):
            try:
                return (
                    urllib.request.urlopen(
                        f"https://127.0.0.1:{port}/", context=context, timeout=1
                    )
                    .read()
                    .decode()
                )
            except OSError as error:
                last = type(error).__name__ + ": " + str(error)
                time.sleep(0.1)
        print(
            run(
                "systemctl",
                "show",
                unit,
                "--property=ActiveState,Result,ExecMainStatus",
                check=False,
            ).stdout
        )
        print(
            run(
                "journalctl",
                "-u",
                unit,
                "--no-pager",
                "--output=cat",
                "--lines=10",
                check=False,
            ).stdout
        )
        raise AssertionError("owned nginx did not answer: " + last)

    def snapshot():
        return {
            str(path): path.read_bytes()
            for path in [
                config / "nginx.conf",
                tls / "server.crt",
                tls / "server.key",
                unit_file,
            ]
        }

    try:
        before_root = run(
            "findmnt", "-n", "-o", "TARGET,PROPAGATION", "-T", "/run"
        ).stdout
        predictive = publish(request("old", check=True))
        assert predictive.returncode == 0, predictive.stderr
        assert not unit_file.exists() and not (config / "nginx.conf").exists()
        fresh_failed = publish(
            request(
                "old",
                unit_data=unit_text.replace(
                    "/usr/sbin/nginx -c "
                    + str(config)
                    + '/nginx.conf -g "daemon off;"',
                    "/bin/false",
                ),
            )
        )
        assert fresh_failed.returncode == 1
        assert not unit_file.exists() and not (config / "nginx.conf").exists()
        assert not os.path.lexists(
            pathlib.Path("/etc/systemd/system/multi-user.target.wants") / unit
        )
        assert not (
            pathlib.Path("/var/lib/vpn-nginx-publication") / unit / "pending.json"
        ).exists()
        first = publish(request("old"))
        assert first.returncode == 0, first.stderr
        assert body() == "old"
        assert run("systemctl", "is-enabled", unit).stdout.strip() == "enabled"
        prior = snapshot()
        fifo = config / "unrelated-fifo"
        os.mkfifo(fifo, 0o600)
        preparation_failed = publish(request("old"))
        assert preparation_failed.returncode == 1
        assert snapshot() == prior and body() == "old"
        assert not (
            pathlib.Path("/var/lib/vpn-nginx-publication") / unit / "pending.json"
        ).exists()
        fifo.unlink()
        preparation_retry = publish(request("old"))
        assert preparation_retry.returncode == 0, preparation_retry.stderr
        assert json.loads(preparation_retry.stdout)["changed"] is False
        invalid = publish(request("new", private_key=b"not-a-private-key"))
        assert invalid.returncode == 1
        assert snapshot() == prior and body() == "old"
        repeated = publish(request("old"))
        assert repeated.returncode == 0, repeated.stderr
        assert json.loads(repeated.stdout)["changed"] is False
        valid = publish(request("new"))
        assert valid.returncode == 0, valid.stderr
        assert body() == "new"
        prior = snapshot()
        failed = publish(
            request(
                "rejected",
                unit_data=unit_text.replace(
                    "/usr/sbin/nginx -c "
                    + str(config)
                    + '/nginx.conf -g "daemon off;"',
                    "/bin/false",
                ),
            )
        )
        assert failed.returncode == 1
        assert snapshot() == prior and body() == "new"
        assert run("systemctl", "is-enabled", unit).stdout.strip() == "enabled"
        run("systemctl", "disable", unit)
        failed = publish(
            request(
                "rejected",
                unit_data=unit_text.replace(
                    "/usr/sbin/nginx -c "
                    + str(config)
                    + '/nginx.conf -g "daemon off;"',
                    "/bin/false",
                ),
            )
        )
        assert failed.returncode == 1
        assert snapshot() == prior and body() == "new"
        assert (
            run("systemctl", "is-enabled", unit, check=False).stdout.strip()
            == "disabled"
        )
        assert (
            run("findmnt", "-n", "-o", "TARGET,PROPAGATION", "-T", "/run").stdout
            == before_root
        )
        # Interrupt the real helper around permanent publication and activation.
        # The wrapper only pauses after actual helper operations; no success is faked.
        wrapper = base / "interrupt.py"
        barrier = base / "barrier"
        wrapper.write_text(
            "import importlib.util,json,os,signal,sys\n"
            "from pathlib import Path\n"
            f"spec=importlib.util.spec_from_file_location('transaction',{str(helper)!r})\n"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
            "phase=sys.argv[1];barrier=Path(sys.argv[2])\n"
            "def pause():\n barrier.write_text('ready');os.kill(os.getpid(),signal.SIGSTOP)\n"
            "original_apply=m.apply\n"
            "def apply(path,row,created):\n original_apply(path,row,created)\n"
            f" if phase=='first-write' and str(path)=={str(config / 'nginx.conf')!r}: pause()\n"
            "m.apply=apply\n"
            "original_persist=m.persist\n"
            "def persist(path,data):\n original_persist(path,data)\n"
            " if path.name=='pending.json' and data.get('phase')==phase: pause()\n"
            "m.persist=persist\n"
            "print(json.dumps(m.publish(json.load(sys.stdin))))\n"
        )

        def interrupted(document, phase):
            barrier.unlink(missing_ok=True)
            process = subprocess.Popen(
                ["/usr/bin/python3", str(wrapper), phase, str(barrier)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                process.stdin.write(json.dumps(document))
                process.stdin.close()
                deadline = time.monotonic() + 40
                while not barrier.exists():
                    assert (
                        process.poll() is None
                    ), "actual transaction exited before interruption boundary"
                    assert (
                        time.monotonic() < deadline
                    ), "actual transaction never reached interruption boundary"
                    time.sleep(0.05)
                process.kill()
                assert process.wait(timeout=5) == -9
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

        for phase in ("prepared", "first-write", "activating", "activated"):
            requested = "recovered-" + phase
            interrupted(request(requested), phase)
            assert (
                Path("/var/lib/vpn-nginx-publication") / unit / "pending.json"
            ).exists()
            resumed = publish(request(requested))
            assert resumed.returncode == 0, resumed.stderr
            assert json.loads(resumed.stdout)["changed"] is True
            assert body() == requested
            assert not list(
                (Path("/var/lib/vpn-nginx-publication") / unit).glob("candidate-*")
            )
            repeated = publish(request(requested))
            assert (
                repeated.returncode == 0
                and json.loads(repeated.stdout)["changed"] is False
            )
        interrupted(request("recover-after-recovery-death"), "activating")
        interrupted(request("recover-after-recovery-death"), "recovering")
        resumed = publish(request("recover-after-recovery-death"))
        assert resumed.returncode == 0, resumed.stderr
        assert body() == "recover-after-recovery-death"
        reload_unit = unit_text.replace(
            "PrivateTmp=true", "ExecReload=/bin/kill -HUP $MAINPID\nPrivateTmp=true"
        )
        baseline = publish(request("reload-baseline", unit_data=reload_unit))
        assert baseline.returncode == 0 and body() == "reload-baseline", baseline.stderr
        reload_request = request("reload-positive", unit_data=reload_unit)
        reload_request["activation"] = "reload"
        positive = publish(reload_request)
        assert positive.returncode == 0 and body() == "reload-positive", positive.stderr
        receipt_path = (
            Path("/var/lib/vpn-nginx-publication")
            / unit
            / "native-regression.activated.json"
        )
        old_receipt = receipt_path.read_bytes()
        adoption_wrapper = base / "adoption.py"
        adoption_marker = base / "reload-ack"
        release = base / "release-hup"
        adoption_wrapper.write_text(
            "import importlib.util,json,os,signal,subprocess,sys\nfrom pathlib import Path\n"
            f"spec=importlib.util.spec_from_file_location('transaction',{str(helper)!r})\n"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
            "original=m.command\n"
            "def command(argv):\n"
            f" if argv==['systemctl','reload',{unit!r}]:\n"
            f"  Path({str(adoption_marker)!r}).write_text('manager-ack')\n"
            "  if sys.argv[1]=='delayed':\n"
            f"   pid=original(['systemctl','show',{unit!r},'--property=MainPID','--value']).strip()\n"
            f'   code="import os,signal,time;from pathlib import Path;gate=Path({str(release)!r});deadline=time.monotonic()+5\\nwhile not gate.exists():\\n assert time.monotonic()<deadline;time.sleep(.02)\\nos.kill(int("+pid+"),signal.SIGHUP)"\n'
            "   subprocess.Popen(['/usr/bin/python3','-c',code],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
            "  return ''\n"
            " return original(argv)\n"
            "m.command=command\nprint(json.dumps(m.publish(json.load(sys.stdin))))\n"
        )
        desired = request("delayed-adopted", unit_data=reload_unit)
        desired["activation"] = "reload"
        delayed = subprocess.Popen(
            ["/usr/bin/python3", str(adoption_wrapper), "delayed"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            delayed.stdin.write(json.dumps(desired))
            delayed.stdin.close()
            deadline = time.monotonic() + 20
            while not adoption_marker.exists():
                assert delayed.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.02)
            time.sleep(0.2)
            assert receipt_path.read_bytes() == old_receipt
            assert body() == "reload-positive"
            assert (
                delayed.poll() is None
            ), "manager ack must not acknowledge worker adoption"
            release.write_text("release actual HUP")
            assert delayed.wait(timeout=20) == 0
            assert body() == "delayed-adopted"
            assert receipt_path.read_bytes() != old_receipt
        finally:
            if delayed.poll() is None:
                delayed.kill()
                delayed.wait(timeout=5)
            delayed.stdout.close()
            delayed.stderr.close()
        prior = snapshot()
        prior_receipt = receipt_path.read_bytes()
        denied = request("never-adopted", unit_data=reload_unit)
        denied["activation"] = "reload"
        rejected = subprocess.run(
            ["/usr/bin/python3", str(adoption_wrapper), "non-adoption"],
            input=json.dumps(denied),
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert rejected.returncode == 1
        assert snapshot() == prior and receipt_path.read_bytes() == prior_receipt
        assert body() == "delayed-adopted"
        # Missing receipt must adopt unchanged bytes rather than report a stale success.
        receipt = (
            Path("/var/lib/vpn-nginx-publication")
            / unit
            / "native-regression.activated.json"
        )
        receipt.unlink()
        adopted = publish(desired)
        assert adopted.returncode == 0 and json.loads(adopted.stdout)["changed"] is True
        print(
            json.dumps(
                {
                    "predictive_no_publication": True,
                    "credential_exact_namespace": True,
                    "valid_https_start": True,
                    "invalid_key_preserves_bytes_and_https": True,
                    "unchanged_is_idempotent": True,
                    "valid_restart_replaces_body": True,
                    "failed_activation_restores_complete_prior_tree_unit_https": True,
                    "parent_run_mount_preserved": True,
                }
            )
        )
    finally:
        run("systemctl", "stop", unit, check=False)
        run("systemctl", "disable", unit, check=False)
        unit_file.unlink(missing_ok=True)
        run("systemctl", "daemon-reload", check=False)
        state = pathlib.Path("/var/lib/vpn-nginx-publication") / unit
        if state.exists():
            shutil.rmtree(state)
        shutil.rmtree(base)
