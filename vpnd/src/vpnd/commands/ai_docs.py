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


def emit_docs(docs, out):
    out = Path(out)
    md = out / "md"
    md.mkdir(parents=True, exist_ok=True)
    sections: dict[str, list[tuple[str, str]]] = {}
    full = ""
    for relative, body in _pages(docs):
        slug = relative[:-3]
        folder = relative.rsplit("/", 1)[0] if "/" in relative else ""
        sections.setdefault(folder, []).append((_title(slug, body), slug))
        full += f"\n\n---\n\n## {slug}\n\n{body.decode('utf-8')}"
        target = md / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
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
    for heading, pages in ordered:
        index += f"\n## {heading}\n\n" + "".join(f"- [{title}](/md/{slug}.md)\n" for title, slug in pages)
    if optional:
        index += "\n## Optional\n\n"
        for heading, pages in optional:
            index += "".join(f"- [{title}](/md/{slug}.md): {heading.lower()}\n" for title, slug in pages)
    (out / "llms.txt").write_text(index, encoding="utf-8")
    (out / "llms-full.txt").write_text(full, encoding="utf-8")


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
