use clap::{Args, Parser, Subcommand, ValueEnum};

#[derive(Parser, Debug)]
#[command(
    name = "vpnd",
    version,
    about = "Convenience CLI for vpn-deploy (wraps Make / Terraform / Ansible / SOPS)",
    long_about = None,
)]
pub struct Cli {
    /// Print the underlying shell invocations and exit without running them.
    #[arg(long, global = true)]
    pub explain: bool,

    /// Target environment.
    #[arg(long, short = 'e', global = true, env = "VPN_ENV", default_value = "prod")]
    pub env: String,

    /// Cloud provider Terraform root.
    #[arg(long, short = 'p', global = true, env = "VPN_PROVIDER", default_value = "upcloud")]
    pub provider: String,

    /// Skip interactive confirmation prompts.
    #[arg(long, short = 'y', global = true)]
    pub yes: bool,

    /// Emit machine-readable JSON instead of human output (where supported).
    #[arg(long, global = true)]
    pub json: bool,

    /// Override the vpn-deploy repo root (default: discover from cwd).
    #[arg(long, global = true, env = "VPN_DEPLOY_ROOT")]
    pub root: Option<std::path::PathBuf>,

    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    /// Interactive deploy wizard.
    Deploy(DeployArgs),
    /// Idempotent re-deploy against existing host(s).
    Reconverge(ReconvergeArgs),
    /// Bundled recipient handoff (URL + QR + sing-box + app cards).
    Share(ShareArgs),
    /// Diagnostic bundle.
    Doctor(DoctorArgs),
    /// Profile-aware probing.
    Probe(ProbeArgs),
    /// Multi-protocol simultaneity DPI probe across a configured matrix.
    ProbeMatrix(ProbeMatrixArgs),
    /// Pre-deploy guards (spot-check, certs, perms, render, schema).
    Preflight(PreflightArgs),
    /// Fleet-wide operations.
    Fleet(FleetArgs),
    /// Local host registry.
    Host(HostArgs),
    /// Machine-readable docs endpoints for AI assistants.
    AiDocs(AiDocsArgs),
    /// Check for a newer vpnd release on GitHub (cached 24 h).
    Update(UpdateArgs),
    /// Emit shell completions to stdout.
    Completions(CompletionsArgs),
}

#[derive(Args, Debug)]
pub struct DeployArgs {
    /// Skip running pre-deploy guards (mirrors `SKIP_PRECHECK=1`).
    #[arg(long)]
    pub skip_precheck: bool,
    /// Tag a known-good commit after a successful verify run.
    #[arg(long)]
    pub tag_on_success: bool,
}

#[derive(Args, Debug)]
pub struct ReconvergeArgs {
    /// Limit to a single host from the registry.
    #[arg(long)]
    pub host: Option<String>,
    /// Stop after dry-run; do not apply.
    #[arg(long)]
    pub dry_run: bool,
}

#[derive(Args, Debug)]
pub struct ShareArgs {
    /// Client name.
    pub client: String,
    /// Also emit a QR code image.
    #[arg(long)]
    pub qr: bool,
    /// QR payload type.
    #[arg(long, value_enum, default_value_t = ShareType::Singbox)]
    pub r#type: ShareType,
    /// Output directory for generated artifacts (default: ./share/<client>/).
    #[arg(long)]
    pub out: Option<std::path::PathBuf>,
    /// Opaque subscription token from `make issue-sub-token CLIENT=<c> --print-token-only`.
    /// If omitted, the URL falls back to the (enumerable) client name.
    #[arg(long)]
    pub token: Option<String>,
}

#[derive(ValueEnum, Clone, Copy, Debug)]
pub enum ShareType {
    Singbox,
    Uri,
}

#[derive(Args, Debug)]
pub struct DoctorArgs {
    /// Host alias from the registry; omitted = active env's primary host.
    #[arg(long)]
    pub host: Option<String>,
    /// Format output as a clipboard-ready prompt for an AI assistant.
    #[arg(long)]
    pub ai: bool,
    /// Copy AI prompt to the system clipboard (requires --ai).
    #[arg(long)]
    pub clip: bool,
    /// Pack a diagnostic gzip-tar bundle at this path (orthogonal to --ai).
    #[arg(long)]
    pub bundle: Option<std::path::PathBuf>,
}

#[derive(Args, Debug)]
pub struct ProbeArgs {
    /// Host alias from the registry; omitted = active env's primary host.
    #[arg(long)]
    pub host: Option<String>,
    /// Which profile to probe.
    #[arg(long, value_enum, default_value_t = Profile::All)]
    pub profile: Profile,
}

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum Profile {
    P0,
    P1,
    P2,
    All,
}

#[derive(Args, Debug)]
pub struct ProbeMatrixArgs {
    /// Run duration. Accepts plain seconds or NN{s,m,h,d}.
    #[arg(long, default_value = "4h")]
    pub duration: String,
    /// Poll interval between matrix sweeps (seconds). Overrides config.
    #[arg(long)]
    pub poll_interval_seconds: Option<u64>,
    /// Path to the matrix config YAML. Default: <root>/vpnd/config/probe-matrix.yaml.
    #[arg(long)]
    pub config: Option<std::path::PathBuf>,
    /// Output path for the report JSON. Default: <root>/vpnd/state/probe-matrix-<unix-ms>.json.
    #[arg(long)]
    pub output: Option<std::path::PathBuf>,
}

#[derive(Args, Debug)]
pub struct PreflightArgs {
    /// Skip the certificate-validity check (faster smoke).
    #[arg(long)]
    pub skip_certs: bool,
}

#[derive(Args, Debug)]
pub struct FleetArgs {
    #[command(subcommand)]
    pub action: FleetAction,
}

#[derive(Subcommand, Debug)]
pub enum FleetAction {
    /// Summary table across every host:env pair.
    Status,
    /// Coordinated rotation across the fleet (`scripts/fleet-rotate.sh`).
    Rotate {
        /// Path to the fleet plan YAML.
        #[arg(long)]
        plan: std::path::PathBuf,
        /// Resume a partially-completed rotation.
        #[arg(long)]
        resume: bool,
        /// Show what would happen without making changes.
        #[arg(long)]
        dry_run: bool,
    },
    /// Diff fleet state against the last known-good tag.
    Drift,
}

#[derive(Args, Debug)]
pub struct HostArgs {
    #[command(subcommand)]
    pub action: HostAction,
}

#[derive(Subcommand, Debug)]
pub enum HostAction {
    /// List registered hosts.
    List,
    /// Show one host record.
    Show {
        name: String,
    },
    /// Add a host record.
    Add {
        name: String,
        #[arg(long)]
        env: String,
        #[arg(long)]
        provider: String,
        #[arg(long)]
        ipv4: Option<String>,
        #[arg(long)]
        ipv6: Option<String>,
    },
    /// Remove a host record.
    Remove {
        name: String,
    },
}

#[derive(Args, Debug)]
pub struct AiDocsArgs {
    /// Output directory (default: ./ai-docs/).
    #[arg(long)]
    pub out: Option<std::path::PathBuf>,
}

#[derive(Args, Debug, Clone)]
pub struct UpdateArgs {
    /// Print the GitHub API URL that would be queried and exit without fetching.
    #[arg(long)]
    pub explain: bool,
}

#[derive(Args, Debug, Clone)]
pub struct CompletionsArgs {
    /// Shell to generate completions for: bash, zsh, fish, powershell.
    pub shell: String,
}
