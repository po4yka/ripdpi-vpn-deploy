use anyhow::Result;
use owo_colors::OwoColorize;

use crate::cli::DeployArgs;
use crate::config::Context;
use crate::runner::{make, Cmd};
use crate::wizard::{confirm, section, Summary};

/// Ordered make targets mirroring the Makefile pipeline, so `--explain` is
/// the README of the deploy flow.
fn plan_steps(ctx: &Context, args: &DeployArgs) -> Vec<Cmd> {
    let mut steps: Vec<Cmd> = vec![
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

    steps.push(deploy_step);
    steps.push(verify_step);
    steps.push(make::target(ctx, "smoke-test"));
    steps.push(make::target(ctx, "clean"));
    steps
}

fn build_plan_summary(ctx: &Context, args: &DeployArgs) -> Summary {
    let mut s = Summary::new("Deploy plan");
    // Fixed placeholders, never filesystem paths: the summary is the
    // operator-facing panel and must not echo secret-file locations.
    s.add("env", &ctx.env)
        .add("provider", &ctx.provider)
        .add("repo", "<checkout root>")
        .add("sops file", "(sops-managed store)")
        .add("secrets file", "(runtime plaintext — never logged)")
        .add(
            "skip precheck",
            if args.skip_precheck { "yes" } else { "no" },
        )
        .add(
            "tag on success",
            if args.tag_on_success { "yes" } else { "no" },
        );
    s
}

pub async fn run(ctx: &Context, args: DeployArgs) -> Result<()> {
    section(
        "Deploy wizard",
        "Bundles: validate → decrypt → plan → apply → inventory → wait → preflight → site → verify.",
    );

    build_plan_summary(ctx, &args).render();

    if !ctx.yes && !ctx.explain && !confirm("Proceed with these settings?", true)? {
        eprintln!("{}", "aborted by user".yellow());
        return Ok(());
    }

    // Any step failure triggers best-effort plaintext-secrets cleanup
    // before the original error surfaces.
    let steps = plan_steps(ctx, &args);
    let outcome: Result<()> = async {
        for cmd in &steps {
            cmd.run(ctx.explain).await?;
        }
        Ok(())
    }
    .await;
    super::finish_or_cleanup(ctx, outcome).await?;

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

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    fn fake_ctx() -> Context {
        use std::path::PathBuf;
        Context {
            root: PathBuf::from("/repo"),
            ansible_dir: PathBuf::from("/repo/ansible"),
            tf_root: PathBuf::from("/repo/terraform/providers/upcloud"),
            env: "prod".into(),
            provider: "upcloud".into(),
            sops_file: PathBuf::from("/config/prod.secrets.sops.yaml"),
            secrets_file: PathBuf::from("/tmp/vpn-prod.secrets.yaml"),
            config_dir: PathBuf::from("/config"),
            explain: true,
            yes: true,
            json: false,
        }
    }

    fn target_names(ctx: &Context, args: &DeployArgs) -> Vec<String> {
        plan_steps(ctx, args)
            .iter()
            .map(|cmd| cmd.explain())
            .collect()
    }

    #[test]
    fn pipeline_matches_makefile_order_and_ends_with_clean() {
        let ctx = fake_ctx();
        let args = DeployArgs {
            skip_precheck: false,
            tag_on_success: false,
        };
        let rendered = target_names(&ctx, &args);
        let expected = [
            "check-prereqs",
            "validate",
            "decrypt",
            "init",
            "plan",
            "apply",
            "inventory",
            "wait",
            "deploy",
            "verify",
            "smoke-test",
            "clean",
        ];
        assert_eq!(rendered.len(), expected.len(), "step count drifted");
        for (rendered_step, expected_step) in rendered.iter().zip(expected.iter()) {
            assert!(
                rendered_step.contains(&format!("make {expected_step} ")),
                "expected make {expected_step} in step: {rendered_step}"
            );
        }
        assert!(rendered.last().expect("steps").contains("make clean"));
    }

    #[test]
    fn skip_precheck_and_tag_on_success_flow_into_their_targets() {
        let ctx = fake_ctx();
        let args = DeployArgs {
            skip_precheck: true,
            tag_on_success: true,
        };
        let rendered = target_names(&ctx, &args);
        let deploy = rendered
            .iter()
            .find(|s| s.contains("make deploy "))
            .expect("deploy step");
        assert!(deploy.contains("SKIP_PRECHECK=1"), "{deploy}");
        let verify = rendered
            .iter()
            .find(|s| s.contains("make verify "))
            .expect("verify step");
        assert!(verify.contains("TAG_ON_SUCCESS=1"), "{verify}");
    }

    /// The plan summary is the operator-facing panel: it must render
    /// fixed placeholders, never filesystem paths or secrets filenames.
    #[test]
    fn plan_summary_renders_placeholders_not_paths() {
        let dir = tempfile::tempdir().unwrap();
        let mut ctx = fake_ctx();
        ctx.root = dir.path().into();
        ctx.sops_file = std::path::PathBuf::from("/deep/nested/prod.secrets.sops.yaml");
        ctx.secrets_file = std::path::PathBuf::from("/runtime/vpn-prod.secrets.yaml");

        let args = DeployArgs {
            skip_precheck: false,
            tag_on_success: true,
        };
        let summary = build_plan_summary(&ctx, &args);
        assert!(!summary.rows().is_empty());
        for (_key, value) in summary.rows() {
            assert!(
                !value.contains('/') && !value.contains(".yaml"),
                "summary row leaks a path-like value: {value}"
            );
        }
    }
}
