use anyhow::Result;
use clap::Parser;

use vpnd::{cli, commands, config};

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();

    let cli = cli::Cli::parse();

    // Completions doesn't need a repo root — handle it before Context::discover.
    if let cli::Command::Completions(args) = &cli.command {
        return commands::completions::run(args.clone());
    }

    // update --explain also doesn't need a repo root.
    if let cli::Command::Update(args) = &cli.command {
        if args.explain || cli.explain {
            println!("# vpnd update would query:");
            println!("  GET https://api.github.com/repos/po4yka/ripdpi-vpn-deploy/releases/latest");
            return Ok(());
        }
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
    let filter = EnvFilter::try_from_env("VPND_LOG").unwrap_or_else(|e| {
        eprintln!("vpnd: VPND_LOG parse error ({e}); falling back to warn");
        EnvFilter::new("warn")
    });
    fmt()
        .with_env_filter(filter)
        .with_target(false)
        .without_time()
        .with_writer(std::io::stderr)
        .init();
}
