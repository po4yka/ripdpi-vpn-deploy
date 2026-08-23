use anyhow::Result;

use crate::cli::PreflightArgs;
use crate::config::Context;
use crate::runner::{make, Cmd};

/// Pre-deploy guards in execution order; `check-certs` is skippable because
/// cert renewal is an operator decision, never an accident.
fn required_steps(ctx: &Context, skip_certs: bool) -> Vec<Cmd> {
    let mut steps: Vec<Cmd> = vec![
        make::target(ctx, "validate-secrets"),
        make::target(ctx, "spot-check-secrets"),
        make::target(ctx, "audit-permissions"),
    ];
    if !skip_certs {
        steps.push(make::target(ctx, "check-certs"));
    }
    steps
}

pub async fn run(ctx: &Context, args: PreflightArgs) -> Result<()> {
    // Ensure we have a decrypted secrets file to inspect.
    if !ctx.secrets_file.is_file() {
        make::target(ctx, "decrypt").run(ctx.explain).await?;
        ctx.secure_secrets_file();
    }

    for cmd in &required_steps(ctx, args.skip_certs) {
        cmd.run(ctx.explain).await?;
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
            json: false,
        }
    }

    #[test]
    fn guards_run_in_order_and_include_certs_by_default() {
        let ctx = fake_ctx();
        let rendered: Vec<String> = required_steps(&ctx, false)
            .iter()
            .map(|cmd| cmd.explain())
            .collect();
        let names = ["validate-secrets", "spot-check-secrets", "audit-permissions", "check-certs"];
        assert_eq!(rendered.len(), names.len());
        for (step, name) in rendered.iter().zip(names.iter()) {
            assert!(step.contains(&format!("make {name} ")), "{step}");
        }
    }

    #[test]
    fn skip_certs_drops_only_the_cert_check() {
        let ctx = fake_ctx();
        let rendered: Vec<String> = required_steps(&ctx, true)
            .iter()
            .map(|cmd| cmd.explain())
            .collect();
        assert_eq!(rendered.len(), 3);
        assert!(rendered.iter().all(|s| !s.contains("check-certs")));
    }
}
