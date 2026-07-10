use anyhow::{anyhow, Result};
use owo_colors::OwoColorize;

use crate::cli::ReconvergeArgs;
use crate::config::Context;
use crate::runner::make;
use crate::runner::ansible;
use crate::state::{version, Registry};
use crate::wizard::{confirm, section, Summary};

pub async fn run(ctx: &Context, args: ReconvergeArgs) -> Result<()> {
    section(
        "Reconverge",
        "Idempotent re-deploy against an existing host. Bundles decrypt → plan → dry-run → apply if drifted.",
    );

    let limit = if let Some(name) = &args.host {
        let reg = Registry::load()?;
        let host = reg.get(name).ok_or_else(|| anyhow!("host '{}' not in registry", name))?;
        if host.env != ctx.env || host.provider != ctx.provider {
            return Err(anyhow!("host '{}' belongs to {}/{} not {}/{}", name, host.env, host.provider, ctx.env, ctx.provider));
        }
        version::warn_on_skew(name, host);
        Some(host.ipv4.clone().ok_or_else(|| anyhow!("host '{}' has no IPv4 limit address", name))?)
    } else { None };

    let mut s = Summary::new("Reconverge plan");
    s.add("env", &ctx.env)
        .add("provider", &ctx.provider)
        .add("host", args.host.as_deref().unwrap_or("(all in env)"))
        .add("mode", if args.dry_run { "dry-run only" } else { "apply if changed" });
    s.render();

    if !ctx.yes && !ctx.explain && !confirm("Proceed?", true)? {
        eprintln!("{}", "aborted by user".yellow());
        return Ok(());
    }

    // Reconverge = re-decrypt, re-plan, dry-run, then site.yml (idempotent steps will no-op).
    make::target(ctx, "decrypt").run(ctx.explain).await?;
    ctx.secure_secrets_file();
    make::target(ctx, "init").run(ctx.explain).await?;
    make::target(ctx, "plan").run(ctx.explain).await?;
    let mut dry_run = ansible::dry_run(ctx);
    if let Some(host) = &limit { dry_run = dry_run.arg("--limit").arg(host); }
    dry_run.run(ctx.explain).await?;

    if args.dry_run {
        eprintln!("{}", "dry-run only — stopping before apply".cyan());
        return Ok(());
    }

    let mut deploy = ansible::site(ctx);
    if let Some(host) = &limit { deploy = deploy.arg("--limit").arg(host); }
    deploy.run(ctx.explain).await?;
    let mut verify = ansible::verify(ctx);
    if let Some(host) = &limit { verify = verify.arg("--limit").arg(host); }
    verify.run(ctx.explain).await?;
    make::target(ctx, "clean").run(ctx.explain).await?;

    if !ctx.explain {
        println!();
        println!("{}", "Reconverge complete.".green().bold());
    }
    Ok(())
}
