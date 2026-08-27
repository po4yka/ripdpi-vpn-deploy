use anyhow::Result;
use owo_colors::OwoColorize;

use crate::cli::{ProbeArgs, Profile};
use crate::config::Context;
use crate::runner::{make, Cmd};
use crate::state::{ipv4_limit, Registry};

pub async fn run(ctx: &Context, args: ProbeArgs) -> Result<()> {
    // --host must resolve through the registry (env/provider matched);
    // unknown aliases fail before any probe step is built.
    let registry = Registry::load()?;
    let address = args
        .host
        .as_ref()
        .map(|name| {
            let host = registry.resolve_for(name, &ctx.env, &ctx.provider)?;
            ipv4_limit(name, &host)
        })
        .transpose()?;

    let mut steps: Vec<Cmd> = Vec::new();

    if matches!(args.profile, Profile::P0 | Profile::All) {
        steps.push(make::target(ctx, "validate-target"));
        steps.push(make::target(ctx, "probing-summary"));
        steps.push(make::target(ctx, "tspu-canary"));
    }
    if matches!(args.profile, Profile::P1 | Profile::All) {
        if let Some(host) = &address {
            steps.push(make::target_with(
                ctx,
                "test-tls-policing",
                &[("HOST", host)],
            ));
        } else {
            eprintln!(
                "{} skipping P1 TLS policing test — needs --host",
                "note:".yellow()
            );
        }
    }
    if matches!(args.profile, Profile::P2 | Profile::All) {
        steps.push(make::target(ctx, "burn-check"));
        steps.push(make::target(ctx, "asn-drift"));
    }

    for cmd in &steps {
        cmd.run(ctx.explain).await?;
    }
    Ok(())
}
