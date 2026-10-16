"""Actual session-escaping workers remain owned after their launcher exits."""

import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from native_common import ROOT

pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize("kill_owner", [False, True])
def test_native_scope_reclaims_separate_session_and_preserves_foreign_worker(tmp_path, kill_owner):
    spec = importlib.util.spec_from_file_location(
        "owned_orchestrator_lab", ROOT / "tests/integration/transport_runtime_acceptance/fixture.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    identity = tmp_path / "child-pid"
    source = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True);"
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid));"
        "time.sleep(60) if sys.argv[2]=='True' else None"
    )
    foreign = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
    try:
        with fixture.owned_orchestrator(
            [sys.executable, "-c", source, str(identity), str(kill_owner)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ) as (owner, _scope):
            deadline = time.monotonic() + 10
            while not identity.exists():
                assert time.monotonic() < deadline, "native-descendant-not-started"
                time.sleep(.05)
            child = int(identity.read_text())
            assert os.getsid(child) == child
            if kill_owner:
                os.killpg(owner.pid, signal.SIGKILL)
                assert owner.wait(timeout=5) == -signal.SIGKILL
            else:
                assert owner.wait(timeout=5) == 0
        deadline = time.monotonic() + 5
        while os.path.exists(Path("/proc") / str(child) / "exe"):
            assert time.monotonic() < deadline, "native-descendant-cleanup-unconfirmed"
            time.sleep(.05)
        assert foreign.poll() is None
    finally:
        foreign.terminate()
        foreign.wait(timeout=5)
