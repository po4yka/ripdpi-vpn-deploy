use anyhow::Result;
use owo_colors::OwoColorize;

use crate::cli::DeployArgs;
use crate::config::Context;
use crate::runner::{make, Cmd};
use crate::wizard::{confirm, section, Summary};

pub async fn run(ctx: &Context, args: DeployArgs) -> Result<()> {
    section(
        "Deploy wizard",
        "Bundles: validate → decrypt → plan → apply → inventory → wait → preflight → site → verify.",
    );

    let mut s = Summary::new("Deploy plan");
    s.add("env", &ctx.env)
        .add("provider", &ctx.provider)
        .add("repo", ctx.root.display().to_string())
        .add("sops file", ctx.sops_file.display().to_string())
        .add("secrets file", ctx.secrets_file.display().to_string())
        .add(
            "skip precheck",
            if args.skip_precheck { "yes" } else { "no" },
        )
        .add(
            "tag on success",
            if args.tag_on_success { "yes" } else { "no" },
        );
    s.render();

    if !ctx.yes && !ctx.explain && !confirm("Proceed with these settings?", true)? {
        eprintln!("{}", "aborted by user".yellow());
        return Ok(());
    }

    // Order matches the Makefile pipeline, so `--explain` is the README of the deploy flow.
    let steps: Vec<Cmd> = vec![
        make::target(ctx, "check-prereqs"),
        make::target(ctx, "validate"),
        make::target(ctx, "decrypt"),
        make::target(ctx, "init"),
        make::target(ctx, "plan"),
        make::target(ctx, "apply"),
        make::target(ctx, "inventory"),
        make::target(ctx, "wait"),
    ];

    let deploy_step = if args.skip_precheck {
        make::target_with(ctx, "deploy", &[("SKIP_PRECHECK", "1")])
    } else {
        make::target(ctx, "deploy")
    };

    let verify_step = if args.tag_on_success {
        make::target_with(ctx, "verify", &[("TAG_ON_SUCCESS", "1")])
    } else {
        make::target(ctx, "verify")
    };

    let mut all = steps;
    all.push(deploy_step);
    all.push(verify_step);
    all.push(make::target(ctx, "smoke-test"));
    all.push(make::target(ctx, "clean"));

    for cmd in &all {
        cmd.run(ctx.explain).await?;
    }

    if !ctx.explain {
        success_summary(ctx);
    }
    Ok(())
}

fn success_summary(ctx: &Context) {
    println!();
    println!("{}", "Deploy complete.".green().bold());
    println!();
    println!(
        "  active profiles:  P0 REALITY, P1 nginx-xhttp, P2 hysteria + amneziawg (per group_vars)"
    );
    println!("  env:              {}", ctx.env);
    println!("  provider:         {}", ctx.provider);
    println!();
    println!("  next:");
    println!(
        "    {} share a client: {}",
        "▸".cyan(),
        "vpnd share <name> --qr".bold()
    );
    println!(
        "    {} diagnose:       {}",
        "▸".cyan(),
        "vpnd doctor".bold()
    );
    println!(
        "    {} re-deploy:      {}",
        "▸".cyan(),
        "vpnd reconverge".bold()
    );
    println!();
    println!(
        "  runbooks: docs/RUNBOOK-deploy.md, docs/RUNBOOK-rollback.md, docs/RUNBOOK-incident.md"
    );
}
