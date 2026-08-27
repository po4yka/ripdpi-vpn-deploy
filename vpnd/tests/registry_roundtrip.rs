//! Production Registry::save/load, isolated in a child process so HOME is never
//! mutated in a concurrent test process.
#![allow(clippy::unwrap_used, clippy::expect_used)]
use vpnd::state::{Host, Registry};

#[test]
fn production_registry_io_roundtrip_and_fail_closed_errors() {
    if std::env::var_os("VPND_REGISTRY_CHILD").is_none() {
        let root = tempfile::tempdir().unwrap();
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "production_registry_io_roundtrip_and_fail_closed_errors",
                "--nocapture",
            ])
            .env("VPND_REGISTRY_CHILD", root.path())
            .env("HOME", root.path())
            .env("XDG_CONFIG_HOME", root.path().join(".config"))
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}\n{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        return;
    }
    let root = std::path::PathBuf::from(std::env::var_os("VPND_REGISTRY_CHILD").unwrap());
    let path = Registry::path().unwrap();
    assert!(path.starts_with(root));
    assert!(Registry::load().unwrap().hosts.is_empty());
    let mut registry = Registry::default();
    let host = Host {
        env: "staging".into(),
        provider: "upcloud".into(),
        ipv4: Some("192.0.2.1".into()),
        ipv6: Some("2001:db8::1".into()),
        deployed_with: Some("1.3.0".into()),
    };
    for name in ["zeta", "alpha", "middle"] {
        registry.upsert(name, host.clone());
    }
    registry.save().unwrap();
    assert!(path.is_file());
    let mut loaded = Registry::load().unwrap();
    assert_eq!(
        loaded.hosts.keys().map(String::as_str).collect::<Vec<_>>(),
        ["alpha", "middle", "zeta"]
    );
    let actual = loaded.get("alpha").unwrap();
    assert_eq!(actual.env, host.env);
    assert_eq!(actual.provider, host.provider);
    assert_eq!(actual.ipv4, host.ipv4);
    assert_eq!(actual.ipv6, host.ipv6);
    assert_eq!(actual.deployed_with, host.deployed_with);
    loaded.upsert(
        "alpha",
        Host {
            env: "prod".into(),
            provider: "vultr".into(),
            ipv4: None,
            ipv6: None,
            deployed_with: None,
        },
    );
    assert!(loaded.remove("middle").is_some());
    assert!(loaded.remove("missing").is_none());
    loaded.save().unwrap();
    let loaded = Registry::load().unwrap();
    assert_eq!(loaded.hosts.len(), 2);
    assert_eq!(loaded.get("alpha").unwrap().env, "prod");
    assert!(loaded.get("alpha").unwrap().ipv4.is_none());
    Registry::default().save().unwrap();
    assert!(Registry::load().unwrap().hosts.is_empty());
    std::fs::write(&path, "invalid toml").unwrap();
    assert!(Registry::load().is_err());
    std::fs::remove_file(&path).unwrap();
    std::fs::create_dir(&path).unwrap();
    assert!(
        Registry::load().is_err(),
        "an unreadable registry path must not become an empty registry"
    );
    assert!(registry.save().is_err());
}
