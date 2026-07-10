//! End-to-end coverage for the `vpnd share` command against canonical secrets.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;
use std::os::unix::fs::PermissionsExt;

use tempfile::TempDir;
use vpnd::cli::{ShareArgs, ShareType};
use vpnd::commands::share;
use vpnd::config::Context;

const FIXTURE: &str = include_str!("../../tests/fixtures/secrets-sample.yml");

fn context(root: &TempDir, secrets_file: PathBuf) -> Context {
    Context {
        root: root.path().to_path_buf(),
        ansible_dir: root.path().join("ansible"),
        tf_root: root.path().join("terraform/providers/upcloud"),
        env: "test".into(),
        provider: "upcloud".into(),
        sops_file: root.path().join("test.secrets.sops.yaml"),
        secrets_file,
        config_dir: root.path().join("config"),
        explain: false,
        yes: true,
        json: false,
    }
}

#[tokio::test]
async fn share_generates_a_bundle_for_a_canonical_xray_client() {
    let root = TempDir::new().unwrap();
    let secrets_file = root.path().join("secrets.yaml");
    let out = root.path().join("bundle");
    std::fs::write(
        root.path().join("Makefile"),
        "emit-singbox:\n\t@printf '%s\\n' '{\"outbounds\":[]}'\n",
    )
    .unwrap();
    std::fs::write(
        &secrets_file,
        format!("{FIXTURE}\nsubscription:\n  server_name: sub.example.com\n  port: 8444\n"),
    )
    .unwrap();
    std::fs::set_permissions(&secrets_file, std::fs::Permissions::from_mode(0o600)).unwrap();

    share::run(
        &context(&root, secrets_file),
        ShareArgs {
            client: "phone".into(),
            qr: false,
            r#type: ShareType::Singbox,
            out: Some(out.clone()),
            token: Some("test-token_123".into()),
        },
    )
    .await
    .expect("share must accept canonical xray.clients");

    assert_eq!(
        std::fs::read_to_string(out.join("config.singbox.json")).unwrap(),
        "{\"outbounds\":[]}\n"
    );
    let page = std::fs::read_to_string(out.join("index.html")).unwrap();
    assert!(page.contains("phone"));
    assert!(page.contains("https://sub.example.com:8444/sub/test-token_123"));
    assert_eq!(out.metadata().unwrap().permissions().mode() & 0o777, 0o700);
    assert_eq!(out.join("config.singbox.json").metadata().unwrap().permissions().mode() & 0o777, 0o600);
}
