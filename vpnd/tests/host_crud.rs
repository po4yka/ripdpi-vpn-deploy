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

#[test]
fn json_flag_emits_machine_readable_list_and_show() {
    let root = tempfile::tempdir().unwrap();
    for path in ["ansible", "terraform/providers/upcloud"] {
        std::fs::create_dir_all(root.path().join(path)).unwrap();
    }
    let invoke = |args: &[&str]| {
        std::process::Command::new(env!("CARGO_BIN_EXE_vpnd"))
            .args([
                "--root",
                root.path().to_str().unwrap(),
                "--provider",
                "upcloud",
            ])
            .args(args)
            .env("HOME", root.path())
            .env("XDG_CONFIG_HOME", root.path().join(".config"))
            .env("VPND_LOG", "error")
            .output()
            .unwrap()
    };

    // Empty registry: --json emits an empty JSON array on stdout.
    let empty = invoke(&["host", "list", "--json"]);
    assert!(empty.status.success());
    let parsed: serde_json::Value = serde_json::from_slice(&empty.stdout).unwrap();
    assert!(parsed.as_array().unwrap().is_empty());

    assert!(invoke(&[
        "host",
        "add",
        "phone",
        "--env",
        "prod",
        "--provider",
        "upcloud",
        "--ipv4",
        "203.0.113.9"
    ])
    .status
    .success());

    // List: a JSON array with one record carrying the registered fields.
    let listed = invoke(&["host", "list", "--json"]);
    assert!(listed.status.success());
    let hosts: serde_json::Value = serde_json::from_slice(&listed.stdout).unwrap();
    let entries = hosts.as_array().unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0]["name"], "phone");
    assert_eq!(entries[0]["env"], "prod");
    assert_eq!(entries[0]["ipv4"], "203.0.113.9");
    assert!(entries[0]["deployed_with"].is_null());

    // Show: compact single-line JSON under --json, pretty object without.
    let shown = invoke(&["host", "show", "phone", "--json"]);
    assert!(shown.status.success());
    let one_line = String::from_utf8_lossy(&shown.stdout);
    assert_eq!(
        one_line.matches('\n').count(),
        1,
        "compact JSON: {one_line}"
    );
    let record: serde_json::Value = serde_json::from_slice(&shown.stdout).unwrap();
    assert_eq!(record["provider"], "upcloud");
    let pretty = invoke(&["host", "show", "phone"]);
    let pretty_text = String::from_utf8_lossy(&pretty.stdout);
    assert!(
        pretty_text.matches('\n').count() > 1,
        "human mode stays pretty: {pretty_text}"
    );
}
