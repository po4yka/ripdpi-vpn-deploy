use anyhow::Result;
use clap::Parser;
use std::process::ExitCode;
use tokio::signal::unix::{signal, SignalKind};

use vpnd::{cli, commands, config};

#[tokio::main]
async fn main() -> ExitCode {
    init_tracing();
    let cli = cli::Cli::parse();
    let outcome: Result<ExitCode> = async {
        // Interactive commands keep default signal behavior: a synchronous
        // stdin read or prompt would prevent this select from being polled.
        if !matches!(&cli.command, cli::Command::Doctor(_)) {
            return execute(cli).await.map(|()| ExitCode::SUCCESS);
        }
        // Doctor owns captured process groups but has no durable output to
        // flush. ProbeMatrix installs its listener inside the command so it
        // can persist an interrupted checkpoint before returning.
        let mut interrupt = signal(SignalKind::interrupt())?;
        let mut terminate = signal(SignalKind::terminate())?;
        tokio::select! {
            biased;
            _ = interrupt.recv() => Ok(ExitCode::from(130)),
            _ = terminate.recv() => Ok(ExitCode::from(143)),
            result = execute(cli) => result.map(|()| ExitCode::SUCCESS),
        }
    }
    .await;
    match outcome {
        Ok(code) => code,
        Err(error) => {
            eprintln!("Error: {error:#}");
            error
                .downcast_ref::<commands::probe_matrix::Interrupted>()
                .map_or(ExitCode::FAILURE, |interrupted| {
                    ExitCode::from(interrupted.exit_code())
                })
        }
    }
}

async fn execute(cli: cli::Cli) -> Result<()> {
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
