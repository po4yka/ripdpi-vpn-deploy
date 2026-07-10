//! Integration tests for commands::ai_docs emission.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::fs;
use tempfile::TempDir;
use vpnd::cli::AiDocsArgs;
use vpnd::config::Context;

fn make_ctx(root: &std::path::Path, config_dir: &std::path::Path, explain: bool) -> Context {
    Context {
        root: root.to_path_buf(),
        ansible_dir: root.join("ansible"),
        tf_root: root.join("terraform").join("providers").join("upcloud"),
        env: "prod".into(),
        provider: "upcloud".into(),
        sops_file: config_dir.join("prod.secrets.sops.yaml"),
        secrets_file: std::path::PathBuf::from("/tmp/vpn-prod.secrets.yaml"),
        config_dir: config_dir.to_path_buf(),
        explain,
        yes: false,
        json: false,
    }
}

fn scaffold_docs(root: &std::path::Path) {
    let docs = root.join("docs");
    fs::create_dir_all(&docs).unwrap();
    fs::write(docs.join("ALPHA.md"), "# Alpha\n\nAlpha content here.\n").unwrap();
    fs::write(docs.join("BETA.md"), "# Beta\n\nBeta content here.\n").unwrap();
}

#[tokio::test]
async fn emits_llms_txt_index() {
    let repo = TempDir::new().unwrap();
    let config = TempDir::new().unwrap();
    let out_dir = TempDir::new().unwrap();
    scaffold_docs(repo.path());

    let ctx = make_ctx(repo.path(), config.path(), false);
    let args = AiDocsArgs {
        out: Some(out_dir.path().to_path_buf()),
    };

    vpnd::commands::ai_docs::run(&ctx, args)
        .await
        .expect("ai_docs must succeed");

    let index = fs::read_to_string(out_dir.path().join("llms.txt")).expect("llms.txt must exist");
    assert!(
        index.contains("ALPHA"),
        "index must list ALPHA doc, got: {index}"
    );
    assert!(
        index.contains("BETA"),
        "index must list BETA doc, got: {index}"
    );
}

#[tokio::test]
async fn emits_llms_full_txt_concatenation() {
    let repo = TempDir::new().unwrap();
    let config = TempDir::new().unwrap();
    let out_dir = TempDir::new().unwrap();
    scaffold_docs(repo.path());

    let ctx = make_ctx(repo.path(), config.path(), false);
    let args = AiDocsArgs {
        out: Some(out_dir.path().to_path_buf()),
    };

    vpnd::commands::ai_docs::run(&ctx, args).await.unwrap();

    let full =
        fs::read_to_string(out_dir.path().join("llms-full.txt")).expect("llms-full.txt must exist");
    assert!(
        full.contains("Alpha content here"),
        "full must contain alpha body, got: {full}"
    );
    assert!(
        full.contains("Beta content here"),
        "full must contain beta body, got: {full}"
    );
}

#[tokio::test]
async fn emits_per_doc_copies_in_md_subdir() {
    let repo = TempDir::new().unwrap();
    let config = TempDir::new().unwrap();
    let out_dir = TempDir::new().unwrap();
    scaffold_docs(repo.path());

    let ctx = make_ctx(repo.path(), config.path(), false);
    let args = AiDocsArgs {
        out: Some(out_dir.path().to_path_buf()),
    };

    vpnd::commands::ai_docs::run(&ctx, args).await.unwrap();

    let md_dir = out_dir.path().join("md");
    assert!(md_dir.is_dir(), "md/ subdir must exist");
    assert!(
        md_dir.join("ALPHA.md").is_file(),
        "ALPHA.md per-doc copy must exist"
    );
    assert!(
        md_dir.join("BETA.md").is_file(),
        "BETA.md per-doc copy must exist"
    );
}

#[tokio::test]
async fn index_sorted_by_path() {
    let repo = TempDir::new().unwrap();
    let config = TempDir::new().unwrap();
    let out_dir = TempDir::new().unwrap();
    // Insert in reverse order to test sort
    let docs = repo.path().join("docs");
    fs::create_dir_all(&docs).unwrap();
    fs::write(docs.join("ZEBRA.md"), "# Zebra\n").unwrap();
    fs::write(docs.join("AARDVARK.md"), "# Aardvark\n").unwrap();

    let ctx = make_ctx(repo.path(), config.path(), false);
    let args = AiDocsArgs {
        out: Some(out_dir.path().to_path_buf()),
    };
    vpnd::commands::ai_docs::run(&ctx, args).await.unwrap();

    let index = fs::read_to_string(out_dir.path().join("llms.txt")).unwrap();
    let aardvark_pos = index.find("AARDVARK").unwrap();
    let zebra_pos = index.find("ZEBRA").unwrap();
    assert!(
        aardvark_pos < zebra_pos,
        "index must be sorted alphabetically, got: {index}"
    );
}

#[tokio::test]
async fn explain_mode_does_not_write_files() {
    let repo = TempDir::new().unwrap();
    let config = TempDir::new().unwrap();
    let out_dir = TempDir::new().unwrap();
    scaffold_docs(repo.path());

    let ctx = make_ctx(repo.path(), config.path(), true); // explain=true
    let args = AiDocsArgs {
        out: Some(out_dir.path().to_path_buf()),
    };

    vpnd::commands::ai_docs::run(&ctx, args).await.unwrap();

    // With explain=true the output files must NOT be created
    assert!(
        !out_dir.path().join("llms.txt").exists(),
        "--explain must not write llms.txt"
    );
    assert!(
        !out_dir.path().join("llms-full.txt").exists(),
        "--explain must not write llms-full.txt"
    );
}
