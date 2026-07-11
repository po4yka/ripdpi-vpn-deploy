"""Honeypot rolling gauges must age out events during idle periods."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "honeypot" / "templates" / "honeypot.py.j2"

renderer_spec = importlib.util.spec_from_file_location("honeypot_metrics_renderer", RENDERER)
renderer = importlib.util.module_from_spec(renderer_spec)
sys.modules[renderer_spec.name] = renderer
renderer_spec.loader.exec_module(renderer)


def _metric(text: str, name: str) -> int:
    match = re.search(rf"^{re.escape(name)} (\d+)$", text, re.MULTILINE)
    assert match is not None
    return int(match.group(1))


def test_rolling_gauges_expire_events_after_sixty_calendar_minutes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    variables = renderer.merge_render_vars()
    variables["honeypot"] = {
        **variables["honeypot"],
        "log_dir": str(tmp_path / "log"),
        "textfile_dir": str(tmp_path / "textfile"),
    }
    source = renderer.render_template(TEMPLATE, variables)
    module_path = tmp_path / "rendered_honeypot.py"
    module_path.write_text(source, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("rendered_honeypot", module_path)
    honeypot = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = honeypot
    spec.loader.exec_module(honeypot)

    monkeypatch.setattr(honeypot.time, "time", lambda: 120 * 60)
    assert honeypot._bump("192.0.2.1", None)

    monkeypatch.setattr(honeypot.time, "time", lambda: 179 * 60)
    honeypot._flush_textfile()

    metrics = (tmp_path / "textfile" / "vpn_honeypot.prom").read_text(encoding="utf-8")
    assert _metric(metrics, "vpn_honeypot_events_total") == 1
    assert _metric(metrics, "vpn_honeypot_events_last_minute") == 0
    assert _metric(metrics, "vpn_honeypot_events_60min") == 1

    monkeypatch.setattr(honeypot.time, "time", lambda: 180 * 60)
    honeypot._flush_textfile()

    metrics = (tmp_path / "textfile" / "vpn_honeypot.prom").read_text(encoding="utf-8")
    assert _metric(metrics, "vpn_honeypot_events_total") == 1
    assert _metric(metrics, "vpn_honeypot_events_last_minute") == 0
    assert _metric(metrics, "vpn_honeypot_events_60min") == 0
