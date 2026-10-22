"""Publish deterministic Markdown endpoints from checkout or packaged docs.

The index follows the llms.txt convention: an H1, a blockquote summary, one
H2 section per documentation folder with one link per page, and an
``Optional`` section for archived pages that an agent may skip.
"""

import asyncio
from pathlib import Path
from vpnd.docs_bundle import docs_path

TITLE = "# vpn-deploy docs index"
SUMMARY = (
    "> Operator and contributor documentation for vpn-deploy: a layered "
    "Terraform, cloud-init, Ansible and SOPS deployment of a multi-profile "
    "VPN stack built for filtered networks. Pages under `md/` are verbatim "
    "copies of the repository's `docs/` tree."
)
# Folder -> section heading, in reading order. Folders outside this map are
# appended alphabetically; top-level pages come first as "Overview".
SECTIONS = [
    ("tutorials", "Tutorials"),
    ("how-to", "How-to guides"),
    ("reference", "Reference"),
    ("explanation", "Explanation"),
    ("decisions", "Decisions"),
    ("research", "Research"),
]
OPTIONAL = {"archive": "Archive"}
# Folders with their own contracts that are not documentation pages.
EXCLUDED = {"tasks", "demo", "measurements"}
# Written next to md/: the pages this command emitted, one relative path per
# line. A rerun removes only those, never files it did not write.
MANIFEST = ".vpnd-ai-docs"


def _pages(docs):
    for path in sorted(docs.rglob("*.md"), key=lambda p: p.relative_to(docs).as_posix()):
        relative = path.relative_to(docs)
        if not path.is_file() or any(part in EXCLUDED for part in relative.parts[:-1]):
            continue
        yield relative.as_posix(), path.read_bytes()


def _title(slug: str, body: bytes) -> str:
    for raw in body.split(b"\n", 20):
        line = raw.decode("utf-8", "replace").rstrip("\r")
        if line.startswith("# "):
            return line[2:].strip()
    return slug


def _no_symlinks(md, relative=""):
    """Refuse to write or delete through a symlink inside md/: a link planted at
    any path component would redirect the page to an unrelated file."""
    checked = [md]
    for part in Path(relative).parts:
        checked.append(checked[-1] / part)
    for path in checked:
        if path.is_symlink():
            raise RuntimeError(f"refusing to write through symlink {path}")


def _previous_pages(out):
    """Pages the previous run recorded; a tree without a manifest was not
    written by this command, so nothing in it is ever deleted."""
    manifest = out / MANIFEST
    if not manifest.is_file():
        return []
    pages = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        relative = Path(line)
        if line and not relative.is_absolute() and ".." not in relative.parts:
            pages.append(relative.as_posix())
    return pages


def _remove_pages(md, pages):
    for relative in pages:
        _no_symlinks(md, relative)
        page = md / relative
        if page.is_file():
            page.unlink()
    if md.is_dir():
        directories = (p for p in md.rglob("*") if p.is_dir() and not p.is_symlink())
        for directory in sorted(directories, reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()


def _write_manifest(out, pages):
    (out / MANIFEST).write_text("".join(f"{relative}\n" for relative in pages), encoding="utf-8")


def _write_page(target, body):
    target.write_bytes(body)


def emit_docs(docs, out):
    out = Path(out)
    md = out / "md"
    # Decode every page before writing anything, so a page that is not UTF-8
    # fails the run with the output tree untouched.
    pages = [(relative, body, body.decode("utf-8")) for relative, body in _pages(docs)]
    current = [relative for relative, _, _ in pages]
    _no_symlinks(md)
    for relative in current:
        _no_symlinks(md, relative)
    previous = _previous_pages(out)
    out.mkdir(parents=True, exist_ok=True)
    # Record the union before the first write: if this run stops part-way, the
    # next run still knows every page that may exist and removes the stale ones.
    _write_manifest(out, list(dict.fromkeys(previous + current)))
    _remove_pages(md, [relative for relative in previous if relative not in set(current)])
    md.mkdir(parents=True, exist_ok=True)
    sections: dict[str, list[tuple[str, str]]] = {}
    full = ""
    for relative, body, text in pages:
        slug = relative[:-3]
        folder = relative.rsplit("/", 1)[0] if "/" in relative else ""
        sections.setdefault(folder, []).append((_title(slug, body), slug))
        full += f"\n\n---\n\n## {slug}\n\n{text}"
        target = md / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_page(target, body)
    index = f"{TITLE}\n\n{SUMMARY}\n"
    ordered = []
    if "" in sections:
        ordered.append(("Overview", sections.pop("")))
    for folder, heading in SECTIONS:
        if folder in sections:
            ordered.append((heading, sections.pop(folder)))
    for folder in sorted(sections):
        if folder not in OPTIONAL:
            ordered.append((folder, sections.pop(folder)))
    optional = [(OPTIONAL[folder], sections.pop(folder)) for folder in sorted(sections)]
    for heading, pages_in in ordered:
        index += f"\n## {heading}\n\n" + "".join(f"- [{title}](/md/{slug}.md)\n" for title, slug in pages_in)
    if optional:
        index += "\n## Optional\n\n"
        for heading, pages_in in optional:
            index += "".join(f"- [{title}](/md/{slug}.md): {heading.lower()}\n" for title, slug in pages_in)
    (out / "llms.txt").write_text(index, encoding="utf-8")
    (out / "llms-full.txt").write_text(full, encoding="utf-8")
    _write_manifest(out, current)


async def run(ctx, args):
    out = Path(args.out) if args.out else ctx.root / "ai-docs"
    if ctx.explain:
        print(f"→ would emit llms.txt, llms-full.txt, and per-doc markdown to {out}")
        return 0
    docs = ctx.root / "docs"
    if not docs.is_dir():
        docs = docs_path()
    await asyncio.to_thread(emit_docs, docs, out)
    print(
        f"✓ ai-docs emitted to {out}\n\n  llms.txt:       {out / 'llms.txt'}\n  llms-full.txt:  {out / 'llms-full.txt'}\n  per-doc:        {out / 'md'}/"
    )
    return 0
