use anyhow::{anyhow, Result};
use owo_colors::OwoColorize;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

/// Fluent builder for an external process invocation.
///
/// The shape mirrors `tokio::process::Command` but carries a human-readable
/// description and supports `--explain` (print-don't-run).
#[derive(Debug, Clone)]
pub struct Cmd {
    program: String,
    args: Vec<OsString>,
    env: Vec<(String, String)>,
    cwd: Option<PathBuf>,
    description: Option<String>,
}

impl Cmd {
    pub fn new(program: impl Into<String>) -> Self {
        Self {
            program: program.into(),
            args: Vec::new(),
            env: Vec::new(),
            cwd: None,
            description: None,
        }
    }

    pub fn arg(mut self, a: impl Into<OsString>) -> Self {
        self.args.push(a.into());
        self
    }

    #[allow(dead_code)] // bulk-arg convenience not yet called by any wired subcommand; retained for upcoming multi-target commands
    pub fn args<I, S>(mut self, items: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<OsString>,
    {
        self.args.extend(items.into_iter().map(Into::into));
        self
    }

    pub fn env(mut self, k: impl Into<String>, v: impl Into<String>) -> Self {
        self.env.push((k.into(), v.into()));
        self
    }

    pub fn cwd(mut self, p: PathBuf) -> Self {
        self.cwd = Some(p);
        self
    }

    pub fn describe(mut self, d: impl Into<String>) -> Self {
        self.description = Some(d.into());
        self
    }

    /// Shell-quoted form suitable for `--explain` output.
    pub fn explain(&self) -> String {
        let mut parts: Vec<String> = Vec::new();
        for (k, v) in &self.env {
            parts.push(format!("{}={}", k, shell_words::quote(v)));
        }
        parts.push(shell_words::quote(&self.program).into_owned());
        for a in &self.args {
            parts.push(shell_words::quote(&a.to_string_lossy()).into_owned());
        }
        let mut s = parts.join(" ");
        if let Some(cwd) = &self.cwd {
            s = format!(
                "(cd {} && {})",
                shell_words::quote(&cwd.to_string_lossy()),
                s
            );
        }
        s
    }

    /// Print to stderr in the `--explain` style. Always called for the `--explain` flag,
    /// and useful as a status line in interactive runs.
    pub fn print_explain(&self) {
        if let Some(d) = &self.description {
            eprintln!("{} {}", "→".cyan(), d.bold());
        }
        eprintln!("  {} {}", "$".dimmed(), self.explain().dimmed());
    }

    /// Run interactively, streaming stdout/stderr to the parent terminal.
    pub async fn run(&self, explain_only: bool) -> Result<i32> {
        self.print_explain();
        if explain_only {
            return Ok(0);
        }

        let mut cmd = Command::new(&self.program);
        // Dropping a spawned Cmd (timeout, cancellation) must not orphan the
        // child: probe-matrix cells run unattended for hours.
        cmd.kill_on_drop(true);
        cmd.args(self.args.iter());
        for (k, v) in &self.env {
            cmd.env(k, v);
        }
        if let Some(cwd) = &self.cwd {
            cmd.current_dir(cwd);
        }
        let status = cmd.status().await?;
        let rc = status.code().unwrap_or(-1);
        if !status.success() {
            return Err(anyhow!(
                "command failed (rc={}): {}",
                rc,
                self.description.as_deref().unwrap_or(&self.program)
            ));
        }
        Ok(rc)
    }

    /// Run capturing stdout, returning it as a String. Stderr is streamed to the terminal.
    pub async fn capture(&self, explain_only: bool) -> Result<Output> {
        self.print_explain();
        if explain_only {
            return Ok(Output {
                rc: 0,
                stdout: String::new(),
            });
        }

        let mut cmd = Command::new(&self.program);
        // Same orphan-prevention contract as run(): dropped futures must kill
        // the child, not leave it probing in the background.
        cmd.kill_on_drop(true)
            .args(self.args.iter())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        for (k, v) in &self.env {
            cmd.env(k, v);
        }
        if let Some(cwd) = &self.cwd {
            cmd.current_dir(cwd);
        }
        let mut child = cmd.spawn()?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow!("no stdout"))?;
        let mut buf = String::new();
        let mut reader = BufReader::new(stdout).lines();
        while let Some(line) = reader.next_line().await? {
            buf.push_str(&line);
            buf.push('\n');
        }
        let status = child.wait().await?;
        let rc = status.code().unwrap_or(-1);
        if !status.success() {
            return Err(anyhow!(
                "command failed (rc={}): {}",
                rc,
                self.description.as_deref().unwrap_or(&self.program)
            ));
        }
        Ok(Output { rc, stdout: buf })
    }
}

#[allow(dead_code)]
// rc field kept for callers that need to distinguish exit codes under --explain semantics; stdout is used today, rc not yet read externally
#[derive(Debug)]
pub struct Output {
    pub rc: i32,
    pub stdout: String,
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn explain_plain_program_no_env_no_cwd() {
        let cmd = Cmd::new("echo").arg("hello");
        assert_eq!(cmd.explain(), "echo hello");
    }

    #[test]
    fn explain_arg_with_spaces_is_quoted() {
        let cmd = Cmd::new("echo").arg("hello world");
        let s = cmd.explain();
        assert!(
            s.contains("'hello world'") || s.contains("\"hello world\""),
            "space in arg must be shell-quoted, got: {s}"
        );
    }

    #[test]
    fn explain_arg_with_single_quote() {
        let cmd = Cmd::new("echo").arg("it's here");
        let s = cmd.explain();
        // shell-words should produce a form the shell can re-parse
        assert!(
            s.contains("it") && s.contains("s here"),
            "single-quoted arg must survive quoting, got: {s}"
        );
        assert!(
            !s.contains("it's here"),
            "bare unquoted apostrophe must not appear, got: {s}"
        );
    }

    #[test]
    fn explain_arg_with_double_quote() {
        let cmd = Cmd::new("echo").arg("say \"hi\"");
        let s = cmd.explain();
        // shell-words must quote the argument (single or double quoting both valid)
        assert!(
            s.len() > 10,
            "double-quoted arg must be represented, got: {s}"
        );
        // The literal unquoted form `echo say "hi"` would split into three words;
        // shell-words must produce a single-token form like `'say "hi"'` or `"say \"hi\""`.
        let unquoted = "echo say \"hi\"";
        assert_ne!(
            s, unquoted,
            "arg with double-quotes must be shell-quoted, got: {s}"
        );
    }

    #[test]
    fn explain_arg_with_dollar_var() {
        let cmd = Cmd::new("echo").arg("$HOME");
        let s = cmd.explain();
        // $HOME must be quoted so the shell does not expand it
        assert!(
            !s.ends_with(" $HOME"),
            "dollar-var must be shell-quoted, got: {s}"
        );
    }

    #[test]
    fn explain_arg_with_newline() {
        let cmd = Cmd::new("echo").arg("line1\nline2");
        let s = cmd.explain();
        // A literal newline in an unquoted token is a shell syntax error; shell-words must quote it
        assert!(
            !s.contains('\n') || s.contains('\'') || s.contains('"'),
            "newline in arg must be quoted, got: {s:?}"
        );
    }

    #[test]
    fn explain_env_vars_appear_before_program() {
        let cmd = Cmd::new("make")
            .env("FOO", "bar")
            .env("BAZ", "qux")
            .arg("target");
        let s = cmd.explain();
        let make_pos = s.find("make").expect("'make' must appear");
        let foo_pos = s.find("FOO=").expect("FOO= must appear");
        let baz_pos = s.find("BAZ=").expect("BAZ= must appear");
        assert!(foo_pos < make_pos, "FOO= must precede program, got: {s}");
        assert!(baz_pos < make_pos, "BAZ= must precede program, got: {s}");
        // Declaration order preserved
        assert!(foo_pos < baz_pos, "FOO= must come before BAZ=, got: {s}");
    }

    #[test]
    fn explain_env_value_with_spaces_is_quoted() {
        let cmd = Cmd::new("echo").env("K", "value with spaces");
        let s = cmd.explain();
        assert!(
            !s.contains("K=value with spaces"),
            "space in env value must be quoted, got: {s}"
        );
    }

    #[test]
    fn explain_cwd_wraps_with_cd_and_ampersand() {
        let cmd = Cmd::new("make").arg("all").cwd(PathBuf::from("/some/path"));
        let s = cmd.explain();
        assert!(s.starts_with("(cd "), "must start with (cd, got: {s}");
        assert!(s.contains("&& make"), "must contain && program, got: {s}");
        assert!(s.ends_with(')'), "must end with ), got: {s}");
    }

    #[test]
    fn explain_cwd_with_spaces_is_quoted() {
        let cmd = Cmd::new("make").cwd(PathBuf::from("/path with spaces/repo"));
        let s = cmd.explain();
        assert!(
            !s.contains("(cd /path with spaces"),
            "cwd with spaces must be quoted, got: {s}"
        );
    }

    #[test]
    fn explain_env_ordering_is_stable() {
        // env vars must appear in insertion order, not sorted
        let cmd = Cmd::new("x")
            .env("ZEBRA", "1")
            .env("ALPHA", "2")
            .env("MANGO", "3");
        let s = cmd.explain();
        let z = s.find("ZEBRA=").unwrap();
        let a = s.find("ALPHA=").unwrap();
        let m = s.find("MANGO=").unwrap();
        assert!(z < a && a < m, "env must be in insertion order, got: {s}");
    }
}
