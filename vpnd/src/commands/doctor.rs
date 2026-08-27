use anyhow::{Context as _, Result};
use owo_colors::OwoColorize;

use crate::cli::DoctorArgs;
use crate::config::Context;
use crate::docs_bundle;
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
        make::target(ctx, "fleet-status"),
        make::target(ctx, "burn-check"),
        make::target(ctx, "asn-drift"),
        make::target(ctx, "check-ip-reputation"),
        make::target(ctx, "probing-summary"),
        make::target(ctx, "audit-permissions"),
    ];

    let mut report = String::new();
    for cmd in &steps {
        let out = cmd.capture(ctx.explain).await?;
        report.push_str(&format!(
            "### {}\n\n```\n{}\n```\n\n",
            cmd.redacted_explain(),
            out.stdout
        ));
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
    Ok(())
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
    use flate2::{write::GzEncoder, Compression};
    use tar::Builder;

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
    let audit_cmd = make::target(ctx, "audit-log");
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

    // Build gzip-tar in memory.
    let gz_buf: Vec<u8> = Vec::new();
    let enc = GzEncoder::new(gz_buf, Compression::default());
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

    std::fs::write(out_path, &gz_bytes)
        .with_context(|| format!("write bundle to {}", out_path.display()))?;

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
pub fn redact_secrets(s: String, resolved_secrets_path: &str) -> String {
    let trailing_newline = s.ends_with('\n');
    let mut result = s
        .lines()
        .map(|line| {
            let historical_default = line.contains("/tmp/vpn-") && line.contains(".secrets.yaml");
            if (!resolved_secrets_path.is_empty() && line.contains(resolved_secrets_path))
                || historical_default
            {
                "<redacted: secrets file path>"
            } else {
                line
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    if trailing_newline {
        result.push('\n');
    }
    result
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
