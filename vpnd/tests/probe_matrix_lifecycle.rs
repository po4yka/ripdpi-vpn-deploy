//! Real CLI validation tests. Local driver fixtures are not live network proof.
#![allow(clippy::unwrap_used, clippy::expect_used)]
use serde_json::{json, Value};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::process::CommandExt;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

struct Fixture {
    root: tempfile::TempDir,
}

impl Drop for Fixture {
    fn drop(&mut self) {
        for path in pid_files(self) {
            let pids = std::fs::read_to_string(path).unwrap();
            for pid in pids.lines() {
                let _ = Command::new("kill")
                    .args(["-KILL", pid])
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status();
            }
        }
    }
}

fn pid_files(fixture: &Fixture) -> Vec<std::path::PathBuf> {
    std::fs::read_dir(fixture.root.path())
        .unwrap()
        .filter_map(|entry| {
            let path = entry.unwrap().path();
            (path
                .extension()
                .is_some_and(|extension| extension == "pids"))
            .then_some(path)
        })
        .collect()
}

fn running(pid: &str) -> bool {
    let output = Command::new("ps")
        .args(["-o", "stat=", "-p", pid])
        .output()
        .unwrap();
    let status = String::from_utf8_lossy(&output.stdout);
    output.status.success() && !status.trim().is_empty() && !status.trim().starts_with('Z')
}

struct Running(std::process::Child);
impl Drop for Running {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

// Python's stdlib provides a real controlling PTY without a test dependency or
// unsafe Rust. Pipe byte consumption and the real dialoguer prompt are readiness
// handshakes; the signal deadline does not depend on a guessed startup sleep.
const INTERACTIVE_SIGNALS: &str = r#"
import array, fcntl, json, os, pathlib, pty, select, signal, subprocess, sys, tempfile, termios, time

binary = sys.argv[1]
failures = []
with tempfile.TemporaryDirectory(prefix='vpnd-interactive-signals-') as temporary:
    root = pathlib.Path(temporary)
    for directory in ('ansible', 'terraform/providers/upcloud', 'bin'):
        (root / directory).mkdir(parents=True)
    (root / 'Makefile').write_text('emit-singbox:\n\t@touch emitted\n')
    secret = root / 'vpn-test.secrets.yaml'
    secret.write_text('xray:\n  clients:\n    - name: phone\nsubscription:\n  server_name: sub.example.com\n')
    secret.chmod(0o600)
    inventory = root / 'bin/ansible-inventory'
    data = {'vpn': {'hosts': ['fixture-node']}, '_meta': {'hostvars': {'fixture-node': {'env': 'test', 'provider': 'upcloud', 'ansible_host': '192.0.2.1'}}}}
    inventory.write_text('#!/bin/sh\nprintf \'%s\\n\' \'' + json.dumps(data) + '\'\n')
    inventory.chmod(0o700)
    environment = dict(os.environ, XDG_RUNTIME_DIR=temporary, VPN_ENV='test', VPN_PROVIDER='upcloud', PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'])
    command = [binary, '--root', temporary, '--env', 'test', '--provider', 'upcloud']
    for signum in (signal.SIGINT, signal.SIGTERM):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b'synthetic-token')
        child = subprocess.Popen(command + ['share', 'phone', '--token-stdin'], stdin=read_fd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
        try:
            ready_deadline = time.monotonic() + 5
            while True:
                pending = array.array('i', [0])
                fcntl.ioctl(read_fd, termios.FIONREAD, pending)
                if pending[0] == 0:
                    break
                assert child.poll() is None and time.monotonic() < ready_deadline, 'share never consumed stdin'
                time.sleep(.01)
            child.send_signal(signum)
            try:
                assert child.wait(timeout=3) == -signum, 'share did not terminate by the requested signal'
            except subprocess.TimeoutExpired:
                failures.append('share-' + signum.name)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()
            os.close(read_fd)
            os.close(write_fd)
        assert not (root / 'emitted').exists(), 'share ran emission without EOF'

        pid, terminal = pty.fork()
        if pid == 0:
            os.execvpe(binary, command + ['reconverge'], environment)
        reaped = False
        try:
            transcript = b''
            ready_deadline = time.monotonic() + 5
            while b'Proceed?' not in transcript:
                assert time.monotonic() < ready_deadline, 'reconverge never reached confirmation'
                if select.select([terminal], [], [], .05)[0]:
                    transcript += os.read(terminal, 8192)
            os.kill(pid, signum)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                waited, status = os.waitpid(pid, os.WNOHANG)
                if waited:
                    reaped = True
                    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signum, 'reconverge did not terminate by the requested signal'
                    break
                if sys.platform == 'darwin' and terminal is not None:
                    state = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True, check=False).stdout.strip()
                    # Darwin P_WEXIT (E) can await PTY-master release. Observe it
                    # BEFORE closing, then require the exact original signal;
                    # SIGHUP from closing a live terminal cannot satisfy this.
                    if 'E' in state:
                        os.close(terminal)
                        terminal = None
                time.sleep(.01)
            if not reaped:
                failures.append('reconverge-' + signum.name)
        finally:
            if terminal is not None:
                os.close(terminal)
            if not reaped:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
assert not failures, 'interactive signal cancellation blocked: ' + ', '.join(failures)
"#;

#[test]
fn share_stdin_and_reconverge_prompt_preserve_signal_termination() {
    let output = Command::new("python3")
        .args(["-c", INTERACTIVE_SIGNALS, env!("CARGO_BIN_EXE_vpnd")])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn hanging_control_records_unknown_and_continues_real_make_cells() {
    let fixture = Fixture::new(
        "sh control.sh",
        "touch cell-invoked; printf '%s\\n' '{\"verdict\":\"ok\",\"rtt_ms\":1}'",
    );
    std::fs::write(fixture.root.path().join("control.sh"),
        "printf '%s\\n' \"$PPID\" \"$$\" > control.pids.tmp\nmv control.pids.tmp control.pids\nexec sleep 60\n").unwrap();
    let mut child = Running(fixture.command("1s").spawn().unwrap());
    let deadline = Instant::now() + Duration::from_secs(8);
    let status = loop {
        if let Some(status) = child.0.try_wait().unwrap() {
            break status;
        }
        assert!(
            Instant::now() < deadline,
            "control timeout did not bound the CLI"
        );
        std::thread::sleep(Duration::from_millis(20));
    };
    assert!(status.success());
    assert!(fixture.root.path().join("control.pids").exists());
    assert!(fixture.root.path().join("cell-invoked").exists());
    let report: Value =
        serde_json::from_slice(&std::fs::read(fixture.root.path().join("report.json")).unwrap())
            .unwrap();
    assert_eq!(report["schema_version"], 2);
    assert_eq!(report["controls"][0]["verdict"], "unknown");
    assert_eq!(report["controls"][0]["error_kind"], "control_timeout");
    assert_eq!(report["cells"].as_array().unwrap().len(), 2);
}

#[test]
fn invalid_durations_fail_before_probes_without_panicking() {
    let mut accepted = Vec::new();
    for duration in [
        "0",
        "0s",
        "0m",
        "0h",
        "0d",
        "18446744073709551615d",
        "18446744073709551615s",
    ] {
        for explain in [false, true] {
            let fixture = Fixture::new("touch invoked", "touch invoked");
            let mut command = fixture.command(duration);
            if explain {
                command.arg("--explain");
            }
            let status = command.status().unwrap();
            if status.success() || status.code() == Some(101) {
                accepted.push((duration, explain, status.code()));
            }
            assert!(!fixture.root.path().join("invoked").exists());
        }
    }
    assert!(
        accepted.is_empty(),
        "invalid durations accepted or panicked: {accepted:?}"
    );
}

#[test]
fn unrepresentable_next_poll_finishes_with_observed_results() {
    let mut failures = Vec::new();
    for cli_override in [false, true] {
        let fixture = Fixture::new(
            "printf '%s\\n' '{\"verdict\":\"ok\",\"rtt_ms\":1}'",
            "touch cell-invoked; printf '%s\\n' '{\"verdict\":\"ok\",\"rtt_ms\":1}'",
        );
        let mut command = fixture.command("1s");
        if cli_override {
            command.args(["--poll-interval-seconds", "18446744073709551615"]);
        } else {
            let path = fixture.root.path().join("matrix.yaml");
            let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
            config["poll_interval_seconds"] = json!(u64::MAX);
            std::fs::write(path, config.to_string()).unwrap();
        }
        command.stderr(Stdio::piped());
        let mut child = Running(command.spawn().unwrap());
        let deadline = Instant::now() + Duration::from_secs(5);
        let status = loop {
            if let Some(status) = child.0.try_wait().unwrap() {
                break status;
            }
            assert!(
                Instant::now() < deadline,
                "overflowing schedule stalled the CLI"
            );
            std::thread::sleep(Duration::from_millis(20));
        };
        assert!(fixture.root.path().join("cell-invoked").exists());
        if !status.success() {
            use std::io::Read;
            let mut stderr = String::new();
            child
                .0
                .stderr
                .take()
                .unwrap()
                .read_to_string(&mut stderr)
                .unwrap();
            failures.push((cli_override, status.code(), stderr));
            continue;
        }
        let report: Value = serde_json::from_slice(
            &std::fs::read(fixture.root.path().join("report.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(report["schema_version"], 2);
        assert_eq!(report["controls"].as_array().unwrap().len(), 1);
        assert_eq!(report["controls"][0]["verdict"], "ok");
        let cells = report["cells"].as_array().unwrap();
        assert_eq!(cells.len(), 2);
        assert!(cells
            .iter()
            .all(|cell| cell["tick"] == 0 && cell["verdict"] == "ok"));
    }
    assert!(
        failures.is_empty(),
        "unrepresentable next poll failed: {failures:?}"
    );
}

#[test]
fn direct_and_foreground_signals_reclaim_probe_jobs_and_doctor_captures() {
    let mut failures = Vec::new();
    for doctor in [false, true] {
        for signal in ["INT", "TERM"] {
            for foreground in [false, true] {
                let fixture = Fixture::new(
                    "printf '%s\\n' '{\"verdict\":\"ok\",\"rtt_ms\":1}'",
                    "sh hanging.sh",
                );
                let path = fixture.root.path().join("matrix.yaml");
                let mut config: Value =
                    serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
                config["control"]["timeout_seconds"] = json!(10);
                std::fs::write(path, config.to_string()).unwrap();
                std::fs::write(fixture.root.path().join("hanging.sh"),
                    "record=\"${1:-$TARGET_ID}.pids\"\nsleep 60 &\ngrandchild=$!\nprintf '%s\\n' \"$PPID\" \"$$\" \"$grandchild\" > \"$record.tmp\"\nmv \"$record.tmp\" \"$record\"\nwait\n").unwrap();
                let mut command = if doctor {
                    std::fs::write(
                        fixture.root.path().join("Makefile"),
                        "fleet-status:\n\t@sh hanging.sh doctor\n",
                    )
                    .unwrap();
                    let mut command = Command::new(env!("CARGO_BIN_EXE_vpnd"));
                    command
                        .args(["--root", fixture.root.path().to_str().unwrap(), "doctor"])
                        .env_remove("MAKEFLAGS")
                        .env_remove("MFLAGS")
                        .stdout(Stdio::null())
                        .stderr(Stdio::null());
                    command
                } else {
                    fixture.command("30s")
                };
                command.process_group(0);
                let mut child = Running(command.spawn().unwrap());
                let ready = Instant::now() + Duration::from_secs(8);
                while pid_files(&fixture).len() != if doctor { 1 } else { 2 } {
                    assert!(
                        child.0.try_wait().unwrap().is_none(),
                        "CLI exited before fixture readiness"
                    );
                    assert!(
                        Instant::now() < ready,
                        "captured processes never became ready"
                    );
                    std::thread::sleep(Duration::from_millis(20));
                }
                let pids: Vec<String> = pid_files(&fixture)
                    .iter()
                    .flat_map(|path| {
                        std::fs::read_to_string(path)
                            .unwrap()
                            .lines()
                            .map(str::to_owned)
                            .collect::<Vec<_>>()
                    })
                    .collect();
                assert!(pids.iter().all(|pid| running(pid)));
                let destination = format!("{}{}", if foreground { "-" } else { "" }, child.0.id());
                assert!(Command::new("kill")
                    .args(["-s", signal, "--", &destination])
                    .status()
                    .unwrap()
                    .success());
                let deadline = Instant::now() + Duration::from_secs(3);
                let status = loop {
                    if let Some(status) = child.0.try_wait().unwrap() {
                        break status;
                    }
                    assert!(Instant::now() < deadline, "signal did not stop the CLI");
                    std::thread::sleep(Duration::from_millis(20));
                };
                while pids.iter().any(|pid| running(pid)) && Instant::now() < deadline {
                    std::thread::sleep(Duration::from_millis(20));
                }
                if status.code() != Some(if signal == "INT" { 130 } else { 143 })
                    || pids.iter().any(|pid| running(pid))
                {
                    failures.push((doctor, signal, foreground, status.code()));
                }
            }
        }
    }
    assert!(
        failures.is_empty(),
        "signal cancellation failures: {failures:?}"
    );
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
