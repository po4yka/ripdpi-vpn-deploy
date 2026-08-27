use anyhow::{Context as _, Result};
use owo_colors::OwoColorize;
use serde::{Deserialize, Serialize};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::cli::UpdateArgs;
use crate::config::Context;

const GITHUB_API_URL: &str =
    "https://api.github.com/repos/po4yka/ripdpi-vpn-deploy/releases/latest";
const CACHE_FILE: &str = "last-update-check.toml";
const TTL_SECS: u64 = 86_400; // 24 h

#[derive(Debug, Serialize, Deserialize)]
struct Cache {
    checked_at: u64,
    latest_tag: String,
}

#[derive(Debug, Deserialize)]
struct GhRelease {
    tag_name: String,
}

pub async fn run(ctx: &Context, args: UpdateArgs) -> Result<()> {
    if ctx.explain || args.explain {
        println!("# vpnd update would query:");
        println!("  GET {GITHUB_API_URL}");
        println!("# Cache: {}/{CACHE_FILE}", ctx.config_dir.display());
        return Ok(());
    }

    // Try cache first.
    let cache_path = ctx.config_dir.join(CACHE_FILE);
    let now_secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::ZERO)
        .as_secs();

    if let Some(tag) = check_update(&cache_path, now_secs, || fetch_latest_tag(GITHUB_API_URL)) {
        print_notice(&tag);
    }
    Ok(())
}

fn check_update(
    path: &std::path::Path,
    now: u64,
    fetch: impl FnOnce() -> Result<String>,
) -> Option<String> {
    if let Some(cached) = load_cache(path, now) {
        return Some(cached.latest_tag);
    }
    match fetch() {
        Ok(tag) => {
            let cache = Cache {
                checked_at: now,
                latest_tag: tag.clone(),
            };
            // The advisory notice must work even if the cache cannot be written.
            if let Some(parent) = path.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            if let Ok(raw) = toml::to_string(&cache) {
                let _ = std::fs::write(path, raw);
            }
            Some(tag)
        }
        Err(error) => {
            tracing::debug!("update check failed (non-fatal): {error}");
            None
        }
    }
}

fn load_cache(path: &std::path::Path, now: u64) -> Option<Cache> {
    let raw = std::fs::read_to_string(path).ok()?;
    let cache: Cache = toml::from_str(&raw).ok()?;
    if now
        .checked_sub(cache.checked_at)
        .is_some_and(|age| age < TTL_SECS)
    {
        Some(cache)
    } else {
        None
    }
}

fn fetch_latest_tag(url: &str) -> Result<String> {
    let mut resp = ureq::get(url)
        .header("User-Agent", format!("vpnd/{}", env!("CARGO_PKG_VERSION")))
        .call()
        .context("GitHub releases API request failed")?;
    let release: GhRelease = resp
        .body_mut()
        .read_json()
        .context("parse GitHub release JSON")?;
    Ok(release.tag_name)
}

fn print_notice(latest_tag: &str) {
    let current = format!("v{}", env!("CARGO_PKG_VERSION"));
    // Only show notice when the tags differ.
    if latest_tag != format!("vpnd-{current}") && latest_tag.starts_with("vpnd-v") {
        let stripped = latest_tag.trim_start_matches("vpnd-");
        eprintln!(
            "{} A newer vpnd release is available: {} (you have {}). \
             See https://github.com/po4yka/ripdpi-vpn-deploy/releases",
            "notice:".yellow(),
            stripped.green().bold(),
            current.dimmed(),
        );
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;
    #[test]
    fn refresh_writes_real_cache_and_fresh_hits_skip_fetch() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("nested").join(CACHE_FILE);
        let tag = "vpnd-v9.0.0";
        assert_eq!(
            check_update(&path, 100_000, || Ok(tag.into())).as_deref(),
            Some(tag)
        );
        let cached = load_cache(&path, 100_001).unwrap();
        assert_eq!(cached.checked_at, 100_000);
        assert_eq!(cached.latest_tag, tag);
        assert_eq!(
            check_update(&path, 100_001, || Err(anyhow::anyhow!("unexpected fetch"))).as_deref(),
            Some(tag)
        );
        assert_eq!(
            check_update(&path, 100_000 + TTL_SECS, || Ok("vpnd-v10.0.0".into())).as_deref(),
            Some("vpnd-v10.0.0")
        );
        assert_eq!(
            load_cache(&path, 100_000 + TTL_SECS).unwrap().latest_tag,
            "vpnd-v10.0.0"
        );
        std::fs::write(&path, "corrupt").unwrap();
        assert_eq!(
            check_update(&path, 200_000, || Ok(tag.into())).as_deref(),
            Some(tag)
        );
        assert_eq!(load_cache(&path, 200_000).unwrap().latest_tag, tag);
        assert!(check_update(&path, 300_000, || Err(anyhow::anyhow!("offline"))).is_none());
        let unwritable = root.path().join("file");
        std::fs::write(&unwritable, "not a directory").unwrap();
        assert_eq!(
            check_update(&unwritable.join(CACHE_FILE), 1, || Ok(tag.into())).as_deref(),
            Some(tag)
        );
    }

    #[test]
    fn release_fetch_uses_real_http_json_and_rejects_http_or_schema_errors() {
        use std::io::{Read, Write};
        for (status, body, expected) in [
            (
                "200 OK",
                r#"{"tag_name":"vpnd-v9.0.0"}"#,
                Some("vpnd-v9.0.0"),
            ),
            ("200 OK", "{}", None),
            ("200 OK", "not json", None),
            ("503 Service Unavailable", "{}", None),
        ] {
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let url = format!("http://{}/releases/latest", listener.local_addr().unwrap());
            let server = std::thread::spawn(move || {
                let (mut socket, _) = listener.accept().unwrap();
                socket
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut buffer = [0; 4096];
                let length = socket.read(&mut buffer).unwrap();
                let request = String::from_utf8_lossy(&buffer[..length]);
                assert!(request.starts_with("GET /releases/latest HTTP/1.1"));
                assert!(request.to_lowercase().contains("user-agent: vpnd/"));
                write!(
                    socket,
                    "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .unwrap();
            });
            let result = fetch_latest_tag(&url);
            assert_eq!(result.ok().as_deref(), expected);
            server.join().unwrap();
        }
    }

    #[test]
    fn production_cache_load_enforces_ttl_and_rejects_corrupt_or_future_data() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join(CACHE_FILE);
        assert!(load_cache(&path, 100_000).is_none());
        for (raw, fresh) in [
            ("invalid toml".to_string(), false),
            ("".to_string(), false),
            ("checked_at = 100000".to_string(), false),
            (
                "checked_at = 100001\nlatest_tag = 'vpnd-v9.0.0'".to_string(),
                false,
            ),
            (
                format!(
                    "checked_at = {}\nlatest_tag = 'vpnd-v9.0.0'",
                    100_000 - TTL_SECS
                ),
                false,
            ),
            (
                format!(
                    "checked_at = {}\nlatest_tag = 'vpnd-v9.0.0'",
                    100_001 - TTL_SECS
                ),
                true,
            ),
        ] {
            std::fs::write(&path, raw).unwrap();
            let cached = load_cache(&path, 100_000);
            assert_eq!(cached.is_some(), fresh);
            if let Some(cache) = cached {
                assert_eq!(cache.latest_tag, "vpnd-v9.0.0");
            }
        }
    }
}
