//! Real CLI/process/checkpoint tests. Local driver fixtures are not live network proof.
#![allow(clippy::unwrap_used, clippy::expect_used)]
use serde_json::{json, Value};
use std::os::unix::fs::PermissionsExt;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

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
    fn report(&self) -> Option<Value> {
        serde_json::from_slice(&std::fs::read(self.root.path().join("report.json")).ok()?).ok()
    }
}
struct Running(Child);
impl Drop for Running {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
fn wait(child: &mut Child) -> std::process::ExitStatus {
    let deadline = Instant::now() + Duration::from_secs(8);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status;
        }
        assert!(
            Instant::now() < deadline,
            "CLI did not finish within bounded test budget"
        );
        std::thread::sleep(Duration::from_millis(20));
    }
}
const OK: &str = "printf '%s\\n' '{\"verdict\":\"ok\",\"rtt_ms\":1}'";

#[test]
fn zero_duration_is_rejected_without_running_probes() {
    let fixture = Fixture::new("touch invoked", "touch invoked");
    assert!(!fixture.command("0s").status().unwrap().success());
    assert!(!fixture.root.path().join("invoked").exists());
    assert!(fixture.report().is_none());
}

#[test]
fn control_timeout_is_bounded_and_checkpointed_as_unknown() {
    let fixture = Fixture::new("sleep 60", OK);
    let mut child = Running(fixture.command("1s").spawn().unwrap());
    assert!(wait(&mut child.0).success());
    let report = fixture.report().unwrap();
    assert_eq!(report["schema_version"], 3);
    assert_eq!(report["completed"], true);
    assert_eq!(report["interrupted"], false);
    assert_eq!(report["controls"][0]["verdict"], "unknown");
    assert_eq!(report["controls"][0]["error_kind"], "control_timeout");
    assert_eq!(report["cells"].as_array().unwrap().len(), 2);
    assert!(report["windows"].as_array().unwrap().is_empty());
}

#[test]
fn interrupts_preserve_completed_ticks_and_mark_partial_report() {
    for signal in ["INT", "TERM"] {
        let fixture = Fixture::new(OK, OK);
        let mut child = Running(fixture.command("30s").spawn().unwrap());
        let deadline = Instant::now() + Duration::from_secs(4);
        let checkpoint = loop {
            if let Some(report) = fixture.report() {
                if report["controls"].as_array().is_some_and(|c| !c.is_empty()) {
                    break report;
                }
            }
            assert!(
                Instant::now() < deadline,
                "no per-tick checkpoint before interruption"
            );
            std::thread::sleep(Duration::from_millis(20));
        };
        assert_eq!(checkpoint["completed"], false);
        assert!(Command::new("kill")
            .args([&format!("-{signal}"), &child.0.id().to_string()])
            .status()
            .unwrap()
            .success());
        assert_eq!(
            wait(&mut child.0).code(),
            Some(if signal == "INT" { 130 } else { 143 })
        );
        let report = fixture.report().unwrap();
        assert_eq!(report["interrupted"], true);
        assert_eq!(report["completed"], false);
        let prior = checkpoint["cells"].as_array().unwrap();
        let final_cells = report["cells"].as_array().unwrap();
        assert_eq!(&final_cells[..prior.len()], prior);
        let journal = std::fs::read_to_string(fixture.root.path().join("report.jsonl")).unwrap();
        let records: Vec<Value> = journal
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        assert_eq!(records.last().unwrap()["interrupted"], true);
        let recorded_cells: Vec<Value> = records
            .iter()
            .flat_map(|record| record["cells"].as_array().unwrap().clone())
            .collect();
        assert_eq!(&recorded_cells, final_cells);
    }
}

#[test]
fn invalid_config_and_profile_inputs_fail_before_probe_execution() {
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
            "malformed" => std::fs::write(&path, "not json").unwrap(),
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

#[test]
fn interrupt_during_cells_keeps_observed_cells_and_cancels_unfinished_work() {
    let fixture=Fixture::new(OK,"if [ '$(TARGET_ID)' = pair-dual ]; then printf '%s\\n' '{\"verdict\":\"blocked\"}'; else echo $$$$ > cell-pid; sleep 60 & echo $$! >> cell-pid; wait; fi");
    let mut child = Running(fixture.command("30s").spawn().unwrap());
    let deadline = Instant::now() + Duration::from_secs(4);
    let pids = loop {
        if let Ok(pids) = std::fs::read_to_string(fixture.root.path().join("cell-pid")) {
            if pids.lines().count() == 2 {
                break pids;
            }
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(10));
    };
    // Give the quick cell a chance to be collected while the other is blocked.
    std::thread::sleep(Duration::from_millis(50));
    assert!(Command::new("kill")
        .args(["-TERM", &child.0.id().to_string()])
        .status()
        .unwrap()
        .success());
    assert_eq!(wait(&mut child.0).code(), Some(143));
    let report = fixture.report().unwrap();
    let cells = report["cells"].as_array().unwrap();
    assert_eq!(cells.len(), 2);
    assert_eq!(cells[0]["verdict"], "blocked");
    assert_eq!(cells[1]["verdict"], "unknown");
    assert_eq!(cells[1]["error_kind"], "interrupted");
    assert_eq!(report["observations"][0]["kind"], "indeterminate");
    for pid in pids.lines() {
        let output = Command::new("ps")
            .args(["-o", "stat=", "-p", pid])
            .output()
            .unwrap();
        assert!(
            !output.status.success()
                || String::from_utf8_lossy(&output.stdout)
                    .trim()
                    .starts_with('Z'),
            "probe descendant survived CLI interruption"
        );
    }
}
