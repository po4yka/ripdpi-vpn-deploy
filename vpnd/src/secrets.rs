use anyhow::{anyhow, Context as _, Result};
use serde::Deserialize;
use std::path::Path;

/// Minimal typed view of the SOPS-decrypted payload at `/tmp/vpn-<env>.secrets.yaml`.
///
/// This is read-only and intentionally tolerant: unknown keys are preserved as raw YAML
/// so the schema lives in `scripts/validate-secrets.py`, not here.
#[derive(Deserialize)]
pub struct Secrets {
    #[serde(default)]
    pub xray: XraySecrets,
    #[serde(default)]
    pub nginx_xhttp: NginxXhttpSecrets,
    #[serde(default)]
    pub subscription: SubscriptionSecrets,
    #[serde(flatten)]
    pub(crate) _extra: serde_yaml::Mapping,
}

impl std::fmt::Debug for Secrets {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Secrets")
            .field("xray_clients", &self.xray.clients.len())
            .field("extra_keys", &self._extra.len())
            .finish()
    }
}

#[derive(Deserialize, Default)]
pub struct XraySecrets {
    #[serde(default)]
    pub clients: Vec<Client>,
    #[serde(flatten)]
    pub(crate) _extra: serde_yaml::Mapping,
}

#[derive(Deserialize, Default)]
pub struct NginxXhttpSecrets {
    #[serde(default)]
    pub server_name: Option<String>,
    #[serde(flatten)]
    pub(crate) _extra: serde_yaml::Mapping,
}

#[derive(Deserialize, Default)]
pub struct SubscriptionSecrets {
    #[serde(default)]
    pub server_name: Option<String>,
    #[serde(default)]
    pub port: Option<u64>,
    #[serde(flatten)]
    pub(crate) _extra: serde_yaml::Mapping,
}

#[allow(dead_code)]
// uuid and short_id are deserialized but not yet consumed; Phase 2 share-bundle expansion will read them to construct per-client VLESS URIs
#[derive(Deserialize, Clone)]
pub struct Client {
    pub name: String,
    #[serde(default)]
    pub uuid: Option<String>,
    #[serde(default)]
    pub short_id: Option<String>,
    #[serde(flatten)]
    pub(crate) _extra: serde_yaml::Mapping,
}

impl std::fmt::Debug for Client {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // name is a human label, not a secret — keep it for diagnostics.
        // uuid, short_id and _extra are secret-bearing and are omitted.
        f.debug_struct("Client")
            .field("name", &self.name)
            .finish_non_exhaustive()
    }
}

impl Secrets {
    pub fn load(path: &Path) -> Result<Self> {
        use std::os::unix::fs::MetadataExt;
        let metadata = std::fs::symlink_metadata(path)
            .with_context(|| format!("inspect {}", path.display()))?;
        let owner = std::process::Command::new("id")
            .arg("-u")
            .output()
            .context("resolve current uid")?;
        let uid = std::str::from_utf8(&owner.stdout)
            .context("decode current uid")?
            .trim()
            .parse::<u32>()
            .context("parse current uid")?;
        if !metadata.file_type().is_file() || metadata.uid() != uid || metadata.mode() & 0o077 != 0
        {
            return Err(anyhow!(
                "decrypted secrets at {} is missing or has unsafe owner, type, or permissions",
                path.display()
            ));
        }
        let bytes = std::fs::read(path).with_context(|| format!("read {}", path.display()))?;
        let s: Secrets = serde_yaml::from_slice(&bytes).context("parse decrypted secrets YAML")?;
        Ok(s)
    }

    pub fn find_client(&self, name: &str) -> Option<&Client> {
        self.xray.clients.iter().find(|c| c.name == name)
    }

    /// Number of unknown top-level keys captured by the catch-all flatten field.
    pub fn extra_key_count(&self) -> usize {
        self._extra.len()
    }

    /// Names of unknown top-level keys captured by the catch-all flatten field.
    pub fn extra_key_names(&self) -> Vec<&str> {
        self._extra.keys().filter_map(|k| k.as_str()).collect()
    }

    pub fn subscription_host(&self) -> Option<&str> {
        self.subscription.server_name.as_deref()
    }

    pub fn subscription_port(&self) -> Option<u64> {
        self.subscription.port
    }
}
