"""Naive build inputs must be immutable and checksum-verified."""

from pathlib import Path


def test_naive_forwardproxy_is_commit_pinned_and_checksum_required():
    root = Path(__file__).resolve().parents[2]
    defaults = (root / "ansible/roles/naive/defaults/main.yml").read_text()
    tasks = (root / "ansible/roles/naive/tasks/main.yml").read_text()
    assert "forwardproxy@d62c80d3dd2c706b6b87579844d2397bddd18317" in defaults
    assert "naive.xcaddy_sha256 is match" in tasks
