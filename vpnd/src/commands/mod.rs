use anyhow::Result;
use owo_colors::OwoColorize;

use crate::config::Context;
use crate::state::Registry;

pub mod ai_docs;
pub mod completions;
pub mod deploy;
pub mod doctor;
pub mod fleet;
pub mod host;
pub mod preflight;
pub mod probe;
pub mod probe_matrix;
pub mod reconverge;
pub mod share;
pub mod update;

/// Run secrets cleanup after every pipeline outcome, including dry runs. The
/// ORIGINAL error always takes precedence: cleanup failures are logged,
/// never mask the root cause. Explain mode never executes cleanup, like
/// every other step.
pub(crate) async fn finish_with_cleanup(ctx: &Context, outcome: Result<()>) -> Result<()> {
    let cleanup = crate::runner::make::target(ctx, "clean")
        .run(ctx.explain)
        .await;
    match outcome {
        Err(err) => {
            eprintln!(
                "{} pipeline failed — attempted secrets cleanup (make clean)",
                "error:".red().bold()
            );
            if let Err(cleanup_err) = cleanup {
                eprintln!("{} cleanup also failed: {cleanup_err}", "warn:".yellow());
            }
            Err(err)
        }
        Ok(()) => cleanup.map(|_| ()),
    }
}

/// Validate an optional `--host` alias against the loaded registry with
/// env/provider matching. Unknown or cross-env aliases fail before any
/// command runs; `None` is always fine.
pub(crate) fn ensure_host_in_registry(
    ctx: &Context,
    reg: &Registry,
    host: Option<&String>,
) -> Result<()> {
    let Some(name) = host else {
        return Ok(());
    };
    reg.resolve_for(name, &ctx.env, &ctx.provider)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;
    use crate::state::Host;

    fn ctx_in(dir: &std::path::Path, explain: bool) -> Context {
        Context {
            root: dir.into(),
            ansible_dir: dir.into(),
            tf_root: dir.into(),
            env: "prod".into(),
            provider: "upcloud".into(),
            sops_file: dir.join("sops.yaml"),
            secrets_file: dir.join("vpn-prod.secrets.yaml"),
            config_dir: dir.into(),
            explain,
            yes: true,
            json: false,
        }
    }

    /// Failure-injection proof for the cleanup contract:
    ///   * a failed middle step still runs best-effort cleanup AFTER the
    ///     failure (sentinel file written by the stub `clean` target),
    ///   * the ORIGINAL step error is surfaced even when cleanup itself
    ///     exits nonzero.
    #[tokio::test]
    async fn cleanup_runs_after_failure_and_original_error_wins() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("Makefile"),
            ".PHONY: clean\nclean:\n\t@echo cleaned >> stamp\n\t@exit 7\n",
        )
        .unwrap();
        let ctx = ctx_in(dir.path(), false);

        let outcome: Result<()> = async {
            for program in ["true", "false"] {
                crate::runner::Cmd::new(program)
                    .describe(format!("test step: {program}"))
                    .run(false)
                    .await?;
            }
            Ok(())
        }
        .await;

        let err = finish_with_cleanup(&ctx, outcome)
            .await
            .expect_err("failed middle step must propagate");
        assert!(
            err.to_string().contains("exited") || err.to_string().contains("false"),
            "original error must win, got: {err}"
        );
        let stamp = dir.path().join("stamp");
        assert!(
            stamp.is_file(),
            "cleanup sentinel missing — clean never ran"
        );
        assert_eq!(
            std::fs::read_to_string(stamp).unwrap().trim(),
            "cleaned",
            "cleanup must run after the failure, not before"
        );
    }

    #[tokio::test]
    async fn successful_pipeline_requires_successful_cleanup() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("Makefile"), "clean:\n\t@exit 7\n").unwrap();
        let ctx = ctx_in(dir.path(), false);
        let err = finish_with_cleanup(&ctx, Ok(()))
            .await
            .expect_err("cleanup failure must fail the command");
        assert!(err.to_string().contains("make clean"));
    }

    #[test]
    fn ensure_host_rejects_unknown_alias_and_accepts_match() {
        let dir = tempfile::tempdir().unwrap();
        let ctx = ctx_in(dir.path(), false);
        let mut reg = Registry::default();
        reg.upsert(
            "prod1",
            Host {
                env: "prod".into(),
                provider: "upcloud".into(),
                ipv4: Some("203.0.113.5".into()),
                ipv6: None,
                deployed_with: None,
            },
        );
        assert!(ensure_host_in_registry(&ctx, &reg, Some(&"ghost".to_string())).is_err());
        assert!(ensure_host_in_registry(&ctx, &reg, None).is_ok());
        assert!(ensure_host_in_registry(&ctx, &reg, Some(&"prod1".to_string())).is_ok());
    }
}
