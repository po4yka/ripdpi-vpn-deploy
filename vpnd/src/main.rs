use anyhow::Result;
use clap::Parser;

use vpnd::{cli, commands, config};

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();

    let cli = cli::Cli::parse();

    // Completions and update --explain don't need a repo root.
    match &cli.command {
        cli::Command::Completions(args) => return commands::completions::run(args.clone()),
        cli::Command::Update(args) if args.explain || cli.explain => {
            println!("# vpnd update would query:");
            println!("  GET https://api.github.com/repos/po4yka/vpn-deploy/releases/latest");
            return Ok(());
        }
        _ => {}
    }

    let ctx = config::Context::discover(&cli)?;

    match cli.command {
        cli::Command::Deploy(args) => commands::deploy::run(&ctx, args).await,
        cli::Command::Reconverge(args) => commands::reconverge::run(&ctx, args).await,
        cli::Command::Share(args) => commands::share::run(&ctx, args).await,
        cli::Command::Doctor(args) => commands::doctor::run(&ctx, args).await,
        cli::Command::Probe(args) => commands::probe::run(&ctx, args).await,
        cli::Command::ProbeMatrix(args) => commands::probe_matrix::run(&ctx, args).await,
        cli::Command::Preflight(args) => commands::preflight::run(&ctx, args).await,
        cli::Command::Fleet(args) => commands::fleet::run(&ctx, args).await,
        cli::Command::Host(args) => commands::host::run(&ctx, args).await,
        cli::Command::AiDocs(args) => commands::ai_docs::run(&ctx, args).await,
        cli::Command::Update(args) => commands::update::run(&ctx, args).await,
        cli::Command::Completions(args) => commands::completions::run(args),
    }
}

fn init_tracing() {
    use tracing_subscriber::{fmt, EnvFilter};
    let filter = EnvFilter::try_from_env("VPND_LOG").unwrap_or_else(|_| EnvFilter::new("warn"));
    fmt().with_env_filter(filter).with_target(false).without_time().with_writer(std::io::stderr).init();
}
