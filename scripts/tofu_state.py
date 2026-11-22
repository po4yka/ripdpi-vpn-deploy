"""Read the OpenTofu state of one PROVIDER/ENV through scripts/terraform-env.sh.

State lives encrypted in the remote backend; `state pull` decrypts it in
memory. Callers keep the bytes in memory and never write them to disk.
"""
from __future__ import annotations

import os
import subprocess
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
        result = subprocess.run([str(WRAPPER), "state", "pull"], cwd=ROOT, env=child,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise StateError("state-pull-failed") from None
    if result.returncode != 0:
        raise StateError("state-pull-failed")
    if len(result.stdout) > MAX_STATE_BYTES:
        raise StateError("state-too-large")
    return result.stdout if result.stdout.strip() else None
