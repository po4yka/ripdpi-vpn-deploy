//! Integration tests for state::Registry TOML round-trip.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::PathBuf;
use tempfile::TempDir;
use vpnd::state::{Host, Registry};

/// Override XDG_CONFIG_HOME so Registry::path() resolves inside the temp dir.
/// Returns (TempDir, PathBuf) — TempDir must stay alive for the test duration.
fn isolated_registry(dir: &TempDir) -> PathBuf {
    // Registry::path() uses directories::BaseDirs which reads HOME / XDG_CONFIG_HOME.
    // Inject via std::env is not safe in parallel tests, so we operate directly on
    // the Registry struct and use save/load with explicit paths instead.
    // We bypass the env altogether by constructing the path manually.
    let config_dir = dir.path().join("vpn-provision");
    std::fs::create_dir_all(&config_dir).unwrap();
    config_dir.join("hosts.toml")
}

fn save_to(reg: &Registry, path: &PathBuf) {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).unwrap();
    }
    let s = toml::to_string_pretty(reg).unwrap();
    std::fs::write(path, s).unwrap();
}

fn load_from(path: &PathBuf) -> Registry {
    if !path.is_file() {
        return Registry::default();
    }
    let s = std::fs::read_to_string(path).unwrap();
    toml::from_str(&s).unwrap()
}

fn make_host(env: &str, provider: &str) -> Host {
    Host {
        env: env.to_string(),
        provider: provider.to_string(),
        ipv4: Some("192.0.2.1".to_string()),
        ipv6: Some("2001:db8::1".to_string()),
        deployed_with: Some("0.1.0".to_string()),
    }
}

#[test]
fn upsert_three_hosts_save_load_all_fields_preserved() {
    let dir = TempDir::new().unwrap();
    let path = isolated_registry(&dir);

    let mut reg = Registry::default();
    reg.upsert("alpha", make_host("prod", "upcloud"));
    reg.upsert(
        "beta",
        Host {
            env: "staging".into(),
            provider: "hetzner".into(),
            ipv4: None,
            ipv6: Some("2001:db8::2".to_string()),
            deployed_with: None,
        },
    );
    reg.upsert(
        "gamma",
        Host {
            env: "prod".into(),
            provider: "vultr".into(),
            ipv4: Some("198.51.100.1".to_string()),
            ipv6: None,
            deployed_with: Some("0.2.0".to_string()),
        },
    );

    save_to(&reg, &path);
    let loaded = load_from(&path);

    assert_eq!(loaded.hosts.len(), 3);

    let alpha = loaded.get("alpha").expect("alpha must exist");
    assert_eq!(alpha.env, "prod");
    assert_eq!(alpha.provider, "upcloud");
    assert_eq!(alpha.ipv4.as_deref(), Some("192.0.2.1"));
    assert_eq!(alpha.ipv6.as_deref(), Some("2001:db8::1"));
    assert_eq!(alpha.deployed_with.as_deref(), Some("0.1.0"));

    let beta = loaded.get("beta").expect("beta must exist");
    assert_eq!(beta.env, "staging");
    assert!(beta.ipv4.is_none(), "beta ipv4 must be None");
    assert_eq!(beta.deployed_with, None);

    let gamma = loaded.get("gamma").expect("gamma must exist");
    assert_eq!(gamma.provider, "vultr");
    assert!(gamma.ipv6.is_none(), "gamma ipv6 must be None");
}

#[test]
fn upsert_overwrites_existing_host() {
    let dir = TempDir::new().unwrap();
    let path = isolated_registry(&dir);

    let mut reg = Registry::default();
    reg.upsert("myhost", make_host("prod", "upcloud"));
    save_to(&reg, &path);

    let mut reg2 = load_from(&path);
    reg2.upsert(
        "myhost",
        Host {
            env: "staging".into(),
            provider: "hetzner".into(),
            ipv4: None,
            ipv6: None,
            deployed_with: None,
        },
    );
    save_to(&reg2, &path);

    let loaded = load_from(&path);
    let h = loaded.get("myhost").unwrap();
    assert_eq!(h.env, "staging", "upsert must overwrite env");
    assert_eq!(h.provider, "hetzner", "upsert must overwrite provider");
    assert!(h.ipv4.is_none());
}

#[test]
fn remove_returns_some_for_existing_host() {
    let mut reg = Registry::default();
    reg.upsert("todelete", make_host("prod", "upcloud"));
    let removed = reg.remove("todelete");
    assert!(
        removed.is_some(),
        "remove must return Some for existing host"
    );
    assert!(
        reg.get("todelete").is_none(),
        "host must be gone after remove"
    );
}

#[test]
fn remove_returns_none_for_missing_host() {
    let mut reg = Registry::default();
    let result = reg.remove("doesnotexist");
    assert!(result.is_none(), "remove must return None for missing host");
}

#[test]
fn btreemap_ordering_is_stable_across_save_load() {
    let dir = TempDir::new().unwrap();
    let path = isolated_registry(&dir);

    let mut reg = Registry::default();
    // Insert in reverse alphabetical order
    reg.upsert("zebra", make_host("prod", "upcloud"));
    reg.upsert("alpha", make_host("prod", "upcloud"));
    reg.upsert("mango", make_host("prod", "upcloud"));
    save_to(&reg, &path);

    let loaded = load_from(&path);
    let keys: Vec<&String> = loaded.hosts.keys().collect();
    assert_eq!(
        keys,
        vec!["alpha", "mango", "zebra"],
        "BTreeMap must yield sorted order"
    );
}

#[test]
fn empty_registry_round_trips() {
    let dir = TempDir::new().unwrap();
    let path = isolated_registry(&dir);
    let reg = Registry::default();
    save_to(&reg, &path);
    let loaded = load_from(&path);
    assert!(loaded.hosts.is_empty());
}
