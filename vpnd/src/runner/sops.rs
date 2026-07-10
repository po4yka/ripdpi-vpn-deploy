#![allow(dead_code)] // exposed for future commands that decrypt outside `make decrypt`

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

/// `sops --decrypt <sops_file> > <secrets_file>`
///
/// `sops` writes to stdout when no `--output` is given. The wrapper here uses
/// `--output` so we don't need a shell redirection — keeps `--explain` honest.
pub fn decrypt(ctx: &Context) -> Cmd {
    Cmd::new("sops")
        .arg("--decrypt")
        .arg("--output")
        .arg(ctx.secrets_file.to_string_lossy().to_string())
        .arg(ctx.sops_file.to_string_lossy().to_string())
        .describe(format!("sops --decrypt → {}", ctx.secrets_file.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decrypt_program_is_sops() {
        let ctx = fake_ctx();
        let s = decrypt(&ctx).explain();
        assert!(
            s.starts_with("sops") || s.contains(" sops "),
            "program must be sops, got: {s}"
        );
    }

    #[test]
    fn decrypt_contains_decrypt_flag() {
        let ctx = fake_ctx();
        let s = decrypt(&ctx).explain();
        assert!(s.contains("--decrypt"), "must contain --decrypt, got: {s}");
    }

    #[test]
    fn decrypt_contains_output_flag_and_secrets_file() {
        let ctx = fake_ctx();
        let s = decrypt(&ctx).explain();
        assert!(s.contains("--output"), "must contain --output, got: {s}");
        assert!(
            s.contains("/tmp/vpn-prod.secrets.yaml"),
            "output must be secrets_file, got: {s}"
        );
    }

    #[test]
    fn decrypt_contains_sops_source_file() {
        let ctx = fake_ctx();
        let s = decrypt(&ctx).explain();
        assert!(
            s.contains("prod.secrets.sops.yaml"),
            "must reference sops_file, got: {s}"
        );
    }
}
