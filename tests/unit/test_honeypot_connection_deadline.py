"""Honeypot connections must hold a worker slot only for a bounded time.

The per-recv timeout reset bug let a dribbling reader pin a slot
indefinitely; the absolute monotonic deadline computed from accept time
bounds the total hold. Slot-exhaustion closes must be counted and
surfaced in the Prometheus textfile instead of closing silently.
"""

from __future__ import annotations

import importlib.util
import re
import socket
import sys
import threading
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "honeypot" / "templates" / "honeypot.py.j2"

renderer_spec = importlib.util.spec_from_file_location(
    "honeypot_deadline_renderer", RENDERER
)
renderer = importlib.util.module_from_spec(renderer_spec)
sys.modules[renderer_spec.name] = renderer
renderer_spec.loader.exec_module(renderer)


def _metric(text: str, name: str) -> int:
    match = re.search(rf"^{re.escape(name)} (\d+)$", text, re.MULTILINE)
    assert match is not None
    return int(match.group(1))


def _render_module(tmp_path: Path):
    variables = renderer.merge_render_vars()
    variables["honeypot"] = {
        **variables["honeypot"],
        "log_dir": str(tmp_path / "log"),
        "textfile_dir": str(tmp_path / "textfile"),
        "connection_deadline_seconds": 1,
    }
    source = renderer.render_template(TEMPLATE, variables)
    module_path = tmp_path / "rendered_honeypot.py"
    module_path.write_text(source, encoding="utf-8")

    spec = importlib.util.spec_from_file_location(
        "rendered_honeypot_deadline", module_path
    )
    honeypot = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = honeypot
    spec.loader.exec_module(honeypot)
    return honeypot


def test_slow_reader_is_bounded_by_total_deadline(tmp_path: Path, monkeypatch) -> None:
    honeypot = _render_module(tmp_path)

    parent, child = socket.socketpair()
    stop = threading.Event()

    def dribble() -> None:
        # One byte well inside any single recv timeout: under the old
        # per-recv reset this keeps the handler alive until 512 bytes.
        child.settimeout(0.5)
        while not stop.is_set():
            try:
                child.sendall(b"x")
            except OSError:
                return
            time.sleep(0.25)

    peer = threading.Thread(target=dribble, daemon=True)
    peer.start()
    try:
        start = time.monotonic()
        honeypot._handle(parent, ("192.0.2.7", 4444))
        elapsed = time.monotonic() - start
    finally:
        stop.set()
        parent.close()
        child.close()

    # Deadline renders as 1s; allow scheduler slack but far below the
    # unbounded dribble duration.
    assert elapsed < 4.0, f"slow reader held the slot {elapsed:.2f}s"


def test_slot_exhaustion_drops_are_counted_and_exported(
    tmp_path: Path, monkeypatch
) -> None:
    honeypot = _render_module(tmp_path)

    # Exhaust every slot before any connection arrives.
    honeypot._workers = type(honeypot._workers)(0)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    port = listener.getsockname()[1]

    loop = threading.Thread(target=honeypot._accept_loop, args=(listener,), daemon=True)
    loop.start()
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        time.sleep(0.4)
    finally:
        client.close()
        listener.close()

    assert honeypot._slot_exhaustion_drops == 1

    honeypot._flush_textfile()
    metrics = (tmp_path / "textfile" / "vpn_honeypot.prom").read_text(encoding="utf-8")
    assert _metric(metrics, "vpn_honeypot_slot_exhaustion_drops_total") == 1
