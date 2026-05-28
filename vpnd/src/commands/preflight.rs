use anyhow::Result;

use crate::cli::PreflightArgs;
use crate::config::Context;
use crate::runner::{make, Cmd};

pub async fn run(ctx: &Context, args: PreflightArgs) -> Result<()> {
    // Ensure we have a decrypted secrets file to inspect.
    if !ctx.secrets_file.is_file() {
        make::target(ctx, "decrypt").run(ctx.explain).await?;
        ctx.secure_secrets_file();
    }

    let mut steps: Vec<Cmd> = vec![
        make::target(ctx, "validate-secrets"),
        make::target(ctx, "spot-check-secrets"),
        make::target(ctx, "audit-permissions"),
    ];
    if !args.skip_certs {
        steps.push(make::target(ctx, "check-certs"));
    }

    for cmd in &steps {
        cmd.run(ctx.explain).await?;
    }
    Ok(())
}
