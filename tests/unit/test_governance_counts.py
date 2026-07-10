"""Documentation claims about repository coverage must match the live tree."""

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_governance_counts_match_live_repository():
    roles = len([path for path in (ROOT / "ansible/roles").iterdir() if path.is_dir()])
    templates = len(list((ROOT / "ansible/roles").rglob("*.j2")))
    collected = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    test_count = int(re.search(r"(\d+) tests collected", collected).group(1))
    testing = (ROOT / "docs/TESTING.md").read_text()
    assert f"{roles} roles" in (ROOT / "AGENTS.md").read_text()
    assert f"{roles} roles" in (ROOT / "CLAUDE.md").read_text()
    assert f"({templates} templates)" in testing
    assert f"({test_count} collected)" in testing
    assert "molecule / per-role tests. v2." not in (ROOT / "docs/ARCHITECTURE.md").read_text()
