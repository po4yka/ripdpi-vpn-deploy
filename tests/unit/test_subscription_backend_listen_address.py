"""The delivery backend must stay behind nginx on loopback."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "ansible/roles/subscription-host/tasks/enable.yml"


@pytest.mark.parametrize("address, accepted", [
    (None, True), ("127.0.0.1", True), ("::1", True), ("0.0.0.0", False), ("10.0.0.5", False), ("::", False),
])
def test_role_refuses_a_non_loopback_backend_address(tmp_path, address, accepted):
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required to evaluate the role guard"
    guard = next(task for task in yaml.safe_load(TASKS.read_text())
                 if task["name"] == "Require a loopback address for the delivery backend")
    subscription = {} if address is None else {"bootstrap_listen_addr": address}
    play = [{"hosts": "localhost", "gather_facts": False, "become": False,
             "vars": {"subscription": subscription}, "tasks": [guard]}]
    playbook = tmp_path / "guard.yml"
    playbook.write_text(yaml.safe_dump(play))
    result = subprocess.run([executable, "-i", "localhost,", "-c", "local", str(playbook)],
                            capture_output=True, text=True, cwd=tmp_path, check=False)
    assert (result.returncode == 0) is accepted, result.stdout[-400:]
