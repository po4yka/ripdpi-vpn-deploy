"""Shared fixtures for the vpn-deploy test tree.

Adds the repo root to sys.path so test modules can import the helper
loaders below without an editable install.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_addoption(parser):
    parser.addoption("--fail-on-skip", action="store_true",
                     help="Fail a required lane if any selected test is skipped")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "native_runtime: Linux integration with Terraform, Alertmanager and UID/GID capabilities"
    )


def pytest_sessionfinish(session, exitstatus):
    if session.config.getoption("--fail-on-skip"):
        reporter = session.config.pluginmanager.getplugin("terminalreporter")
        if reporter and reporter.stats.get("skipped"):
            session.exitstatus = 1
