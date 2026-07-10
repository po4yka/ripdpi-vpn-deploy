//! Snapshot tests for shell completion output.
//!
//! Locks in the clap-generated completion shape so accidental CLI flag changes
//! surface as clear PR diffs rather than silent regressions.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use clap::CommandFactory;
use clap_complete::{generate, shells};
use vpnd::cli::Cli;

fn generate_completion(shell_name: &str) -> String {
    let mut cmd = Cli::command();
    let mut buf = Vec::new();
    match shell_name {
        "bash" => generate(shells::Bash, &mut cmd, "vpnd", &mut buf),
        "zsh" => generate(shells::Zsh, &mut cmd, "vpnd", &mut buf),
        "fish" => generate(shells::Fish, &mut cmd, "vpnd", &mut buf),
        _ => panic!("unsupported shell: {shell_name}"),
    }
    String::from_utf8(buf).expect("completion output must be valid UTF-8")
}

#[test]
fn bash_completion_snapshot() {
    let output = generate_completion("bash");
    insta::assert_snapshot!("bash_completions", output);
}

#[test]
fn zsh_completion_snapshot() {
    let output = generate_completion("zsh");
    insta::assert_snapshot!("zsh_completions", output);
}

#[test]
fn fish_completion_snapshot() {
    let output = generate_completion("fish");
    insta::assert_snapshot!("fish_completions", output);
}

// Structural assertions that hold regardless of exact snapshot content:

#[test]
fn bash_completion_contains_vpnd_subcommands() {
    let output = generate_completion("bash");
    // Each top-level subcommand must appear in the completion script
    for subcmd in [
        "deploy", "share", "doctor", "host", "update", "completions",
        "reconverge", "probe", "probe-matrix", "preflight", "fleet", "ai-docs",
    ] {
        assert!(
            output.contains(subcmd),
            "bash completion must mention '{subcmd}'"
        );
    }
}

#[test]
fn zsh_completion_contains_vpnd_subcommands() {
    let output = generate_completion("zsh");
    for subcmd in [
        "deploy", "share", "doctor", "host", "update", "completions",
        "reconverge", "probe", "probe-matrix", "preflight", "fleet", "ai-docs",
    ] {
        assert!(
            output.contains(subcmd),
            "zsh completion must mention '{subcmd}'"
        );
    }
}

#[test]
fn fish_completion_contains_vpnd_subcommands() {
    let output = generate_completion("fish");
    for subcmd in [
        "deploy", "share", "doctor", "host", "update", "completions",
        "reconverge", "probe", "probe-matrix", "preflight", "fleet", "ai-docs",
    ] {
        assert!(
            output.contains(subcmd),
            "fish completion must mention '{subcmd}'"
        );
    }
}

#[test]
fn share_completions_offer_only_token_input_flags() {
    for shell in ["bash", "zsh", "fish"] {
        let output = generate_completion(shell);
        match shell {
            "bash" => {
                assert!(output.contains("--token-stdin"));
                assert!(output.contains("--token-file"));
                assert!(!output.contains("--token "));
            }
            "zsh" => {
                assert!(output.contains("--token-stdin"));
                assert!(output.contains("--token-file"));
                assert!(!output.contains("--token=["));
            }
            "fish" => {
                assert!(output.contains("-l token-stdin"));
                assert!(output.contains("-l token-file"));
                assert!(!output.contains(" -l token -d "));
            }
            _ => unreachable!("unsupported completion shell"),
        }
    }
}

#[test]
fn bash_completion_mentions_global_flags() {
    let output = generate_completion("bash");
    assert!(output.contains("--explain") || output.contains("explain"),
        "bash completion must include --explain flag");
}
