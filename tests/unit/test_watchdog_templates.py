"""Rendered-artifact tests for authenticated watchdog REALITY probes."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.template_render import merge_render_vars, render_template


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "ansible" / "roles" / "watchdog" / "templates"


def _multi_cohort_vars() -> dict:
    vars_ = deepcopy(merge_render_vars())
    vars_["watchdog_reality_probes"] = [
        {
            "name": "primary",
            "port": 443,
            "flow_mode": "vision",
            "finalmask": False,
            "clients": ["watchdog"],
        },
        {
            "name": "alternate",
            "port": 8443,
            "flow_mode": "mux",
            "finalmask": True,
            "clients": ["watchdog"],
        },
    ]
    return vars_


def test_probe_config_maps_every_cohort_to_a_distinct_socks_inbound():
    vars_ = _multi_cohort_vars()
    rendered = render_template(TEMPLATES / "reality-probe.json.j2", vars_)
    config = json.loads(rendered)

    assert [inbound["port"] for inbound in config["inbounds"]] == [31082, 31083]
    assert [
        outbound["settings"]["vnext"][0]["port"]
        for outbound in config["outbounds"]
    ] == [443, 8443]
    assert config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
    assert "flow" not in config["outbounds"][1]["settings"]["vnext"][0]["users"][0]
    assert config["outbounds"][1]["mux"]["enabled"] is True
    assert config["outbounds"][1]["streamSettings"]["sockopt"]["finalmask"] == "Sudoku"


def test_environment_lists_every_probe_without_client_credentials():
    vars_ = _multi_cohort_vars()
    rendered = render_template(TEMPLATES / "vpn-watchdog.env.j2", vars_)
    watchdog_client = next(
        client for client in vars_["xray"]["clients"] if client["name"] == "watchdog"
    )

    assert "XRAY_REALITY_PROBES=443:31082,8443:31083" in rendered
    assert watchdog_client["uuid"] not in rendered
    assert watchdog_client["short_id"] not in rendered
