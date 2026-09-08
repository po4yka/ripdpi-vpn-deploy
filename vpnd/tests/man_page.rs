//! The man page is generated from the real clap tree, never from a
//! hand-maintained replica: `build.rs` once carried a second copy of the CLI
//! shape and drifted (wrong probe-matrix duration default, share subcommand
//! missing its required token flags). This test renders every page from
//! `Cli::command()` into `target/man/`, walks the full command tree, and
//! fails when any visible subcommand or long flag is missing from its page.
//! Seeded-drift assertions pin the exact values the replica got wrong.
//!
//! Generation writes `target/man/vpnd*.1` as a side effect; install with
//! `sudo install -m 644 target/man/vpnd.1 /usr/local/share/man/man1/`.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use clap::{Command, CommandFactory as _};
use clap_mangen::Man;
use vpnd::cli::Cli;

/// Render the whole page set: root plus one page per subcommand, keyed by
/// the qualified roff name (`vpnd`, `vpnd-doctor`, `vpnd-fleet-status`, …).
/// Roff escapes `-` as `\-`; pages are normalized so plain flag names can
/// be asserted.
fn render_page_set() -> Vec<(String, String)> {
    let mut queue: Vec<(String, Command)> = vec![("vpnd".into(), Cli::command())];
    let mut pages: Vec<(String, String)> = Vec::new();
    while let Some((parent, mut command)) = queue.pop() {
        command.build();
        let name = if parent == "vpnd" && command.get_name() == "vpnd" {
            "vpnd".to_string()
        } else {
            format!("{parent}-{}", command.get_name())
        };
        let children: Vec<(String, Command)> = command
            .get_subcommands()
            .filter(|child| child.get_name() != "help")
            .map(|child| (name.clone(), child.clone()))
            .collect();
        queue.extend(children);

        let mut buffer = Vec::new();
        Man::new(command)
            .render(&mut buffer)
            .expect("clap_mangen render must succeed");
        let page = String::from_utf8(buffer)
            .expect("roff output must be valid UTF-8")
            .replace("\\-", "-");
        pages.push((name, page));
    }
    pages
}

fn visible_long_flags(command: &Command) -> Vec<String> {
    command
        .get_arguments()
        .filter(|arg| !arg.is_positional() && !arg.is_hide_set())
        .filter_map(|arg| arg.get_long().map(|long| long.to_string()))
        .collect()
}

#[test]
fn man_pages_cover_every_subcommand_and_visible_flag() {
    let pages = render_page_set();

    for expected in [
        "vpnd",
        "vpnd-deploy",
        "vpnd-reconverge",
        "vpnd-share",
        "vpnd-doctor",
        "vpnd-probe",
        "vpnd-probe-matrix",
        "vpnd-preflight",
        "vpnd-fleet",
        "vpnd-fleet-status",
        "vpnd-fleet-rotate",
        "vpnd-fleet-drift",
        "vpnd-host",
        "vpnd-host-list",
        "vpnd-host-show",
        "vpnd-host-add",
        "vpnd-host-remove",
        "vpnd-ai-docs",
        "vpnd-update",
        "vpnd-completions",
    ] {
        assert!(
            pages.iter().any(|(name, _)| name == expected),
            "missing man page for {expected}; rendered: {:?}",
            pages.iter().map(|(name, _)| name).collect::<Vec<_>>()
        );
    }

    let root_page = &pages
        .iter()
        .find(|(name, _)| name == "vpnd")
        .expect("root page")
        .1;
    for subcommand in [
        "deploy",
        "share",
        "doctor",
        "probe-matrix",
        "host",
        "update",
    ] {
        assert!(
            root_page.contains(subcommand),
            "root page must list the '{subcommand}' subcommand"
        );
    }

    // Walk the live tree again and require every visible long flag of every
    // command to appear in its own page: this is the parity gate — a flag
    // can only reach the page through the same Command the binary parses.
    let mut queue: Vec<(String, Command)> = vec![("vpnd".into(), Cli::command())];
    while let Some((parent, mut command)) = queue.pop() {
        command.build();
        let name = if parent == "vpnd" && command.get_name() == "vpnd" {
            "vpnd".to_string()
        } else {
            format!("{parent}-{}", command.get_name())
        };
        let children: Vec<(String, Command)> = command
            .get_subcommands()
            .filter(|child| child.get_name() != "help")
            .map(|child| (name.clone(), child.clone()))
            .collect();
        queue.extend(children);

        let page = &pages
            .iter()
            .find(|(page_name, _)| page_name == &name)
            .unwrap_or_else(|| panic!("missing page {name}"))
            .1;
        for long in visible_long_flags(&command) {
            assert!(
                page.contains(&format!("--{long}")),
                "man page '{name}' must document --{long}"
            );
        }
    }
}

#[test]
fn man_pages_render_the_real_flag_values_the_replica_drifted_on() {
    let pages = render_page_set();
    let page = |name: &str| {
        pages
            .iter()
            .find(|(page_name, _)| page_name == name)
            .unwrap_or_else(|| panic!("missing page {name}"))
            .1
            .clone()
    };

    // The historical replica documented probe-matrix --duration with a 1h
    // default while the CLI parses 4h. The real tree must win.
    let probe_matrix = page("vpnd-probe-matrix");
    assert!(
        probe_matrix.contains("--duration"),
        "probe-matrix page must document --duration"
    );
    assert!(
        probe_matrix.contains("4h"),
        "probe-matrix page must carry the real 4h duration default"
    );

    // The historical replica omitted share's required token flags entirely.
    let share = page("vpnd-share");
    assert!(share.contains("--token-stdin"), "{share}");
    assert!(share.contains("--token-file"), "{share}");

    // doctor --clip declares its --ai dependency at parse time; the page
    // must show both flags.
    let doctor = page("vpnd-doctor");
    assert!(doctor.contains("--clip"), "{doctor}");
    assert!(doctor.contains("--ai"), "{doctor}");
}

#[test]
fn man_pages_are_written_to_target_man_for_install() {
    let out_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join("man");
    std::fs::create_dir_all(&out_dir).unwrap();

    for (name, page) in render_page_set() {
        let file_name = if name == "vpnd" {
            "vpnd.1".to_string()
        } else {
            format!("{name}.1")
        };
        std::fs::write(out_dir.join(file_name), page).unwrap();
    }
    assert!(out_dir.join("vpnd.1").is_file());
    assert!(out_dir.join("vpnd-doctor.1").is_file());
    assert!(out_dir.join("vpnd-fleet-status.1").is_file());
}
