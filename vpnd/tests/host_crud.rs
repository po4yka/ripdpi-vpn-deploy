//! Actual host CLI calls across independent processes, with a private HOME.
#![allow(clippy::unwrap_used, clippy::expect_used)]
#[test]
fn host_cli_persists_add_show_overwrite_and_remove() {
    let root = tempfile::tempdir().unwrap();
    for path in [
        "ansible",
        "terraform/providers/upcloud",
        "terraform/providers/hetzner",
        "terraform/providers/vultr",
    ] {
        std::fs::create_dir_all(root.path().join(path)).unwrap();
    }
    let invoke = |args: &[&str]| {
        std::process::Command::new(env!("CARGO_BIN_EXE_vpnd"))
            .args([
                "--root",
                root.path().to_str().unwrap(),
                "--provider",
                "upcloud",
                "host",
            ])
            .args(args)
            .env("HOME", root.path())
            .env("XDG_CONFIG_HOME", root.path().join(".config"))
            .env("VPND_LOG", "error")
            .output()
            .unwrap()
    };
    assert!(String::from_utf8_lossy(&invoke(&["list"]).stderr).contains("no hosts registered"));
    assert!(invoke(&[
        "add",
        "test-host",
        "--env",
        "staging",
        "--provider",
        "hetzner",
        "--ipv4",
        "192.0.2.1",
        "--ipv6",
        "2001:db8::1"
    ])
    .status
    .success());
    let output = invoke(&["show", "test-host"]);
    assert!(output.status.success());
    let host: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(host["env"], "staging");
    assert_eq!(host["provider"], "hetzner");
    assert_eq!(host["ipv4"], "192.0.2.1");
    assert_eq!(host["ipv6"], "2001:db8::1");
    assert!(String::from_utf8_lossy(&invoke(&["list"]).stdout).contains("test-host"));
    assert!(
        invoke(&["add", "test-host", "--env", "prod", "--provider", "vultr"])
            .status
            .success()
    );
    let host: serde_json::Value =
        serde_json::from_slice(&invoke(&["show", "test-host"]).stdout).unwrap();
    assert_eq!(host["provider"], "vultr");
    assert!(host["ipv4"].is_null());
    assert!(invoke(&["remove", "test-host"]).status.success());
    assert!(!invoke(&["show", "test-host"]).status.success());
    assert!(!invoke(&["remove", "test-host"]).status.success());
    assert!(String::from_utf8_lossy(&invoke(&["list"]).stderr).contains("no hosts registered"));
}
