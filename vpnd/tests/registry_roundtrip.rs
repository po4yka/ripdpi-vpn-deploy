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

    // Atomic persistence: concurrent writers must never leave a torn or
    // unparsable hosts.toml, a concurrent reader must always observe one
    // complete file, and no temp files survive completed saves.
    std::fs::remove_dir(&path).unwrap();
    let stop = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let reader_stop = stop.clone();
    let reader = std::thread::spawn(move || {
        let mut observations = 0usize;
        while !reader_stop.load(std::sync::atomic::Ordering::Relaxed) {
            Registry::load().expect("reader saw a torn registry");
            observations += 1;
        }
        observations
    });
    let mut writers = Vec::new();
    for worker in 0..4u32 {
        writers.push(std::thread::spawn(move || {
            for round in 0..25u32 {
                let mut registry = Registry::default();
                registry.upsert(
                    "worker",
                    Host {
                        env: format!("env-{worker}-{round}"),
                        provider: "upcloud".into(),
                        ipv4: None,
                        ipv6: None,
                        deployed_with: None,
                    },
                );
                registry.save().unwrap();
            }
        }));
    }
    for writer in writers {
        writer.join().unwrap();
    }
    stop.store(true, std::sync::atomic::Ordering::Relaxed);
    let observations = reader.join().unwrap();
    assert!(observations > 0, "reader must have observed the writes");
    let settled = Registry::load().unwrap();
    assert_eq!(settled.hosts.len(), 1, "final file is one complete write");
    let directory = path.parent().unwrap();
    let leftovers: Vec<String> = std::fs::read_dir(directory)
        .unwrap()
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .filter(|name| name.contains(".tmp."))
        .collect();
    assert!(
        leftovers.is_empty(),
        "completed saves must not leave temp files: {leftovers:?}"
    );
}
