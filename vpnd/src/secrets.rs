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
    pub clients: Vec<Client>,
    #[serde(default)]
    pub server_name: Option<String>,
    #[serde(default)]
    pub xhttp_host: Option<String>,
    #[serde(flatten)]
    pub(crate) _extra: serde_yaml::Mapping,
}

impl std::fmt::Debug for Secrets {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Secrets")
            .field("clients", &self.clients.len())
            .field("extra_keys", &self._extra.len())
            .finish()
    }
}

#[allow(dead_code)] // uuid and short_id are deserialized but not yet consumed; Phase 2 share-bundle expansion will read them to construct per-client VLESS URIs
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
        f.debug_struct("Client")
            .finish_non_exhaustive()
    }
}

impl Secrets {
    pub fn load(path: &Path) -> Result<Self> {
        if !path.is_file() {
            return Err(anyhow!(
                "decrypted secrets not found at {} — run `vpnd ... ` (which will call `make decrypt`)",
                path.display()
            ));
        }
        let bytes = std::fs::read(path).with_context(|| format!("read {}", path.display()))?;
        let s: Secrets = serde_yaml::from_slice(&bytes).context("parse decrypted secrets YAML")?;
        Ok(s)
    }

    pub fn find_client(&self, name: &str) -> Option<&Client> {
        self.clients.iter().find(|c| c.name == name)
    }

    /// Number of unknown top-level keys captured by the catch-all flatten field.
    pub fn extra_key_count(&self) -> usize {
        self._extra.len()
    }

    /// Names of unknown top-level keys captured by the catch-all flatten field.
    pub fn extra_key_names(&self) -> Vec<&str> {
        self._extra.keys().filter_map(|k| k.as_str()).collect()
    }
}
