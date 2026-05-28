// Build scripts are allowed to panic on failure — that is the standard
// mechanism for aborting a Cargo build with a diagnostic message.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    // Re-run only when cli.rs changes.
    println!("cargo:rerun-if-changed=src/cli.rs");

    let out = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("target")
        .join("man");
    fs::create_dir_all(&out).unwrap();

    // Build the clap Command from the bin crate's CLI definition.
    // clap_mangen operates on a clap::Command value produced at build time.
    let cmd = build_cli();
    let man = clap_mangen::Man::new(cmd);
    let mut buf = Vec::new();
    man.render(&mut buf).expect("clap_mangen render failed");
    fs::write(out.join("vpnd.1"), buf).expect("write target/man/vpnd.1 failed");
}

/// Minimal replica of the top-level CLI shape sufficient for man-page generation.
/// Keep in sync with src/cli.rs.
fn build_cli() -> clap::Command {
    use clap::{Arg, Command};

    Command::new("vpnd")
        .version(env!("CARGO_PKG_VERSION"))
        .about("Convenience CLI for vpn-deploy (wraps Make / Terraform / Ansible / SOPS)")
        .arg(Arg::new("explain").long("explain").global(true).action(clap::ArgAction::SetTrue).help("Print the underlying shell invocations and exit without running them"))
        .arg(Arg::new("env").long("env").short('e').global(true).default_value("prod").help("Target environment"))
        .arg(Arg::new("provider").long("provider").short('p').global(true).default_value("upcloud").help("Cloud provider Terraform root"))
        .arg(Arg::new("yes").long("yes").short('y').global(true).action(clap::ArgAction::SetTrue).help("Skip interactive confirmation prompts"))
        .arg(Arg::new("json").long("json").global(true).action(clap::ArgAction::SetTrue).help("Emit machine-readable JSON instead of human output"))
        .arg(Arg::new("root").long("root").global(true).help("Override the vpn-deploy repo root"))
        .subcommand(Command::new("deploy").about("Interactive deploy wizard")
            .arg(Arg::new("skip-precheck").long("skip-precheck").action(clap::ArgAction::SetTrue))
            .arg(Arg::new("tag-on-success").long("tag-on-success").action(clap::ArgAction::SetTrue)))
        .subcommand(Command::new("reconverge").about("Idempotent re-deploy against existing host(s)")
            .arg(Arg::new("host").long("host"))
            .arg(Arg::new("dry-run").long("dry-run").action(clap::ArgAction::SetTrue)))
        .subcommand(Command::new("share").about("Bundled recipient handoff (URL + QR + sing-box + app cards)")
            .arg(Arg::new("client").required(true))
            .arg(Arg::new("qr").long("qr").action(clap::ArgAction::SetTrue))
            .arg(Arg::new("type").long("type").default_value("singbox"))
            .arg(Arg::new("out").long("out")))
        .subcommand(Command::new("doctor").about("Diagnostic bundle")
            .arg(Arg::new("host").long("host"))
            .arg(Arg::new("ai").long("ai").action(clap::ArgAction::SetTrue).help("Format output as a clipboard-ready prompt for an AI assistant"))
            .arg(Arg::new("clip").long("clip").action(clap::ArgAction::SetTrue).help("Copy AI prompt to the system clipboard (requires --ai)"))
            .arg(Arg::new("bundle").long("bundle").help("Pack diagnostic bundle into a gzip-tar at this path")))
        .subcommand(Command::new("probe").about("Profile-aware probing")
            .arg(Arg::new("host").long("host"))
            .arg(Arg::new("profile").long("profile").default_value("all")))
        .subcommand(Command::new("probe-matrix").about("Multi-protocol simultaneity DPI probe across a (protocol × destination) matrix")
            .arg(Arg::new("duration").long("duration").default_value("1h").help("Total run duration (e.g. 30m, 2h, 1d)"))
            .arg(Arg::new("poll-interval-seconds").long("poll-interval-seconds").help("Seconds between ticks (overrides config)"))
            .arg(Arg::new("config").long("config").help("Path to probe-matrix.yaml config"))
            .arg(Arg::new("output").long("output").help("Path to write the JSON report")))
        .subcommand(Command::new("preflight").about("Pre-deploy guards (spot-check, certs, perms, render, schema)")
            .arg(Arg::new("skip-certs").long("skip-certs").action(clap::ArgAction::SetTrue)))
        .subcommand(Command::new("fleet").about("Fleet-wide operations")
            .subcommand(Command::new("status").about("Summary table across every host:env pair"))
            .subcommand(Command::new("rotate").about("Coordinated rotation across the fleet")
                .arg(Arg::new("plan").long("plan").required(true))
                .arg(Arg::new("resume").long("resume").action(clap::ArgAction::SetTrue))
                .arg(Arg::new("dry-run").long("dry-run").action(clap::ArgAction::SetTrue)))
            .subcommand(Command::new("drift").about("Diff fleet state against the last known-good tag")))
        .subcommand(Command::new("host").about("Local host registry")
            .subcommand(Command::new("list").about("List registered hosts"))
            .subcommand(Command::new("show").about("Show one host record").arg(Arg::new("name").required(true)))
            .subcommand(Command::new("add").about("Add a host record")
                .arg(Arg::new("name").required(true))
                .arg(Arg::new("env").long("env").required(true))
                .arg(Arg::new("provider").long("provider").required(true))
                .arg(Arg::new("ipv4").long("ipv4"))
                .arg(Arg::new("ipv6").long("ipv6")))
            .subcommand(Command::new("remove").about("Remove a host record").arg(Arg::new("name").required(true))))
        .subcommand(Command::new("ai-docs").about("Machine-readable docs endpoints for AI assistants")
            .arg(Arg::new("out").long("out")))
        .subcommand(Command::new("update").about("Check for a newer vpnd release on GitHub")
            .arg(Arg::new("explain").long("explain").action(clap::ArgAction::SetTrue).help("Print the API URL that would be checked and exit")))
        .subcommand(Command::new("completions").about("Emit shell completions to stdout")
            .arg(Arg::new("shell").required(true).help("bash | zsh | fish | powershell")))
}
