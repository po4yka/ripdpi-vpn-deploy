use anyhow::Result;

use crate::cli::{FleetAction, FleetArgs};
use crate::config::Context;
use crate::runner::{make, Cmd};

fn status_target(ctx: &Context) -> Cmd {
    if ctx.json {
        make::target_with(ctx, "fleet-status", &[("JSON", "1")])
    } else {
        make::target(ctx, "fleet-status")
    }
}

pub async fn run(ctx: &Context, args: FleetArgs) -> Result<()> {
    match args.action {
        FleetAction::Status => {
            status_target(ctx).run(ctx.explain).await?;
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

#[cfg(test)]
#[allow(clippy::expect_used)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    fn fake_ctx(json: bool) -> Context {
        Context {
            root: PathBuf::from("/repo"),
            ansible_dir: PathBuf::from("/repo/ansible"),
            tf_root: PathBuf::from("/repo/terraform/providers/upcloud"),
            env: "prod".into(),
            provider: "upcloud".into(),
            sops_file: PathBuf::from("/config/prod.secrets.sops.yaml"),
            secrets_file: PathBuf::from("/tmp/vpn-prod.secrets.yaml"),
            config_dir: PathBuf::from("/config"),
            explain: false,
            yes: false,
            json,
        }
    }

    #[test]
    fn status_target_forwards_global_json_after_provider() {
        let plain = status_target(&fake_ctx(false)).explain();
        assert!(plain.contains("fleet-status"));
        assert!(!plain.contains("JSON=1"));

        let json = status_target(&fake_ctx(true)).explain();
        let provider = json.find("PROVIDER=upcloud").expect("provider argument");
        let json_flag = json.find("JSON=1").expect("JSON argument");
        assert!(provider < json_flag, "JSON follows provider: {json}");
    }
}
