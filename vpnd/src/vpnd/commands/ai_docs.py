"""Publish deterministic Markdown endpoints from checkout or packaged docs."""

import asyncio
from pathlib import Path
from vpnd.docs_bundle import docs_path


def emit_docs(docs, out):
    out = Path(out)
    md = out / "md"
    md.mkdir(parents=True, exist_ok=True)
    index, full = "# vpn-deploy docs index\n\n", ""
    for path in sorted(
        (p for p in docs.iterdir() if p.name.endswith(".md") and p.is_file()), key=lambda p: p.name
    ):
        slug = path.name[:-3]
        body = path.read_bytes().decode("utf-8")
        index += f"- [{slug}](/md/{slug}.md)\n"
        full += f"\n\n---\n\n## {slug}\n\n{body}"
        (md / path.name).write_text(body, encoding="utf-8")
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
