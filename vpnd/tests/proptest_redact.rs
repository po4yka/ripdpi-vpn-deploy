//! Property-based tests for the redact_secrets helper (commands::doctor).
//!
//! Covers three invariants:
//!   1. Any line containing /tmp/vpn-<env>.secrets.yaml is replaced by the
//!      redaction marker, regardless of surrounding text.
//!   2. Any line containing the RESOLVED runtime path — including non-/tmp
//!      shapes such as a user cache dir — is replaced by the marker.
//!   3. Multi-line strings with no secrets path are passed through unchanged.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use proptest::prelude::*;
use vpnd::commands::doctor::redact_secrets;

/// Strategy: a random ASCII identifier for the env segment (letters + digits + hyphens).
fn env_strategy() -> impl Strategy<Value = String> {
    "[a-z][a-z0-9-]{0,15}".prop_map(|s| s)
}

/// A resolved secrets path in a non-/tmp location (user cache dir shape).
fn resolved_path_strategy() -> impl Strategy<Value = String> {
    (
        "(/Users/[a-z]+/Library/Caches/|/home/[a-z]+/.cache/|/var/root/cache/)"
            .prop_map(|s| s.to_string()),
        "[a-z][a-z0-9-]{0,15}",
    )
        .prop_map(|(dir, env)| format!("{dir}/vpn-provision/vpn-{env}.secrets.yaml"))
}

/// Strategy: a single non-empty line (no embedded newlines) with no secrets
/// path pattern. Empty lines are excluded because the `lines() + join("\n")`
/// idiom in `redact_secrets` is lossy on all-empty inputs (`"\n".lines()` is
/// a single empty line, but `[""].join("\n")` is the empty string — they
/// round-trip differently). Real bug-relevant inputs are never empty, so
/// constraining the strategy keeps the property meaningful.
fn safe_line_strategy() -> impl Strategy<Value = String> {
    "[ -~]{1,80}".prop_filter("must not contain secrets pattern", |s| {
        !s.contains(".secrets.yaml")
    })
}
proptest! {
    /// A line of the form `<prefix>/tmp/vpn-<env>.secrets.yaml<suffix>` must be
    /// replaced by the redaction marker no matter what surrounds the path.
    #[test]
    fn redact_masks_any_historical_default_path(
        prefix in "[ -~]{0,40}",
        env in env_strategy(),
        suffix in "[ -~]{0,40}",
    ) {
        let line = format!("{prefix}/tmp/vpn-{env}.secrets.yaml{suffix}");
        let result = redact_secrets(line, "");
        prop_assert_eq!(
            result.as_str(),
            "<redacted: secrets file path>",
            "line containing historical default secrets path must be fully replaced"
        );
    }

    /// The resolved runtime path is masked even when it lives outside
    /// /tmp — e.g. under a user cache dir when XDG_RUNTIME_DIR is unset.
    #[test]
    fn redact_masks_resolved_non_tmp_paths(
        prefix in "[ -~]{0,40}",
        resolved in resolved_path_strategy(),
        suffix in "[ -~]{0,40}",
    ) {
        prop_assume!(!(prefix.contains("/tmp/vpn-") || suffix.contains("/tmp/vpn-")));
        let line = format!("{prefix}{resolved}{suffix}");
        let result = redact_secrets(line, &resolved);
        prop_assert_eq!(
            result.as_str(),
            "<redacted: secrets file path>",
            "line containing the resolved secrets path must be fully replaced"
        );
    }

    /// For any multi-line input with no secrets-path lines, every line is
    /// passed through unchanged.
    ///
    /// `redact_secrets` is implemented as `lines().map(...).join("\n")`, which
    /// is lossy on trailing newlines: `"a\n".lines()` yields `["a"]`. We test
    /// the per-line invariant directly to avoid that ambiguity.
    #[test]
    fn redact_preserves_non_secret_lines(
        lines in prop::collection::vec(safe_line_strategy(), 1..10),
    ) {
        let input = lines.join("\n");
        prop_assume!(!(input.contains("/tmp/vpn-") && input.contains(".secrets.yaml")));
        let result = redact_secrets(input.clone(), "/nonexistent/resolved.secrets.yaml");
        let input_lines: Vec<&str> = input.lines().collect();
        let result_lines: Vec<&str> = result.lines().collect();
        prop_assert_eq!(
            input_lines,
            result_lines,
            "every non-secrets line must pass through unchanged"
        );
    }
}
