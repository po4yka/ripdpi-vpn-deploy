"""Complete test outcomes for the assertion-transfer and no-skip acceptance gates."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUTCOMES = {}


def fingerprint():
    paths = sorted((ROOT / "vpnd/src/vpnd").rglob("*.py"))
    paths += sorted((ROOT / "vpnd/tests").glob("*.py"))
    paths += [ROOT / "vpnd/pyproject.toml", ROOT / "vpnd/templates/recipient.html"]
    data = hashlib.sha256()
    for path in paths:
        data.update(str(path.relative_to(ROOT)).encode())
        data.update(path.read_bytes())
    return data.hexdigest()


def pytest_addoption(parser):
    parser.addoption("--vpnd-results", help="Write complete vpnd outcome evidence as JSON")
    parser.addoption("--fail-on-vpnd-skip", action="store_true", help="Reject skipped vpnd cases")


def pytest_sessionstart(session):
    OUTCOMES.clear()
    session.vpnd_source_fingerprint = fingerprint()


def pytest_runtest_logreport(report):
    node = report.nodeid if report.nodeid.startswith("vpnd/") else "vpnd/" + report.nodeid
    phases = OUTCOMES.setdefault(node, {})
    phases[report.when] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    skipped = any("skipped" in phases.values() for phases in OUTCOMES.values())
    if skipped and session.config.getoption("--fail-on-vpnd-skip"):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    path = session.config.getoption("--vpnd-results")
    if path:
        result = {
            "fingerprint": session.vpnd_source_fingerprint,
            "exitstatus": int(session.exitstatus),
            "cases": OUTCOMES,
        }
        Path(path).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
