"""Execute the rendered rotation policy against real Xray and protocol traffic."""
from copy import deepcopy
from pathlib import Path
import subprocess
import time

import pytest

from scripts.template_render import render_template
from test_xhttp_endpoint_contract_native import fixture

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("protocol", ["p0", "p1"])
def test_real_nonempty_rotation_restores_authenticated_service_and_retains_inactive(protocol):
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend(protocol)
        client = stack.start_client(protocol)
        time.sleep(.5)
        stack.run_driver(client)
        unit = stack.token + "-frontend.service"
        before = fixture.command(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
        values = deepcopy(stack.values)
        values["vpn"]["enable_transport_egress"] = False
        values.update(xray_log_dir=str(stack.library / "logs"), xray_runtime_user=stack.users["x"], xray_runtime_group=stack.users["x"])
        policy = render_template(ROOT / "ansible/roles/monitoring/templates/logrotate-xray.j2", values)
        # The complete production policy runs against this invocation's owned
        # real service rather than acquiring the global deployed unit name.
        policy = policy.replace("xray.service", unit)
        config = stack.file("rotation.conf", policy)
        state = stack.library / "logrotate.state"
        assert (stack.library / "logs/access.log").stat().st_size > 0
        fixture.command(["logrotate", "--force", "--state", str(state), str(config)])
        after = fixture.command(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
        assert after != before and int(after) > 0
        time.sleep(.5)
        stack.run_driver(client)
        fixture.command(["systemctl", "stop", unit])
        with (stack.library / "logs/access.log").open("a") as stream:
            stream.write("owned inactive rotation case\n")
        fixture.command(["logrotate", "--force", "--state", str(state), str(config)])
        inactive = subprocess.run(["systemctl", "is-active", "--quiet", unit], capture_output=True, timeout=10)
        assert inactive.returncode != 0
    finally:
        stack.close()
