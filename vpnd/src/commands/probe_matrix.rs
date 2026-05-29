//! `vpnd probe-matrix` — multi-protocol simultaneity DPI probe across a
//! (protocol × destination-class) matrix on a configurable poll interval.
//!
//! Motivation: when a filtering pipeline applies policy at a level above
//! per-protocol fingerprinting, single-protocol probes miss the signal.
//! A simultaneity matrix captures whether several encrypted protocols
//! drop together — that pattern is the load-bearing observation.
//!
//! Layering: vpnd owns the loop (duration, poll interval, JSON
//! aggregation, onset/recovery analysis). Per-cell probe semantics
//! live in `scripts/probe-matrix-cell.sh` (Make target
//! `probe-matrix-cell`) so the canonical-shell-surface contract from
//! `vpnd/CLAUDE.md` is preserved.

use anyhow::{anyhow, Context as _, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::cli::ProbeMatrixArgs;
use crate::config::Context;
use crate::runner::make;

const SCHEMA_VERSION: u32 = 1;

/// On-disk config the operator supplies. Lives outside the binary so the
/// destination IP table is operator-owned (the code carries no addresses).
#[derive(Debug, Clone, Deserialize)]
struct MatrixConfig {
    vantage: String,
    #[serde(default)]
    poll_interval_seconds: Option<u64>,
    protocols: Vec<Protocol>,
    destinations: Vec<Destination>,
}

/// Protocols probed in parallel each tick.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "kebab-case")]
enum Protocol {
    /// Telegram MTProto.
    Mtproto,
    /// VLESS over XHTTP transport.
    XhttpVless,
    /// Trojan over XHTTP transport.
    XhttpTrojan,
    /// Trojan over plain TCP.
    TcpTrojan,
    /// Plain TLS on any non-443 port.
    TlsNon443,
}

impl Protocol {
    fn as_kebab(&self) -> &'static str {
        match self {
            Protocol::Mtproto => "mtproto",
            Protocol::XhttpVless => "xhttp-vless",
            Protocol::XhttpTrojan => "xhttp-trojan",
            Protocol::TcpTrojan => "tcp-trojan",
            Protocol::TlsNon443 => "tls-non-443",
        }
    }
}

/// Destination class encodes the *technical signature* of the
/// destination ASN bucket. Operators map this to actual IPs in their
/// config — the code carries no operator-identifying labels.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "kebab-case")]
enum DestinationClass {
    /// Domestic ASN that historically clears filtering peering checks.
    DomesticAllowlisted,
    /// Domestic ASN with no specific allowlist treatment.
    DomesticGeneric,
    /// Foreign-DC ASN bucket that historically triggers connection-
    /// freeze rules on filtered networks.
    ForeignNonAllowlist,
}

impl DestinationClass {
    fn as_kebab(&self) -> &'static str {
        match self {
            DestinationClass::DomesticAllowlisted => "domestic-allowlisted",
            DestinationClass::DomesticGeneric => "domestic-generic",
            DestinationClass::ForeignNonAllowlist => "foreign-non-allowlist",
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
struct Destination {
    class: DestinationClass,
    /// IP:port literal supplied by the operator.
    endpoint: String,
}

/// Per-cell verdict at one tick.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum Verdict {
    Ok,
    Throttled,
    Blocked,
    Unknown,
    Error,
}

#[derive(Debug, Clone, Serialize)]
struct CellResult {
    timestamp_unix_ms: u64,
    protocol: Protocol,
    destination_class: DestinationClass,
    endpoint: String,
    verdict: Verdict,
    #[serde(skip_serializing_if = "Option::is_none")]
    rtt_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_kind: Option<String>,
}

/// Result of a single per-cell probe invocation — what the wrapper
/// script is contracted to emit on stdout as one JSON object.
#[derive(Debug, Clone, Deserialize)]
struct CellProbeOutput {
    verdict: Verdict,
    #[serde(default)]
    rtt_ms: Option<u64>,
    #[serde(default)]
    error_kind: Option<String>,
}

/// Onset (first non-OK tick) and recovery (first OK tick after an onset)
/// per (protocol, destination_class) pair. Both are unix-ms or None when
/// the cell never crossed the boundary during the run.
#[derive(Debug, Clone, Serialize)]
struct OnsetRecovery {
    protocol: Protocol,
    destination_class: DestinationClass,
    onset_unix_ms: Option<u64>,
    recovery_unix_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MatrixReport {
    schema_version: u32,
    vantage: String,
    started_at_unix_ms: u64,
    finished_at_unix_ms: u64,
    poll_interval_seconds: u64,
    cells: Vec<CellResult>,
    windows: Vec<OnsetRecovery>,
}

pub async fn run(ctx: &Context, args: ProbeMatrixArgs) -> Result<()> {
    let config_path = args
        .config
        .clone()
        .unwrap_or_else(|| ctx.root.join("vpnd").join("config").join("probe-matrix.yaml"));
    let cfg = load_config(&config_path)?;
    let poll_interval = Duration::from_secs(
        args.poll_interval_seconds
            .or(cfg.poll_interval_seconds)
            .unwrap_or(300),
    );
    let duration = parse_duration(&args.duration)?;

    if ctx.explain {
        explain(ctx, &cfg, duration, poll_interval, &config_path);
        return Ok(());
    }

    let started = SystemTime::now();
    let started_ms = unix_ms(started);
    let deadline = started + duration;

    let mut cells: Vec<CellResult> = Vec::new();
    let mut tick = 0u32;
    loop {
        let now = SystemTime::now();
        if now >= deadline {
            break;
        }
        eprintln!(
            "probe-matrix: tick {} @ {}s elapsed",
            tick,
            now.duration_since(started).unwrap_or_default().as_secs()
        );
        for protocol in &cfg.protocols {
            for dest in &cfg.destinations {
                let cell_timeout = Duration::from_secs(30);
                let result = match tokio::time::timeout(
                    cell_timeout,
                    probe_cell(ctx, &cfg.vantage, *protocol, dest, now, ctx.explain),
                )
                .await
                {
                    Ok(r) => r?,
                    Err(_elapsed) => CellResult {
                        timestamp_unix_ms: unix_ms(now),
                        protocol: *protocol,
                        destination_class: dest.class,
                        endpoint: dest.endpoint.clone(),
                        verdict: Verdict::Unknown,
                        rtt_ms: None,
                        error_kind: Some("timeout".to_string()),
                    },
                };
                cells.push(result);
            }
        }
        tick += 1;

        // Sleep until the next tick or the deadline.
        let next = now + poll_interval;
        if next >= deadline {
            break;
        }
        tokio::time::sleep(poll_interval).await;
    }

    let finished_ms = unix_ms(SystemTime::now());
    let windows = compute_windows(&cells);

    let report = MatrixReport {
        schema_version: SCHEMA_VERSION,
        vantage: cfg.vantage,
        started_at_unix_ms: started_ms,
        finished_at_unix_ms: finished_ms,
        poll_interval_seconds: poll_interval.as_secs(),
        cells,
        windows,
    };

    let out_path = args
        .output
        .clone()
        .unwrap_or_else(|| default_output_path(ctx, started_ms));
    write_report(&report, &out_path)?;
    println!("wrote {}", out_path.display());
    Ok(())
}

fn load_config(path: &Path) -> Result<MatrixConfig> {
    let raw = std::fs::read_to_string(path)
        .with_context(|| format!("reading probe-matrix config at {}", path.display()))?;
    let cfg: MatrixConfig = serde_yaml::from_str(&raw)
        .with_context(|| format!("parsing probe-matrix config at {}", path.display()))?;
    if cfg.protocols.is_empty() {
        return Err(anyhow!("probe-matrix config has no protocols"));
    }
    if cfg.destinations.is_empty() {
        return Err(anyhow!("probe-matrix config has no destinations"));
    }
    Ok(cfg)
}

fn parse_duration(s: &str) -> Result<Duration> {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        return Err(anyhow!("empty duration"));
    }
    let (num_part, unit_part) = trimmed.split_at(
        trimmed
            .find(|c: char| !c.is_ascii_digit())
            .unwrap_or(trimmed.len()),
    );
    let n: u64 = num_part
        .parse()
        .with_context(|| format!("duration must start with digits: {trimmed}"))?;
    let secs = match unit_part {
        "s" | "" => n,
        "m" => n * 60,
        "h" => n * 3600,
        "d" => n * 86400,
        other => return Err(anyhow!("unknown duration unit: '{other}'")),
    };
    Ok(Duration::from_secs(secs))
}

fn unix_ms(t: SystemTime) -> u64 {
    t.duration_since(UNIX_EPOCH)
        // as_millis() returns u128; clamp to u64::MAX on overflow (year ~584 million)
        .map(|d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX))
        .unwrap_or(0)
}

fn default_output_path(ctx: &Context, started_ms: u64) -> PathBuf {
    ctx.root
        .join("vpnd")
        .join("state")
        .join(format!("probe-matrix-{started_ms}.json"))
}

fn write_report(report: &MatrixReport, path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating {}", parent.display()))?;
    }
    let raw = serde_json::to_string_pretty(report)?;
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, raw).with_context(|| format!("writing {}", tmp.display()))?;
    std::fs::rename(&tmp, path).with_context(|| format!("renaming {}", path.display()))?;
    Ok(())
}

async fn probe_cell(
    ctx: &Context,
    vantage: &str,
    protocol: Protocol,
    dest: &Destination,
    now: SystemTime,
    explain: bool,
) -> Result<CellResult> {
    let cmd = make::target_with(
        ctx,
        "probe-matrix-cell",
        &[
            ("VANTAGE", vantage),
            ("PROTOCOL", protocol.as_kebab()),
            ("DEST_CLASS", dest.class.as_kebab()),
            ("DEST", &dest.endpoint),
        ],
    );

    match cmd.capture(explain).await {
        Ok(out) => match serde_json::from_str::<CellProbeOutput>(&out.stdout) {
            Ok(probe) => Ok(CellResult {
                timestamp_unix_ms: unix_ms(now),
                protocol,
                destination_class: dest.class,
                endpoint: dest.endpoint.clone(),
                verdict: probe.verdict,
                rtt_ms: probe.rtt_ms,
                error_kind: probe.error_kind,
            }),
            Err(err) => Ok(CellResult {
                timestamp_unix_ms: unix_ms(now),
                protocol,
                destination_class: dest.class,
                endpoint: dest.endpoint.clone(),
                verdict: Verdict::Error,
                rtt_ms: None,
                error_kind: Some(format!("parse: {err}")),
            }),
        },
        Err(err) => Ok(CellResult {
            timestamp_unix_ms: unix_ms(now),
            protocol,
            destination_class: dest.class,
            endpoint: dest.endpoint.clone(),
            verdict: Verdict::Error,
            rtt_ms: None,
            error_kind: Some(format!("invoke: {err}")),
        }),
    }
}

fn compute_windows(cells: &[CellResult]) -> Vec<OnsetRecovery> {
    let mut by_key: BTreeMap<(String, String), Vec<&CellResult>> = BTreeMap::new();
    for c in cells {
        by_key
            .entry((c.protocol.as_kebab().to_string(), c.destination_class.as_kebab().to_string()))
            .or_default()
            .push(c);
    }
    let mut out = Vec::with_capacity(by_key.len());
    for ((_p, _d), mut series) in by_key {
        series.sort_by_key(|c| c.timestamp_unix_ms);
        let mut onset: Option<u64> = None;
        let mut recovery: Option<u64> = None;
        for c in &series {
            let bad = !matches!(c.verdict, Verdict::Ok);
            if bad && onset.is_none() {
                onset = Some(c.timestamp_unix_ms);
            } else if !bad && onset.is_some() && recovery.is_none() {
                recovery = Some(c.timestamp_unix_ms);
            }
        }
        if let Some(first) = series.first() {
            out.push(OnsetRecovery {
                protocol: first.protocol,
                destination_class: first.destination_class,
                onset_unix_ms: onset,
                recovery_unix_ms: recovery,
            });
        }
    }
    out
}

fn explain(
    ctx: &Context,
    cfg: &MatrixConfig,
    duration: Duration,
    poll_interval: Duration,
    config_path: &Path,
) {
    let n_protocols = cfg.protocols.len();
    let n_destinations = cfg.destinations.len();
    let ticks = duration.as_secs() / poll_interval.as_secs().max(1);
    let cells_total = (ticks as usize) * n_protocols * n_destinations;
    println!("# vpnd probe-matrix would orchestrate:");
    println!("  vantage:        {}", cfg.vantage);
    println!("  config:         {}", config_path.display());
    println!("  duration:       {}s", duration.as_secs());
    println!("  poll_interval:  {}s", poll_interval.as_secs());
    println!("  protocols:      {n_protocols} ({})",
             cfg.protocols.iter().map(|p| p.as_kebab()).collect::<Vec<_>>().join(", "));
    println!("  destinations:   {n_destinations} (classes: {})",
             cfg.destinations.iter().map(|d| d.class.as_kebab()).collect::<Vec<_>>().join(", "));
    println!("  ticks:          {ticks}");
    println!("  cell invocations: {cells_total}");
    println!();
    println!("# each cell shells out to:");
    let sample = make::target_with(
        ctx,
        "probe-matrix-cell",
        &[
            ("VANTAGE", &cfg.vantage),
            ("PROTOCOL", "<proto>"),
            ("DEST_CLASS", "<class>"),
            ("DEST", "<ip:port>"),
        ],
    );
    println!("  {}", sample.explain());
}

// ---------------------------------------------------------------------------
// Test helpers — exposed to integration tests so the snapshot fixture has a
// deterministic builder that does not touch the network.
// ---------------------------------------------------------------------------

#[doc(hidden)]
pub fn synthetic_report_for_snapshot() -> MatrixReport {
    // Fixed unix-ms anchors so the snapshot stays stable.
    let started = 1_700_000_000_000u64;
    let interval_ms = 300_000u64; // 5 min
    let mut cells = Vec::new();

    // Two ticks, 3 protocols, 2 destinations = 12 cells.
    let protocols = [
        Protocol::Mtproto,
        Protocol::XhttpVless,
        Protocol::TcpTrojan,
    ];
    let dests = [
        (DestinationClass::DomesticAllowlisted, "10.0.0.1:443"),
        (DestinationClass::ForeignNonAllowlist, "203.0.113.1:443"),
    ];

    for tick in 0..2 {
        let ts = started + tick * interval_ms;
        for proto in &protocols {
            for (class, ep) in &dests {
                // Synthetic verdict pattern: foreign-non-allowlist drops on
                // the second tick across every protocol — that's the
                // simultaneity signature the report is designed to surface.
                let verdict = if *class == DestinationClass::ForeignNonAllowlist && tick == 1 {
                    Verdict::Blocked
                } else {
                    Verdict::Ok
                };
                cells.push(CellResult {
                    timestamp_unix_ms: ts,
                    protocol: *proto,
                    destination_class: *class,
                    endpoint: (*ep).to_string(),
                    verdict,
                    rtt_ms: if matches!(verdict, Verdict::Ok) { Some(42) } else { None },
                    error_kind: None,
                });
            }
        }
    }

    let windows = compute_windows(&cells);
    MatrixReport {
        schema_version: SCHEMA_VERSION,
        vantage: "synthetic".into(),
        started_at_unix_ms: started,
        finished_at_unix_ms: started + 2 * interval_ms,
        poll_interval_seconds: interval_ms / 1000,
        cells,
        windows,
    }
}

#[doc(hidden)]
pub fn report_to_json(report: &MatrixReport) -> Result<String, serde_json::Error> {
    serde_json::to_string_pretty(report)
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod tests {
    use super::*;

    #[test]
    fn duration_parses_common_forms() {
        assert_eq!(parse_duration("60s").unwrap(), Duration::from_secs(60));
        assert_eq!(parse_duration("5m").unwrap(), Duration::from_secs(300));
        assert_eq!(parse_duration("4h").unwrap(), Duration::from_secs(4 * 3600));
        assert_eq!(parse_duration("1d").unwrap(), Duration::from_secs(86400));
        assert_eq!(parse_duration("120").unwrap(), Duration::from_secs(120));
        assert!(parse_duration("").is_err());
        assert!(parse_duration("4y").is_err());
    }

    #[test]
    fn synthetic_report_has_expected_shape() {
        let report = synthetic_report_for_snapshot();
        // 2 ticks × 3 protocols × 2 destinations = 12 cells
        assert_eq!(report.cells.len(), 12);
        // 3 × 2 = 6 (protocol, class) windows
        assert_eq!(report.windows.len(), 6);
        // foreign-non-allowlist windows should have an onset on tick 1,
        // domestic-allowlisted windows should have onset = None.
        for w in &report.windows {
            match w.destination_class {
                DestinationClass::ForeignNonAllowlist => assert!(w.onset_unix_ms.is_some()),
                _ => assert!(w.onset_unix_ms.is_none()),
            }
        }
    }
}
