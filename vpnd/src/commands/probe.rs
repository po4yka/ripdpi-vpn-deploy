use anyhow::Result;
use owo_colors::OwoColorize;

use crate::cli::{ProbeArgs, Profile};
use crate::config::Context;
use crate::runner::{make, Cmd};

pub async fn run(ctx: &Context, args: ProbeArgs) -> Result<()> {
    let mut steps: Vec<Cmd> = Vec::new();

    if matches!(args.profile, Profile::P0 | Profile::All) {
        steps.push(make::target(ctx, "validate-target"));
        steps.push(make::target(ctx, "probing-summary"));
        steps.push(make::target(ctx, "tspu-canary"));
    }
    if matches!(args.profile, Profile::P1 | Profile::All) {
        if let Some(host) = &args.host {
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
