"""Actual pair publication/recovery and systemd HTTP asset-consumer adoption.

The disposable consumer exposes its startup pair; this is not Xray routing proof.
"""

from __future__ import annotations
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_geodata_recovers_killed_pair_and_adopts_actual_consumer():
    assert sys.platform == "linux" and os.geteuid() == 0
    suffix = uuid.uuid4().hex[:12]
    base = Path("/var/lib") / ("p2-geodata-recovery-" + suffix)
    base.mkdir(mode=0o755)
    installed = base / "installed"
    installed.mkdir(mode=0o755)
    sources = base / "sources"
    sources.mkdir(mode=0o700)
    unit = "p2-geodata-recovery-" + suffix + ".service"
    unit_file = Path("/etc/systemd/system") / unit
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    for name in ("geosite.dat", "geoip.dat"):
        (installed / name).write_bytes(("old-" + name).encode())
        (installed / name).chmod(0o640)
    consumer = base / "consumer.py"
    consumer.write_text(
        "from http.server import BaseHTTPRequestHandler,HTTPServer\nfrom pathlib import Path\n"
        f"root=Path({str(installed)!r})\n"
        "body=b'|'.join((root/name).read_bytes() for name in ('geosite.dat','geoip.dat'))\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(body)\n"
        " def log_message(self,*args): pass\n"
        f"HTTPServer(('127.0.0.1',{port}),Handler).serve_forever()\n"
    )
    unit_file.write_text(
        f"[Service]\nType=simple\nExecStart=/usr/bin/python3 {consumer}\n"
    )
    unit_file.chmod(0o644)
    activator = base / "activate.sh"
    activator.write_text(
        (ROOT / "ansible/roles/geodata/templates/vpn-xray-geodata-activate.sh.j2")
        .read_text()
        .replace("xray.service", unit)
    )
    activator.chmod(0o750)
    barrier = base / "barrier"
    helper = base / "publisher.py"
    helper.write_text(
        "import importlib.util,json,os,signal,subprocess,sys\nfrom pathlib import Path\n"
        f"spec=importlib.util.spec_from_file_location('publisher',{str(ROOT / 'ansible/roles/geodata/files/geodata_publish.py')!r})\n"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
        f"barrier=Path({str(barrier)!r});phase=sys.argv[1]\n"
        'def pause():\n barrier.write_text("ready");os.kill(os.getpid(),signal.SIGSTOP)\n'
        "def activate():\n"
        f" result=subprocess.run([{str(activator)!r}],capture_output=True,timeout=10)\n"
        ' if result.returncode:\n  print("activation_rc="+str(result.returncode)+" phase="+phase,file=sys.stderr);raise RuntimeError("actual-activation")\n'
        ' return result.stdout.strip()==b"active"\n'
        "m.activate=activate\noriginal=m.persist\n"
        "def persist(path,data):\n original(path,data)\n"
        ' if data.get("phase")==phase: pause()\n'
        "m.persist=persist\noriginal_replace=m.replace\n"
        "def replace(source,destination,**kwargs):\n original_replace(source,destination,**kwargs)\n"
        f' if phase=="first-write" and str(destination)=={str(installed / "geosite.dat")!r}: pause()\n'
        "m.replace=replace\n"
        "print(json.dumps(m.publish(json.load(sys.stdin))))\n"
    )

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(sources), **kwargs)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def run(argv):
        result = subprocess.run(argv, capture_output=True, timeout=20)
        assert result.returncode == 0, "actual native service command failed"

    def document(label):
        for name in ("geosite.dat", "geoip.dat"):
            (sources / name).write_bytes((label + "-" + name).encode())
        return dict(
            install_dir=str(installed),
            sources={
                name: dict(
                    url=f"http://127.0.0.1:{server.server_port}/{name}",
                    sha256=hashlib.sha256((sources / name).read_bytes()).hexdigest(),
                )
                for name in ("geosite.dat", "geoip.dat")
            },
        )

    def publish(value, phase="none"):
        return subprocess.run(
            [sys.executable, str(helper), phase],
            input=json.dumps(value),
            text=True,
            capture_output=True,
            timeout=30,
        )

    def body():
        deadline = time.monotonic() + 5
        while True:
            try:
                return urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=1
                ).read()
            except OSError:
                assert time.monotonic() < deadline, "actual consumer never became ready"
                time.sleep(0.05)

    def kill(value, phase):
        barrier.unlink(missing_ok=True)
        child = subprocess.Popen(
            [sys.executable, str(helper), phase],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            child.stdin.write(json.dumps(value))
            child.stdin.close()
            deadline = time.monotonic() + 20
            while not barrier.exists():
                assert child.poll() is None, (
                    "publisher failed before actual boundary: "
                    + child.stderr.read(1500)
                    if child.poll() is not None
                    else ""
                )
                assert time.monotonic() < deadline
                time.sleep(0.02)
            child.kill()
            assert child.wait(timeout=5) == -9
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()

    try:
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "start", unit])
        assert body() == b"old-geosite.dat|old-geoip.dat"
        for phase in ("first-write", "activating", "activated"):
            value = document(phase)
            kill(value, phase)
            result = publish(value)
            assert result.returncode == 0, "known interrupted pair must recover"
            assert json.loads(result.stdout)["changed"] is True
            assert body() == (phase + "-geosite.dat|" + phase + "-geoip.dat").encode()
            result = publish(value)
            assert (
                result.returncode == 0 and json.loads(result.stdout)["changed"] is False
            )
            # Respect the real systemd default restart burst window between
            # deliberate multi-restart faults; do not relax its guard.
            time.sleep(11)
        value = document("recovery-death")
        kill(value, "activating")
        kill(value, "recovering")
        assert publish(value).returncode == 0
        assert body() == b"recovery-death-geosite.dat|recovery-death-geoip.dat"
        (installed / ".geodata-activated.json").unlink()
        result = publish(value)
        assert result.returncode == 0 and json.loads(result.stdout)["changed"] is True
        assert body() == b"recovery-death-geosite.dat|recovery-death-geoip.dat"
        # A hash-current receipt cannot leave known asset metadata unreadable to
        # the unprivileged Xray account. Check actual kernel access as nobody.
        for name in ("geosite.dat", "geoip.dat"):
            (installed / name).chmod(0o600)
        read = [
            "runuser",
            "-u",
            "nobody",
            "--",
            "/usr/bin/python3",
            "-c",
            "from pathlib import Path;import sys;Path(sys.argv[1]).read_bytes()",
            str(installed / "geoip.dat"),
        ]
        assert subprocess.run(read, capture_output=True, timeout=5).returncode != 0
        fixed = publish(value)
        assert fixed.returncode == 0 and json.loads(fixed.stdout)["changed"] is True
        assert all(
            (installed / name).stat().st_mode & 0o777 == 0o644
            for name in ("geosite.dat", "geoip.dat")
        )
        assert subprocess.run(read, capture_output=True, timeout=5).returncode == 0
        assert body() == b"recovery-death-geosite.dat|recovery-death-geoip.dat"
        repeated = publish(value)
        assert (
            repeated.returncode == 0 and json.loads(repeated.stdout)["changed"] is False
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=10)
        unit_file.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=10)
        shutil.rmtree(base)
