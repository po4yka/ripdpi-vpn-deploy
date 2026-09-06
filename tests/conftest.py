"""Shared fixtures for the vpn-deploy test tree.

Adds the repo root to sys.path so test modules can import the helper
loaders below without an editable install.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_addoption(parser):
    parser.addoption("--fail-on-skip", action="store_true",
                     help="Fail a required lane if any selected test is skipped")
    parser.addoption("--shard-report", type=Path,
                     help="Write complete collection and execution coverage for a CI group")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "native_runtime: Linux integration with Terraform, Alertmanager and UID/GID capabilities"
    )
    if config.getoption("--shard-report"):
        config.pluginmanager.register(ShardReport(config), "shard-report")


def pytest_sessionfinish(session, exitstatus):
    if session.config.getoption("--fail-on-skip"):
        reporter = session.config.pluginmanager.getplugin("terminalreporter")
        if reporter and reporter.stats.get("skipped"):
            session.exitstatus = 1


class ShardReport:
    """Observe pytest-split without changing collection, ordering or outcomes."""

    def __init__(self, config):
        self.config = config
        if config.getoption("splits", default=None) != 4:
            raise pytest.UsageError("shard reports require exactly four groups")
        if not config.getoption("store_durations") or not config.getoption("clean_durations"):
            raise pytest.UsageError("shard reports require fresh selected-test durations")
        self.profile = Path(config.getoption("durations_path"))
        try:
            raw = self.profile.read_bytes()
            durations = json.loads(raw)
            if not isinstance(durations, dict) or not durations or any(
                not isinstance(key, str) or type(value) not in (int, float)
                or not math.isfinite(value) or value < 0
                for key, value in durations.items()
            ):
                raise ValueError("invalid durations")
        except (OSError, ValueError) as error:
            raise pytest.UsageError("a nonempty measured duration profile is required") from error
        self.profile_sha256 = hashlib.sha256(raw).hexdigest()
        self.expected = []
        self.selected = []
        self.finished = []

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, items):
        # Snapshot before marker/-k filtering and pytest-split selection.
        self.expected = sorted(item.nodeid for item in items
                               if item.get_closest_marker("native_runtime") is None)
        yield
        self.selected = sorted(item.nodeid for item in items)

    def pytest_runtest_logfinish(self, nodeid):
        self.finished.append(nodeid)

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_sessionfinish(self, session):
        # Observe the final skip verdict and pytest-split's fresh duration file.
        yield
        report = {
            "group": self.config.getoption("group"),
            "groups": 4,
            "profile_sha256": self.profile_sha256,
            "expected": self.expected,
            "selected": self.selected,
            "finished": sorted(self.finished),
            "exitstatus": int(session.exitstatus),
            "durations": json.loads(self.profile.read_text()),
        }
        path = self.config.getoption("--shard-report")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, sort_keys=True) + "\n")
