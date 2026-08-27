use anyhow::{anyhow, Context as _, Result};
use std::path::{Path, PathBuf};

use crate::cli::Cli;

/// Resolved paths and flags for a single `vpnd` invocation.
#[allow(dead_code)]
// several fields (ansible_dir, tf_root, json) are reserved for subcommands not yet wired; removing them would break the Context contract
#[derive(Debug, Clone)]
pub struct Context {
    pub root: PathBuf,
    pub ansible_dir: PathBuf,
    pub tf_root: PathBuf,
    pub env: String,
    pub provider: String,
    pub sops_file: PathBuf,
    pub secrets_file: PathBuf,
    pub config_dir: PathBuf,
    pub explain: bool,
    pub yes: bool,
    pub json: bool,
}

impl Context {
    pub fn discover(cli: &Cli) -> Result<Self> {
        let root = match &cli.root {
            Some(p) => p
                .canonicalize()
                .with_context(|| format!("--root {} not found", p.display()))?,
            None => find_repo_root().context(
                "could not locate vpn-deploy repo root (set VPN_DEPLOY_ROOT or cd into it)",
            )?,
        };

        let ansible_dir = root.join("ansible");
        let tf_root = root.join("terraform").join("providers").join(&cli.provider);

        if !ansible_dir.is_dir() {
            return Err(anyhow!(
                "missing {} — not a vpn-deploy repo root",
                ansible_dir.display()
            ));
        }
        if !tf_root.is_dir() {
            return Err(anyhow!(
                "missing {} — unknown provider '{}' (expected upcloud | hetzner | vultr | scaleway)",
                tf_root.display(),
                cli.provider
            ));
        }

        let config_dir = directories::BaseDirs::new()
            .map(|b| b.config_dir().join("vpn-provision"))
            .ok_or_else(|| anyhow!("could not resolve user config dir"))?;

        let sops_file = config_dir.join(format!("{}.secrets.sops.yaml", cli.env));
        let runtime_dir = resolve_runtime_dir(&config_dir);
        let secrets_file = runtime_dir.join(format!("vpn-{}.secrets.yaml", cli.env));

        Ok(Self {
            root,
            ansible_dir,
            tf_root,
            env: cli.env.clone(),
            provider: cli.provider.clone(),
            sops_file,
            secrets_file,
            config_dir,
            explain: cli.explain,
            yes: cli.yes,
            json: cli.json,
        })
    }

    pub fn ansible_cfg(&self) -> PathBuf {
        self.ansible_dir.join("ansible.cfg")
    }

    /// Ensure the decrypted secrets file has mode 0600 if it exists.
    /// Called immediately after a successful decrypt step. Fallible by
    /// contract: a chmod that cannot be applied means the plaintext
    /// secrets sit world-readable — the caller must abort, not continue.
    pub fn secure_secrets_file(&self) -> Result<()> {
        use std::os::unix::fs::PermissionsExt;
        if self.secrets_file.exists() {
            let perms = std::fs::Permissions::from_mode(0o600);
            std::fs::set_permissions(&self.secrets_file, perms).with_context(|| {
                format!(
                    "failed to set 0600 on decrypted secrets {}",
                    self.secrets_file.display()
                )
            })?;
        }
        Ok(())
    }
}

/// Resolve the directory holding the decrypted secrets file. XDG_RUNTIME_DIR
/// wins; otherwise fall back to the user cache dir, then a repo-local
/// runtime dir. Single authority so make (via the explicit SECRETS_FILE
/// kv) and vpnd always agree on one location.
fn resolve_runtime_dir(config_dir: &Path) -> PathBuf {
    std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            directories::BaseDirs::new()
                .map(|b| b.cache_dir().join("vpn-provision"))
                .unwrap_or_else(|| config_dir.join("runtime"))
        })
}

fn find_repo_root() -> Result<PathBuf> {
    let cwd = std::env::current_dir()?;
    for ancestor in cwd.ancestors() {
        if is_repo_root(ancestor) {
            return Ok(ancestor.to_path_buf());
        }
    }
    Err(anyhow!(
        "no vpn-deploy repo root found at or above {}",
        cwd.display()
    ))
}

fn is_repo_root(p: &Path) -> bool {
    p.join("Makefile").is_file() && p.join("ansible").is_dir() && p.join("terraform").is_dir()
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;
    use std::sync::Mutex;

    // Env-var mutation is process-global; serialize the resolution-matrix
    // test against any other test touching the environment.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn runtime_dir_resolution_matrix_xdg_set_and_unset() {
        let _guard = ENV_LOCK.lock().unwrap();
        let config_dir = Path::new("/fixture-config");

        // XDG_RUNTIME_DIR set wins outright.
        std::env::set_var("XDG_RUNTIME_DIR", "/runtime-xdg");
        assert_eq!(
            resolve_runtime_dir(config_dir),
            PathBuf::from("/runtime-xdg")
        );

        // XDG_RUNTIME_DIR unset falls back to the user cache dir when
        // BaseDirs is available in this environment.
        std::env::remove_var("XDG_RUNTIME_DIR");
        let fallback = resolve_runtime_dir(config_dir);
        match directories::BaseDirs::new() {
            Some(b) => {
                assert_eq!(fallback, b.cache_dir().join("vpn-provision"));
            }
            None => {
                assert_eq!(fallback, config_dir.join("runtime"));
            }
        }

        std::env::remove_var("XDG_RUNTIME_DIR");
    }

    // Path-based chmod only honors parent-directory bits on Linux; darwin
    // grants it from file ownership alone, so the injection is exercised
    // on Linux CI runners and compiled out elsewhere.
    #[cfg(target_os = "linux")]
    #[test]
    fn secure_secrets_file_propagates_chmod_failure() {
        let _guard = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        // procfs rejects chmod even for root, so this is a stable Linux
        // failure injection rather than relying on parent-directory bits.
        let secrets = PathBuf::from("/proc/version");

        let ctx = Context {
            root: dir.path().into(),
            ansible_dir: dir.path().into(),
            tf_root: dir.path().into(),
            env: "test".into(),
            provider: "upcloud".into(),
            sops_file: dir.path().into(),
            secrets_file: secrets.clone(),
            config_dir: dir.path().into(),
            explain: false,
            yes: false,
            json: false,
        };
        let outcome = ctx.secure_secrets_file();
        let err = outcome.expect_err("chmod on procfs must fail");
        assert!(
            err.to_string().contains("failed to set 0600"),
            "unexpected error: {err}"
        );
    }
}
