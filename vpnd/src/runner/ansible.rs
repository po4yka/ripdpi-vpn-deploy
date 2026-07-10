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

/// Builder for `ansible-playbook playbooks/<name>.yml` pinned to the repo's ansible config.
pub fn playbook(ctx: &Context, name: &str) -> Cmd {
    let path = ctx
        .ansible_dir
        .join("playbooks")
        .join(format!("{name}.yml"));
    Cmd::new("ansible-playbook")
        .arg(path.to_string_lossy().to_string())
        .env(
            "ANSIBLE_CONFIG",
            ctx.ansible_cfg().to_string_lossy().to_string(),
        )
        .env(
            "VPN_SECRETS_FILE",
            ctx.secrets_file.to_string_lossy().to_string(),
        )
        .describe(format!("ansible-playbook playbooks/{name}.yml"))
}

pub fn site(ctx: &Context) -> Cmd {
    playbook(ctx, "site")
}

pub fn verify(ctx: &Context) -> Cmd {
    playbook(ctx, "verify")
}

pub fn smoke(ctx: &Context) -> Cmd {
    playbook(ctx, "smoke-test")
}

pub fn rotate(ctx: &Context) -> Cmd {
    playbook(ctx, "rotate-credentials")
}

pub fn dry_run(ctx: &Context) -> Cmd {
    site(ctx)
        .arg("--check")
        .arg("--diff")
        .describe("ansible-playbook site.yml --check --diff")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn playbook_program_is_ansible_playbook() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "site").explain();
        assert!(
            s.contains("ansible-playbook"),
            "program must be ansible-playbook, got: {s}"
        );
    }

    #[test]
    fn playbook_path_contains_playbook_name() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "rotate-credentials").explain();
        assert!(
            s.contains("rotate-credentials.yml"),
            "playbook path must include name.yml, got: {s}"
        );
    }

    #[test]
    fn playbook_sets_ansible_config_env() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "site").explain();
        assert!(
            s.contains("ANSIBLE_CONFIG="),
            "must set ANSIBLE_CONFIG, got: {s}"
        );
        assert!(
            s.contains("ansible.cfg"),
            "ANSIBLE_CONFIG must point to ansible.cfg, got: {s}"
        );
    }

    #[test]
    fn playbook_sets_vpn_secrets_file_env() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "site").explain();
        assert!(
            s.contains("VPN_SECRETS_FILE="),
            "must set VPN_SECRETS_FILE, got: {s}"
        );
        assert!(
            s.contains("/tmp/vpn-prod.secrets.yaml"),
            "VPN_SECRETS_FILE must be secrets_file, got: {s}"
        );
    }

    #[test]
    fn dry_run_appends_check_and_diff() {
        let ctx = fake_ctx();
        let s = dry_run(&ctx).explain();
        assert!(
            s.contains("--check"),
            "dry_run must include --check, got: {s}"
        );
        assert!(
            s.contains("--diff"),
            "dry_run must include --diff, got: {s}"
        );
    }

    #[test]
    fn site_uses_site_playbook() {
        let ctx = fake_ctx();
        let s = site(&ctx).explain();
        assert!(s.contains("site.yml"), "site() must use site.yml, got: {s}");
    }

    #[test]
    fn rotate_uses_rotate_credentials_playbook() {
        let ctx = fake_ctx();
        let s = rotate(&ctx).explain();
        assert!(
            s.contains("rotate-credentials.yml"),
            "rotate() must use rotate-credentials.yml, got: {s}"
        );
    }
}
