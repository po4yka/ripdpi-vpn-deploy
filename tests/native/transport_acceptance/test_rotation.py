"""Actual logrotate must recover the running exact Xray and fresh client traffic."""

import importlib.util
from pathlib import Path
import subprocess

import pytest

from native_common import ROOT
from template_render import render_template

pytestmark = pytest.mark.native_runtime


def test_nonempty_native_log_rotation_recovers_authenticated_xray(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "four_rotation_lab",
        ROOT / "tests/integration/transport_runtime_acceptance/fixture.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with module.Lab() as lab:
        assert lab.converge("xray") == 0
        from transport_runtime_accept import Adapter, fields, read_parameters

        parameters = read_parameters()
        log = Path("/var/log/xray/access.log")
        assert log.stat().st_size > 0, "real-authenticated-Xray-log-empty"
        before = fields("xray.service")["MainPID"]
        policy = tmp_path / "logrotate.conf"
        policy.write_text(
            render_template(
                ROOT / "ansible/roles/monitoring/templates/logrotate-xray.j2",
                lab.context,
            )
        )
        observed = subprocess.run(
            ["logrotate", "--force", "--state", str(tmp_path / "state"), str(policy)],
            capture_output=True,
            timeout=90,
        )
        assert observed.returncode == 0, "native-logrotate-recovery-refused"
        assert fields("xray.service")["ActiveState"] == "active"
        assert fields("xray.service")["MainPID"] != before
        Adapter(
            [],
            parameters["probe_url"],
            parameters["expected_status"],
            parameters["timeout"],
            parameters["clients"],
        ).ready()
        assert any(log.parent.glob("access.log.1*"))
