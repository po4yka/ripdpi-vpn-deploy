"""Actual candidate nginx -t preserves shared temp ownership under the unit floor."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def run(*args, check=True):
    result = subprocess.run(
        args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def test_real_candidate_validation_keeps_shared_nginx_temps_read_only():
    assert sys.platform == "linux" and os.geteuid() == 0
    assert shutil.which("nginx")
    suffix = uuid.uuid4().hex[:10]
    unit = "vpn-p2-cdn-candidate-" + suffix + ".service"
    unit_path = Path("/etc/systemd/system") / unit
    base = Path("/var/lib") / ("vpn-p2-cdn-candidate-" + suffix)
    assert not base.exists() and not unit_path.exists()
    base.mkdir(mode=0o700)
    # A fixture-owned read-only binding makes the original chown failure
    # deterministic, independent of another test's default worker identity.
    shared_fixture = base / "shared-nginx"
    shared_fixture.mkdir(mode=0o755)
    for name in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
        (shared_fixture / name).mkdir(mode=0o700)
    fixture_pid = base / "nginx.pid"
    fixture_pid.touch()
    shared = Path("/var/lib/nginx")
    before = {
        str(path): (path.stat().st_uid, path.stat().st_gid, path.stat().st_mode)
        for path in shared.rglob("*")
        if path.is_dir()
    }
    source = (
        ROOT / "ansible/roles/cdn-front/templates/refresh-cf-prefixes.sh.j2"
    ).read_text()
    candidate = source.split('cat > "$WORK/nginx-candidate.conf" <<EOF\n', 1)[1].split(
        "\nEOF", 1
    )[0]
    script = base / "validate.sh"
    script.write_text(
        '#!/bin/bash\nset -euo pipefail\nWORK="$(mktemp -d -t cdn-prefixes.native.XXXXXX)"\ntrap \'rm -rf "$WORK"\' EXIT\nprintf "set_real_ip_from 198.51.100.0/24;\\n" > "$WORK/cloudflare.real_ip.new"\ncat > "$WORK/nginx-candidate.conf" <<EOF\n'
        + candidate
        + '\nEOF\n/usr/sbin/nginx -t -q -c "$WORK/nginx-candidate.conf"\n'
    )
    script.chmod(0o750)
    template = (
        ROOT / "ansible/roles/cdn-front/templates/cdn-front-prefix-refresh.service.j2"
    ).read_text()
    rendered = template.replace("{{ cdn_front.cf_prefix_dir }}", str(base)).replace(
        "/run/nginx.pid", str(fixture_pid)
    )
    rendered = rendered.replace("Requires=nginx.service\n", "").replace(
        "After=network-online.target nginx.service", "After=network-online.target"
    )
    rendered = rendered.replace(
        "ExecStart=/usr/local/sbin/cdn-front-refresh-cf-prefixes",
        "ExecStart=" + str(script),
    )
    rendered += "\nBindReadOnlyPaths=" + str(shared_fixture) + ":/var/lib/nginx\n"
    unit_path.write_text(rendered)
    try:
        run("systemctl", "daemon-reload")
        started = run("systemctl", "start", unit, check=False)
        if started.returncode:
            evidence = run(
                "journalctl",
                "-u",
                unit,
                "--no-pager",
                "--output=cat",
                "--lines=10",
                check=False,
            ).stdout
            raise AssertionError(evidence)
        state = run(
            "systemctl", "show", unit, "--property=Result,ExecMainStatus"
        ).stdout
        assert "Result=success" in state and "ExecMainStatus=0" in state
        after = {
            str(path): (path.stat().st_uid, path.stat().st_gid, path.stat().st_mode)
            for path in shared.rglob("*")
            if path.is_dir()
        }
        assert (
            after == before
        ), "candidate must not chown or create shared distro temp directories"

        rejected = script.read_text()
        for directive in (
            "client_body_temp_path",
            "proxy_temp_path",
            "fastcgi_temp_path",
            "uwsgi_temp_path",
            "scgi_temp_path",
        ):
            rejected = (
                "\n".join(
                    line
                    for line in rejected.splitlines()
                    if not line.strip().startswith(directive + " ")
                )
                + "\n"
            )
        script.write_text(rejected)
        failed = run("systemctl", "start", unit, check=False)
        assert (
            failed.returncode != 0
        ), "original shared-temp candidate must fail under the same floor"
        journal = run(
            "journalctl",
            "-u",
            unit,
            "--no-pager",
            "--output=cat",
            "--lines=10",
            check=False,
        ).stdout
        assert "Read-only file system" in journal and "/var/lib/nginx/body" in journal
    finally:
        run("systemctl", "stop", unit, check=False)
        unit_path.unlink(missing_ok=True)
        run("systemctl", "daemon-reload", check=False)
        shutil.rmtree(base)
