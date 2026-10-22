import asyncio
from types import SimpleNamespace

import pytest
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


def setup_tree(root):
    ctx = setup(root)
    docs = root / "docs"
    for folder, name, title in [
        ("how-to", "deploy.md", "Deploy"),
        ("reference", "secrets.md", "Secrets"),
        ("archive", "old-audit-2026-07.md", "Old audit"),
        ("tasks", "README.md", "Tasks"),
        ("tasks/issues", "some-task.md", "Some task"),
        ("demo", "README.md", "Demo"),
        ("measurements", "report-2026-07-15.md", "Report"),
    ]:
        (docs / folder).mkdir(parents=True, exist_ok=True)
        (docs / folder / name).write_text(f"# {title}\nbody of {title}\n")
    return ctx


# Rust test: vpnd/tests/ai_docs_emit.rs::emits_llms_txt_index
def test_emits_llms_txt_index(tmp_path):
    asyncio.run(run(setup(tmp_path), SimpleNamespace(out=tmp_path / "out")))
    text = (tmp_path / "out/llms.txt").read_text()
    assert (
        text.startswith("# vpn-deploy docs index\n\n> ")
        and "## Overview" in text
        and "- [Alpha](/md/ALPHA.md)" in text
        and "- [Beta](/md/BETA.md)" in text
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


def test_tree_pages_are_sectioned_by_folder_with_archive_optional(tmp_path):
    asyncio.run(run(setup_tree(tmp_path), SimpleNamespace(out=tmp_path / "out")))
    text = (tmp_path / "out/llms.txt").read_text()
    overview, how_to, reference, optional = (
        text.index("## Overview"),
        text.index("## How-to guides"),
        text.index("## Reference"),
        text.index("## Optional"),
    )
    assert overview < how_to < reference < optional
    assert "- [Deploy](/md/how-to/deploy.md)" in text
    assert "- [Secrets](/md/reference/secrets.md)" in text
    assert "- [Old audit](/md/archive/old-audit-2026-07.md): archive" in text
    assert text.index("## Optional") < text.index("Old audit")
    assert (tmp_path / "out/md/how-to/deploy.md").read_text() == "# Deploy\nbody of Deploy\n"
    assert "## how-to/deploy" in (tmp_path / "out/llms-full.txt").read_text()


def test_task_demo_and_measurement_folders_are_not_documentation_pages(tmp_path):
    asyncio.run(run(setup_tree(tmp_path), SimpleNamespace(out=tmp_path / "out")))
    text = (tmp_path / "out/llms.txt").read_text()
    full = (tmp_path / "out/llms-full.txt").read_text()
    for excluded in ("Tasks", "Some task", "Demo", "Report"):
        assert excluded not in text and excluded not in full
    assert not (tmp_path / "out/md/tasks").exists()
    assert not (tmp_path / "out/md/demo").exists()
    assert not (tmp_path / "out/md/measurements").exists()


def test_pages_emitted_by_an_earlier_run_are_removed_on_rerun(tmp_path):
    ctx = setup_tree(tmp_path)
    moved = tmp_path / "docs/RUNBOOK-deploy.md"
    moved.write_text("# old location\n")
    asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert (tmp_path / "out/md/RUNBOOK-deploy.md").exists()
    moved.unlink()
    (tmp_path / "docs/how-to/deploy.md").rename(tmp_path / "docs/reference/deploy.md")
    asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert not (tmp_path / "out/md/RUNBOOK-deploy.md").exists()
    assert not (tmp_path / "out/md/how-to").exists()
    assert (tmp_path / "out/md/reference/deploy.md").read_text() == "# Deploy\nbody of Deploy\n"


def test_files_the_command_did_not_write_are_never_deleted(tmp_path):
    ctx = setup_tree(tmp_path)
    foreign = tmp_path / "out/md/notes/mine.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("# not generated\n")
    stray = tmp_path / "out/md/how-to/stray.md"
    stray.parent.mkdir(parents=True)
    stray.write_text("# not generated either\n")
    for _ in range(2):  # without a manifest, then with the manifest of the first run
        asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
        assert foreign.read_text() == "# not generated\n"
        assert stray.read_text() == "# not generated either\n"
    assert (tmp_path / "out/md/how-to/deploy.md").read_text() == "# Deploy\nbody of Deploy\n"


def test_a_symlinked_directory_in_the_output_tree_is_refused(tmp_path):
    ctx = setup_tree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "deploy.md").write_text("# keep me\n")
    (tmp_path / "out/md").mkdir(parents=True)
    (tmp_path / "out/md/how-to").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert (elsewhere / "deploy.md").read_text() == "# keep me\n"
    assert not (tmp_path / "out/llms.txt").exists()


def test_a_symlinked_page_in_the_output_tree_is_refused(tmp_path):
    ctx = setup(tmp_path)
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("# keep me\n")
    (tmp_path / "out/md").mkdir(parents=True)
    (tmp_path / "out/md/ALPHA.md").symlink_to(elsewhere)
    with pytest.raises(RuntimeError, match="symlink"):
        asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert elsewhere.read_text() == "# keep me\n"


def test_a_page_that_is_not_utf8_fails_before_anything_is_written(tmp_path):
    ctx = setup(tmp_path)
    (tmp_path / "docs/ZETA.md").write_bytes(b"# bad\n\xff\xfe\n")
    with pytest.raises(UnicodeDecodeError):
        asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert not (tmp_path / "out").exists()


def test_manifest_lists_every_page_before_the_first_page_is_written(tmp_path, monkeypatch):
    from vpnd.commands import ai_docs

    ctx = setup(tmp_path)

    def disk_full(target, body):
        raise OSError("disk full")

    monkeypatch.setattr(ai_docs, "_write_page", disk_full)
    with pytest.raises(OSError):
        asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert (tmp_path / "out/.vpnd-ai-docs").read_text().splitlines() == ["ALPHA.md", "BETA.md"]
    monkeypatch.undo()
    # Whatever the failed run left behind is removed once its source is gone.
    (tmp_path / "out/md/BETA.md").write_text("# partially written\n")
    (tmp_path / "docs/BETA.md").unlink()
    asyncio.run(run(ctx, SimpleNamespace(out=tmp_path / "out")))
    assert not (tmp_path / "out/md/BETA.md").exists()
    assert (tmp_path / "out/.vpnd-ai-docs").read_text() == "ALPHA.md\n"
