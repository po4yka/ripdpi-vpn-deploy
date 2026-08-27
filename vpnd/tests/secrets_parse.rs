//! Integration tests for secrets::Secrets parsing against the canonical fixture.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::Path;
use vpnd::secrets::Secrets;

static FIXTURE: &str = include_str!("../../tests/fixtures/secrets-sample.yml");

fn load_fixture() -> Secrets {
    // Write the fixture to a temp file so Secrets::load (which checks is_file) works.
    let tmp = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(tmp.path(), FIXTURE).unwrap();
    Secrets::load(tmp.path()).expect("fixture must parse")
}

#[test]
fn fixture_loads_without_error() {
    let _ = load_fixture();
}

#[test]
fn find_client_hit_returns_correct_client() {
    let s = load_fixture();
    let client = s
        .find_client("phone")
        .expect("canonical xray client must be found");
    assert_eq!(client.name, "phone");
}

#[test]
fn find_client_miss_returns_none() {
    let s = load_fixture();
    assert!(s.find_client("nonexistent-client-xyz").is_none());
}

#[test]
fn extra_preserves_unknown_top_level_keys() {
    let s = load_fixture();
    // The fixture has keys: xray, nginx_xhttp, hysteria, amneziawg_*, backup, watchdog_secrets
    // All unknown to the typed struct → they land in the extra mapping.
    assert!(
        s.extra_key_count() > 0,
        "extra_key_count must be non-zero for fixture with many custom keys"
    );
}

#[test]
fn malformed_or_empty_secrets_fail_without_a_typed_payload() {
    for raw in [
        "",
        " \n",
        "[unclosed",
        "42",
        "xray: 7",
        "xray: {clients: [{uuid: secret}]}",
    ] {
        let file = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(file.path(), raw).unwrap();
        assert!(
            Secrets::load(file.path()).is_err(),
            "unexpected accepted input {raw:?}"
        );
    }
}

#[test]
fn load_fails_gracefully_for_missing_file() {
    let err = Secrets::load(Path::new("/nonexistent/path/secrets.yaml")).unwrap_err();
    assert!(!err.to_string().is_empty());
}

#[test]
fn load_rejects_group_readable_secrets() {
    use std::os::unix::fs::PermissionsExt;

    let tmp = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(tmp.path(), FIXTURE).unwrap();
    std::fs::set_permissions(tmp.path(), std::fs::Permissions::from_mode(0o640)).unwrap();
    assert!(Secrets::load(tmp.path()).is_err());
}

#[test]
fn load_rejects_symlinked_secrets() {
    use std::os::unix::fs::symlink;

    let target = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(target.path(), FIXTURE).unwrap();
    let link_dir = tempfile::TempDir::new().unwrap();
    let link = link_dir.path().join("secrets.yaml");
    symlink(target.path(), &link).unwrap();
    assert!(Secrets::load(&link).is_err());
}

#[test]
fn fixture_exposes_nginx_xhttp_server_name() {
    let s = load_fixture();
    assert_eq!(
        s.nginx_xhttp.server_name.as_deref(),
        Some("vpn.example.com")
    );
}
