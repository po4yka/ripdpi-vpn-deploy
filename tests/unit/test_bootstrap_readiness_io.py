"""Bounded controller subprocess I/O; fixtures do not establish live SSH."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module():
    spec = importlib.util.spec_from_file_location("bootstrap_readiness_io", ROOT / "scripts/bootstrap_readiness.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_bounded_input_reaches_child_without_argv_or_environment():
    readiness = module()
    payload = b'{"nonce":"fixture-only"}'
    status, output = readiness.run_command(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        timeout=5, capture=True, input_data=payload,
    )
    assert status == 0 and output == payload


def test_deferred_cancellation_allows_one_cleanup_command():
    readiness = module()
    readiness._cancelled = 15
    with pytest.raises(SystemExit):
        readiness.run_command([sys.executable, "-c", "pass"], timeout=5)
    status, _ = readiness.run_command(
        [sys.executable, "-c", "import sys; sys.exit(0)"], timeout=5, defer_cancellation=True,
    )
    assert status == 0
    readiness._cancelled = 0


def test_input_size_and_type_are_rejected_before_spawn():
    readiness = module()
    for payload in ("not-bytes", b"x" * 65537):
        with pytest.raises(readiness.ReadinessError, match="command input invalid"):
            readiness.run_command([sys.executable, "-c", "pass"], timeout=5, input_data=payload)


@pytest.mark.parametrize('limit,accepted', [(65536, False), (1_049_600, True)])
def test_large_inspection_output_remains_bounded(limit, accepted):
    readiness = module()
    operation = lambda: readiness.run_command(
        [sys.executable, '-c', 'import sys;sys.stdout.write("x"*100000)'],
        timeout=5, capture=True, output_limit=limit)
    if accepted:
        status, output = operation()
        assert status == 0 and len(output) == 100000
    else:
        with pytest.raises(readiness.ReadinessError, match='command output limit'):
            operation()


@pytest.mark.parametrize('limit', [True, 0, -1, 1_049_601])
def test_invalid_output_budget_refuses_before_spawn(limit):
    readiness = module()
    with pytest.raises(readiness.ReadinessError, match='output limit invalid'):
        readiness.run_command(['missing-command'], timeout=5, output_limit=limit)
