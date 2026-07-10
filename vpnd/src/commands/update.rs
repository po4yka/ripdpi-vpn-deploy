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

    if let Some(cached) = load_cache(&cache_path, now_secs) {
        print_notice(&cached.latest_tag);
        return Ok(());
    }

    // Fetch from GitHub — never block the caller on failure.
    match fetch_latest_tag() {
        Ok(tag) => {
            let cache = Cache {
                checked_at: now_secs,
                latest_tag: tag.clone(),
            };
            // Best-effort write; ignore errors.
            let _ = std::fs::create_dir_all(&ctx.config_dir);
            if let Ok(s) = toml::to_string(&cache) {
                let _ = std::fs::write(&cache_path, s);
            }
            print_notice(&tag);
        }
        Err(e) => {
            tracing::debug!("update check failed (non-fatal): {e}");
        }
    }
    Ok(())
}

fn load_cache(path: &std::path::Path, now: u64) -> Option<Cache> {
    let raw = std::fs::read_to_string(path).ok()?;
    let cache: Cache = toml::from_str(&raw).ok()?;
    if now.saturating_sub(cache.checked_at) < TTL_SECS {
        Some(cache)
    } else {
        None
    }
}

fn fetch_latest_tag() -> Result<String> {
    let mut resp = ureq::get(GITHUB_API_URL)
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
    if latest_tag != current && latest_tag.starts_with("vpnd-v") {
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
