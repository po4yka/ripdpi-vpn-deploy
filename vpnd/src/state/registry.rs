use anyhow::{anyhow, Context as _, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::PathBuf;

/// Local-only host registry, persisted at `~/.config/vpn-provision/hosts.toml`.
///
/// Modeled after Meridian's per-server registry: the operator names a host once,
/// and every `vpnd <cmd> --host <name>` resolves to the same env/provider/IP.
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct Registry {
    #[serde(default)]
    pub hosts: BTreeMap<String, Host>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Host {
    pub env: String,
    pub provider: String,
    #[serde(default)]
    pub ipv4: Option<String>,
    #[serde(default)]
    pub ipv6: Option<String>,
    #[serde(default)]
    pub deployed_with: Option<String>,
}

impl Registry {
    pub fn path() -> Result<PathBuf> {
        let base = directories::BaseDirs::new().ok_or_else(|| anyhow!("no user config dir"))?;
        Ok(base.config_dir().join("vpn-provision").join("hosts.toml"))
    }

    pub fn load() -> Result<Self> {
        let p = Self::path()?;
        let s = match std::fs::read_to_string(&p) {
            Ok(raw) => raw,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(Self::default())
            }
            Err(error) => return Err(error).with_context(|| format!("read {}", p.display())),
        };
        toml::from_str(&s).with_context(|| format!("parse {}", p.display()))
    }

    pub fn save(&self) -> Result<()> {
        let p = Self::path()?;
        if let Some(dir) = p.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let s = toml::to_string_pretty(self)?;
        std::fs::write(&p, s).with_context(|| format!("write {}", p.display()))?;
        Ok(())
    }

    pub fn upsert(&mut self, name: &str, host: Host) {
        self.hosts.insert(name.to_string(), host);
    }

    pub fn remove(&mut self, name: &str) -> Option<Host> {
        self.hosts.remove(name)
    }

    pub fn get(&self, name: &str) -> Option<&Host> {
        self.hosts.get(name)
    }

    /// Resolve a registered host and enforce env/provider match with the
    /// active context — the single authority every `--host` consumer
    /// (reconverge, doctor, probe) shares.
    pub fn resolve_for(&self, name: &str, env: &str, provider: &str) -> Result<Host> {
        let host = self
            .get(name)
            .ok_or_else(|| anyhow!("host '{name}' not in registry"))?;
        if host.env != env || host.provider != provider {
            return Err(anyhow!(
                "host '{}' belongs to {}/{} not {}/{}",
                name,
                host.env,
                host.provider,
                env,
                provider
            ));
        }
        Ok(host.clone())
    }
}

/// Strict IPv4 literal for ansible `--limit` values. Registry entries that
/// carry pattern-ish values ("all", "prod:*", malformed octets) must be
/// rejected before the value reaches an ansible command line — a pattern
/// would silently widen the limit from one host to an entire group.
pub fn ipv4_limit(host_name: &str, host: &Host) -> Result<String> {
    let raw = host
        .ipv4
        .as_deref()
        .ok_or_else(|| anyhow!("host '{host_name}' has no IPv4 limit address"))?;
    let ip: std::net::Ipv4Addr = raw.parse().map_err(|_| {
        anyhow!(
            "host '{host_name}' ipv4 '{raw}' is not an IPv4 literal — refusing to build --limit"
        )
    })?;
    Ok(ip.to_string())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    fn host(env: &str, provider: &str, ipv4: Option<&str>) -> Host {
        Host {
            env: env.into(),
            provider: provider.into(),
            ipv4: ipv4.map(Into::into),
            ipv6: None,
            deployed_with: None,
        }
    }

    #[test]
    fn resolve_for_rejects_unknown_alias() {
        let mut reg = Registry::default();
        reg.upsert("prod1", host("prod", "upcloud", Some("203.0.113.5")));
        let err = reg
            .resolve_for("ghost", "prod", "upcloud")
            .expect_err("unknown alias must fail");
        assert!(err.to_string().contains("not in registry"), "{err}");
    }

    #[test]
    fn resolve_for_rejects_env_or_provider_mismatch() {
        let mut reg = Registry::default();
        reg.upsert("box", host("staging", "hetzner", None));
        assert!(reg.resolve_for("box", "prod", "hetzner").is_err());
        assert!(reg.resolve_for("box", "staging", "vultr").is_err());
        assert!(reg.resolve_for("box", "staging", "hetzner").is_ok());
    }

    /// Rejection table: none of these values may ever reach a --limit.
    #[test]
    fn ipv4_limit_rejection_table() {
        for bad in [
            "all",
            "prod:*",
            "999.1.1.1",
            "",
            "203.0.113.5x",
            "prod:!tag",
        ] {
            let h = host("prod", "upcloud", Some(bad));
            assert!(
                ipv4_limit("bad-host", &h).is_err(),
                "value '{bad}' must be rejected as a limit"
            );
        }
    }

    #[test]
    fn ipv4_limit_rejects_zero_padded_octets() {
        // std Ipv4Addr parsing is strict: no leading zeros, so ambiguous
        // octal-looking forms can never reach an ansible --limit.
        let h = host("prod", "upcloud", Some("203.000.113.005"));
        assert!(ipv4_limit("padded", &h).is_err());
    }

    #[test]
    fn ipv4_limit_accepts_literal() {
        let h = host("prod", "upcloud", Some("203.0.113.5"));
        assert_eq!(ipv4_limit("ok", &h).unwrap(), "203.0.113.5");
    }

    #[test]
    fn ipv4_limit_requires_an_address() {
        let h = host("prod", "upcloud", None);
        let err = ipv4_limit("noip", &h).expect_err("missing ipv4 must fail");
        assert!(err.to_string().contains("no IPv4 limit address"), "{err}");
    }
}
