"""Unit tests for scripts/scan-reality-targets.sh.

The script wraps a third-party binary (RealiTLScanner) that cannot be stubbed
via PATH (the script resolves it by an absolute cached path, not via PATH).
Tests here cover the argument-validation and early-exit paths that fire before
the binary is invoked.  The actual scan logic is exercised in CI where the
binary can be downloaded; those paths are skipped locally with a clear reason.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
SCRIPT = REPO_ROOT / "scripts" / "scan-reality-targets.sh"


def _run(args: list[str], tmp_path: Path | None = None, **kwargs) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = f"{STUBS_BIN}:{env['PATH']}"
    if tmp_path is not None:
        # Redirect TOOL_CACHE so the script never writes to the real cache.
        env["TOOL_CACHE"] = str(tmp_path / "tool-cache")
    return subprocess.run(
        ["bash", str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# Argument validation (no binary needed)
# ---------------------------------------------------------------------------

def test_no_args_exits_nonzero(tmp_path):
    """Script must exit non-zero and print usage when no seed source is given."""
    result = _run([], tmp_path=tmp_path)
    assert result.returncode != 0, "expected non-zero exit with no args"
    stderr = result.stderr + result.stdout
    assert any(
        kw in stderr.lower()
        for kw in ("seeds", "cidr", "crawl", "usage", "pick", "error")
    ), f"expected usage hint in output, got:\n{stderr[:600]}"


def test_unknown_arg_exits_nonzero(tmp_path):
    """Unknown flag must produce a non-zero exit."""
    result = _run(["--unknown-flag", "value"], tmp_path=tmp_path)
    assert result.returncode != 0


def test_help_flag(tmp_path):
    """--help must exit non-zero (usage) and mention --seeds."""
    result = _run(["--help"], tmp_path=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "--seeds" in combined or "seeds" in combined.lower()


def test_seeds_file_not_found_implies_install_attempt(tmp_path):
    """With a valid --seeds flag the script proceeds past arg-parse into
    the binary install phase.  On a host without the binary it will either
    attempt a download (Linux) or check for 'go' (macOS) — both paths exit
    non-zero in a hermetic test environment without internet or Go.

    This confirms that argument validation passes and the binary-install
    gate is reached.
    """
    seeds_file = tmp_path / "seeds.txt"
    seeds_file.write_text("198.51.100.1\n")
    result = _run(["--seeds", str(seeds_file)], tmp_path=tmp_path)
    # The script will fail trying to install/find the binary — that's expected.
    # What matters is it does NOT fail on argument parsing (which exits 1 with
    # "pick one of" message).
    pick_error = "pick one of" in (result.stdout + result.stderr)
    assert not pick_error, (
        "script failed at argument validation rather than binary install phase"
    )


def test_cidr_flag_reaches_install_phase(tmp_path):
    """--cidr flag passes argument validation; script fails at binary install."""
    result = _run(["--cidr", "198.51.100.0/24"], tmp_path=tmp_path)
    pick_error = "pick one of" in (result.stdout + result.stderr)
    assert not pick_error, (
        "script failed at argument validation rather than binary install phase"
    )


def test_macos_installer_uses_the_declared_lowercase_go_module_path():
    script = SCRIPT.read_text()

    assert 'go install "github.com/xtls/RealiTLScanner@${REALI_VERSION}"' in script
    assert 'github.com/XTLS/RealiTLScanner@${REALI_VERSION}' not in script


@pytest.mark.skip(
    reason=(
        "Full scan requires RealiTLScanner binary and network access. "
        "Run manually: scripts/scan-reality-targets.sh --seeds <file>"
    )
)
def test_full_scan_verdict_aggregation(tmp_path):
    """Placeholder for a future integration test that exercises the full
    post-filter + ASN-annotation pipeline against a real scan result."""
    pass
