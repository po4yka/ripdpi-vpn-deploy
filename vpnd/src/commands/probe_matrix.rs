// Topology-aware implementation for `vpnd probe-matrix`.

use anyhow::{anyhow, Context as _, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::task::JoinSet;

use crate::cli::ProbeMatrixArgs;
use crate::config::Context;
use crate::runner::make;

const SCHEMA_VERSION: u32 = 2;

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct MatrixConfig {
    schema_version: u32,
    vantage: String,
    poll_interval_seconds: Option<u64>,
    control: ControlConfig,
    protocols: Vec<Protocol>,
    targets: Vec<Target>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct ControlConfig {
    url: String,
    expected_status: u16,
    timeout_seconds: u64,
    degraded_after_ms: u64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[serde(rename_all = "kebab-case")]
enum Protocol {
    Mtproto,
    XhttpVless,
    XhttpTrojan,
    TcpTrojan,
    TlsNon443,
}

impl Protocol {
    fn name(self) -> &'static str {
        match self {
            Self::Mtproto => "mtproto",
            Self::XhttpVless => "xhttp-vless",
            Self::XhttpTrojan => "xhttp-trojan",
            Self::TcpTrojan => "tcp-trojan",
            Self::TlsNon443 => "tls-non-443",
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[serde(rename_all = "kebab-case")]
enum DestinationClass {
    #[serde(rename = "allowlist-pattern")]
    Allowlist,
    #[serde(rename = "neutral-pattern")]
    Neutral,
    #[serde(rename = "non-allowlist-pattern")]
    NonAllowlist,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[serde(rename_all = "kebab-case")]
enum Topology {
    SingleIpDualRole,
    SplitHopIngress,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Target {
    id: String,
    comparison_set: String,
    destination_class: DestinationClass,
    topology: Topology,
    profile_file: PathBuf,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum Verdict {
    Ok,
    Throttled,
    Blocked,
    Unknown,
    Error,
}

impl Verdict {
    fn name(self) -> &'static str {
        match self {
            Self::Ok => "ok",
            Self::Throttled => "throttled",
            Self::Blocked => "blocked",
            Self::Unknown => "unknown",
            Self::Error => "error",
        }
    }

    fn usable(self) -> bool {
        matches!(self, Self::Ok | Self::Throttled)
    }
}

#[derive(Debug, Clone, Deserialize)]
struct ProbeOutput {
    verdict: Verdict,
    rtt_ms: Option<u64>,
    error_kind: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct ControlResult {
    tick: u32,
    timestamp_unix_ms: u64,
    verdict: Verdict,
    #[serde(skip_serializing_if = "Option::is_none")]
    rtt_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_kind: Option<String>,
    sweep_duration_ms: u64,
    overrun_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
struct CellResult {
    tick: u32,
    timestamp_unix_ms: u64,
    protocol: Protocol,
    target_id: String,
    comparison_set: String,
    destination_class: DestinationClass,
    topology: Topology,
    verdict: Verdict,
    #[serde(skip_serializing_if = "Option::is_none")]
    rtt_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_kind: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct Window {
    protocol: Protocol,
    target_id: String,
    comparison_set: String,
    destination_class: DestinationClass,
    topology: Topology,
    onset_unix_ms: Option<u64>,
    recovery_unix_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
enum ObservationKind {
    ProtocolSpecific,
    DestinationClassWideCollateral,
    DualRoleTargetingCandidate,
    Indeterminate,
}

#[derive(Debug, Clone, Serialize)]
struct Observation {
    tick: u32,
    kind: ObservationKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    protocol: Option<Protocol>,
    #[serde(skip_serializing_if = "Option::is_none")]
    destination_class: Option<DestinationClass>,
    comparison_sets: Vec<String>,
    evidence_target_ids: Vec<String>,
    reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct MatrixReport {
    schema_version: u32,
    vantage: String,
    started_at_unix_ms: u64,
    finished_at_unix_ms: u64,
    poll_interval_seconds: u64,
    controls: Vec<ControlResult>,
    cells: Vec<CellResult>,
    windows: Vec<Window>,
    observations: Vec<Observation>,
}

pub async fn run(ctx: &Context, args: ProbeMatrixArgs) -> Result<()> {
    let requested = args
        .config
        .clone()
        .unwrap_or_else(|| ctx.root.join("vpnd/config/probe-matrix.yaml"));
    let config_path = requested
        .canonicalize()
        .with_context(|| format!("resolving {}", requested.display()))?;
    let config = load_config(&config_path)?;
    let interval = Duration::from_secs(
        args.poll_interval_seconds
            .or(config.poll_interval_seconds)
            .unwrap_or(300),
    );
    if interval.is_zero() {
        return Err(anyhow!("poll interval must be greater than zero"));
    }
    let duration = parse_duration(&args.duration)?;
    if ctx.explain {
        explain(ctx, &config, duration, interval, &config_path);
        return Ok(());
    }

    let wall_start = SystemTime::now();
    let mono_start = tokio::time::Instant::now();
    let deadline = mono_start + duration;
    let mut controls = Vec::new();
    let mut cells = Vec::new();
    let mut tick = 0u32;
    while tokio::time::Instant::now() < deadline {
        let tick_start = tokio::time::Instant::now();
        let tick_wall = SystemTime::now();
        let mut control = run_control(
            ctx,
            &config_path,
            tick,
            tick_wall,
            Duration::from_secs(config.control.timeout_seconds),
        )
        .await;
        let mut jobs = JoinSet::new();
        for (pindex, protocol) in config.protocols.iter().copied().enumerate() {
            for (tindex, target) in config.targets.iter().cloned().enumerate() {
                let ctx = ctx.clone();
                let path = config_path.clone();
                let timeout = Duration::from_secs(config.control.timeout_seconds);
                let order = pindex * config.targets.len() + tindex;
                let control_verdict = control.verdict;
                jobs.spawn(async move {
                    let value = tokio::time::timeout(
                        timeout,
                        run_cell(
                            &ctx,
                            &path,
                            tick,
                            tick_wall,
                            protocol,
                            &target,
                            control_verdict,
                        ),
                    )
                    .await
                    .unwrap_or_else(|_| {
                        cell_error(
                            tick,
                            tick_wall,
                            protocol,
                            &target,
                            Verdict::Unknown,
                            "timeout",
                        )
                    });
                    (order, value)
                });
            }
        }
        cells.extend(collect_ordered(jobs).await?);

        let sweep = tokio::time::Instant::now().duration_since(tick_start);
        control.sweep_duration_ms = ms(sweep);
        control.overrun_ms = ms(sweep.saturating_sub(interval));
        controls.push(control);
        tick = tick.saturating_add(1);
        let next = scheduled_tick(mono_start, interval, tick);
        if next >= deadline {
            break;
        }
        if next > tokio::time::Instant::now() {
            tokio::time::sleep_until(next).await;
        }
    }
    let report = MatrixReport {
        schema_version: SCHEMA_VERSION,
        vantage: config.vantage,
        started_at_unix_ms: unix_ms(wall_start),
        finished_at_unix_ms: unix_ms(SystemTime::now()),
        poll_interval_seconds: interval.as_secs(),
        windows: windows(&cells),
        observations: analyze(&config.protocols, &cells),
        controls,
        cells,
    };
    let output = args.output.unwrap_or_else(|| {
        ctx.root.join(format!(
            "vpnd/state/probe-matrix-{}.json",
            unix_ms(wall_start)
        ))
    });
    write_report(&report, &output)?;
    println!("wrote {}", output.display());
    Ok(())
}

async fn collect_ordered<T: Send + 'static>(mut jobs: JoinSet<(usize, T)>) -> Result<Vec<T>> {
    let mut ordered = Vec::new();
    while let Some(result) = jobs.join_next().await {
        ordered.push(result.context("probe cell task")?);
    }
    ordered.sort_by_key(|(order, _)| *order);
    Ok(ordered.into_iter().map(|(_, value)| value).collect())
}

fn scheduled_tick(
    start: tokio::time::Instant,
    interval: Duration,
    tick: u32,
) -> tokio::time::Instant {
    start + interval.saturating_mul(tick)
}

fn load_config(path: &Path) -> Result<MatrixConfig> {
    let raw =
        std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;
    let config: MatrixConfig =
        serde_yaml_ng::from_str(&raw).with_context(|| format!("parsing {}", path.display()))?;
    validate_config(&config)?;
    validate_profiles(&config)?;
    Ok(config)
}

fn validate_profiles(config: &MatrixConfig) -> Result<()> {
    use std::os::unix::fs::MetadataExt;

    let uid = uzers::get_current_uid();
    let mut comparison_fingerprints: BTreeMap<&str, serde_json::Value> = BTreeMap::new();
    for target in &config.targets {
        let metadata = std::fs::symlink_metadata(&target.profile_file)
            .with_context(|| format!("inspecting target profile for '{}'", target.id))?;
        if !metadata.file_type().is_file()
            || metadata.uid() != uid
            || metadata.mode() & 0o777 != 0o600
        {
            return Err(anyhow!(
                "target '{}' profile must be an owner-controlled 0600 regular file",
                target.id
            ));
        }
        let raw = std::fs::read_to_string(&target.profile_file)
            .with_context(|| format!("reading target profile for '{}'", target.id))?;
        let profile: serde_json::Value = serde_json::from_str(&raw)
            .with_context(|| format!("parsing target profile for '{}'", target.id))?;
        if profile
            .get("schema_version")
            .and_then(serde_json::Value::as_u64)
            != Some(1)
            || profile.get("target_id").and_then(serde_json::Value::as_str)
                != Some(target.id.as_str())
        {
            return Err(anyhow!(
                "target '{}' profile identity or schema is invalid",
                target.id
            ));
        }
        let available = profile
            .get("protocols")
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| anyhow!("target '{}' profile has no protocols", target.id))?;
        for protocol in &config.protocols {
            if !available.contains_key(protocol.name()) {
                return Err(anyhow!(
                    "target '{}' profile is missing protocol '{}'",
                    target.id,
                    protocol.name()
                ));
            }
        }
        let fingerprint = transport_fingerprint(profile);
        if let Some(expected) = comparison_fingerprints.get(target.comparison_set.as_str()) {
            if expected != &fingerprint {
                return Err(anyhow!(
                    "comparison_set '{}' must use identical runtime and transport parameters",
                    target.comparison_set
                ));
            }
        } else {
            comparison_fingerprints.insert(&target.comparison_set, fingerprint);
        }
    }
    Ok(())
}

fn transport_fingerprint(mut profile: serde_json::Value) -> serde_json::Value {
    if let Some(root) = profile.as_object_mut() {
        root.remove("target_id");
        root.remove("endpoint");
        if let Some(protocols) = root
            .get_mut("protocols")
            .and_then(serde_json::Value::as_object_mut)
        {
            for settings in protocols
                .values_mut()
                .filter_map(serde_json::Value::as_object_mut)
            {
                settings.remove("secret");
                settings.remove("uuid");
                settings.remove("password");
            }
        }
    }
    profile
}

fn validate_config(config: &MatrixConfig) -> Result<()> {
    if config.schema_version != SCHEMA_VERSION {
        return Err(anyhow!("schema_version must be {SCHEMA_VERSION}"));
    }
    if !technical_id(&config.vantage)
        || !config.control.url.starts_with("https://")
        || !(100..=599).contains(&config.control.expected_status)
        || !(1..=60).contains(&config.control.timeout_seconds)
        || config.control.degraded_after_ms == 0
    {
        return Err(anyhow!("invalid vantage or control configuration"));
    }
    if config.protocols.is_empty() || config.targets.is_empty() {
        return Err(anyhow!("protocols and targets are required"));
    }
    if config.protocols.iter().collect::<BTreeSet<_>>().len() != config.protocols.len() {
        return Err(anyhow!("protocols must be unique"));
    }
    let mut ids = BTreeSet::new();
    let mut pairs: BTreeMap<&str, Vec<&Target>> = BTreeMap::new();
    for target in &config.targets {
        if !technical_id(&target.id)
            || !technical_id(&target.comparison_set)
            || !target.profile_file.is_absolute()
            || !ids.insert(target.id.as_str())
        {
            return Err(anyhow!("invalid or duplicate target"));
        }
        pairs
            .entry(&target.comparison_set)
            .or_default()
            .push(target);
    }
    for (name, pair) in pairs {
        let topologies = pair
            .iter()
            .map(|target| target.topology)
            .collect::<BTreeSet<_>>();
        if pair.len() != 2
            || pair[0].destination_class != pair[1].destination_class
            || topologies != BTreeSet::from([Topology::SingleIpDualRole, Topology::SplitHopIngress])
        {
            return Err(anyhow!(
                "comparison_set '{name}' must pair both topologies in one class"
            ));
        }
    }
    Ok(())
}

fn technical_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value.as_bytes()[0].is_ascii_lowercase()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
}

async fn run_control(
    ctx: &Context,
    path: &Path,
    tick: u32,
    now: SystemTime,
    timeout: Duration,
) -> ControlResult {
    let path = path.to_string_lossy();
    let command = make::target_with(ctx, "probe-matrix-control", &[("MATRIX_CONFIG", &path)]);
    let probe = match tokio::time::timeout(timeout, command.capture(false)).await {
        Ok(result) => capture(result),
        Err(_) => ProbeOutput {
            verdict: Verdict::Unknown,
            rtt_ms: None,
            error_kind: Some("control_timeout".to_string()),
        },
    };
    ControlResult {
        tick,
        timestamp_unix_ms: unix_ms(now),
        verdict: probe.verdict,
        rtt_ms: probe.rtt_ms,
        error_kind: probe.error_kind,
        sweep_duration_ms: 0,
        overrun_ms: 0,
    }
}

async fn run_cell(
    ctx: &Context,
    path: &Path,
    tick: u32,
    now: SystemTime,
    protocol: Protocol,
    target: &Target,
    control: Verdict,
) -> CellResult {
    let path = path.to_string_lossy();
    let command = make::target_with(
        ctx,
        "probe-matrix-cell",
        &[
            ("MATRIX_CONFIG", &path),
            ("TARGET_ID", &target.id),
            ("PROTOCOL", protocol.name()),
            ("CONTROL_VERDICT", control.name()),
        ],
    );
    let probe = capture(command.capture(false).await);
    CellResult {
        tick,
        timestamp_unix_ms: unix_ms(now),
        protocol,
        target_id: target.id.clone(),
        comparison_set: target.comparison_set.clone(),
        destination_class: target.destination_class,
        topology: target.topology,
        verdict: probe.verdict,
        rtt_ms: probe.rtt_ms,
        error_kind: probe.error_kind,
    }
}

fn capture(output: Result<crate::runner::process::Output>) -> ProbeOutput {
    match output {
        Ok(output) => serde_json::from_str(output.stdout.trim()).unwrap_or(ProbeOutput {
            verdict: Verdict::Error,
            rtt_ms: None,
            error_kind: Some("invalid-output".to_string()),
        }),
        Err(_) => ProbeOutput {
            verdict: Verdict::Error,
            rtt_ms: None,
            error_kind: Some("invoke".to_string()),
        },
    }
}

fn cell_error(
    tick: u32,
    now: SystemTime,
    protocol: Protocol,
    target: &Target,
    verdict: Verdict,
    kind: &str,
) -> CellResult {
    CellResult {
        tick,
        timestamp_unix_ms: unix_ms(now),
        protocol,
        target_id: target.id.clone(),
        comparison_set: target.comparison_set.clone(),
        destination_class: target.destination_class,
        topology: target.topology,
        verdict,
        rtt_ms: None,
        error_kind: Some(kind.to_string()),
    }
}

fn windows(cells: &[CellResult]) -> Vec<Window> {
    let mut series: BTreeMap<(Protocol, String), Vec<&CellResult>> = BTreeMap::new();
    for cell in cells {
        series
            .entry((cell.protocol, cell.target_id.clone()))
            .or_default()
            .push(cell);
    }
    series
        .into_values()
        .filter_map(|mut values| {
            values.sort_by_key(|cell| cell.tick);
            let first = *values.first()?;
            let onset = values
                .iter()
                .find(|cell| cell.verdict != Verdict::Ok)
                .map(|cell| cell.timestamp_unix_ms);
            let recovery = onset.and_then(|value| {
                values
                    .iter()
                    .find(|cell| cell.timestamp_unix_ms > value && cell.verdict == Verdict::Ok)
                    .map(|cell| cell.timestamp_unix_ms)
            });
            Some(Window {
                protocol: first.protocol,
                target_id: first.target_id.clone(),
                comparison_set: first.comparison_set.clone(),
                destination_class: first.destination_class,
                topology: first.topology,
                onset_unix_ms: onset,
                recovery_unix_ms: recovery,
            })
        })
        .collect()
}

fn analyze(protocols: &[Protocol], cells: &[CellResult]) -> Vec<Observation> {
    let mut ticks: BTreeMap<u32, Vec<&CellResult>> = BTreeMap::new();
    for cell in cells {
        ticks.entry(cell.tick).or_default().push(cell);
    }
    let mut output = Vec::new();
    for (tick, values) in ticks {
        if values
            .iter()
            .any(|cell| matches!(cell.verdict, Verdict::Unknown | Verdict::Error))
        {
            output.push(observation(
                tick,
                ObservationKind::Indeterminate,
                None,
                None,
                &[],
                &[],
                "required evidence is unknown or error",
            ));
            continue;
        }
        for protocol in protocols {
            let mut affected = Vec::new();
            let mut qualified_classes = BTreeSet::new();
            for class in values
                .iter()
                .map(|cell| cell.destination_class)
                .collect::<BTreeSet<_>>()
            {
                let candidates = values
                    .iter()
                    .copied()
                    .filter(|cell| cell.protocol == *protocol && cell.destination_class == class)
                    .collect::<Vec<_>>();
                let topologies = candidates
                    .iter()
                    .map(|cell| cell.topology)
                    .collect::<BTreeSet<_>>();
                let impaired = candidates
                    .iter()
                    .all(|cell| matches!(cell.verdict, Verdict::Blocked | Verdict::Throttled));
                let alternatives = candidates.iter().all(|cell| {
                    values.iter().any(|other| {
                        other.target_id == cell.target_id
                            && other.protocol != *protocol
                            && other.verdict == Verdict::Ok
                    })
                });
                if topologies
                    == BTreeSet::from([Topology::SingleIpDualRole, Topology::SplitHopIngress])
                    && impaired
                    && alternatives
                {
                    qualified_classes.insert(class);
                    affected.extend(candidates);
                }
            }
            if qualified_classes.len() >= 2 {
                output.push(observation(tick, ObservationKind::ProtocolSpecific, Some(*protocol), None, &affected, &affected, "one protocol is impaired across both topologies in at least two destination classes while another remains healthy"));
            }
        }
        let classes = values
            .iter()
            .map(|cell| cell.destination_class)
            .collect::<BTreeSet<_>>();
        for class in &classes {
            let affected = values
                .iter()
                .copied()
                .filter(|cell| cell.destination_class == *class)
                .collect::<Vec<_>>();
            let blocked = affected.len() >= protocols.len() * 2
                && affected.iter().all(|cell| cell.verdict == Verdict::Blocked);
            let control_class = classes.iter().any(|other| {
                other != class
                    && values
                        .iter()
                        .filter(|cell| cell.destination_class == *other)
                        .all(|cell| cell.verdict.usable())
            });
            if blocked && control_class {
                output.push(observation(
                    tick,
                    ObservationKind::DestinationClassWideCollateral,
                    None,
                    Some(*class),
                    &affected,
                    &affected,
                    "all protocols are blocked across both topologies in one destination class",
                ));
            }
        }
        let mut matched = Vec::new();
        let mut matched_classes = BTreeSet::new();
        for set in values
            .iter()
            .map(|cell| cell.comparison_set.as_str())
            .collect::<BTreeSet<_>>()
        {
            let dual = values
                .iter()
                .copied()
                .filter(|cell| {
                    cell.comparison_set == set && cell.topology == Topology::SingleIpDualRole
                })
                .collect::<Vec<_>>();
            let split = values
                .iter()
                .copied()
                .filter(|cell| {
                    cell.comparison_set == set && cell.topology == Topology::SplitHopIngress
                })
                .collect::<Vec<_>>();
            if dual.len() == protocols.len()
                && split.len() == protocols.len()
                && dual.iter().all(|cell| cell.verdict == Verdict::Blocked)
                && split.iter().all(|cell| cell.verdict.usable())
            {
                matched_classes.insert(dual[0].destination_class);
                matched.extend(dual.into_iter().chain(split));
            }
        }
        if matched_classes.len() >= 2 {
            output.push(observation(
                tick,
                ObservationKind::DualRoleTargetingCandidate,
                None,
                None,
                &matched,
                &matched,
                "single-IP targets are blocked while matched split-hop targets remain usable",
            ));
        }
    }
    output
}

fn observation(
    tick: u32,
    kind: ObservationKind,
    protocol: Option<Protocol>,
    class: Option<DestinationClass>,
    sets: &[&CellResult],
    targets: &[&CellResult],
    reason: &str,
) -> Observation {
    Observation {
        tick,
        kind,
        protocol,
        destination_class: class,
        comparison_sets: sets
            .iter()
            .map(|cell| cell.comparison_set.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect(),
        evidence_target_ids: targets
            .iter()
            .map(|cell| cell.target_id.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect(),
        reason: reason.to_string(),
    }
}

fn parse_duration(value: &str) -> Result<Duration> {
    let value = value.trim();
    let split = value
        .find(|character: char| !character.is_ascii_digit())
        .unwrap_or(value.len());
    let (number, unit) = value.split_at(split);
    let number: u64 = number.parse().context("duration must start with digits")?;
    let multiplier = match unit {
        "" | "s" => 1,
        "m" => 60,
        "h" => 3_600,
        "d" => 86_400,
        _ => return Err(anyhow!("unknown duration unit")),
    };
    Ok(Duration::from_secs(number.saturating_mul(multiplier)))
}

fn write_report(report: &MatrixReport, path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temporary = path.with_extension("json.tmp");
    std::fs::write(&temporary, report_to_json(report)?)?;
    std::fs::rename(temporary, path)?;
    Ok(())
}

fn explain(
    ctx: &Context,
    config: &MatrixConfig,
    duration: Duration,
    interval: Duration,
    path: &Path,
) {
    let ticks = duration.as_secs().div_ceil(interval.as_secs());
    println!("# vpnd probe-matrix would orchestrate:");
    println!("  vantage: {}", config.vantage);
    println!("  config: {}", path.display());
    println!("  ticks: {ticks}");
    println!("  protocols: {}", config.protocols.len());
    println!("  targets: {}", config.targets.len());
    println!(
        "  target ids: {}",
        config
            .targets
            .iter()
            .map(|target| target.id.as_str())
            .collect::<Vec<_>>()
            .join(", ")
    );
    let path = path.to_string_lossy();
    let command = make::target_with(
        ctx,
        "probe-matrix-cell",
        &[
            ("MATRIX_CONFIG", &path),
            ("TARGET_ID", "<target-id>"),
            ("PROTOCOL", "<protocol>"),
            ("CONTROL_VERDICT", "<verdict>"),
        ],
    );
    println!("  {}", command.explain());
}

fn ms(duration: Duration) -> u64 {
    u64::try_from(duration.as_millis()).unwrap_or(u64::MAX)
}

fn unix_ms(time: SystemTime) -> u64 {
    time.duration_since(UNIX_EPOCH).map(ms).unwrap_or(0)
}

#[doc(hidden)]
pub fn synthetic_report_for_snapshot() -> MatrixReport {
    let started = 1_700_000_000_000;
    let protocols = [Protocol::Mtproto, Protocol::XhttpVless, Protocol::TcpTrojan];
    let targets = [
        (
            "allow-dual",
            "allow-pair",
            DestinationClass::Allowlist,
            Topology::SingleIpDualRole,
        ),
        (
            "allow-split",
            "allow-pair",
            DestinationClass::Allowlist,
            Topology::SplitHopIngress,
        ),
        (
            "nonallow-dual",
            "nonallow-pair",
            DestinationClass::NonAllowlist,
            Topology::SingleIpDualRole,
        ),
        (
            "nonallow-split",
            "nonallow-pair",
            DestinationClass::NonAllowlist,
            Topology::SplitHopIngress,
        ),
    ];
    let mut cells = Vec::new();
    for tick in 0..2 {
        for protocol in protocols {
            for (id, set, class, topology) in targets {
                let verdict = if tick == 1 && topology == Topology::SingleIpDualRole {
                    Verdict::Blocked
                } else {
                    Verdict::Ok
                };
                cells.push(CellResult {
                    tick,
                    timestamp_unix_ms: started + u64::from(tick) * 300_000,
                    protocol,
                    target_id: id.to_string(),
                    comparison_set: set.to_string(),
                    destination_class: class,
                    topology,
                    verdict,
                    rtt_ms: verdict.usable().then_some(42),
                    error_kind: None,
                });
            }
        }
    }
    MatrixReport {
        schema_version: 2,
        vantage: "synthetic".to_string(),
        started_at_unix_ms: started,
        finished_at_unix_ms: started + 600_000,
        poll_interval_seconds: 300,
        controls: (0..2)
            .map(|tick| ControlResult {
                tick,
                timestamp_unix_ms: started + u64::from(tick) * 300_000,
                verdict: Verdict::Ok,
                rtt_ms: Some(20),
                error_kind: None,
                sweep_duration_ms: 50,
                overrun_ms: 0,
            })
            .collect(),
        windows: windows(&cells),
        observations: analyze(&protocols, &cells),
        cells,
    }
}

#[doc(hidden)]
pub fn report_to_json(report: &MatrixReport) -> Result<String, serde_json::Error> {
    serde_json::to_string_pretty(report)
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn matrix_cells(
        verdict: impl Fn(Protocol, DestinationClass, Topology) -> Verdict,
    ) -> (Vec<Protocol>, Vec<CellResult>) {
        let protocols = vec![Protocol::Mtproto, Protocol::XhttpVless];
        let classes = [
            DestinationClass::Allowlist,
            DestinationClass::Neutral,
            DestinationClass::NonAllowlist,
        ];
        let mut cells = Vec::new();
        for (index, class) in classes.into_iter().enumerate() {
            for topology in [Topology::SingleIpDualRole, Topology::SplitHopIngress] {
                for protocol in &protocols {
                    cells.push(CellResult {
                        tick: 0,
                        timestamp_unix_ms: 1,
                        protocol: *protocol,
                        target_id: format!(
                            "target-{index}-{}",
                            if topology == Topology::SingleIpDualRole {
                                "dual"
                            } else {
                                "split"
                            }
                        ),
                        comparison_set: format!("pair-{index}"),
                        destination_class: class,
                        topology,
                        verdict: verdict(*protocol, class, topology),
                        rtt_ms: None,
                        error_kind: None,
                    });
                }
            }
        }
        (protocols, cells)
    }

    #[test]
    fn paired_targets_are_required() {
        let config = MatrixConfig {
            schema_version: 2,
            vantage: "filtered-path-a".to_string(),
            poll_interval_seconds: Some(300),
            control: ControlConfig {
                url: "https://control.example/probe".to_string(),
                expected_status: 204,
                timeout_seconds: 15,
                degraded_after_ms: 3000,
            },
            protocols: vec![Protocol::Mtproto],
            targets: vec![Target {
                id: "only-dual".to_string(),
                comparison_set: "pair-a".to_string(),
                destination_class: DestinationClass::Neutral,
                topology: Topology::SingleIpDualRole,
                profile_file: PathBuf::from("/tmp/profile.json"),
            }],
        };
        assert!(validate_config(&config).is_err());
    }

    #[test]
    fn paired_profiles_require_matching_transport_parameters() {
        let directory = tempfile::TempDir::new().unwrap();
        let profile = |id: &str, port: u16| {
            serde_json::json!({
                "schema_version": 1,
                "target_id": id,
                "endpoint": "192.0.2.1",
                "expected_xray_version": "v26.3.27",
                "expected_mtg_version": "v2.2.8",
                "expected_mtproto_helper_version": "gotd-v0.160.0",
                "protocols": {"mtproto": {"port": port, "secret": id}}
            })
        };
        let mut targets = Vec::new();
        for (id, topology, port) in [
            ("pair-dual", Topology::SingleIpDualRole, 10443),
            ("pair-split", Topology::SplitHopIngress, 10444),
        ] {
            let path = directory.path().join(format!("{id}.json"));
            std::fs::write(&path, serde_json::to_vec(&profile(id, port)).unwrap()).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
            targets.push(Target {
                id: id.to_string(),
                comparison_set: "pair".to_string(),
                destination_class: DestinationClass::Neutral,
                topology,
                profile_file: path,
            });
        }
        let config = MatrixConfig {
            schema_version: 2,
            vantage: "filtered-path-a".to_string(),
            poll_interval_seconds: Some(300),
            control: ControlConfig {
                url: "https://control.example/probe".to_string(),
                expected_status: 204,
                timeout_seconds: 15,
                degraded_after_ms: 3000,
            },
            protocols: vec![Protocol::Mtproto],
            targets,
        };
        assert!(validate_profiles(&config).is_err());
    }

    #[tokio::test]
    async fn concurrent_collection_is_ordered_and_isolates_timeout() {
        let started = tokio::time::Instant::now();
        let mut jobs = JoinSet::new();
        jobs.spawn(async {
            tokio::time::sleep(Duration::from_millis(80)).await;
            (0, "slow")
        });
        jobs.spawn(async {
            let value = tokio::time::timeout(
                Duration::from_millis(20),
                tokio::time::sleep(Duration::from_millis(200)),
            )
            .await
            .map(|_| "unexpected")
            .unwrap_or("timeout");
            (1, value)
        });
        jobs.spawn(async {
            tokio::time::sleep(Duration::from_millis(10)).await;
            (2, "fast")
        });
        assert_eq!(
            collect_ordered(jobs).await.unwrap(),
            ["slow", "timeout", "fast"]
        );
        assert!(started.elapsed() < Duration::from_millis(150));
    }

    #[test]
    fn fixed_rate_schedule_does_not_accumulate_sweep_time() {
        let started = tokio::time::Instant::now();
        assert_eq!(
            scheduled_tick(started, Duration::from_secs(5), 3).duration_since(started),
            Duration::from_secs(15)
        );
    }

    #[test]
    fn synthetic_report_detects_dual_role_candidate() {
        let report = synthetic_report_for_snapshot();
        assert_eq!(report.schema_version, 2);
        assert!(report
            .observations
            .iter()
            .any(|item| item.kind == ObservationKind::DualRoleTargetingCandidate));
    }

    #[test]
    fn analyzer_detects_protocol_specific_in_two_of_three_classes() {
        let (protocols, cells) = matrix_cells(|protocol, class, _| {
            if protocol == Protocol::Mtproto && class != DestinationClass::NonAllowlist {
                Verdict::Blocked
            } else {
                Verdict::Ok
            }
        });
        assert!(analyze(&protocols, &cells)
            .iter()
            .any(|item| item.kind == ObservationKind::ProtocolSpecific
                && item.protocol == Some(Protocol::Mtproto)));
    }

    #[test]
    fn analyzer_detects_destination_class_collateral() {
        let (protocols, cells) = matrix_cells(|_, class, _| {
            if class == DestinationClass::Neutral {
                Verdict::Blocked
            } else {
                Verdict::Ok
            }
        });
        assert!(analyze(&protocols, &cells).iter().any(|item| item.kind
            == ObservationKind::DestinationClassWideCollateral
            && item.destination_class == Some(DestinationClass::Neutral)));
    }

    #[test]
    fn unknown_evidence_is_indeterminate_and_suppresses_positive_results() {
        let (protocols, cells) = matrix_cells(|protocol, class, topology| {
            if protocol == Protocol::Mtproto
                && class == DestinationClass::Neutral
                && topology == Topology::SingleIpDualRole
            {
                Verdict::Unknown
            } else {
                Verdict::Blocked
            }
        });
        let observations = analyze(&protocols, &cells);
        assert_eq!(observations.len(), 1);
        assert_eq!(observations[0].kind, ObservationKind::Indeterminate);
    }
}
