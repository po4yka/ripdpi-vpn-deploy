import asyncio
from types import SimpleNamespace
from artifact_helpers import scaffold, context
from vpnd.commands.ai_docs import run


def setup(root):
    scaffold(root)
    docs = root / "docs"
    docs.mkdir()
    (docs / "BETA.md").write_text("# Beta\nsecond document\n")
    (docs / "ALPHA.md").write_text("# Alpha\nfirst document\n")
    (docs / "ignored.txt").write_text("not markdown")
    return context(root)


# Rust test: vpnd/tests/ai_docs_emit.rs::emits_llms_txt_index
def test_emits_llms_txt_index(tmp_path):
    asyncio.run(run(setup(tmp_path), SimpleNamespace(out=tmp_path / "out")))
    text = (tmp_path / "out/llms.txt").read_text()
    assert (
        text.startswith("# vpn-deploy docs index")
        and "- [ALPHA](/md/ALPHA.md)" in text
        and "- [BETA](/md/BETA.md)" in text
        and "ignored" not in text
    )


# Rust test: vpnd/tests/ai_docs_emit.rs::emits_llms_full_txt_concatenation
def test_emits_llms_full_txt_concatenation(tmp_path):
    asyncio.run(run(setup(tmp_path), SimpleNamespace(out=tmp_path / "out")))
    text = (tmp_path / "out/llms-full.txt").read_text()
    assert (
        "## ALPHA" in text
        and "# Alpha\nfirst document\n" in text
        and "## BETA" in text
        and "# Beta\nsecond document\n" in text
    )


# Rust test: vpnd/tests/ai_docs_emit.rs::emits_per_doc_copies_in_md_subdir
def test_emits_per_doc_copies_in_md_subdir(tmp_path):
    asyncio.run(run(setup(tmp_path), SimpleNamespace(out=tmp_path / "out")))
    for name in ["ALPHA.md", "BETA.md"]:
        assert (tmp_path / "out/md" / name).read_text() == (tmp_path / "docs" / name).read_text()
    assert len(list((tmp_path / "out/md").iterdir())) == 2


# Rust test: vpnd/tests/ai_docs_emit.rs::index_sorted_by_path
def test_index_sorted_by_path(tmp_path):
    asyncio.run(run(setup(tmp_path), SimpleNamespace(out=tmp_path / "out")))
    text = (tmp_path / "out/llms.txt").read_text()
    assert text.index("ALPHA") < text.index("BETA")


# Rust test: vpnd/tests/ai_docs_emit.rs::explain_mode_does_not_write_files
def test_explain_mode_does_not_write_files(tmp_path):
    ctx = setup(tmp_path)
    ctx.explain = True
    asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert not (tmp_path / "out").exists()


def test_raw_markdown_copies_preserve_crlf_and_control_separators(tmp_path):
    ctx = setup(tmp_path)
    body = b"# Raw\r\nLine\vwith\rseparators\r\n"
    (tmp_path / "docs/RAW.md").write_bytes(body)
    asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert (tmp_path / "out/md/RAW.md").read_bytes() == body
    assert body in (tmp_path / "out/llms-full.txt").read_bytes()
