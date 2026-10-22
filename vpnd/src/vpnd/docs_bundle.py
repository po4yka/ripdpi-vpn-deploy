"""Reviewed package docs with a checkout fallback anchored to this module."""

from importlib.resources import files
from pathlib import Path
from vpnd.text import lf_lines

KEYWORD_MAP = [
    ("fleet-status", ["how-to/incident.md", "how-to/rollback.md"]),
    ("asn-drift", ["how-to/incident.md"]),
    ("burn-check", ["how-to/incident.md", "how-to/rotate.md"]),
]


def docs_path():
    packaged = files("vpnd").joinpath("data/docs")
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[3] / "docs"


def relevant_runbook_excerpts(report):
    seen = set()
    out = ""
    for keyword, names in KEYWORD_MAP:
        if keyword not in report:
            continue
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            path = docs_path().joinpath(name)
            if path.is_file():
                excerpt = "\n".join(lf_lines(path.read_bytes().decode("utf-8"))[:60])
                out += f"\n---\n### Runbook excerpt: {name}\n\n{excerpt}\n"
    return out
