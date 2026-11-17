"""Finite coverage silence for one node while a deploy restarts its transports."""
from __future__ import annotations

import contextlib
import datetime
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ("DEPLOY_SILENCE_OWNER", "DEPLOY_SILENCE_COLLECTOR", "DEPLOY_SILENCE_ENVIRONMENT")
MAIN_SECONDS = 7500  # per-host site.yml timeout plus the create round trip
TAIL_SECONDS = 300  # next heartbeat + alert `for` + keep_firing_for


def _warn(category):
    print("deploy: warning: maintenance silence " + category, file=sys.stderr)


def _operator():
    spec = importlib.util.spec_from_file_location("deploy_silence_operator", ROOT / "scripts/observability-operator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(environment, node, seconds):
    start = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return json.dumps({
        "schema_version": 1,
        "reason": "deploy-transport-restart",
        "starts_at": start.isoformat().replace("+00:00", "Z"),
        "ends_at": (start + datetime.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
        "matchers": {"environment": environment, "node": node, "component": "observability-external-coverage"},
    }, sort_keys=True).encode()


@contextlib.contextmanager
def coverage_silence(node, environ=None):
    """Silence the node's external coverage alert for the enclosed mutation.

    Every silence failure only warns: monitoring must never block a deploy.
    """
    environ = os.environ if environ is None else environ
    values = [environ.get(name, "") for name in SETTINGS]
    if not any(values) or not node:
        yield
        return
    if not all(values):
        _warn("configuration incomplete")
        yield
        return
    owner, collector, environment = values
    inventory = Path(environ.get("DEPLOY_SILENCE_INVENTORY") or ROOT / "ansible/inventory/generated.ini")
    known_hosts = Path(environ.get("DEPLOY_KNOWN_HOSTS") or Path.home() / ".ssh/known_hosts")
    try:
        operator = _operator()
    except Exception:  # noqa: BLE001 - categorical warning boundary
        _warn("unavailable")
        yield
        return

    def call(**kwargs):
        try:
            return operator.maintenance_silence(inventory, collector, known_hosts, owner, **kwargs)
        except Exception:  # noqa: BLE001 - remote diagnostics may carry private paths
            return None

    main = call(request=_request(environment, str(node), MAIN_SECONDS))
    if main is None:
        _warn("not created")
        yield
        return
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        # Deleting first on success would release the suppressed firing alert.
        if succeeded and call(request=_request(environment, str(node), TAIL_SECONDS)) is None:
            _warn("tail not created")
        if call(silence_id=main) is None:
            _warn("not deleted; it expires at its finite end")
