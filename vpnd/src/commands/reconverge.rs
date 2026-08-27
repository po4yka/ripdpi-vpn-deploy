use anyhow::Result;
use owo_colors::OwoColorize;

use crate::cli::ReconvergeArgs;
use crate::config::Context;
use crate::runner::ansible;
use crate::runner::make;
use crate::state::{version, Registry};
use crate::wizard::{confirm, section, Summary};

pub async fn run(ctx: &Context, args: ReconvergeArgs) -> Result<()> {
    section(
        "Reconverge",
        "Idempotent re-deploy against an existing host. Bundles decrypt → plan → dry-run → apply if drifted.",
    );

    let registered_host = if let Some(name) = &args.host {
        let reg = Registry::load()?;
        let host = reg.resolve_for(name, &ctx.env, &ctx.provider)?;
        version::warn_on_skew(name, &host);
        Some((name.as_str(), host))
    } else {
        None
    };
    let limit = ansible::scoped_limit(
        ctx,
        registered_host.as_ref().map(|(name, host)| (*name, host)),
    )
    .await?;

    let mut s = Summary::new("Reconverge plan");
    s.add("env", &ctx.env)
        .add("provider", &ctx.provider)
        .add("host", args.host.as_deref().unwrap_or("(all in env)"))
        .add(
            "mode",
            if args.dry_run {
                "dry-run only"
            } else {
                "apply if changed"
            },
        );
    s.render();

    if !ctx.yes && !ctx.explain && !confirm("Proceed?", true)? {
        eprintln!("{}", "aborted by user".yellow());
        return Ok(());
    }

    // Reconverge = re-decrypt, re-plan, dry-run, then site.yml (idempotent steps will no-op).
    // Any failure triggers best-effort plaintext-secrets cleanup first.
    let outcome: Result<()> = async {
        make::target(ctx, "decrypt").run(ctx.explain).await?;
        ctx.secure_secrets_file()?;
        make::target(ctx, "init").run(ctx.explain).await?;
        make::target(ctx, "plan").run(ctx.explain).await?;
        let dry_run = ansible::dry_run(ctx).arg("--limit").arg(&limit);
        dry_run.run(ctx.explain).await?;

        if args.dry_run {
            eprintln!("{}", "dry-run only — stopping before apply".cyan());
            return Ok(());
        }

        let deploy = ansible::site(ctx).arg("--limit").arg(&limit);
        deploy.run(ctx.explain).await?;
        let verify = ansible::verify(ctx).arg("--limit").arg(&limit);
        verify.run(ctx.explain).await?;
        Ok(())
    }
    .await;
    super::finish_with_cleanup(ctx, outcome).await?;

    if !ctx.explain {
        println!();
        println!("{}", "Reconverge complete.".green().bold());
    }
    Ok(())
}
