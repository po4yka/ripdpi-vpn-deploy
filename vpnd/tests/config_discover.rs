//! Integration tests for config::Context discovery logic.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::fs;
use tempfile::TempDir;
use vpnd::cli::Cli;
use vpnd::config::Context;

/// Build a minimal fake CLI pointing at `root` with the given provider.
fn make_cli(root: &std::path::Path, provider: &str) -> Cli {
    use clap::Parser;
    Cli::parse_from([
        "vpnd",
        "--root",
        root.to_str().unwrap(),
        "--provider",
        provider,
        "completions",
        "bash",
    ])
}

/// Scaffold a valid repo root: Makefile + ansible/ + terraform/providers/<provider>/
fn scaffold_repo(dir: &TempDir, provider: &str) -> std::path::PathBuf {
    let root = dir.path().to_path_buf();
    fs::write(root.join("Makefile"), "# fake\n").unwrap();
    fs::create_dir_all(root.join("ansible")).unwrap();
    fs::create_dir_all(root.join("terraform").join("providers").join(provider)).unwrap();
    root
}

#[test]
fn root_override_wins_over_ancestor_walk() {
    let dir = TempDir::new().unwrap();
    let root = scaffold_repo(&dir, "upcloud");
    let cli = make_cli(&root, "upcloud");
    let ctx = Context::discover(&cli).expect("must succeed with --root override");
    assert_eq!(ctx.root, root.canonicalize().unwrap());
}

#[test]
fn missing_ansible_dir_returns_error() {
    let dir = TempDir::new().unwrap();
    let root = dir.path().to_path_buf();
    fs::write(root.join("Makefile"), "# fake\n").unwrap();
    // no ansible/
    fs::create_dir_all(root.join("terraform").join("providers").join("upcloud")).unwrap();
    let cli = make_cli(&root, "upcloud");
    let err = Context::discover(&cli).unwrap_err();
    assert!(
        err.to_string().contains("ansible"),
        "error must mention ansible, got: {err}"
    );
}

#[test]
fn unknown_provider_returns_error() {
    let dir = TempDir::new().unwrap();
    let root = scaffold_repo(&dir, "upcloud");
    // provider "bogus" has no directory
    let cli = make_cli(&root, "bogus");
    let err = Context::discover(&cli).unwrap_err();
    let msg = err.to_string();
    assert!(
        msg.contains("bogus") || msg.contains("provider") || msg.contains("unknown"),
        "error must mention provider, got: {msg}"
    );
}

#[test]
fn missing_root_dir_returns_error() {
    use clap::Parser;
    let cli = Cli::parse_from([
        "vpnd",
        "--root",
        "/nonexistent/path/that/does/not/exist",
        "completions",
        "bash",
    ]);
    let err = Context::discover(&cli).unwrap_err();
    assert!(
        !err.to_string().is_empty(),
        "must return an error for missing --root"
    );
}

#[test]
fn context_env_and_provider_propagated() {
    let dir = TempDir::new().unwrap();
    let root = scaffold_repo(&dir, "hetzner");
    use clap::Parser;
    let cli = Cli::parse_from([
        "vpnd",
        "--root",
        root.to_str().unwrap(),
        "--env",
        "staging",
        "--provider",
        "hetzner",
        "completions",
        "bash",
    ]);
    let ctx = Context::discover(&cli).unwrap();
    assert_eq!(ctx.env, "staging");
    assert_eq!(ctx.provider, "hetzner");
}
