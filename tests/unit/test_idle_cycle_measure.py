"""Exercise the portable measurement driver without contacting a TLS endpoint."""

import json
import os
from pathlib import Path
import subprocess


def test_short_cycle_emits_integer_milliseconds_with_bsd_date(tmp_path):
    root = Path(__file__).resolve().parents[2]
    tools = tmp_path / "bin"
    tools.mkdir()
    # Model BSD date's literal unsupported %N; ISO date calls remain real.
    date = tools / "date"
    date.write_text('#!/bin/sh\ncase "$*" in *%s%3N*) echo 1233N;; *) exec /bin/date "$@";; esac\n')
    date.chmod(0o755)
    openssl = tools / "openssl"
    openssl.write_text('#!/bin/sh\necho "synthetic TLS command output"\n')
    openssl.chmod(0o755)
    output = tmp_path / "report.json"
    result = subprocess.run([
        "bash", str(root / "scripts/idle-cycle-measure.sh"),
        "--target", "example.invalid:443", "--sni", "example.invalid",
        "--vantage", "short-idle", "--schedule", "0s", "--followup-count", "1",
        "--output", str(output),
    ], env={**os.environ, "PATH": f"{tools}:{os.environ['PATH']}"},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert len(report["results"]) == 2
    for probe in report["results"]:
        assert all(type(probe[key]) is int for key in ("pre_ms", "post_ms", "elapsed_ms"))
        assert probe["pre_ms"] > 1_000_000_000_000
        assert probe["post_ms"] - probe["pre_ms"] == probe["elapsed_ms"] >= 0
