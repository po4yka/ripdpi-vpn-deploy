use anyhow::Result;

use crate::cli::{FleetAction, FleetArgs};
use crate::config::Context;
use crate::runner::make;

/// Translate the fleet action into the single make invocation it runs.
fn rotation_target(
    ctx: &Context,
    plan: &std::path::Path,
    resume: bool,
    dry_run: bool,
) -> crate::runner::Cmd {
    let plan_str = plan.to_string_lossy().to_string();
    let mut kvs = vec![("PLAN", plan_str.as_str())];
    if resume {
        kvs.push(("RESUME", "1"));
    }
    if dry_run {
        kvs.push(("DRY_RUN", "1"));
    }
    make::target_with(ctx, "fleet-rotate", &kvs)
}

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
            rotation_target(ctx, &plan, resume, dry_run)
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

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;
    use std::path::Path;

    fn fake_ctx() -> Context {
        use std::path::PathBuf;
        Context {
            root: PathBuf::from("/repo"),
            ansible_dir: PathBuf::from("/repo/ansible"),
            tf_root: PathBuf::from("/repo/terraform/providers/upcloud"),
            env: "prod".into(),
            provider: "upcloud".into(),
            sops_file: PathBuf::from("/config/prod.secrets.sops.yaml"),
            secrets_file: PathBuf::from("/tmp/vpn-prod.secrets.yaml"),
            config_dir: PathBuf::from("/config"),
            explain: true,
            yes: true,
            json: false,
        }
    }

    #[test]
    fn rotate_flags_map_to_make_kvs() {
        let ctx = fake_ctx();
        let plain = rotation_target(&ctx, Path::new("/p/fleet.yaml"), false, false).explain();
        assert!(plain.contains("PLAN=/p/fleet.yaml"), "{plain}");
        assert!(!plain.contains("RESUME=") && !plain.contains("DRY_RUN="), "{plain}");

        let full = rotation_target(&ctx, Path::new("/p/fleet.yaml"), true, true).explain();
        assert!(full.contains("RESUME=1"), "{full}");
        assert!(full.contains("DRY_RUN=1"), "{full}");
    }
}
