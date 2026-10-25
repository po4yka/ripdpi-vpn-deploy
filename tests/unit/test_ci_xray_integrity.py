"""Execute the CI installer with real ZIP/hash tools and a local download fixture."""

import hashlib
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import zipfile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github/actions/install-xray/action.yml"


def installer():
    return yaml.safe_load(ACTION.read_text())["runs"]["steps"][0]


def test_ci_xray_consumers_share_one_reviewed_pin():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for job in ("python-validators", "unit-tests"):
        steps = workflow["jobs"][job]["steps"]
        installs = [s for s in steps if s.get("uses") == "./.github/actions/install-xray"]
        assert len(installs) == 1
        assert "with" not in installs[0]
    assert "Xray-linux-64.zip" not in (ROOT / ".github/workflows/ci.yml").read_text()
    pin = installer()["env"]
    example = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    assert pin["XRAY_VERSION"] == example["xray"]["version"]
    assert len(pin["XRAY_SHA256"]) == 64
    assert set(pin["XRAY_SHA256"]) <= set("0123456789abcdef")


@pytest.mark.parametrize("case", [
    "valid", "corrupt", "download-error", "version-drift", "runtime-error",
    "timeout-recovered", "timeout-exhausted", "timeout-corrupt",
])
def test_installer_never_executes_or_installs_unverified_bytes(tmp_path, case):
    step = installer()
    repo = tmp_path / "repo"
    (repo / "secrets").mkdir(parents=True)
    version = "v0.0.0" if case == "version-drift" else step["env"]["XRAY_VERSION"]
    (repo / "secrets/prod.secrets.example.yaml").write_text(
        yaml.safe_dump({"xray": {"version": version}})
    )
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as fixture:
        fixture.writestr("xray", '#!/bin/sh\necho executed >> "$EXEC_LOG"\nexit ' +
                         ("7" if case == "runtime-error" else "0") + "\n")
        fixture.writestr("geoip.dat", b"fixture geoip")
        fixture.writestr("geosite.dat", b"fixture geosite")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if case in {"corrupt", "timeout-corrupt"}:
        with archive.open("ab") as stream:
            stream.write(b"tampered")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/usr/bin/env python3\nimport os, pathlib, sys\n'
        'pathlib.Path(os.environ["DOWNLOAD_LOG"]).write_text("called")\n'
        'args = sys.argv[1:]\n'
        'url = "https://github.com/XTLS/Xray-core/releases/download/" + '
        'os.environ["XRAY_VERSION"] + "/Xray-linux-64.zip"\n'
        'args[args.index(url)] = os.environ["DOWNLOAD_URL"]\n'
        'os.execv(os.environ["REAL_CURL"], [os.environ["REAL_CURL"], *args, '
        '"--max-time", "0.5", "--retry-delay", "1", "--noproxy", "127.0.0.1"])\n'
    )
    curl.chmod(0o755)
    sudo = bin_dir / "sudo"
    sudo.write_text(
        '#!/usr/bin/env python3\nimport os, subprocess, sys\n'
        'args = sys.argv[1:]\n'
        'assert args[:2] == ["install", "-m"] and args[2] in {"0755", "0644"}\n'
        'assert args[-1] in {"/usr/local/bin/xray", "/usr/local/bin"}\n'
        'args[-1] = args[-1].replace("/usr/local/bin", os.environ["INSTALL_ROOT"])\n'
        'subprocess.run(args, check=True)\n'
    )
    sudo.chmod(0o755)
    runner_temp = tmp_path / "runner temp"
    runner_temp.mkdir()
    install_root = tmp_path / "installed"
    install_root.mkdir()
    installed = install_root / "xray"
    installed.write_text("existing runtime")
    attempts = []

    class Download(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            attempts.append(self.path)
            if case == "timeout-exhausted" or (case.startswith("timeout-") and len(attempts) == 1):
                time.sleep(1)
                self.close_connection = True
                return
            if case == "download-error":
                self.send_error(404)
                return
            data = archive.read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Download)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = dict(os.environ, **step["env"])
    env.update(XRAY_SHA256=digest, PATH=f"{bin_dir}:{os.environ['PATH']}",
               RUNNER_TEMP=str(runner_temp), INSTALL_ROOT=str(install_root),
               EXEC_LOG=str(tmp_path / "executed"),
               DOWNLOAD_LOG=str(tmp_path / "downloaded"),
               REAL_CURL=shutil.which("curl"),
               DOWNLOAD_URL=f"http://127.0.0.1:{server.server_port}/xray.zip")
    try:
        result = subprocess.run(["bash", "-c", step["run"]], cwd=repo, env=env,
                                capture_output=True, text=True, timeout=15)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert (result.returncode == 0) == (case in {"valid", "timeout-recovered"}), result.stderr
    if case in {"timeout-recovered", "timeout-corrupt"}:
        assert len(attempts) == 2
    elif case == "timeout-exhausted":
        assert result.returncode == 28
        assert len(attempts) == 4
    elif case == "download-error":
        assert result.returncode == 22
        assert len(attempts) == 1
    assert (tmp_path / "executed").exists() == (case in {"valid", "runtime-error", "timeout-recovered"})
    if case in {"valid", "timeout-recovered"}:
        with zipfile.ZipFile(archive) as fixture:
            for name in ("xray", "geoip.dat", "geosite.dat"):
                assert (install_root / name).read_bytes() == fixture.read(name)
    else:
        assert installed.read_text() == "existing runtime"
    if case in {"corrupt", "download-error", "timeout-exhausted", "timeout-corrupt"}:
        assert not list(runner_temp.rglob("xray"))
    if case == "version-drift":
        assert not (tmp_path / "downloaded").exists()
