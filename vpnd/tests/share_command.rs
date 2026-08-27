//! End-to-end coverage for the `vpnd share` command against canonical secrets.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;

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
    std::fs::create_dir(&out).unwrap();
    for name in ["config.singbox.tmp", "index.tmp", "qr.tmp", "qr-ripdpi.tmp"] {
        std::fs::write(out.join(name), "interrupted old write").unwrap();
    }
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
            qr: true,
            r#type: ShareType::Singbox,
            out: Some(out.clone()),
            token_stdin: false,
            token_file: Some({
                let token = root.path().join("token");
                std::fs::write(&token, "test-token_123\n").unwrap();
                std::fs::set_permissions(&token, std::fs::Permissions::from_mode(0o600)).unwrap();
                token
            }),
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
    for name in [
        "config.singbox.json",
        "index.html",
        "qr.svg",
        "qr-ripdpi.svg",
    ] {
        assert_eq!(
            out.join(name).metadata().unwrap().permissions().mode() & 0o777,
            0o600,
            "{name}"
        );
    }
    // Previously interrupted files are not owned by this invocation. They
    // neither block publication nor get silently deleted by a new writer.
    for name in ["config.singbox.tmp", "index.tmp", "qr.tmp", "qr-ripdpi.tmp"] {
        assert_eq!(
            std::fs::read_to_string(out.join(name)).unwrap(),
            "interrupted old write"
        );
    }
    assert_eq!(std::fs::read_dir(&out).unwrap().count(), 8);
    assert_eq!(
        out.join("config.singbox.json")
            .metadata()
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
}

#[test]
fn invalid_tokens_from_stdin_and_file_fail_before_emission() {
    use std::io::Write;
    use std::process::{Command, Stdio};
    for source in ["stdin", "token file"] {
        for token in ["", " \n\t", "token/invalid", "token<script>", "токен"] {
            let root = TempDir::new().unwrap();
            std::fs::create_dir_all(root.path().join("ansible")).unwrap();
            std::fs::create_dir_all(root.path().join("terraform/providers/upcloud")).unwrap();
            std::fs::write(
                root.path().join("Makefile"),
                "emit-singbox:\n\t@touch emitted\n",
            )
            .unwrap();
            let secrets = root.path().join("vpn-test.secrets.yaml");
            std::fs::write(&secrets, FIXTURE).unwrap();
            std::fs::set_permissions(&secrets, std::fs::Permissions::from_mode(0o600)).unwrap();
            let mut command = Command::new(env!("CARGO_BIN_EXE_vpnd"));
            command
                .args([
                    "--root",
                    root.path().to_str().unwrap(),
                    "--env",
                    "test",
                    "share",
                    "phone",
                ])
                .env("XDG_RUNTIME_DIR", root.path())
                .env("VPN_ENV", "test")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
            if source == "stdin" {
                command.arg("--token-stdin");
            } else {
                let path = root.path().join("token");
                std::fs::write(&path, token).unwrap();
                std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
                command.arg("--token-file").arg(path);
            }
            let mut child = command.spawn().unwrap();
            child
                .stdin
                .take()
                .unwrap()
                .write_all(token.as_bytes())
                .unwrap();
            let output = child.wait_with_output().unwrap();
            assert!(!output.status.success());
            assert!(
                String::from_utf8_lossy(&output.stderr).contains(source),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            assert!(!root.path().join("emitted").exists());
            assert!(!root.path().join("share").exists());
        }
    }
}

#[tokio::test]
async fn missing_or_blank_host_fails_before_creating_a_bundle() {
    for value in [
        "",
        "nginx_xhttp:\n  server_name: '  '\nsubscription:\n  server_name: ''\n",
    ] {
        let root = TempDir::new().unwrap();
        let secrets = root.path().join("secrets.yaml");
        std::fs::write(
            &secrets,
            format!("xray:\n  clients:\n    - name: phone\n{value}"),
        )
        .unwrap();
        std::fs::set_permissions(&secrets, std::fs::Permissions::from_mode(0o600)).unwrap();
        let token = root.path().join("token");
        std::fs::write(&token, "valid-token").unwrap();
        std::fs::set_permissions(&token, std::fs::Permissions::from_mode(0o600)).unwrap();
        let error = share::run(
            &context(&root, secrets),
            ShareArgs {
                client: "phone".into(),
                qr: false,
                r#type: ShareType::Singbox,
                out: None,
                token_stdin: false,
                token_file: Some(token),
            },
        )
        .await
        .unwrap_err();
        assert!(error.to_string().contains("server_name"), "{error}");
        assert!(!root.path().join("share").exists());
    }
}

#[test]
fn failed_qr_publication_removes_its_temp_file() {
    let root = TempDir::new().unwrap();
    let destination = root.path().join("qr.svg");
    std::fs::create_dir(&destination).unwrap();
    assert!(vpnd::pages::qr::write_svg("sensitive-payload", &destination).is_err());
    assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 1);
    assert!(destination.is_dir());
}

#[test]
fn cli_bundle_artifacts_are_private_even_with_permissive_umask() {
    let root = TempDir::new().unwrap();
    for path in ["ansible", "terraform/providers/upcloud"] {
        std::fs::create_dir_all(root.path().join(path)).unwrap();
    }
    std::fs::write(
        root.path().join("Makefile"),
        "emit-singbox:\n\t@printf '%s\\n' '{\"outbounds\":[]}'\n",
    )
    .unwrap();
    let secrets = root.path().join("vpn-test.secrets.yaml");
    std::fs::write(&secrets, FIXTURE).unwrap();
    std::fs::set_permissions(&secrets, std::fs::Permissions::from_mode(0o600)).unwrap();
    let token = root.path().join("token");
    std::fs::write(&token, "valid-Token_123\n").unwrap();
    std::fs::set_permissions(&token, std::fs::Permissions::from_mode(0o600)).unwrap();
    let out = root.path().join("bundle");
    let output = std::process::Command::new("sh")
        .args([
            "-c",
            "umask 022; exec \"$@\"",
            "sh",
            env!("CARGO_BIN_EXE_vpnd"),
            "--root",
            root.path().to_str().unwrap(),
            "--provider",
            "upcloud",
            "--env",
            "test",
            "share",
            "phone",
            "--qr",
            "--token-file",
            token.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
        ])
        .env("XDG_RUNTIME_DIR", root.path())
        .env("VPND_LOG", "error")
        .env_remove("MAKEFLAGS")
        .env_remove("MFLAGS")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    for name in [
        "config.singbox.json",
        "index.html",
        "qr.svg",
        "qr-ripdpi.svg",
    ] {
        assert_eq!(
            out.join(name).metadata().unwrap().permissions().mode() & 0o777,
            0o600,
            "{name}"
        );
    }
    assert_eq!(std::fs::read_dir(out).unwrap().count(), 4);
}
