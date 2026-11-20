"""Execute the rendered rotation policy against real Xray and protocol traffic."""
from copy import deepcopy
from pathlib import Path
import time

import pytest

from scripts.template_render import render_template
from test_xhttp_endpoint_contract_native import fixture

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("protocol", ["p0", "p1"])
def test_real_nonempty_rotation_keeps_the_process_and_its_sessions(protocol):
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend(protocol)
        socket_timeout = stack.values["watchdog"]["reality_probe_timeout"]
        client = stack.start_client(protocol)
        time.sleep(.5)
        stack.run_driver(client, socket_timeout=socket_timeout)
        unit = stack.token + "-frontend.service"
        before = fixture.command(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
        values = deepcopy(stack.values)
        values.update(xray_log_dir=str(stack.library / "logs"))
        policy = render_template(ROOT / "ansible/roles/monitoring/templates/logrotate-xray.j2", values)
        config = stack.file("rotation.conf", policy)
        state = stack.library / "logrotate.state"
        log = stack.library / "logs/access.log"
        size = log.stat().st_size
        assert size > 0
        fixture.command(["logrotate", "--force", "--state", str(state), str(config)])
        after = fixture.command(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
        assert after == before
        assert log.stat().st_size < size
        assert any(log.parent.glob("access.log.1*"))
        # The surviving process still serves and appends to the truncated file.
        stack.run_driver(client, socket_timeout=socket_timeout)
    finally:
        stack.close()
