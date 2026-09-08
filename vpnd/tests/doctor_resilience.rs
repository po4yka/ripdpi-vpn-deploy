//! Doctor resilience at the process boundary: a failing diagnostic step must
//! not abort the run. The report keeps every completed step, marks the
//! failed one, captures its stderr, and the CLI exits nonzero. External
//! infrastructure commands are explicit `make` doubles, as in
//! deploy_lifecycle.rs.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::io::Read as _;
use std::os::unix::fs::PermissionsExt;
use std::process::{Command, Output};

struct Fixture {
    dir: tempfile::TempDir,
}

impl Fixture {
    fn new() -> Self {
        let fixture = Self {
            dir: tempfile::tempdir().unwrap(),
        };
        let root = fixture.dir.path();
        for path in [
            "bin",
            "ansible/inventory",
            "terraform/providers/upcloud",
            "runtime",
        ] {
            std::fs::create_dir_all(root.join(path)).unwrap();
        }
        std::fs::write(root.join("Makefile"), "# doctor step doubles\n").unwrap();
        fixture.executable(
            "make",
            r#"#!/bin/sh
target=$1
shift
echo "ran $target"
case "$target" in
  fleet-status|asn-drift|check-ip-reputation|probing-summary|audit-permissions)
    echo "$target: healthy" ;;
  burn-check)
    if [ "${FAIL_BURN_CHECK:-0}" = 1 ]; then
      echo "burn-check: address is burned" >&2
      exit 3
    fi
    echo "burn-check: healthy" ;;
esac
"#,
        );
        fixture
    }

    fn executable(&self, name: &str, script: &str) {
        let path = self.dir.path().join("bin").join(name);
        std::fs::write(&path, script).unwrap();
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).unwrap();
    }

    fn command(&self, args: &[&str]) -> Command {
        let root = self.dir.path();
        let mut command = Command::new(env!("CARGO_BIN_EXE_vpnd"));
        command
            .args(["--root", root.to_str().unwrap(), "--env", "test", "--yes"])
            .args(args)
            .env("HOME", root.join("home"))
            .env("XDG_CONFIG_HOME", root.join("home/.config"))
            .env("XDG_RUNTIME_DIR", root.join("runtime"))
            .env("VPND_LOG", "error")
            .env(
                "PATH",
                format!(
                    "{}:{}",
                    root.join("bin").display(),
                    std::env::var("PATH").unwrap()
                ),
            );
        command
    }
}

const STEP_ORDER: [&str; 6] = [
    "make fleet-status",
    "make burn-check",
    "make asn-drift",
    "make check-ip-reputation",
    "make probing-summary",
    "make audit-permissions",
];

fn section_positions(report: &str) -> Vec<usize> {
    // Section headers are the full redacted invocation, e.g.
    // "### (cd <root> && make fleet-status 'ENV=test' …)", so the step
    // name alone is the stable search key.
    STEP_ORDER
        .iter()
        .map(|step| {
            report
                .find(step)
                .unwrap_or_else(|| panic!("report must contain the '{step}' section"))
        })
        .collect()
}

#[test]
fn all_steps_run_and_report_after_a_mid_run_failure() {
    let fixture = Fixture::new();
    let output = fixture
        .command(&["doctor"])
        .env("FAIL_BURN_CHECK", "1")
        .output()
        .unwrap();

    assert!(
        !output.status.success(),
        "a failed diagnostic step must exit nonzero"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("1 of 6 doctor diagnostic steps failed"),
        "failure summary must name the failed count: {stderr}"
    );

    let report = String::from_utf8_lossy(&output.stdout);
    let positions = section_positions(&report);
    // The failure happened at step two; every later step still ran.
    for pair in positions.windows(2) {
        assert!(
            pair[0] < pair[1],
            "sections must appear in step order: {report}"
        );
    }
    assert!(
        report.contains("**Failed**"),
        "the failed step must be marked: {report}"
    );
    assert!(
        report.contains("burn-check: address is burned"),
        "the failed step's stderr must be captured: {report}"
    );
    assert!(
        report.contains("asn-drift: healthy"),
        "steps after the failure must keep their output: {report}"
    );
}

#[test]
fn healthy_run_exits_zero_without_failed_marks() {
    let fixture = Fixture::new();
    let output = fixture.command(&["doctor"]).output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = String::from_utf8_lossy(&output.stdout);
    assert!(!report.contains("**Failed**"), "{report}");
    assert_eq!(section_positions(&report).len(), 6);
}

#[test]
fn bundle_preserves_the_failed_step_evidence() {
    let fixture = Fixture::new();
    let bundle_path = fixture.dir.path().join("doctor-bundle.tar.gz");
    let output = fixture
        .command(&["doctor", "--bundle"])
        .arg(&bundle_path)
        .env("FAIL_BURN_CHECK", "1")
        .output()
        .unwrap();
    assert!(
        !output.status.success(),
        "the nonzero exit must survive --bundle"
    );
    assert!(bundle_path.is_file(), "bundle must exist");

    let bundle_file = std::fs::File::open(&bundle_path).unwrap();
    let gz = flate2::read::GzDecoder::new(bundle_file);
    let mut archive = tar::Archive::new(gz);
    let report_entry = archive
        .entries()
        .unwrap()
        .filter_map(|entry| entry.ok())
        .find(|entry| {
            entry
                .path()
                .map(|path| path.to_string_lossy().ends_with("doctor-report.md"))
                .unwrap_or(false)
        })
        .expect("bundle must contain doctor-report.md");
    let mut report_entry = report_entry;
    let mut bundle_bytes = Vec::new();
    report_entry.read_to_end(&mut bundle_bytes).unwrap();
    let report = String::from_utf8(bundle_bytes).unwrap();
    assert!(report.contains("**Failed**"), "{report}");
    assert!(
        report.contains("burn-check: address is burned"),
        "the exported report must keep the failed step's stderr: {report}"
    );
    assert_eq!(section_positions(&report).len(), 6);
}

#[test]
fn explain_mode_lists_the_steps_without_running_them() {
    let fixture = Fixture::new();
    let output: Output = fixture.command(&["--explain", "doctor"]).output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let explain = String::from_utf8_lossy(&output.stderr);
    for step in STEP_ORDER {
        assert!(
            explain.contains(step),
            "explain output must list '{step}': {explain}"
        );
    }
}
