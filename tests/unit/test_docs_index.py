"""The documentation tree stays navigable and label-free.

docs/README.md lists every page, every page opens with a status line whose
type matches its folder, file names are kebab-case, decision records are
numbered without gaps, relative links resolve to tracked files, and no file
name or heading carries a geographic, carrier or censorship-apparatus label
(docs/STYLE.md, AGENTS.md hard rules).
"""

import posixpath
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OUTSIDE_TREE = {"tasks", "demo", "measurements"}
TYPE_BY_FOLDER = {
    "tutorials": "tutorial",
    "how-to": "how-to",
    "reference": "reference",
    "explanation": "explanation",
    "decisions": "decision",
    "research": "research",
    "archive": "archive",
}
STATUS_LINE = re.compile(
    r"^> \*\*Status:\*\* (?P<status>Current|Snapshot \(\d{4}-\d{2}-\d{2}\)|Research|Archived|"
    r"Superseded by \[[^\]]+\]\([^)]+\))"
    r" · \*\*Type:\*\* (?P<type>tutorial|how-to|reference|explanation|decision|research|archive)"
    r" · \*\*Tier:\*\* (?P<tier>CORE|TACTICAL|RESEARCH|EXCEPTION|—)"
    r"(?: · \*\*Reviewed:\*\* \d{4}-\d{2}-\d{2})?$"
)
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
DECISION = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
LINK = re.compile(r"\]\(([^)\s]+)\)")
# Lower-case tokens that name a place, a regulator, a carrier or a censorship
# apparatus. Names and headings describe behaviour instead (docs/STYLE.md).
FORBIDDEN_LABEL_TOKENS = ("ru-", "-ru", "russia", "tspu", "rkn", "roskomnadzor")
# Pages kept at the old top-level path because an immutable closed task record links to them.
REDIRECT_STUBS = {"OBSERVABILITY-OPERATIONS.md"}


def _tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return {p for p in out.decode().split("\0") if p}


def _pages() -> list[Path]:
    pages = []
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS)
        if rel.parts[0] in OUTSIDE_TREE:
            continue
        if len(rel.parts) == 1 and (rel.name in {"README.md", "STYLE.md"} or rel.name in REDIRECT_STUBS):
            continue
        pages.append(path)
    return pages


def _index_links() -> set[str]:
    text = (DOCS / "README.md").read_text()
    return {link.split("#", 1)[0] for link in LINK.findall(text)}


def test_every_page_is_listed_in_the_index() -> None:
    listed = _index_links()
    missing = [str(p.relative_to(DOCS)) for p in _pages() if str(p.relative_to(DOCS)) not in listed and p.name != "README.md"]
    assert not missing, "pages missing from docs/README.md:\n" + "\n".join(missing)


def test_pages_live_in_a_known_folder_with_a_conforming_name() -> None:
    bad = []
    for page in _pages():
        rel = page.relative_to(DOCS)
        if len(rel.parts) != 2 or rel.parts[0] not in TYPE_BY_FOLDER:
            bad.append(f"{rel}: outside the documented folders")
            continue
        pattern = DECISION if rel.parts[0] == "decisions" and rel.name != "README.md" else KEBAB
        if rel.name != "README.md" and not pattern.match(rel.name):
            bad.append(f"{rel}: file name is not kebab-case (or NNNN-title for decisions)")
    assert not bad, "\n".join(bad)


def test_every_page_opens_with_a_status_line_matching_its_folder() -> None:
    bad = []
    for page in [*_pages(), DOCS / "README.md", DOCS / "STYLE.md", *(DOCS / s for s in REDIRECT_STUBS)]:
        lines = page.read_text().splitlines()
        rel = page.relative_to(DOCS)
        if not lines or not lines[0].startswith("# "):
            bad.append(f"{rel}: first line is not an H1")
            continue
        status = next((line for line in lines[1:4] if line.startswith("> **Status:**")), None)
        match = STATUS_LINE.match(status or "")
        if not match:
            bad.append(f"{rel}: missing or malformed status line")
            continue
        folder = rel.parts[0] if len(rel.parts) == 2 else None
        if folder and match["type"] != TYPE_BY_FOLDER[folder]:
            bad.append(f"{rel}: type {match['type']} does not match folder {folder}")
        if folder == "archive" and match["status"] != "Archived":
            bad.append(f"{rel}: archive pages are Archived")
        if folder == "research" and match["status"] != "Research":
            bad.append(f"{rel}: research pages are Research")
    assert not bad, "\n".join(bad)


def test_decision_records_are_numbered_without_gaps() -> None:
    numbers = sorted(int(p.name[:4]) for p in (DOCS / "decisions").glob("[0-9]*.md"))
    assert numbers == list(range(1, len(numbers) + 1)), numbers
    index = (DOCS / "decisions" / "README.md").read_text()
    for number in numbers:
        assert f"[{number:04d}]" in index, f"decision {number:04d} missing from decisions/README.md"


def test_relative_links_resolve_to_tracked_files() -> None:
    tracked = _tracked()
    tracked_dirs = {str(parent) for path in tracked for parent in PurePosixPath(path).parents if str(parent) != "."}
    broken = []
    documents = [*_pages(), DOCS / "README.md", DOCS / "STYLE.md", ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "AGENTS.md"]
    for document in documents:
        folder = PurePosixPath(document.relative_to(ROOT)).parent
        for link in LINK.findall(document.read_text()):
            target = link.split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            normalized = posixpath.normpath(str(folder / target))
            if normalized not in tracked and normalized not in tracked_dirs:
                broken.append(f"{document.relative_to(ROOT)}: {link}")
    assert not broken, "broken relative links:\n" + "\n".join(broken)


def test_file_names_and_headings_carry_no_forbidden_labels() -> None:
    offenders = []
    for page in [*_pages(), DOCS / "README.md", DOCS / "STYLE.md", ROOT / "README.md"]:
        rel = str(page.relative_to(ROOT))
        name = page.name.lower()
        if any(token in name for token in FORBIDDEN_LABEL_TOKENS):
            offenders.append(f"{rel}: file name")
        for number, line in enumerate(page.read_text().splitlines(), 1):
            if line.startswith("#") and re.search(r"\b(RU|TSPU|RKN|Russia|Russian)\b", line):
                offenders.append(f"{rel}:{number}: heading")
    assert not offenders, "forbidden labels:\n" + "\n".join(offenders)
