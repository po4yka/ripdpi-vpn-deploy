"""Actual pinned P0/P1/Hysteria clients; final kernel/WARP cases have separate owners."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime
spec = importlib.util.spec_from_file_location("transport_owned_native_fixture", ROOT / "tests/integration/transport_destination_boundary/fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.mark.parametrize("profile", ["p0", "p1", "hysteria"])
def test_actual_authenticated_frontend_preserves_guarded_tcp_udp_and_dns(profile):
    if sys.platform != "linux" or os.geteuid() != 0 or os.environ.get("TRANSPORT_NATIVE_ISOLATED") != "1":
        pytest.fail("frontend native acceptance requires explicitly owned isolated Linux root authority")
    for name in ("xray", "hysteria", "nginx", "ip", "systemd-run", "systemctl", "useradd", "userdel", "openssl"):
        if not shutil.which(name):
            pytest.fail("exact frontend native prerequisite is unavailable")
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    assert pins["xray"]["version"].lstrip("v") in fixture.command([shutil.which("xray"), "version"])
    assert pins["hysteria"]["version"].lstrip("v") in fixture.command([shutil.which("hysteria"), "version"])
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend(profile)
        port = stack.start_client(profile)
        time.sleep(.5)
        stack.run_driver(port)
        negative = stack.start_client(profile, True)
        time.sleep(.5)
        stack.run_driver(negative, True)
        # A fresh authenticated positive probe follows wrong-auth refusal.
        stack.run_driver(port)
        counts = json.loads((stack.driver_state / "counts.json").read_text())
        assert counts["private_tcp"] == counts["private_udp"] == counts["private_dns"] == 0
        assert counts["public_tcp"] > 0 and counts["public_udp"] > 0
        assert counts["dns_tcp_txt"] >= 2 and counts["dns_udp_txt"] >= 2
        helper_logs = fixture.command(["journalctl", "--unit", stack.token + "-normalizer", "--no-pager", "-o", "cat"])
        assert all(listener["password"] not in helper_logs for listener in stack.config["listeners"])
        assert "192.0.2.80" not in helper_logs and "mixed4.test" not in helper_logs
    finally:
        stack.close()
