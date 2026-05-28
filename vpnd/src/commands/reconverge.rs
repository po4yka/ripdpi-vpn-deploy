use anyhow::Result;
use owo_colors::OwoColorize;

use crate::cli::ReconvergeArgs;
use crate::config::Context;
use crate::runner::make;
use crate::state::{version, Registry};
use crate::wizard::{confirm, section, Summary};

pub async fn run(ctx: &Context, args: ReconvergeArgs) -> Result<()> {
    section(
        "Reconverge",
        "Idempotent re-deploy against an existing host. Bundles decrypt → plan → dry-run → apply if drifted.",
    );

    if let Some(name) = &args.host {
        let reg = Registry::load()?;
        match reg.get(name) {
            Some(h) => version::warn_on_skew(name, h),
            None => eprintln!("{} host '{}' not in registry; continuing", "note:".yellow(), name),
        }
    }

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
    make::target(ctx, "dry-run").run(ctx.explain).await?;

    if args.dry_run {
        eprintln!("{}", "dry-run only — stopping before apply".cyan());
        return Ok(());
    }

    make::target(ctx, "deploy").run(ctx.explain).await?;
    make::target(ctx, "verify").run(ctx.explain).await?;
    make::target(ctx, "clean").run(ctx.explain).await?;

    if !ctx.explain {
        println!();
        println!("{}", "Reconverge complete.".green().bold());
    }
    Ok(())
}
