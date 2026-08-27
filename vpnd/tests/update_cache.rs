//! Exercise the actual CLI cache path and emitted notices without external HTTP.
#![allow(clippy::unwrap_used, clippy::expect_used)]
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

fn command(root: &std::path::Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_vpnd"));
    command
        .args(["--root", root.to_str().unwrap(), "--provider", "upcloud"])
        .env("HOME", root)
        .env("XDG_CONFIG_HOME", root.join(".config"))
        .env("VPND_LOG", "error");
    command
}
fn cache_dir(root: &std::path::Path) -> std::path::PathBuf {
    #[cfg(target_os = "macos")]
    let base = root.join("Library/Application Support");
    #[cfg(not(target_os = "macos"))]
    let base = root.join(".config");
    base.join("vpn-provision")
}

#[test]
fn fresh_cache_drives_actual_notice_and_suppresses_current_release() {
    let root = tempfile::tempdir().unwrap();
    for path in ["ansible", "terraform/providers/upcloud"] {
        std::fs::create_dir_all(root.path().join(path)).unwrap();
    }
    let cache_dir = cache_dir(root.path());
    std::fs::create_dir_all(&cache_dir).unwrap();
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();
    for (tag, notice) in [
        (format!("vpnd-v{}", env!("CARGO_PKG_VERSION")), false),
        ("vpnd-v999.0.0".into(), true),
        ("other-v999.0.0".into(), false),
    ] {
        let cache = format!("checked_at = {now}\nlatest_tag = \"{tag}\"\n");
        let path = cache_dir.join("last-update-check.toml");
        std::fs::write(&path, &cache).unwrap();
        let output = command(root.path()).arg("update").output().unwrap();
        assert!(output.status.success());
        let stderr = String::from_utf8(output.stderr).unwrap();
        assert_eq!(
            stderr.contains("A newer vpnd release is available"),
            notice,
            "{tag}: {stderr}"
        );
        if notice {
            assert!(stderr.contains("v999.0.0"));
            assert!(stderr.contains(env!("CARGO_PKG_VERSION")));
        }
        assert_eq!(
            std::fs::read_to_string(path).unwrap(),
            cache,
            "fresh cache must not be rewritten"
        );
    }
}

#[test]
fn explain_reports_endpoint_without_creating_cache_or_needing_repository() {
    let root = tempfile::tempdir().unwrap();
    for args in [["--explain", "update"], ["update", "--explain"]] {
        let output = command(root.path()).args(args).output().unwrap();
        assert!(output.status.success());
        assert!(String::from_utf8(output.stdout)
            .unwrap()
            .contains("GET https://api.github.com/repos/po4yka/ripdpi-vpn-deploy/releases/latest"));
        assert!(!cache_dir(root.path()).exists());
    }
}
