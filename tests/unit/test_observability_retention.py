"""The documented retention table is complete, finite and equal to the rendered configuration."""

from __future__ import annotations

import re
from configparser import ConfigParser
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/reference/observability-operations.md"
ROLES = ROOT / "ansible/roles"
REQUIRED = {
    ("Prometheus TSDB", "time"),
    ("Prometheus TSDB", "size"),
    ("vmagent sender queue", "size"),
    ("Collector relay queue", "size"),
    ("Service logs", "time"),
    ("Journal", "time"),
    ("Journal", "size"),
    ("Field-report raw report", "time"),
    ("Field-report aggregates", "time"),
}
UNBOUNDED = {"", "-", "0", "unlimited", "infinite", "forever", "unbounded"}


def _table(text: str) -> dict[tuple[str, str], str]:
    section = text.split("\n## Retention\n", 1)[1].split("\n## ", 1)[0]
    rows: dict[tuple[str, str], str] = {}
    for line in section.splitlines():
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0] not in {"Data class", ""} and not set(cells[0]) <= {"-"}:
            rows[(cells[0], cells[1])] = cells[2]
    return rows


def retention_errors(rows: dict[tuple[str, str], str]) -> list[str]:
    """Every required data class has a finite value; only raw field reports may say none."""
    errors = [f"missing {key}" for key in sorted(REQUIRED - rows.keys())]
    for key, value in rows.items():
        if key == ("Field-report raw report", "time"):
            if value != "none":
                errors.append(f"{key} must be none")
        elif value.lower() in UNBOUNDED or value.lower() == "none":
            errors.append(f"unbounded {key}")
    return errors


def _rendered() -> dict[tuple[str, str], str]:
    values = merge_render_vars()
    prometheus = render_template(
        ROLES / "observability_control_plane/templates/observability-prometheus.service.j2", values
    )
    agent = render_template(ROLES / "observability_agent/templates/observability-agent.service.j2", values)
    relay = render_template(
        ROLES / "observability_control_plane/templates/observability-prometheus-relay.service.j2", values
    )
    logs = {
        name: render_template(ROLES / f"monitoring/templates/{name}", values)
        for name in ("logrotate-xray.j2", "logrotate-nginx.j2")
    }
    rotations = {re.search(r"^\s*rotate (\d+)$", text, re.M).group(1) for text in logs.values()}
    assert all(re.search(r"^\s*daily$", text, re.M) for text in logs.values())
    assert len(rotations) == 1, "service logs must share one retention"
    tasks = yaml.safe_load((ROLES / "monitoring/tasks/enable.yml").read_text(encoding="utf-8"))
    dropin = next(task for task in tasks if task["name"] == "Drop journald hardening config")
    defaults = yaml.safe_load((ROLES / "monitoring/defaults/main.yml").read_text(encoding="utf-8"))
    journal = ConfigParser()
    journal.optionxform = str
    journal.read_string(
        Environment(undefined=StrictUndefined)
        .from_string(dropin["ansible.builtin.copy"]["content"])
        .render(defaults)
    )

    def flag(text: str, name: str) -> str:
        return re.search(rf"{re.escape(name)}=(\S+)", text).group(1)

    tsdb_time = flag(prometheus, "--storage.tsdb.retention.time")
    return {
        ("Prometheus TSDB", "time"): tsdb_time,
        ("Prometheus TSDB", "size"): flag(prometheus, "--storage.tsdb.retention.size"),
        ("vmagent sender queue", "size"): flag(agent, "-remoteWrite.maxDiskUsagePerURL") + " bytes",
        ("Collector relay queue", "size"): flag(relay, "-remoteWrite.maxDiskUsagePerURL") + " bytes",
        ("Service logs", "time"): f"{rotations.pop()} daily rotations",
        ("Journal", "time"): journal["Journal"]["MaxRetentionSec"],
        ("Journal", "size"): journal["Journal"]["SystemMaxUse"],
        # No raw report store exists; aggregates live only in the Prometheus TSDB.
        ("Field-report raw report", "time"): "none",
        ("Field-report aggregates", "time"): tsdb_time,
    }


def test_documented_retention_table_is_complete_and_finite() -> None:
    assert retention_errors(_table(DOC.read_text(encoding="utf-8"))) == []


def test_rendered_configuration_carries_the_documented_retention() -> None:
    assert _table(DOC.read_text(encoding="utf-8")) == _rendered()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: rows.pop(("Journal", "time")),
        lambda rows: rows.update({("Prometheus TSDB", "time"): "unlimited"}),
        lambda rows: rows.update({("vmagent sender queue", "size"): "0"}),
        lambda rows: rows.update({("Field-report raw report", "time"): "7d"}),
        lambda rows: rows.update({("Field-report aggregates", "time"): "none"}),
    ],
    ids=["row-removed", "unlimited", "zero", "raw-retained", "aggregate-none"],
)
def test_retention_check_fails_for_a_missing_or_unbounded_class(mutation) -> None:
    rows = _table(DOC.read_text(encoding="utf-8"))
    mutation(rows)
    assert retention_errors(rows) != []
