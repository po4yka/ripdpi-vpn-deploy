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
/// The check is advisory: a stalled connection must fail the fetch well
/// below any operator patience threshold, never hang the CLI.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);

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
    fetch_latest_tag_with_timeout(url, REQUEST_TIMEOUT)
}

/// The network boundary is explicitly bounded: connect and overall request
/// timeouts mean a black-holed connection errors instead of blocking the
/// async caller indefinitely. Failure stays advisory — the caller converts
/// it into a debug log and exit 0.
fn fetch_latest_tag_with_timeout(url: &str, request_timeout: Duration) -> Result<String> {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(request_timeout))
        .timeout_connect(Some(CONNECT_TIMEOUT))
        .build()
        .into();
    let mut resp = agent
        .get(url)
        .header("User-Agent", format!("vpnd/{}", env!("CARGO_PKG_VERSION")))
        .call()
        .context("GitHub releases API request failed")?;
    let release: GhRelease = resp
        .body_mut()
        .read_json()
        .context("parse GitHub release JSON")?;
    Ok(release.tag_name)
}

/// Strip release-train tag schemes down to the bare version. Two trains
/// publish releases in this repository: repo-wide release-please tags
/// (`vX.Y.Z`) and vpnd-specific tags (`vpnd-vX.Y.Z`). Both carry the same
/// version numbers, so both must normalize to the comparable form — a
/// repo-wide tag must not be discarded as an unknown scheme.
fn normalize_tag(tag: &str) -> Option<&str> {
    let bare = tag.trim().strip_prefix("vpnd-").unwrap_or(tag);
    bare.strip_prefix('v')
}

/// Parse a plain three-part numeric release version. Prerelease or
/// build-suffixed tags fail to parse; an unparseable latest version must
/// never produce a notice, so None is the conservative answer everywhere.
fn parse_version(value: &str) -> Option<(u64, u64, u64)> {
    let mut parts = value.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    if parts.next().is_some() {
        return None;
    }
    Some((major, minor, patch))
}

/// A notice fires only when the latest tag parses to a version strictly
/// newer than the running CLI: a locally newer build never receives a
/// downgrade recommendation, and an equal version stays silent.
fn is_newer(latest_tag: &str) -> bool {
    let current = parse_version(env!("CARGO_PKG_VERSION"));
    let latest = normalize_tag(latest_tag).and_then(parse_version);
    match (current, latest) {
        (Some(current), Some(latest)) => latest > current,
        _ => false,
    }
}

fn print_notice(latest_tag: &str) {
    if !is_newer(latest_tag) {
        return;
    }
    let stripped = latest_tag.trim_start_matches("vpnd-");
    eprintln!(
        "{} A newer vpnd release is available: {} (you have {}). \
         See https://github.com/po4yka/ripdpi-vpn-deploy/releases",
        "notice:".yellow(),
        stripped.green().bold(),
        format!("v{}", env!("CARGO_PKG_VERSION")).dimmed(),
    );
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

    #[test]
    fn normalize_tag_accepts_both_release_train_schemes() {
        assert_eq!(normalize_tag("vpnd-v9.0.0"), Some("9.0.0"));
        assert_eq!(normalize_tag("v9.0.0"), Some("9.0.0"));
        assert_eq!(normalize_tag("vpnd-v0.1.0"), Some("0.1.0"));
        assert_eq!(normalize_tag("release-2026-08-23"), None);
        assert_eq!(normalize_tag("9.0.0"), None, "bare version is not a tag");
    }

    #[test]
    fn notice_requires_a_strictly_newer_parseable_release() {
        let current = parse_version(env!("CARGO_PKG_VERSION")).unwrap();
        let bump = |delta: i64| {
            let total =
                current.0 as i64 * 10_000 + current.1 as i64 * 100 + current.2 as i64 + delta;
            format!(
                "vpnd-v{}.{}.{}",
                total / 10_000,
                total / 100 % 100,
                total % 100
            )
        };
        // Older or equal latest must never produce a downgrade notice.
        assert!(!is_newer(&bump(-1)));
        assert!(!is_newer(&bump(0)));
        // A strictly newer release in either train fires: the vpnd-specific
        // tag and the repo-wide tag carry the same version numbers.
        assert!(is_newer(&bump(1)));
        assert!(is_newer(bump(1).trim_start_matches("vpnd-")));
        // Prerelease suffixes fail the plain parse and stay silent.
        assert!(!is_newer(&format!("{}-rc1", bump(1))));
        // Unparseable tags can never claim to be newer.
        assert!(!is_newer("release-2026-08-23"));
    }

    #[test]
    fn stalled_connection_fails_within_the_explicit_timeout() {
        // The test server accepts the connection and never answers, so only
        // the configured timeout can end the request.
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/releases/latest", listener.local_addr().unwrap());
        let server = std::thread::spawn(move || {
            let (socket, _) = listener.accept().unwrap();
            std::thread::sleep(Duration::from_secs(2));
            drop(socket);
        });
        let started = std::time::Instant::now();
        let result = fetch_latest_tag_with_timeout(&url, Duration::from_secs(1));
        let elapsed = started.elapsed();
        assert!(result.is_err(), "a stalled connection must fail, not hang");
        assert!(
            elapsed < Duration::from_secs(4),
            "the explicit timeout must bound the request, took {elapsed:?}"
        );
        server.join().unwrap();
    }
}
