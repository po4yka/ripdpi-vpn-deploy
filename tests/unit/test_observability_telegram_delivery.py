"""Focused contracts for bounded primary Telegram routing and templates."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"


def _contract() -> dict[str, object]:
    return {
        "config_root": "/etc/observability-control-plane",
        "alerting": {
            "group_wait": "30s",
            "group_interval": "5m",
            "critical_repeat_interval": "1h",
            "warning_repeat_interval": "6h",
            "recovery_stability": "3m",
            "telegram": {
                "chat_id": "-100000000001",
                "topic_id": 42,
                "parse_mode": "HTML",
                "max_alerts": 5,
            },
            "deadman": {
                "enabled": False,
                "receiver_url": "http://127.0.0.1:19093/alerts",
                "repeat_interval": "1m",
            },
        },
    }


def test_telegram_routing_bounds_reminders_and_escapes_every_dynamic_field() -> None:
    contract = _contract()
    rendered = render_template(
        ROLE / "templates/observability-alertmanager.yml.j2",
        {
            "observability_control_plane": contract,
            "_observability_telegram_generation": "c" * 64,
        },
    )
    message = render_template(
        ROLE / "templates/observability-telegram.tmpl.j2",
        {"observability_control_plane": contract},
    )
    parsed = yaml.safe_load(rendered)

    assert parsed["route"]["group_wait"] == "30s"
    assert parsed["route"]["group_interval"] == "5m"
    assert parsed["route"]["repeat_interval"] == "6h"
    assert parsed["route"]["routes"] == [
        {
            "receiver": "telegram-critical",
            "matchers": ['severity="critical"'],
            "repeat_interval": "1h",
        },
        {
            "receiver": "telegram-primary",
            "matchers": ['severity="warning"'],
            "repeat_interval": "6h",
        },
    ]
    telegram = [
        receiver["telegram_configs"][0]
        for receiver in parsed["receivers"]
        if receiver["name"] in {"telegram-primary", "telegram-critical"}
    ]
    assert len(telegram) == 2
    assert all(route["send_resolved"] is True for route in telegram)
    assert all(route["max_alerts"] == 5 for route in telegram)
    assert all(route["parse_mode"] == "HTML" for route in telegram)

    dynamic_fields = (
        ".CommonLabels.alertname",
        ".CommonAnnotations.source_generation",
        ".Labels.environment",
        ".Labels.node",
        ".Labels.component",
        ".Annotations.summary",
        ".Annotations.evidence_class",
        ".Annotations.runbook",
    )
    for field in dynamic_fields:
        assert (
            field
            + ' | reReplaceAll "&" "&amp;" | reReplaceAll "<" "&lt;" | reReplaceAll ">" "&gt;"'
        ) in message
    assert "FIRING" in message
    assert "RESOLVED" in message
    assert "... omitted {{ .TruncatedAlerts }} alerts" in message
    assert ".Annotations.description" not in message
