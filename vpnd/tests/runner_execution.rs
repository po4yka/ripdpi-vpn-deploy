#![allow(clippy::unwrap_used, clippy::expect_used)]

use vpnd::runner::process::Cmd;

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
