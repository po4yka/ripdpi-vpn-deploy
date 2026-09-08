use anyhow::{anyhow, Context as _, Result};
use owo_colors::OwoColorize;

use crate::cli::DoctorArgs;
use crate::config::Context;
use crate::docs_bundle;
use crate::runner::process::CapturePolicy;
use crate::runner::{make, Cmd};
use crate::state::Registry;

pub async fn run(ctx: &Context, args: DoctorArgs) -> Result<()> {
    // Resolve --host against the registry before any diagnostic runs:
    // unknown or cross-env aliases fail loudly instead of labeling the
    // report with a phantom host.
    if args.host.is_some() {
        let reg = Registry::load()?;
        super::ensure_host_in_registry(ctx, &reg, args.host.as_ref())?;
    }

    let steps: Vec<Cmd> = vec![
        make::target(ctx, "fleet-status")?,
        make::target(ctx, "burn-check")?,
        make::target(ctx, "asn-drift")?,
        make::target(ctx, "check-ip-reputation")?,
        make::target(ctx, "probing-summary")?,
        make::target(ctx, "audit-permissions")?,
    ];

    // A failing step is evidence, not a reason to abort: the loop collects
    // every step's captured streams, marks failures, and keeps going so a
    // partial failure yields a complete report instead of nothing.
    let total = steps.len();
    let mut failed_steps = 0usize;
    let mut report = String::new();
    for cmd in steps {
        let cmd = cmd.capture_policy(CapturePolicy::OwnedProcessGroup);
        let header = cmd.redacted_explain();
        match cmd.capture_detailed(ctx.explain).await {
            Ok(out) => {
                let failed = out.rc != 0;
                if failed {
                    failed_steps += 1;
                }
                report.push_str(&render_step_section(
                    &header,
                    &out.stdout,
                    &out.stderr,
                    failed,
                ));
            }
            Err(error) => {
                // Spawn/IO failure is still a completed observation about
                // this step; record it and continue with the rest.
                failed_steps += 1;
                report.push_str(&render_step_section(
                    &header,
                    "",
                    &format!("(capture failed: {error})"),
                    true,
                ));
            }
        }
    }

    if ctx.explain {
        return Ok(());
    }

    // --bundle: pack a gzip-tar with diagnostic info (orthogonal to --ai).
    if let Some(bundle_path) = &args.bundle {
        write_bundle(ctx, &report, bundle_path).await?;
        eprintln!(
            "{} bundle written to {}",
            "ok:".green(),
            bundle_path.display()
        );
    }

    if args.ai {
        let excerpts = docs_bundle::relevant_runbook_excerpts(&report);
        let prompt = ai_prompt(ctx, args.host.as_deref(), &report, &excerpts);
        if args.clip {
            match try_copy_to_clipboard(&prompt).await {
                Ok(()) => eprintln!("{}", "AI prompt copied to clipboard".green()),
                Err(e) => {
                    eprintln!("{} {}; printing to stdout", "note:".yellow(), e);
                    println!("{prompt}");
                }
            }
        } else {
            println!("{prompt}");
        }
    } else if args.bundle.is_none() {
        println!("{}", "Doctor report".bold().underline());
        println!();
        println!(
            "{}",
            redact_secrets(report, &ctx.secrets_file.to_string_lossy())
        );
    }
    if failed_steps > 0 {
        // The report, bundle, and prompt above carry the full evidence; the
        // nonzero exit tells automation that at least one diagnostic failed.
        return Err(anyhow!(
            "{failed_steps} of {total} doctor diagnostic steps failed"
        ));
    }
    Ok(())
}

/// One report section: the redacted invocation, its captured streams, and an
/// explicit Failed marker so a failing step cannot blend into healthy output.
fn render_step_section(explain: &str, stdout: &str, stderr: &str, failed: bool) -> String {
    let mut section = format!("### {explain}\n\n");
    if failed {
        section.push_str("**Failed**\n\n");
    }
    if !stdout.is_empty() {
        section.push_str(&format!("```\n{stdout}```\n\n"));
    }
    if !stderr.is_empty() {
        section.push_str(&format!("stderr:\n\n```\n{stderr}```\n\n"));
    }
    if stdout.is_empty() && stderr.is_empty() && !failed {
        section.push_str("```\n(no output)\n```\n\n");
    }
    section
}

fn ai_prompt(ctx: &Context, host: Option<&str>, report: &str, excerpts: &str) -> String {
    // The prompt leaves the machine (stdout/clipboard); apply the same
    // redaction discipline as bundle entries before embedding anything.
    let secrets_display = ctx.secrets_file.display().to_string();
    let report = redact_secrets(report.to_owned(), &secrets_display);
    let excerpts = redact_secrets(excerpts.to_owned(), &secrets_display);
    let prompt = format!(
        r#"You are debugging a vpn-deploy host running a four-tier multi-profile VPN
stack (P0 VLESS+REALITY+Vision, P1 nginx+XHTTP direct, P2 Hysteria2 + AmneziaWG).

Context:
- env: {env}
- provider: {provider}
- host: {host}
- threat model: RU / TSPU-aware. CDN is NOT the baseline; see docs/CDN-DECISION.md.
- relevant runbooks: docs/RUNBOOK-incident.md, docs/RUNBOOK-rollback.md.

Below is the output of `vpnd doctor`. Please identify the most likely root cause,
propose the smallest safe remediation, and cite which runbook or script applies.

{report}{excerpts}
"#,
        env = ctx.env,
        provider = ctx.provider,
        host = host.unwrap_or("(active env)"),
    );
    redact_secrets(prompt, &secrets_display)
}

async fn write_bundle(ctx: &Context, report: &str, out_path: &std::path::Path) -> Result<()> {
    // Collect all bundle entries as (filename, content) pairs.
    let mut entries: Vec<(String, Vec<u8>)> = Vec::new();

    // Redaction derives from the resolved runtime path, not a hardcoded
    // /tmp assumption.
    let secrets_display = ctx.secrets_file.display().to_string();

    // 1. vpnd version
    entries.push((
        "vpnd-version.txt".into(),
        format!("vpnd {}\n", env!("CARGO_PKG_VERSION")).into_bytes(),
    ));

    // 2. uname -a
    entries.push(("uname.txt".into(), run_capture("uname", &["-a"]).await));

    // 3. terraform --version
    entries.push((
        "terraform-version.txt".into(),
        run_capture("terraform", &["--version"]).await,
    ));

    // 4. ansible --version
    entries.push((
        "ansible-version.txt".into(),
        run_capture("ansible", &["--version"]).await,
    ));

    // 5. audit-log via make (already captured in report; include raw)
    let audit_cmd =
        make::target(ctx, "audit-log")?.capture_policy(CapturePolicy::OwnedProcessGroup);
    let audit_out = audit_cmd
        .capture(false)
        .await
        .map(|o| o.stdout)
        .unwrap_or_else(|e| format!("(audit-log unavailable: {e})\n"));
    entries.push((
        "audit-log.txt".into(),
        redact_secrets(audit_out, &secrets_display).into_bytes(),
    ));

    // 6. The full doctor report.
    entries.push((
        "doctor-report.md".into(),
        redact_secrets(report.to_owned(), &secrets_display).into_bytes(),
    ));

    // Encoding and the final write are bulk CPU+disk work with no awaits:
    // run them on the blocking pool so the async worker is never stalled.
    let out_path = out_path.to_path_buf();
    tokio::task::spawn_blocking(move || -> Result<()> {
        use flate2::{write::GzEncoder, Compression};
        use tar::Builder;

        let enc = GzEncoder::new(Vec::new(), Compression::default());
        let mut tar = Builder::new(enc);
        for (name, data) in &entries {
            let data = redact_secrets(String::from_utf8_lossy(data).into_owned(), &secrets_display)
                .into_bytes();
            let mut header = tar::Header::new_gnu();
            header.set_size(data.len() as u64);
            header.set_mode(0o644);
            header.set_cksum();
            tar.append_data(&mut header, name, data.as_slice())
                .with_context(|| format!("tar append {name}"))?;
        }
        let enc = tar.into_inner().context("tar finish")?;
        let gz_bytes = enc.finish().context("gzip finish")?;
        std::fs::write(&out_path, &gz_bytes)
            .with_context(|| format!("write bundle to {}", out_path.display()))?;
        Ok(())
    })
    .await
    .map_err(|error| anyhow!("bundle encode task failed: {error}"))??;

    Ok(())
}

/// Run a program and capture stdout; on error, return a human note.
async fn run_capture(program: &str, args: &[&str]) -> Vec<u8> {
    use tokio::process::Command;
    match Command::new(program).args(args).output().await {
        Ok(out) => out.stdout,
        Err(e) => format!("({program} unavailable: {e})\n").into_bytes(),
    }
}

/// Redact secrets-file path mentions from exported surfaces. Matches the
/// resolved runtime path exactly (derived from Context, so non-/tmp
/// locations like a user cache dir are covered) plus the historical
/// default-location pattern for older captures.
pub fn redact_secrets(mut text: String, resolved_secrets_path: &str) -> String {
    const MARKER: &str = "<redacted: secrets file path>";
    // A legal Unix path can itself contain newlines. Locate the full path
    // before splitting into lines, and redact every line touched by it.
    if !resolved_secrets_path.is_empty() {
        let mut offset = 0;
        while let Some(relative) = text[offset..].find(resolved_secrets_path) {
            let start = offset + relative;
            let end = start + resolved_secrets_path.len();
            let line_start = text[..start].rfind('\n').map_or(0, |index| index + 1);
            let line_end = text[end..]
                .find('\n')
                .map_or(text.len(), |index| end + index);
            text.replace_range(line_start..line_end, MARKER);
            offset = line_start + MARKER.len();
        }
    }
    text.split_inclusive('\n')
        .map(|line| {
            if line.contains("/tmp/vpn-") && line.contains(".secrets.yaml") {
                if line.ends_with("\r\n") {
                    format!("{MARKER}\r\n")
                } else if line.ends_with('\n') {
                    format!("{MARKER}\n")
                } else {
                    MARKER.to_owned()
                }
            } else {
                line.to_owned()
            }
        })
        .collect()
}

async fn try_copy_to_clipboard(s: &str) -> Result<()> {
    use tokio::io::AsyncWriteExt as _;
    use tokio::process::Command;
    let candidates: &[&[&str]] = &[
        &["pbcopy"],
        &["wl-copy"],
        &["xclip", "-selection", "clipboard"],
        &["xsel", "-b"],
    ];
    for cmd in candidates {
        if which::which(cmd[0]).is_ok() {
            let mut child = Command::new(cmd[0])
                .args(&cmd[1..])
                .stdin(std::process::Stdio::piped())
                .spawn()?;
            // take() moves the handle out so it drops (sending EOF) before
            // wait(); pbcopy/xclip read stdin until EOF, so leaving the handle
            // open across wait() would deadlock.
            if let Some(mut stdin) = child.stdin.take() {
                stdin.write_all(s.as_bytes()).await?;
            }
            child.wait().await?;
            return Ok(());
        }
    }
    Err(anyhow::anyhow!(
        "no clipboard binary found (tried pbcopy, wl-copy, xclip, xsel)"
    ))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
    use super::render_step_section;

    #[test]
    fn healthy_section_renders_invocation_and_stdout() {
        let section = render_step_section("make fleet-status", "all green\n", "", false);
        assert!(
            section.starts_with("### make fleet-status\n\n"),
            "{section}"
        );
        assert!(!section.contains("Failed"), "{section}");
        assert!(section.contains("```\nall green\n```"), "{section}");
        assert!(!section.contains("stderr:"), "{section}");
    }

    #[test]
    fn failed_section_marks_failure_and_keeps_both_streams() {
        let section = render_step_section(
            "make burn-check",
            "partial stdout\n",
            "IP is burned\n",
            true,
        );
        assert!(section.contains("**Failed**"), "{section}");
        assert!(section.contains("```\npartial stdout\n```"), "{section}");
        assert!(
            section.contains("stderr:\n\n```\nIP is burned\n```"),
            "{section}"
        );
        // Ordering: the failed step's stdout comes before its stderr block.
        let stdout_pos = section.find("partial stdout").unwrap();
        let stderr_pos = section.find("IP is burned").unwrap();
        assert!(stdout_pos < stderr_pos, "{section}");
    }

    #[test]
    fn capture_failure_section_records_the_error_without_streams() {
        let section = render_step_section("make fleet-status", "", "(capture failed: boom)", true);
        assert!(section.contains("**Failed**"), "{section}");
        assert!(section.contains("(capture failed: boom)"), "{section}");
    }
}
