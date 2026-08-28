#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::time::Duration;
use vpnd::runner::process::{CapturePolicy, Cmd};

fn running(pid: &str) -> bool {
    let output = std::process::Command::new("ps")
        .args(["-o", "stat=", "-p", pid])
        .output()
        .unwrap();
    let status = String::from_utf8_lossy(&output.stdout);
    output.status.success() && !status.trim().is_empty() && !status.trim().starts_with('Z')
}

struct FixtureProcesses(std::path::PathBuf);
impl Drop for FixtureProcesses {
    fn drop(&mut self) {
        if let Ok(pids) = std::fs::read_to_string(&self.0) {
            for pid in pids.lines() {
                let _ = std::process::Command::new("kill")
                    .args(["-KILL", pid])
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .status();
            }
            for _ in 0..50 {
                if pids.lines().all(|pid| !running(pid)) {
                    eprintln!("fixture cleanup verified: no recorded processes remain");
                    return;
                }
                std::thread::sleep(Duration::from_millis(20));
            }
            eprintln!("fixture cleanup failed: recorded process still running");
        }
    }
}

#[tokio::test]
async fn capture_timeout_terminates_real_make_child_and_grandchild() {
    let make = std::process::Command::new("make")
        .arg("--version")
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&make.stdout).contains("GNU Make"));
    let temp = tempfile::tempdir().unwrap();
    let pids = temp.path().join("processes");
    let _cleanup = FixtureProcesses(pids.clone());
    std::fs::write(temp.path().join("Makefile"), "probe:\n\t@sh child.sh\n").unwrap();
    std::fs::write(temp.path().join("child.sh"),
        "sleep 60 &\ngrandchild=$!\nprintf '%s\\n' \"$PPID\" \"$$\" \"$grandchild\" > \"$PIDS.tmp\"\nmv \"$PIDS.tmp\" \"$PIDS\"\nwait\n").unwrap();
    let command = Cmd::new("make")
        .capture_policy(CapturePolicy::OwnedProcessGroup)
        .arg("probe")
        .cwd(temp.path().to_owned())
        .env("PIDS", pids.to_string_lossy())
        .env("MAKEFLAGS", "")
        .env("MFLAGS", "");
    let mut capture = Box::pin(command.capture(false));
    let ready = async {
        let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
        while !pids.exists() {
            assert!(
                tokio::time::Instant::now() < deadline,
                "Make fixture never became ready"
            );
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    };
    tokio::select! {
        result = &mut capture => panic!("capture exited before readiness: {result:?}"),
        () = ready => {}
    }
    let recorded = std::fs::read_to_string(&pids).unwrap();
    assert_eq!(recorded.lines().count(), 3);
    assert!(
        recorded.lines().all(running),
        "fixture must start the real process tree"
    );
    assert!(
        tokio::time::timeout(Duration::from_millis(50), &mut capture)
            .await
            .is_err()
    );
    drop(capture);
    for _ in 0..50 {
        if recorded.lines().all(|pid| !running(pid)) {
            return;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(
        recorded.lines().all(|pid| !running(pid)),
        "Make descendants survived cancellation"
    );
}

#[tokio::test]
async fn run_and_capture_report_real_process_outcomes() {
    let foreground = Cmd::new("sh")
        .args(["-c", "ps -o pgid= -p $$"])
        .capture(false)
        .await
        .unwrap();
    assert_eq!(
        foreground.stdout.trim().parse::<i32>().unwrap(),
        rustix::process::getpgrp().as_raw_nonzero().get()
    );
    let output = Cmd::new("sh")
        .args(["-c", "printf 'first\\nsecond'"])
        .capture(false)
        .await
        .unwrap();
    assert_eq!(output.rc, 0);
    assert_eq!(output.stdout, "first\nsecond\n");
    assert_eq!(
        Cmd::new("sh")
            .args(["-c", "exit 0"])
            .run(false)
            .await
            .unwrap(),
        0
    );
    for capture in [false, true] {
        for (script, expected) in [("exit 17", "rc=17"), ("kill -TERM $$", "rc=-1")] {
            let command = Cmd::new("sh").args(["-c", script]);
            let error = if capture {
                command.capture(false).await.map(|_| ())
            } else {
                command.run(false).await.map(|_| ())
            }
            .unwrap_err();
            assert!(error.to_string().contains(expected), "{error}");
        }
        let command = Cmd::new("/vpnd-no-such-command");
        assert!(if capture {
            command.capture(false).await.map(|_| ())
        } else {
            command.run(false).await.map(|_| ())
        }
        .is_err());
    }
}
