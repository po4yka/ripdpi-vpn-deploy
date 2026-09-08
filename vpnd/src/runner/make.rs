use anyhow::{anyhow, Result};

use crate::config::Context;
use crate::runner::Cmd;

#[cfg(test)]
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
        explain: false,
        yes: false,
        json: false,
    }
}

/// Charset rules for values forwarded into make command-line variable
/// assignments (REQ-MAKE-KV-CHARSET).
///
/// GNU make recursively expands command-line variable values wherever
/// recipes reference them, and several recipes interpolate `$(HOST)`,
/// `$(MATRIX_CONFIG)` or `$(CLIENT)` inside double-quoted shell strings.
/// A value carrying `$(shell …)` would execute there and an unbalanced
/// quote would break out of recipe quoting, so every value is checked
/// against a per-key allowlist at this single construction point and a
/// rejected value aborts the subcommand before anything spawns.
///
/// Call-site audit (key → rule → source):
///
/// | Key | Rule | Source |
/// |---|---|---|
/// | ENV, PROVIDER | identifier | CLI via Context; PROVIDER is directory-checked at discovery, ENV gains explicit validation for defense in depth |
/// | SECRETS_FILE | runtime-path | Context runtime path under XDG_RUNTIME_DIR — may contain spaces, never make/shell metacharacters |
/// | MATRIX_CONFIG, PLAN | path | canonicalized probe-matrix config, canonicalized fleet plan |
/// | HOST | ip-literal | registry-resolved IPv4 from `state::registry::ipv4_limit` |
/// | CLIENT, TARGET_ID | identifier | operator-typed client name, probe-matrix `technical_id` |
/// | any other key | identifier | unknown keys fail closed: RESUME, DRY_RUN, SKIP_PRECHECK, TAG_ON_SUCCESS, PROTOCOL, CONTROL_VERDICT, … |
#[derive(Clone, Copy)]
enum ValueRule {
    /// Non-empty token over `[A-Za-z0-9._-]`.
    Identifier,
    /// Absolute canonical path: leading `/`, charset `[A-Za-z0-9._/-]`, no
    /// `..` component (callers canonicalize before handing a path over).
    Path,
    /// Absolute runtime path (SECRETS_FILE): rejects make/shell
    /// metacharacters (including `#`, which starts a comment in unquoted
    /// recipe expansions) and control characters, tolerates spaces — argv
    /// carries it as one argument and recipes reference it quoted.
    RuntimePath,
    /// Strict dotted-quad IPv4 literal.
    IpLiteral,
}

impl ValueRule {
    fn name(self) -> &'static str {
        match self {
            Self::Identifier => "identifier [A-Za-z0-9._-]",
            Self::Path => "absolute path [A-Za-z0-9._/-] without .. components",
            Self::RuntimePath => "runtime path without make or shell metacharacters",
            Self::IpLiteral => "IPv4 literal",
        }
    }

    fn accepts(self, value: &str) -> bool {
        match self {
            Self::Identifier => {
                !value.is_empty()
                    && value
                        .chars()
                        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
            }
            Self::Path => {
                value.starts_with('/')
                    && value
                        .chars()
                        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '/' | '-'))
                    && !value.split('/').any(|component| component == "..")
            }
            Self::RuntimePath => {
                value.starts_with('/')
                    && value.chars().all(|c| {
                        !c.is_control()
                            && !matches!(
                                c,
                                '$' | '`'
                                    | '"'
                                    | '\''
                                    | ';'
                                    | '|'
                                    | '&'
                                    | '<'
                                    | '>'
                                    | '('
                                    | ')'
                                    | '\\'
                                    | '#'
                            )
                    })
            }
            Self::IpLiteral => value.parse::<std::net::Ipv4Addr>().is_ok(),
        }
    }
}

/// Rule for a make variable key. Unknown keys fail closed with the
/// conservative identifier charset instead of being allowed through.
fn rule_for(key: &str) -> ValueRule {
    match key {
        "HOST" => ValueRule::IpLiteral,
        "SECRETS_FILE" => ValueRule::RuntimePath,
        "MATRIX_CONFIG" | "PLAN" => ValueRule::Path,
        "CLIENT" | "TARGET_ID" | "ENV" | "PROVIDER" => ValueRule::Identifier,
        _ => ValueRule::Identifier,
    }
}

/// Validate one make command-line variable value against its per-key rule
/// (REQ-MAKE-KV-CHARSET). The error names both the key and the failed rule.
/// SECRETS_FILE values are never echoed: the runner's redaction contract
/// forbids logging the secrets-file location.
pub fn validate_kv(key: &str, value: &str) -> Result<()> {
    let rule = rule_for(key);
    if rule.accepts(value) {
        return Ok(());
    }
    let rendered = if key == "SECRETS_FILE" {
        "(redacted)".to_string()
    } else {
        format!("{value:?}")
    };
    Err(anyhow!(
        "refusing to spawn make: variable {key} value {rendered} fails the {} rule — \
         make expands command-line variable values inside recipe shells",
        rule.name()
    ))
}

/// Build a `make <name> ENV=… PROVIDER=… SECRETS_FILE=…` invocation pinned
/// to the repo root. SECRETS_FILE is carried explicitly on every target so
/// recipes that read or produce the decrypted file (decrypt at minimum,
/// audit-log style consumers wherever their recipe references it) resolve
/// the same path vpnd does — no double-decrypt into divergent locations.
///
/// ENV, PROVIDER and SECRETS_FILE pass the per-key allowlist before the
/// invocation is built; a rejected value aborts the subcommand.
pub fn target(ctx: &Context, name: &str) -> Result<Cmd> {
    let secrets = ctx.secrets_file.display().to_string();
    validate_kv("ENV", &ctx.env)?;
    validate_kv("PROVIDER", &ctx.provider)?;
    validate_kv("SECRETS_FILE", &secrets)?;
    Ok(Cmd::new("make")
        .arg(name)
        .arg(format!("ENV={}", ctx.env))
        .arg(format!("PROVIDER={}", ctx.provider))
        .arg(format!("SECRETS_FILE={secrets}"))
        .sensitive(&secrets)
        .sensitive(ctx.sops_file.to_string_lossy())
        .cwd(ctx.root.clone())
        .describe(format!(
            "make {} ENV={} PROVIDER={}",
            name, ctx.env, ctx.provider
        )))
}

/// Build a `make` target with additional `KEY=VALUE` args appended. Every
/// value passes its per-key charset allowlist first; the first failing key
/// aborts the subcommand with an error naming the key and the rule, so no
/// command can ever carry an unvalidated value into a spawned argv.
pub fn target_with(ctx: &Context, name: &str, kvs: &[(&str, &str)]) -> Result<Cmd> {
    for (key, value) in kvs {
        validate_kv(key, value)?;
    }
    let mut cmd = target(ctx, name)?;
    for (key, value) in kvs {
        cmd = cmd.arg(format!("{key}={value}"));
    }
    Ok(cmd)
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    #[test]
    fn target_pushes_env_then_provider_after_name() {
        let ctx = fake_ctx();
        let s = target(&ctx, "deploy").expect("valid ctx").explain();
        let name_pos = s.find("deploy").expect("target name");
        let env_pos = s.find("ENV=prod").expect("ENV=");
        let prov_pos = s.find("PROVIDER=upcloud").expect("PROVIDER=");
        assert!(name_pos < env_pos, "target name before ENV=, got: {s}");
        assert!(env_pos < prov_pos, "ENV= before PROVIDER=, got: {s}");
    }

    #[test]
    fn target_carries_resolved_secrets_file_after_provider() {
        // Resolution-matrix seam: make must receive exactly the path
        // Context resolved, so `make decrypt` lands where vpnd reads and
        // a decrypt is never duplicated into a divergent location.
        let ctx = fake_ctx();
        let s = target(&ctx, "decrypt").expect("valid ctx").explain();
        let prov_pos = s.find("PROVIDER=upcloud").expect("PROVIDER=");
        let secrets_kv = format!("SECRETS_FILE={}", ctx.secrets_file.display());
        let sec_pos = s.find(&secrets_kv).expect("SECRETS_FILE kv");
        assert!(
            prov_pos < sec_pos,
            "SECRETS_FILE comes after PROVIDER=, got: {s}"
        );
    }

    #[test]
    fn target_program_is_make() {
        let ctx = fake_ctx();
        let s = target(&ctx, "deploy").expect("valid ctx").explain();
        // cwd wraps, but 'make' must still appear
        assert!(s.contains("make"), "program must be make, got: {s}");
    }

    #[test]
    fn target_cwd_is_repo_root() {
        let ctx = fake_ctx();
        let s = target(&ctx, "deploy").expect("valid ctx").explain();
        assert!(s.contains("/repo"), "cwd must be repo root, got: {s}");
    }

    #[test]
    fn target_with_appends_kvs_after_provider() {
        let ctx = fake_ctx();
        let s = target_with(&ctx, "emit-singbox", &[("CLIENT", "phone"), ("EXTRA", "1")])
            .expect("valid kvs")
            .explain();
        let prov_pos = s.find("PROVIDER=").expect("PROVIDER=");
        let client_pos = s.find("CLIENT=phone").expect("CLIENT=phone");
        let extra_pos = s.find("EXTRA=1").expect("EXTRA=1");
        assert!(prov_pos < client_pos, "KVs come after PROVIDER=, got: {s}");
        assert!(
            client_pos < extra_pos,
            "KV insertion order preserved, got: {s}"
        );
    }

    #[test]
    fn target_with_no_extra_kvs_matches_target() {
        let ctx = fake_ctx();
        assert_eq!(
            target(&ctx, "decrypt").expect("valid ctx").explain(),
            target_with(&ctx, "decrypt", &[]).expect("no kvs").explain()
        );
    }

    /// Acceptance table: one legitimate value per audited key must pass and
    /// render into the invocation verbatim — what was validated is exactly
    /// what spawns.
    #[test]
    fn per_key_acceptance_table_passes_legitimate_values() {
        let cases: &[(&str, &str)] = &[
            ("CLIENT", "phone-2"),
            ("HOST", "203.0.113.5"),
            ("TARGET_ID", "p0-direct-1"),
            ("MATRIX_CONFIG", "/tmp/probe-matrix.yaml"),
            ("PLAN", "/plans/fleet-rotation.yaml"),
            ("ENV", "prod"),
            ("PROVIDER", "upcloud"),
            // Runtime paths may carry spaces (XDG_RUNTIME_DIR) — argv
            // passes them as one argument.
            (
                "SECRETS_FILE",
                "/run/user/1000/my runtime/vpn-prod.secrets.yaml",
            ),
            // Unknown keys ride the fail-closed identifier charset.
            ("RESUME", "1"),
        ];
        let ctx = fake_ctx();
        let mut failures: Vec<String> = Vec::new();
        for (key, value) in cases {
            let kv = format!("{key}={value}");
            match target_with(&ctx, "probe-matrix-cell", &[(key, value)]) {
                Ok(cmd) => {
                    let rendered = cmd.explain();
                    if !rendered.contains(&kv) {
                        failures.push(format!("argv must carry {kv} verbatim: {rendered}"));
                    }
                }
                Err(err) => failures.push(format!("{kv} must be accepted: {err}")),
            }
        }
        assert!(
            failures.is_empty(),
            "acceptance table failures: {failures:?}"
        );
    }

    /// Rejection table: a make-metacharacter value must abort with an error
    /// naming both the key and the failed rule.
    #[test]
    fn per_key_rejection_table_aborts_naming_key_and_rule() {
        let cases: &[(&str, &str, &str)] = &[
            ("CLIENT", "$(shell touch /tmp/pwned)", "identifier"),
            ("HOST", "$(shell reboot)", "IPv4 literal"),
            ("HOST", "203.0.113.5; rm -rf /", "IPv4 literal"),
            ("TARGET_ID", "p0;id", "identifier"),
            ("MATRIX_CONFIG", "relative/config.yaml", "path"),
            ("MATRIX_CONFIG", "/tmp/../etc/passwd", "path"),
            ("MATRIX_CONFIG", "/tmp/space name.yaml", "path"),
            ("PLAN", "../escape.yaml", "path"),
            (
                "SECRETS_FILE",
                "/tmp/$(id)/vpn-prod.secrets.yaml",
                "runtime path",
            ),
            // '#' would start a comment in an unquoted recipe expansion.
            (
                "SECRETS_FILE",
                "/tmp/a #/vpn-prod.secrets.yaml",
                "runtime path",
            ),
            ("ENV", "prod;id", "identifier"),
            ("PROVIDER", "$(shell id)", "identifier"),
        ];
        for (key, value, rule) in cases {
            let err =
                validate_kv(key, value).expect_err("a metacharacter value must abort before spawn");
            let msg = err.to_string();
            assert!(msg.contains(key), "error must name the key {key}: {msg}");
            assert!(msg.contains(rule), "error must name the {rule} rule: {msg}");
        }
    }

    #[test]
    fn unknown_keys_fail_closed_to_identifier_charset() {
        assert!(validate_kv("BRAND_NEW_KEY", "ok").is_ok());
        let err = validate_kv("BRAND_NEW_KEY", "$(x)").expect_err("unknown keys must fail closed");
        let msg = err.to_string();
        assert!(msg.contains("BRAND_NEW_KEY"), "{msg}");
        assert!(msg.contains("identifier"), "{msg}");
    }

    #[test]
    fn target_gates_context_values_before_building_invocation() {
        let mut ctx = fake_ctx();
        ctx.env = "prod;id".into();
        let err = target(&ctx, "deploy").expect_err("hostile ENV must abort");
        assert!(err.to_string().contains("ENV"), "{err}");

        let mut ctx = fake_ctx();
        ctx.provider = "$(shell id)".into();
        let err = target(&ctx, "plan").expect_err("hostile PROVIDER must abort");
        assert!(err.to_string().contains("PROVIDER"), "{err}");

        let mut ctx = fake_ctx();
        ctx.secrets_file = PathBuf::from("/tmp/$(id)/vpn-prod.secrets.yaml");
        let err = target(&ctx, "decrypt").expect_err("hostile SECRETS_FILE must abort");
        assert!(err.to_string().contains("SECRETS_FILE"), "{err}");
    }

    #[test]
    fn secrets_file_rejection_redacts_the_value() {
        // The runner never logs the secrets-file location, so the
        // validation error must not echo the rejected path either.
        let err = validate_kv("SECRETS_FILE", "/tmp/$(id)/vpn-prod.secrets.yaml")
            .expect_err("hostile SECRETS_FILE must abort");
        let msg = err.to_string();
        assert!(msg.contains("SECRETS_FILE"), "{msg}");
        assert!(
            !msg.contains("/tmp/$(id)"),
            "validation error must redact the SECRETS_FILE value: {msg}"
        );
    }

    /// Integration-style contract: any rejected value in any position
    /// prevents the Cmd from ever existing, so nothing that fails the
    /// allowlist can reach a spawned argv.
    #[test]
    fn target_with_first_failing_key_aborts_and_nothing_spawns() {
        let ctx = fake_ctx();
        let err = target_with(
            &ctx,
            "emit-singbox",
            &[("CLIENT", "phone"), ("EXTRA", "`id`")],
        )
        .expect_err("any rejected value must abort the invocation");
        assert!(err.to_string().contains("EXTRA"), "{err}");

        let err = target_with(&ctx, "test-tls-policing", &[("HOST", "not-an-ip")])
            .expect_err("HOST must be an IP literal");
        let msg = err.to_string();
        assert!(
            msg.contains("HOST") && msg.contains("IPv4 literal"),
            "{msg}"
        );
    }
}
