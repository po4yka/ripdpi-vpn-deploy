//! Integration tests for the host registry CRUD cycle via direct Registry API.
//! Mirrors what commands::host::run() does but avoids touching the real HOME.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use tempfile::TempDir;
use vpnd::state::{Host, Registry};

fn make_host(env: &str, provider: &str) -> Host {
    Host {
        env: env.to_string(),
        provider: provider.to_string(),
        ipv4: Some("192.0.2.10".to_string()),
        ipv6: Some("2001:db8::10".to_string()),
        deployed_with: Some("0.1.0".to_string()),
    }
}

fn save_and_reload(reg: &Registry, path: &std::path::Path) -> Registry {
    let s = toml::to_string_pretty(reg).unwrap();
    std::fs::write(path, s).unwrap();
    reload(path)
}

fn reload(path: &std::path::Path) -> Registry {
    let raw = std::fs::read_to_string(path).unwrap();
    toml::from_str(&raw).unwrap()
}

#[test]
fn add_then_list_shows_host() {
    let dir = TempDir::new().unwrap();
    let path = dir.path().join("hosts.toml");

    let mut reg = Registry::default();
    reg.upsert("prod-uc1", make_host("prod", "upcloud"));
    let loaded = save_and_reload(&reg, &path);

    assert!(
        loaded.get("prod-uc1").is_some(),
        "host must appear after add+reload"
    );
    assert_eq!(loaded.hosts.len(), 1);
}

#[test]
fn show_returns_correct_fields() {
    let dir = TempDir::new().unwrap();
    let path = dir.path().join("hosts.toml");

    let mut reg = Registry::default();
    reg.upsert(
        "myhost",
        Host {
            env: "staging".into(),
            provider: "hetzner".into(),
            ipv4: Some("203.0.113.5".into()),
            ipv6: None,
            deployed_with: Some("0.2.0".into()),
        },
    );
    let loaded = save_and_reload(&reg, &path);

    let h = loaded.get("myhost").unwrap();
    assert_eq!(h.env, "staging");
    assert_eq!(h.provider, "hetzner");
    assert_eq!(h.ipv4.as_deref(), Some("203.0.113.5"));
    assert!(h.ipv6.is_none());
    assert_eq!(h.deployed_with.as_deref(), Some("0.2.0"));
}

#[test]
fn remove_existing_host_succeeds() {
    let dir = TempDir::new().unwrap();
    let path = dir.path().join("hosts.toml");

    let mut reg = Registry::default();
    reg.upsert("todelete", make_host("prod", "upcloud"));
    let mut loaded = save_and_reload(&reg, &path);

    let removed = loaded.remove("todelete");
    assert!(
        removed.is_some(),
        "remove must return Some for existing host"
    );
    save_and_reload(&loaded, &path);

    // Re-load and verify gone
    let raw = std::fs::read_to_string(&path).unwrap();
    let final_reg: Registry = toml::from_str(&raw).unwrap();
    assert!(
        final_reg.get("todelete").is_none(),
        "host must be absent after remove"
    );
}

#[test]
fn remove_missing_host_returns_none() {
    let mut reg = Registry::default();
    let result = reg.remove("ghost");
    assert!(result.is_none(), "remove of missing host must return None");
}

#[test]
fn add_list_show_remove_full_cycle() {
    let dir = TempDir::new().unwrap();
    let path = dir.path().join("hosts.toml");

    // Add
    let mut reg = Registry::default();
    reg.upsert("cycle-host", make_host("prod", "vultr"));
    let loaded = save_and_reload(&reg, &path);
    assert_eq!(loaded.hosts.len(), 1);

    // Show
    let h = loaded.get("cycle-host").unwrap();
    assert_eq!(h.provider, "vultr");

    // Remove — reload from disk to get a fresh owned copy
    let mut reg2 = reload(&path);
    let _ = reg2.remove("cycle-host");
    save_and_reload(&reg2, &path);

    let raw = std::fs::read_to_string(&path).unwrap();
    let final_reg: Registry = toml::from_str(&raw).unwrap();
    assert!(final_reg.get("cycle-host").is_none());
}

#[test]
fn serialization_preserves_optional_ipv4_ipv6_deployed_with() {
    let dir = TempDir::new().unwrap();
    let path = dir.path().join("hosts.toml");

    let mut reg = Registry::default();
    // All Some
    reg.upsert(
        "full",
        Host {
            env: "prod".into(),
            provider: "upcloud".into(),
            ipv4: Some("192.0.2.1".into()),
            ipv6: Some("2001:db8::1".into()),
            deployed_with: Some("0.1.0".into()),
        },
    );
    // None for all optionals
    reg.upsert(
        "minimal",
        Host {
            env: "prod".into(),
            provider: "upcloud".into(),
            ipv4: None,
            ipv6: None,
            deployed_with: None,
        },
    );

    let loaded = save_and_reload(&reg, &path);

    let full = loaded.get("full").unwrap();
    assert_eq!(full.ipv4.as_deref(), Some("192.0.2.1"));
    assert_eq!(full.ipv6.as_deref(), Some("2001:db8::1"));
    assert_eq!(full.deployed_with.as_deref(), Some("0.1.0"));

    let minimal = loaded.get("minimal").unwrap();
    assert!(minimal.ipv4.is_none());
    assert!(minimal.ipv6.is_none());
    assert!(minimal.deployed_with.is_none());
}

// Two independent registries share no state
#[test]
fn two_registries_are_independent() {
    let mut reg1 = Registry::default();
    let mut reg2 = Registry::default();
    reg1.upsert("host-a", make_host("prod", "upcloud"));
    reg2.upsert("host-b", make_host("staging", "hetzner"));
    assert!(
        reg1.get("host-b").is_none(),
        "reg1 must not see reg2's host"
    );
    assert!(
        reg2.get("host-a").is_none(),
        "reg2 must not see reg1's host"
    );
}
