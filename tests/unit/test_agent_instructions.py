"""Agent instruction files keep one canonical copy of each fact.

Root: AGENTS.md is canonical and CLAUDE.md imports it. Below the root each
CLAUDE.md is canonical and AGENTS.md is a symlink to it. Skills live in
.agents/skills (the path Codex scans) and reach Claude Code through
.claude/skills symlinks. Paths the instructions cite must exist.
"""

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SKILLS = ROOT / ".agents/skills"
CLAUDE_SKILLS = ROOT / ".claude/skills"
# Agent Skills specification fields; tool-specific keys stay out of shared skills.
PORTABLE_FRONTMATTER = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BACKTICK = re.compile(r"`([^`\s]+)`")


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


def test_agent_instructions_reference_existing_paths() -> None:
    top_level = {path.split("/")[0] for path in _tracked() if "/" in path}
    documents = _tracked("AGENTS.md", "*CLAUDE.md", ".agents/skills/*/SKILL.md", "scripts/DESIGN-NOTES.md")
    stale = []
    for document in documents:
        folder = (ROOT / document).parent
        for match in BACKTICK.finditer((ROOT / document).read_text()):
            reference = re.sub(r":\d+(?:-\d+)?$", "", match.group(1).rstrip(".,:;)"))
            if "/" not in reference or reference.startswith(("/", "./", "../", "http")):
                continue
            # Placeholders, globs, and shell expansions are patterns, not paths.
            if re.search(r"[<>*{}$\[\]|~=@]|\.\.\.|…", reference):
                continue
            first = reference.split("/")[0]
            # Nested notes cite paths relative to either the repo or their folder.
            candidates = [ROOT / reference] if first in top_level else []
            if (folder / first).is_dir():
                candidates.append(folder / reference)
            if candidates and not any(candidate.exists() for candidate in candidates):
                stale.append(f"{document}: {reference}")
    assert not stale, "stale path references:\n" + "\n".join(stale)
