"""Keep carrier/geography and external knowledge-store identifiers out of git."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = (
    "roste" + "lecom", "bee" + "line", "mega" + "fon", "m" + "ts",
    "r" + "tk", "rost" + "ov", "izhe" + "vsk", "regime-landscape/" + "wiki",
    "censorship-bypass " + "vault", "source_" + "wiki_pages", "wiki" + " page",
    "obsid" + "ian", "/wiki/" + "concepts/", "censorship-" + "bypass/",
)


def test_tracked_files_do_not_contain_forbidden_identifiers():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode().split("\0")
    offenders = []
    for relative in filter(None, tracked):
        content = (ROOT / relative).read_text(errors="ignore").lower()
        for identifier in FORBIDDEN:
            if identifier in content:
                offenders.append(f"{relative}: {identifier}")
    assert not offenders, "forbidden repository identifiers:\n" + "\n".join(offenders)
