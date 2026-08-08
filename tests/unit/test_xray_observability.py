"""Regression coverage for local-only Xray diagnostic visibility."""

from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

from scripts.template_render import merge_render_vars, render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
XRAY_TEMPLATE = REPO_ROOT / "ansible/roles/xray/templates/config.json.j2"
EXPORTER = REPO_ROOT / "ansible/roles/monitoring/files/xray-stats-exporter.py"
MONITORING_TASKS = REPO_ROOT / "ansible/roles/monitoring/tasks/main.yml"
MONITORING_HANDLERS = REPO_ROOT / "ansible/roles/monitoring/handlers/main.yml"

spec = importlib.util.spec_from_file_location("xray_stats_exporter", EXPORTER)
exporter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = exporter
spec.loader.exec_module(exporter)


def test_xray_stats_service_is_loopback_only_and_counters_are_enabled() -> None:
    config = json.loads(render_template(XRAY_TEMPLATE, merge_render_vars()))

    assert config["api"] == {
        "tag": "api",
        "listen": "127.0.0.1:10086",
        "services": ["StatsService"],
    }
    assert config["stats"] == {}
    assert not any(
        key.startswith("statsUser") for key in config["policy"]["levels"]["0"]
    )
    assert config["policy"]["system"] == {
        "statsInboundUplink": True,
        "statsInboundDownlink": True,
        "statsOutboundUplink": True,
        "statsOutboundDownlink": True,
    }


def test_exporter_keeps_technical_tags_and_ignores_user_records() -> None:
    metrics = exporter.render_metrics(
        {
            "stat": [
                {
                    "name": "inbound>>>vless-reality-primary>>>traffic>>>uplink",
                    "value": "1024",
                },
                {
                    "name": "outbound>>>direct>>>traffic>>>downlink",
                    "value": 2048,
                },
                {
                    "name": "user>>>dad-phone-primary>>>traffic>>>uplink",
                    "value": "512",
                },
                {
                    "name": "user>>>watchdog-primary>>>traffic>>>uplink",
                    "value": "256",
                },
                {
                    "name": "user>>>dad-phone-primary>>>online",
                    "value": "1",
                },
            ]
        },
        collected_at=1_700_000_000,
    )

    assert (
        'vpn_xray_inbound_traffic_bytes_total{inbound="vless-reality-primary",direction="uplink"} 1024'
        in metrics
    )
    assert (
        'vpn_xray_outbound_traffic_bytes_total{outbound="direct",direction="downlink"} 2048'
        in metrics
    )
    assert "vpn_xray_user" not in metrics
    assert "dad-phone" not in metrics
    assert "watchdog" not in metrics


def test_exporter_failure_metric_replaces_stale_success() -> None:
    metrics = exporter.render_failure(collected_at=1_700_000_001)

    assert "vpn_xray_stats_collection_success 0" in metrics
    assert "vpn_xray_stats_collected_timestamp_seconds 1700000001" in metrics
    assert "traffic_bytes" not in metrics


def test_exporter_rejects_unsafe_technical_labels_without_echoing_them() -> None:
    unsafe = 'inbound>>>bad label"value>>>traffic>>>uplink'

    with pytest.raises(exporter.CollectionError, match="unsafe Xray stat tag") as exc:
        exporter.render_metrics(
            {"stat": [{"name": unsafe, "value": "1"}]},
            collected_at=1_700_000_002,
        )

    assert "bad label" not in str(exc.value)


def test_disabling_xray_removes_exporter_units_and_stale_metrics() -> None:
    tasks = yaml.safe_load(MONITORING_TASKS.read_text())
    task_by_name = {task["name"]: task for task in tasks}

    assert task_by_name["Disable stale Xray stats exporter timer"][
        "ansible.builtin.systemd_service"
    ] == {
        "name": "xray-stats-exporter.timer",
        "enabled": False,
        "state": "stopped",
    }
    removed_units = task_by_name["Remove stale Xray stats exporter units"]["loop"]
    assert removed_units == [
        "/etc/systemd/system/xray-stats-exporter.service",
        "/etc/systemd/system/xray-stats-exporter.timer",
    ]
    removed_runtime = task_by_name[
        "Remove stale Xray stats exporter runtime artifacts"
    ]["loop"]
    assert "/usr/local/sbin/xray-stats-exporter" in removed_runtime
    assert any("vpn_xray.prom" in path for path in removed_runtime)


def test_new_timer_handler_is_safe_during_check_mode() -> None:
    handlers = yaml.safe_load(MONITORING_HANDLERS.read_text())
    handler = next(
        item for item in handlers if item["name"] == "Restart Xray stats exporter timer"
    )

    assert handler["when"] == "not ansible_check_mode"
