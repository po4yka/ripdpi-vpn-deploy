#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::time::Duration;
use vpnd::runner::process::Cmd;

fn running(pid: &str) -> bool {
    let result = std::process::Command::new("ps")
        .args(["-o", "stat=", "-p", pid])
        .output()
        .unwrap();
    result.status.success()
        && !String::from_utf8_lossy(&result.stdout)
            .trim()
            .starts_with('Z')
}

struct FixtureProcesses(std::path::PathBuf);
impl Drop for FixtureProcesses {
    fn drop(&mut self) {
        if let Ok(pids) = std::fs::read_to_string(&self.0) {
            for pid in pids.lines() {
                let _ = std::process::Command::new("kill")
                    .args(["-KILL", pid])
                    .status();
            }
        }
    }
}

#[tokio::test]
async fn capture_timeout_terminates_child_and_grandchild() {
    let temp = tempfile::tempdir().unwrap();
    let pids = temp.path().join("pids");
    let _cleanup = FixtureProcesses(pids.clone());
    let command = Cmd::new("sh")
        .args([
            "-c",
            "echo $$ > \"$PIDS\"; sleep 60 & echo $! >> \"$PIDS\"; wait",
        ])
        .env("PIDS", pids.to_string_lossy());
    assert!(
        tokio::time::timeout(Duration::from_millis(300), command.capture(false))
            .await
            .is_err()
    );
    let pids = std::fs::read_to_string(&pids).unwrap();
    assert_eq!(pids.lines().count(), 2);
    for _ in 0..50 {
        if pids.lines().all(|pid| !running(pid)) {
            return;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(
        pids.lines().all(|pid| !running(pid)),
        "capture descendants survived cancellation"
    );
}

#[tokio::test]
async fn run_and_capture_report_real_process_outcomes() {
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
