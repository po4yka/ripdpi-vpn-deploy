"""Read the OpenTofu state of one PROVIDER/ENV through scripts/terraform-env.sh.

State lives encrypted in the remote backend; `state pull` decrypts it in
memory. Callers keep the bytes in memory and never write them to disk.
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts/terraform-env.sh"
MAX_STATE_BYTES = 16 * 1024 * 1024


class StateError(RuntimeError):
    pass


def pull(provider: str, environment: str, *, env=None, timeout: float = 120) -> bytes | None:
    """Return the current state bytes, or None for a workspace without state.

    A missing workspace, a backend or decryption failure and an oversized state
    all raise StateError; none of them is reported as empty.
    """
    child = dict(os.environ if env is None else env)
    child.update(PROVIDER=provider, ENV=environment, TF_IN_AUTOMATION="1", TF_INPUT="0")
    try:
        process = subprocess.Popen([str(WRAPPER), "state", "pull"], cwd=ROOT, env=child,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        raise StateError("state-pull-failed") from None
    def kill():
        # The wrapper's tofu child keeps the pipe open; stop the whole session.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)

    timer = threading.Timer(timeout, kill)
    timer.start()
    try:
        raw = process.stdout.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            kill()
            raise StateError("state-too-large")
        status = process.wait()
    finally:
        timer.cancel()
        process.stdout.close()
        if process.poll() is None:
            kill()
            process.wait()
    if status != 0:
        raise StateError("state-pull-failed")
    return raw if raw.strip() else None
