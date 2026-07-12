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
        let runtime_dir = std::env::var_os("XDG_RUNTIME_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                directories::BaseDirs::new()
                    .map(|b| b.cache_dir().join("vpn-provision"))
                    .unwrap_or_else(|| config_dir.join("runtime"))
            });
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
    /// Called immediately after a successful decrypt step.
    pub fn secure_secrets_file(&self) {
        use std::os::unix::fs::PermissionsExt;
        if self.secrets_file.exists() {
            let perms = std::fs::Permissions::from_mode(0o600);
            let _ = std::fs::set_permissions(&self.secrets_file, perms);
        }
    }
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
