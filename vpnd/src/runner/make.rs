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

/// Build a `make <name> ENV=… PROVIDER=…` invocation pinned to the repo root.
pub fn target(ctx: &Context, name: &str) -> Cmd {
    Cmd::new("make")
        .arg(name)
        .arg(format!("ENV={}", ctx.env))
        .arg(format!("PROVIDER={}", ctx.provider))
        .cwd(ctx.root.clone())
        .describe(format!(
            "make {} ENV={} PROVIDER={}",
            name, ctx.env, ctx.provider
        ))
}

/// Build a `make` target with additional `KEY=VALUE` args appended.
pub fn target_with(ctx: &Context, name: &str, kvs: &[(&str, &str)]) -> Cmd {
    let mut cmd = target(ctx, name);
    for (k, v) in kvs {
        cmd = cmd.arg(format!("{}={}", k, v));
    }
    cmd
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn target_pushes_env_then_provider_after_name() {
        let ctx = fake_ctx();
        let s = target(&ctx, "deploy").explain();
        let name_pos = s.find("deploy").expect("target name");
        let env_pos = s.find("ENV=prod").expect("ENV=");
        let prov_pos = s.find("PROVIDER=upcloud").expect("PROVIDER=");
        assert!(name_pos < env_pos, "target name before ENV=, got: {s}");
        assert!(env_pos < prov_pos, "ENV= before PROVIDER=, got: {s}");
    }

    #[test]
    fn target_program_is_make() {
        let ctx = fake_ctx();
        let s = target(&ctx, "deploy").explain();
        // cwd wraps, but 'make' must still appear
        assert!(s.contains("make"), "program must be make, got: {s}");
    }

    #[test]
    fn target_cwd_is_repo_root() {
        let ctx = fake_ctx();
        let s = target(&ctx, "deploy").explain();
        assert!(s.contains("/repo"), "cwd must be repo root, got: {s}");
    }

    #[test]
    fn target_with_appends_kvs_after_provider() {
        let ctx = fake_ctx();
        let s = target_with(&ctx, "emit-singbox", &[("CLIENT", "phone"), ("EXTRA", "1")]).explain();
        let prov_pos = s.find("PROVIDER=").expect("PROVIDER=");
        let client_pos = s.find("CLIENT=phone").expect("CLIENT=phone");
        let extra_pos = s.find("EXTRA=1").expect("EXTRA=1");
        assert!(prov_pos < client_pos, "KVs come after PROVIDER=, got: {s}");
        assert!(
            client_pos < extra_pos,
            "KV insertion order preserved, got: {s}"
        );
    }

    #[test]
    fn target_with_no_extra_kvs_matches_target() {
        let ctx = fake_ctx();
        assert_eq!(
            target(&ctx, "decrypt").explain(),
            target_with(&ctx, "decrypt", &[]).explain()
        );
    }
}
