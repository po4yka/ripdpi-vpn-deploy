"""Agent instruction files keep one canonical copy of each fact.

Root: AGENTS.md is canonical and CLAUDE.md imports it. Below the root each
CLAUDE.md is canonical and AGENTS.md is a symlink to it. Skills live in
.agents/skills (the path Codex scans) and reach Claude Code through
.claude/skills symlinks. Paths the instructions cite must exist.
"""

import posixpath
import re
import subprocess
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SKILLS = ROOT / ".agents/skills"
CLAUDE_SKILLS = ROOT / ".claude/skills"
# Agent Skills specification fields; tool-specific keys stay out of shared skills.
PORTABLE_FRONTMATTER = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BACKTICK = re.compile(r"`([^`\s]+)`")
FILE_NAME = re.compile(r"/[^/]*\.[a-z][a-z0-9]*$")
# The leading ./ or ../ path of any span, so commands with arguments are checked too.
RELATIVE = re.compile(r"`(\.\.?/[^`\s]+)")


def _tracked(*patterns: str) -> list[str]:
    return subprocess.run(
        ["git", "ls-files", "--", *patterns], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()


def _skill_dirs() -> list[Path]:
    return sorted(path for path in CANONICAL_SKILLS.iterdir() if not path.name.startswith("."))


def test_root_claude_md_imports_the_canonical_agents_md() -> None:
    assert (ROOT / "CLAUDE.md").read_text().splitlines()[0] == "@AGENTS.md"
    assert not (ROOT / "AGENTS.md").is_symlink()


def test_every_nested_claude_md_has_an_agents_md_symlink() -> None:
    missing = []
    for claude_md in _tracked("*/CLAUDE.md"):
        agents_md = ROOT / claude_md.removesuffix("CLAUDE.md") / "AGENTS.md"
        if not agents_md.is_symlink() or agents_md.readlink() != Path("CLAUDE.md"):
            missing.append(str(agents_md.relative_to(ROOT)))
    assert not missing, f"AGENTS.md must be a symlink to the sibling CLAUDE.md: {missing}"


def test_every_nested_agents_md_points_at_a_tracked_claude_md() -> None:
    tracked_claude = set(_tracked("*/CLAUDE.md"))
    orphaned = []
    for agents_md in _tracked("*/AGENTS.md"):
        path = ROOT / agents_md
        if (
            not path.is_symlink()
            or path.readlink() != Path("CLAUDE.md")
            or agents_md.removesuffix("AGENTS.md") + "CLAUDE.md" not in tracked_claude
        ):
            orphaned.append(agents_md)
    assert not orphaned, f"AGENTS.md must be a symlink to a tracked sibling CLAUDE.md: {orphaned}"


def test_skills_have_portable_frontmatter() -> None:
    for skill in _skill_dirs():
        text = (skill / "SKILL.md").read_text()
        assert text.startswith("---\n"), skill.name
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        assert frontmatter["name"] == skill.name and SKILL_NAME.fullmatch(skill.name), skill.name
        assert len(skill.name) <= 64, skill.name
        assert 0 < len(frontmatter["description"]) <= 1024, skill.name
        assert set(frontmatter) <= PORTABLE_FRONTMATTER, f"{skill.name}: {set(frontmatter) - PORTABLE_FRONTMATTER}"


def test_claude_skills_are_symlinks_to_canonical_skills() -> None:
    canonical = {skill.name for skill in _skill_dirs()}
    aliases = {}
    for alias in CLAUDE_SKILLS.iterdir():
        assert alias.is_symlink(), f"{alias.name}: author skills under .agents/skills, not .claude/skills"
        aliases[alias.name] = alias.readlink()
    assert aliases == {name: Path("../../.agents/skills") / name for name in canonical}


def _ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT).returncode == 0


def test_agent_instructions_reference_existing_paths() -> None:
    # Judge against the index, not the local disk: an untracked local file must not
    # hide a stale reference that fails in a clean checkout. Paths the repo
    # deliberately ignores (operator-local runtime state) are valid citations.
    tracked = set(_tracked())
    tracked_dirs = {str(parent) for path in tracked for parent in PurePosixPath(path).parents if str(parent) != "."}
    top_level = {path.split("/")[0] for path in tracked if "/" in path}
    documents = _tracked("AGENTS.md", "*CLAUDE.md", ".agents/skills/*/SKILL.md", "scripts/DESIGN-NOTES.md")
    stale = []
    for document in documents:
        folder = PurePosixPath(document).parent
        text = (ROOT / document).read_text()
        for raw in {*BACKTICK.findall(text), *RELATIVE.findall(text)}:
            reference = re.sub(r":\d+(?:-\d+)?$|::\w+$", "", raw.rstrip(".,:;)"))
            if "/" not in reference or reference.startswith(("/", "http")):
                continue
            # Placeholders, globs, and shell or systemd expansions are patterns, not paths.
            if re.search(r"[<>*{}$\[\]|~=@%]|\.\.\.|…", reference):
                continue
            reference = reference.rstrip("/")
            if reference.startswith(("./", "../")):
                # Explicit relative paths resolve against the note's folder or, for
                # commands run from the checkout root such as ./taskctl, the repo root.
                candidates = [posixpath.normpath(str(base / reference)) for base in (folder, PurePosixPath("."))]
                if not any(c in tracked or c in tracked_dirs or _ignored(c) for c in candidates):
                    stale.append(f"{document}: {reference}")
                continue
            first = reference.split("/")[0]
            # Nested notes cite paths relative to either the repo or their folder.
            candidates = [reference] if first in top_level else []
            if str(folder / first) in tracked_dirs:
                candidates.append(str(folder / reference))
            if not candidates and FILE_NAME.search(reference):
                # An unanchored file name may be relative to a parent folder (sibling roles,
                # ansible/group_vars) or a crate's src/; resolving nowhere means stale, which
                # catches a misspelled first directory. Unanchored non-file text (MIME types,
                # CIDRs, owner/repo) stays unchecked.
                candidates = [str(base / reference) for base in (folder, *folder.parents, folder / "src")]
            if candidates and not any(
                candidate in tracked or candidate in tracked_dirs or _ignored(candidate) for candidate in candidates
            ):
                stale.append(f"{document}: {reference}")
    assert not stale, "stale path references:\n" + "\n".join(stale)
