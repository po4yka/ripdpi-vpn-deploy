"""Rendered-artifact tests for authenticated watchdog REALITY probes."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from scripts.template_render import merge_render_vars, render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "ansible" / "roles" / "watchdog" / "templates"


def _multi_cohort_vars() -> dict:
    vars_ = deepcopy(merge_render_vars())
    vars_["vpn_service_address"] = "192.0.2.50"
    vars_["watchdog_reality_probes"] = [
        {
            "name": "primary",
            "port": 443,
            "p0_reality_shape_input": {
                "flow_mode": "vision",
                "finalmask": False,
            },
            "clients": ["watchdog"],
        },
        {
            "name": "alternate",
            "port": 8443,
            "p0_reality_shape_input": {
                "flow_mode": "mux",
                "finalmask": True,
            },
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
        outbound["settings"]["vnext"][0]["address"] for outbound in config["outbounds"]
    ] == ["192.0.2.50", "192.0.2.50"]
    assert [
        outbound["settings"]["vnext"][0]["port"] for outbound in config["outbounds"]
    ] == [443, 8443]
    assert (
        config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["flow"]
        == "xtls-rprx-vision"
    )
    assert "flow" not in config["outbounds"][1]["settings"]["vnext"][0]["users"][0]
    assert config["outbounds"][1]["mux"]["enabled"] is True
    assert config["outbounds"][1]["streamSettings"]["sockopt"]["finalmask"] == "Sudoku"


def test_probe_config_refuses_an_unknown_p0_shape() -> None:
    variables = _multi_cohort_vars()
    variables["watchdog_reality_probes"][0]["p0_reality_shape_input"][
        "flow_mode"
    ] = "unknown-shape"

    with pytest.raises(UndefinedError, match="unknown-shape"):
        render_template(TEMPLATES / "reality-probe.json.j2", variables)


def test_environment_lists_every_probe_without_client_credentials():
    vars_ = _multi_cohort_vars()
    rendered = render_template(TEMPLATES / "vpn-watchdog.env.j2", vars_)
    watchdog_client = next(
        client for client in vars_["xray"]["clients"] if client["name"] == "watchdog"
    )

    assert "XRAY_REALITY_PROBES=443:31082,8443:31083" in rendered
    assert watchdog_client["uuid"] not in rendered
    assert watchdog_client["short_id"] not in rendered
    assert "XRAY_API_SERVER=127.0.0.1:10086" in rendered


def test_watchdog_fails_when_stats_service_is_not_queryable():
    rendered = render_template(TEMPLATES / "vpn-watchdog.sh.j2", _multi_cohort_vars())

    assert '"xray StatsService query"' in rendered
    assert 'api statsquery "--server=${XRAY_API_SERVER}"' in rendered


def test_watchdog_sandbox_allows_xray_config_validation_to_open_logs():
    variables = _multi_cohort_vars()
    variables["xray_log_dir"] = "/var/log/xray-custom"

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "ReadWritePaths=/var/lib/vpn-watchdog /var/log/xray-custom" in rendered


def test_watchdog_sandbox_keeps_xray_logs_read_only_when_xray_is_disabled():
    variables = _multi_cohort_vars()
    variables["vpn"]["enable_xray_reality"] = False

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "/var/log/xray" not in rendered


def test_watchdog_sandbox_allows_nginx_config_validation_to_open_logs():
    variables = _multi_cohort_vars()
    variables["vpn"]["enable_xray_reality"] = False
    variables["vpn"]["enable_nginx_xhttp"] = True

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "ReadWritePaths=/var/lib/vpn-watchdog /var/log/nginx" in rendered


def test_reality_probe_requires_the_explicit_service_address() -> None:
    variables = _multi_cohort_vars()
    variables.pop("vpn_service_address")

    with pytest.raises(UndefinedError, match="vpn_service_address"):
        render_template(TEMPLATES / "reality-probe.json.j2", variables)
