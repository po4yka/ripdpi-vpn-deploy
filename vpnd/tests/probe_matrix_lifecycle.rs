//! Real CLI validation tests. Local driver fixtures are not live network proof.
#![allow(clippy::unwrap_used, clippy::expect_used)]
use serde_json::{json, Value};
use std::os::unix::fs::PermissionsExt;
use std::process::{Command, Stdio};

struct Fixture {
    root: tempfile::TempDir,
}
impl Fixture {
    fn new(control: &str, cell: &str) -> Self {
        let root = tempfile::tempdir().unwrap();
        for path in ["ansible", "terraform/providers/upcloud"] {
            std::fs::create_dir_all(root.path().join(path)).unwrap();
        }
        std::fs::write(
            root.path().join("Makefile"),
            format!("probe-matrix-control:\n\t@{control}\nprobe-matrix-cell:\n\t@{cell}\n"),
        )
        .unwrap();
        let mut targets = Vec::new();
        for (id, topology) in [
            ("pair-dual", "single-ip-dual-role"),
            ("pair-split", "split-hop-ingress"),
        ] {
            let path = root.path().join(format!("{id}.json"));
            std::fs::write(&path, json!({"schema_version":1,"target_id":id,"endpoint":"192.0.2.1","protocols":{"mtproto":{"port":10443,"secret":id}}}).to_string()).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
            targets.push(json!({"id":id,"comparison_set":"pair","destination_class":"neutral-pattern","topology":topology,"profile_file":path}));
        }
        std::fs::write(root.path().join("matrix.yaml"), json!({"schema_version":2,"vantage":"test-path","poll_interval_seconds":1,"control":{"url":"https://control.example","expected_status":204,"timeout_seconds":1,"degraded_after_ms":500},"protocols":["mtproto"],"targets":targets}).to_string()).unwrap();
        Self { root }
    }
    fn command(&self, duration: &str) -> Command {
        let mut command = Command::new(env!("CARGO_BIN_EXE_vpnd"));
        command.args([
            "--root",
            self.root.path().to_str().unwrap(),
            "--provider",
            "upcloud",
            "probe-matrix",
            "--config",
            self.root.path().join("matrix.yaml").to_str().unwrap(),
            "--duration",
            duration,
            "--output",
            self.root.path().join("report.json").to_str().unwrap(),
        ]);
        command
            .env_remove("MAKEFLAGS")
            .env_remove("MFLAGS")
            .env("VPND_LOG", "error")
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        command
    }
}

#[test]
fn invalid_config_and_profile_inputs_fail_before_probe_execution() {
    let valid = Fixture::new("touch invoked", "touch invoked");
    assert!(valid
        .command("1s")
        .arg("--explain")
        .status()
        .unwrap()
        .success());
    assert!(!valid.root.path().join("invoked").exists());
    for case in 0..19 {
        let fixture = Fixture::new("touch invoked", "touch invoked");
        let path = fixture.root.path().join("matrix.yaml");
        let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        let profile_path = fixture.root.path().join("pair-dual.json");
        let mut profile: Value =
            serde_json::from_slice(&std::fs::read(&profile_path).unwrap()).unwrap();
        match case {
            0 => config["schema_version"] = json!(99),
            1 => config["vantage"] = json!("UPPER invalid"),
            2 => config["control"]["url"] = json!("http://example.com"),
            3 => config["control"]["expected_status"] = json!(600),
            4 => config["control"]["timeout_seconds"] = json!(0),
            5 => config["control"]["degraded_after_ms"] = json!(0),
            6 => config["protocols"] = json!([]),
            7 => config["protocols"] = json!(["mtproto", "mtproto"]),
            8 => config["targets"][1]["id"] = json!("pair-dual"),
            9 => config["targets"][0]["profile_file"] = json!("relative.json"),
            10 => config["targets"][1]["topology"] = json!("single-ip-dual-role"),
            11 => config["targets"][1]["destination_class"] = json!("allowlist-pattern"),
            12 => profile["schema_version"] = json!(99),
            13 => profile["target_id"] = json!("other-target"),
            14 => profile["protocols"] = json!({}),
            15 => profile["protocols"]["mtproto"]["port"] = json!(999),
            16 => std::fs::set_permissions(&profile_path, std::fs::Permissions::from_mode(0o640))
                .unwrap(),
            17 => config["poll_interval_seconds"] = json!(0),
            18 => config["control"]["timeout_seconds"] = json!(61),
            _ => unreachable!(),
        }
        std::fs::write(&path, config.to_string()).unwrap();
        std::fs::write(&profile_path, profile.to_string()).unwrap();
        assert!(
            !fixture
                .command("1s")
                .arg("--explain")
                .status()
                .unwrap()
                .success(),
            "case {case}"
        );
        assert!(!fixture.root.path().join("invoked").exists());
    }
    for kind in ["missing", "symlink", "directory", "malformed"] {
        let fixture = Fixture::new("touch invoked", "touch invoked");
        let path = fixture.root.path().join("pair-dual.json");
        std::fs::remove_file(&path).unwrap();
        match kind {
            "symlink" => {
                std::os::unix::fs::symlink(fixture.root.path().join("pair-split.json"), &path)
                    .unwrap()
            }
            "directory" => std::fs::create_dir(&path).unwrap(),
            "malformed" => {
                std::fs::write(&path, "not json").unwrap();
                std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
            }
            _ => {}
        }
        assert!(
            !fixture
                .command("1s")
                .arg("--explain")
                .status()
                .unwrap()
                .success(),
            "{kind}"
        );
    }
}
