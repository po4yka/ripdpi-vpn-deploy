use anyhow::Result;

use crate::cli::{FleetAction, FleetArgs};
use crate::config::Context;
use crate::runner::make;

pub async fn run(ctx: &Context, args: FleetArgs) -> Result<()> {
    match args.action {
        FleetAction::Status => {
            make::target(ctx, "fleet-status").run(ctx.explain).await?;
        }
        FleetAction::Rotate {
            plan,
            resume,
            dry_run,
        } => {
            let plan_str = plan.to_string_lossy().to_string();
            let mut kvs = vec![("PLAN", plan_str.as_str())];
            if resume {
                kvs.push(("RESUME", "1"));
            }
            if dry_run {
                kvs.push(("DRY_RUN", "1"));
            }
            make::target_with(ctx, "fleet-rotate", &kvs)
                .run(ctx.explain)
                .await?;
        }
        FleetAction::Drift => {
            make::target(ctx, "drift-since-tag")
                .run(ctx.explain)
                .await?;
        }
    }
    Ok(())
}
