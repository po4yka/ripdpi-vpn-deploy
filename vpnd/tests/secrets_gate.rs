//! Gate tests for Secrets::load — open-once fstat discipline.
//!
//! Symlinks are rejected atomically on open; owner/mode checks run on the
//! HELD handle so what is permission-checked is byte-for-byte what gets
//! read (no stat/read swap window).
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::os::unix::fs::PermissionsExt;

use vpnd::config::Context;
use vpnd::secrets::Secrets;

fn harden(path: &std::path::Path) -> anyhow::Result<()> {
    let root = path.parent().unwrap();
    Context {
        root: root.into(),
        ansible_dir: root.into(),
        tf_root: root.into(),
        env: "test".into(),
        provider: "upcloud".into(),
        sops_file: root.join("source.yaml"),
        secrets_file: path.into(),
        config_dir: root.into(),
        explain: false,
        yes: true,
        json: false,
    }
    .secure_secrets_file()
}

#[test]
fn hardening_rejects_missing_plaintext() {
    let dir = tempfile::tempdir().unwrap();
    assert!(harden(&dir.path().join("missing.yaml")).is_err());
}

#[test]
fn hardening_rejects_symlinks_without_chmoding_the_target() {
    let dir = tempfile::tempdir().unwrap();
    let target = dir.path().join("other-file");
    std::fs::write(&target, "not a secret").unwrap();
    std::fs::set_permissions(&target, std::fs::Permissions::from_mode(0o644)).unwrap();
    let link = dir.path().join("secrets.yaml");
    std::os::unix::fs::symlink(&target, &link).unwrap();
    let result = harden(&link);
    assert_eq!(
        target.metadata().unwrap().permissions().mode() & 0o777,
        0o644
    );
    assert!(result.is_err());
}

#[test]
fn hardening_regular_plaintext_sets_0600_and_keeps_it_readable() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("secrets.yaml");
    std::fs::write(&path, STUB_YAML).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap();
    harden(&path).unwrap();
    assert_eq!(path.metadata().unwrap().permissions().mode() & 0o777, 0o600);
    assert!(Secrets::load(&path).unwrap().find_client("phone").is_some());
}

#[test]
fn load_accepts_private_read_only_files() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("read-only.yaml");
    std::fs::write(&path, STUB_YAML).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o400)).unwrap();
    assert!(Secrets::load(&path).unwrap().find_client("phone").is_some());
}

#[test]
fn file_gates_reject_fifos_without_waiting_for_a_writer() {
    let dir = tempfile::tempdir().unwrap();
    let fifo = dir.path().join("not-a-regular-file");
    assert!(std::process::Command::new("mkfifo")
        .args(["-m", "600"])
        .arg(&fifo)
        .status()
        .unwrap()
        .success());
    let (send, receive) = std::sync::mpsc::channel();
    let worker = std::thread::spawn(move || {
        send.send((harden(&fifo).is_err(), Secrets::load(&fifo).is_err()))
            .unwrap();
    });
    assert_eq!(
        receive
            .recv_timeout(std::time::Duration::from_secs(2))
            .unwrap(),
        (true, true)
    );
    worker.join().unwrap();
}

#[test]
fn file_gates_never_follow_concurrently_swapped_symlinks() {
    use std::sync::atomic::{AtomicBool, Ordering};
    let dir = tempfile::tempdir().unwrap();
    let trusted = dir.path().join("trusted.yaml");
    let other = dir.path().join("other.yaml");
    let current = dir.path().join("current.yaml");
    let next = dir.path().join("next.yaml");
    std::fs::write(&trusted, STUB_YAML).unwrap();
    std::fs::write(&other, "xray:\n  clients:\n    - name: redirected\n").unwrap();
    for path in [&trusted, &other] {
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600)).unwrap();
    }
    std::fs::hard_link(&trusted, &current).unwrap();
    let running = AtomicBool::new(true);
    let (reads, redirected) = std::thread::scope(|scope| {
        let writer = scope.spawn(|| {
            while running.load(Ordering::Relaxed) {
                std::os::unix::fs::symlink(&other, &next).unwrap();
                std::fs::rename(&next, &current).unwrap();
                std::fs::hard_link(&trusted, &next).unwrap();
                std::fs::rename(&next, &current).unwrap();
            }
        });
        let mut reads = 0;
        let mut redirected = 0;
        for _ in 0..5000 {
            if let Ok(secrets) = Secrets::load(&current) {
                reads += 1;
                redirected += usize::from(secrets.find_client("redirected").is_some());
            }
        }
        // A path-based chmod after a safe open would still follow a later
        // symlink swap. The unrelated target must retain its original mode.
        std::fs::set_permissions(&other, std::fs::Permissions::from_mode(0o644)).unwrap();
        for _ in 0..5000 {
            let _ = harden(&current);
        }
        running.store(false, Ordering::Relaxed);
        writer.join().unwrap();
        (reads, redirected)
    });
    assert!(
        reads > 0,
        "must exercise successful reads while the path changes"
    );
    assert_eq!(redirected, 0, "an open followed the swapped symlink");
    assert_eq!(
        other.metadata().unwrap().permissions().mode() & 0o777,
        0o644
    );
}

const STUB_YAML: &str =
    "xray:\n  clients:\n    - name: phone\n      uuid: 00000000-0000-0000-0000-000000000000\n";

#[test]
fn load_rejects_symlink_even_to_compliant_file() {
    let dir = tempfile::tempdir().unwrap();
    let target = dir.path().join("real.secrets.yaml");
    std::fs::write(&target, STUB_YAML).unwrap();
    std::fs::set_permissions(&target, std::fs::Permissions::from_mode(0o600)).unwrap();

    let link = dir.path().join("link.secrets.yaml");
    std::os::unix::fs::symlink(&target, &link).unwrap();

    let err = Secrets::load(&link).expect_err("symlinked secrets path must be rejected");
    assert!(
        err.to_string().contains("regular file"),
        "unexpected error: {err}"
    );
}

#[test]
fn load_rejects_loose_mode_on_held_handle() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("loose.secrets.yaml");
    std::fs::write(&path, STUB_YAML).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap();

    let err = Secrets::load(&path).expect_err("0644 secrets file must be rejected");
    assert!(
        err.to_string()
            .contains("unsafe owner, type, or permissions"),
        "unexpected error: {err}"
    );
}

#[test]
fn load_accepts_compliant_0600_regular_file() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("ok.secrets.yaml");
    std::fs::write(&path, STUB_YAML).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();

    let secrets = Secrets::load(&path).expect("compliant 0600 regular file must parse");
    assert!(secrets.find_client("phone").is_some());
}
