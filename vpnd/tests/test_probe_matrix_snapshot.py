from pathlib import Path
from vpnd.commands.probe_matrix import synthetic_report_for_snapshot, report_to_json


# Rust test: vpnd/tests/probe_matrix_snapshot.rs::probe_matrix_report_snapshot
def test_probe_matrix_report_snapshot():
    path = Path(__file__).parent / "snapshots/probe_matrix_snapshot__probe_matrix_report.snap"
    original = path.read_text().split("---", 2)[2].strip()
    assert report_to_json(synthetic_report_for_snapshot()) == original


# Rust test: vpnd/tests/probe_matrix_snapshot.rs::probe_matrix_report_carries_required_top_level_fields
def test_probe_matrix_report_carries_required_top_level_fields():
    text = report_to_json(synthetic_report_for_snapshot())
    for name in [
        "schema_version",
        "completed",
        "interrupted",
        "vantage",
        "started_at_unix_ms",
        "finished_at_unix_ms",
        "poll_interval_seconds",
        "cells",
        "windows",
    ]:
        assert '"' + name + '"' in text


# Rust test: vpnd/tests/probe_matrix_snapshot.rs::probe_matrix_destination_classes_are_technical_signatures
def test_probe_matrix_destination_classes_are_technical_signatures():
    text = report_to_json(synthetic_report_for_snapshot())
    for forbidden in [
        "carrier-name",
        "operator-name",
        "region-name",
        "network-brand",
        "provider-brand",
        "geographic-label",
    ]:
        assert forbidden not in text.lower()
    for required in ["allowlist-pattern", "non-allowlist-pattern"]:
        assert required in text
