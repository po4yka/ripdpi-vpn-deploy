//! Gate tests for Secrets::load — open-once fstat discipline.
//!
//! Symlinks are rejected before opening; owner/mode checks run on the
//! HELD handle so what is permission-checked is byte-for-byte what gets
//! read (no stat/read swap window).
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::os::unix::fs::PermissionsExt;

use vpnd::secrets::Secrets;

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
