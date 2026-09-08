use anyhow::{Context as _, Result};

use crate::cli::{FleetAction, FleetArgs};
use crate::config::Context;
use crate::runner::make;

/// Translate the fleet action into the single make invocation it runs.
fn rotation_target(
    ctx: &Context,
    plan: &std::path::Path,
    resume: bool,
    dry_run: bool,
) -> Result<crate::runner::Cmd> {
    // PLAN is a path-class make variable: canonicalize first so relative
    // operator input lands on the absolute canonical form the validator
    // requires and no traversal survives into the value.
    let plan = plan
        .canonicalize()
        .context("resolving fleet rotation plan")?;
    let plan_str = plan.display().to_string();
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
            make::target(ctx, "fleet-status")?.run(ctx.explain).await?;
        }
        FleetAction::Rotate {
            plan,
            resume,
            dry_run,
        } => {
            rotation_target(ctx, &plan, resume, dry_run)?
                .run(ctx.explain)
                .await?;
        }
        FleetAction::Drift => {
            make::target(ctx, "drift-since-tag")?
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
        }
    }

    #[test]
    fn rotate_flags_map_to_make_kvs() {
        let ctx = fake_ctx();
        let dir = tempfile::tempdir().expect("tempdir");
        let plan = dir.path().join("fleet.yaml");
        std::fs::write(&plan, "").expect("write plan");
        let canonical = plan.canonicalize().expect("canonical plan");

        let plain = rotation_target(&ctx, &plan, false, false)
            .expect("valid plan")
            .explain();
        assert!(
            plain.contains(&format!("PLAN={}", canonical.display())),
            "{plain}"
        );
        assert!(
            !plain.contains("RESUME=") && !plain.contains("DRY_RUN="),
            "{plain}"
        );

        let full = rotation_target(&ctx, &plan, true, true)
            .expect("valid plan")
            .explain();
        assert!(full.contains("RESUME=1"), "{full}");
        assert!(full.contains("DRY_RUN=1"), "{full}");
    }
}
