#![allow(dead_code)] // builders intentionally kept for future commands and tests

use crate::config::Context;
use crate::runner::Cmd;

#[cfg(test)]
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
        explain: false,
        yes: false,
        json: false,
    }
}

pub fn init(ctx: &Context) -> Cmd {
    Cmd::new(
        ctx.root
            .join("scripts/terraform-env.sh")
            .to_string_lossy()
            .to_string(),
    )
    .env("PROVIDER", &ctx.provider)
    .env("ENV", &ctx.env)
    .arg("init")
    .describe(format!("terraform init for {}/{}", ctx.provider, ctx.env))
}

pub fn plan(ctx: &Context) -> Cmd {
    let tfvars = format!("environments/{}.tfvars", ctx.env);
    let tfplan = format!("{}.tfplan", ctx.env);
    Cmd::new(
        ctx.root
            .join("scripts/terraform-env.sh")
            .to_string_lossy()
            .to_string(),
    )
    .env("PROVIDER", &ctx.provider)
    .env("ENV", &ctx.env)
    .arg("plan")
    .arg(format!("-var-file={}", tfvars))
    .arg(format!("-out={}", tfplan))
    .describe(format!("terraform plan -out={}", tfplan))
}

pub fn apply(ctx: &Context) -> Cmd {
    let tfplan = format!("{}.tfplan", ctx.env);
    Cmd::new(
        ctx.root
            .join("scripts/terraform-env.sh")
            .to_string_lossy()
            .to_string(),
    )
    .env("PROVIDER", &ctx.provider)
    .env("ENV", &ctx.env)
    .arg("apply")
    .arg(tfplan.clone())
    .describe(format!("terraform apply {}", tfplan))
}

pub fn output(ctx: &Context) -> Cmd {
    Cmd::new(
        ctx.root
            .join("scripts/terraform-env.sh")
            .to_string_lossy()
            .to_string(),
    )
    .env("PROVIDER", &ctx.provider)
    .env("ENV", &ctx.env)
    .arg("output")
    .arg("-json")
    .describe("terraform output -json")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn init_uses_environment_wrapper() {
        let ctx = fake_ctx();
        let s = init(&ctx).explain();
        assert!(
            s.contains("scripts/terraform-env.sh"),
            "program must be wrapper, got: {s}"
        );
        assert!(
            s.contains("PROVIDER=upcloud"),
            "must pass provider, got: {s}"
        );
        assert!(s.contains("ENV=prod"), "must pass environment, got: {s}");
    }

    #[test]
    fn init_contains_init_subcommand() {
        let ctx = fake_ctx();
        let s = init(&ctx).explain();
        assert!(s.contains("init"), "must contain init subcommand, got: {s}");
    }

    #[test]
    fn plan_contains_var_file_for_env() {
        let ctx = fake_ctx();
        let s = plan(&ctx).explain();
        assert!(
            s.contains("prod.tfvars"),
            "plan must reference env tfvars, got: {s}"
        );
    }

    #[test]
    fn plan_contains_out_flag() {
        let ctx = fake_ctx();
        let s = plan(&ctx).explain();
        assert!(
            s.contains("prod.tfplan"),
            "plan must set -out=<env>.tfplan, got: {s}"
        );
    }

    #[test]
    fn apply_references_tfplan() {
        let ctx = fake_ctx();
        let s = apply(&ctx).explain();
        assert!(
            s.contains("prod.tfplan"),
            "apply must reference <env>.tfplan, got: {s}"
        );
    }

    #[test]
    fn output_contains_json_flag() {
        let ctx = fake_ctx();
        let s = output(&ctx).explain();
        assert!(
            s.contains("-json"),
            "output must include -json flag, got: {s}"
        );
    }

    #[test]
    fn all_cmds_use_environment_wrapper() {
        let ctx = fake_ctx();
        for (name, s) in [
            ("plan", plan(&ctx).explain()),
            ("apply", apply(&ctx).explain()),
            ("output", output(&ctx).explain()),
        ] {
            assert!(
                s.contains("scripts/terraform-env.sh"),
                "{name}: must use workspace wrapper, got: {s}"
            );
        }
    }
}
