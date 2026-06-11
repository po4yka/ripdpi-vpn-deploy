"""Render-check for the xray QUIC-outbound toggle (xray_block_quic_outbound).

Renders ansible/roles/xray/templates/config.json.j2 through the same path the
template render-check uses (scripts/check-templates-render.py), and asserts the
UDP/443 -> block routing rule is present when the toggle is on and absent when
off — in both cases producing valid JSON.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "xray" / "templates" / "config.json.j2"
CTR = REPO_ROOT / "scripts" / "check-templates-render.py"

_spec = importlib.util.spec_from_file_location("check_templates_render", CTR)
ctr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctr)


def _render(toggle: bool | None) -> dict:
    """Render config.json.j2 with the QUIC toggle set (or left at default)."""
    vars_ = ctr.merge_render_vars()
    if toggle is not None:
        vars_ = {**vars_, "xray_block_quic_outbound": toggle}
    text = ctr.render_template(TEMPLATE, vars_)
    return json.loads(text)  # also asserts the render is valid JSON


def _quic_block_rules(cfg: dict) -> list[dict]:
    return [
        r for r in cfg.get("routing", {}).get("rules", [])
        if r.get("network") == "udp"
        and str(r.get("port")) == "443"
        and r.get("outboundTag") == "block"
    ]


def test_quic_rule_present_when_toggle_on():
    rules = _quic_block_rules(_render(True))
    assert len(rules) == 1, "expected exactly one UDP/443 -> block rule when on"


def test_quic_rule_absent_when_toggle_off():
    assert _quic_block_rules(_render(False)) == []


def test_quic_rule_on_by_default():
    # No explicit override -> role default (true) -> rule present.
    assert len(_quic_block_rules(_render(None))) == 1


def test_config_is_valid_json_in_both_states():
    # _render() json.loads() already raises on invalid JSON; assert the rest of
    # the routing block is intact (the always-present default rule survives).
    for toggle in (True, False):
        cfg = _render(toggle)
        outbound_tags = {r.get("outboundTag") for r in cfg["routing"]["rules"]}
        assert "direct" in outbound_tags  # default freedom rule still there
        assert "block" in outbound_tags   # bittorrent/RFC1918 blackhole rules remain
