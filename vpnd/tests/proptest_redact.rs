//! Property-based tests for the redact_secrets helper (commands::doctor).
//!
//! Covers two invariants:
//!   1. Any line containing /tmp/vpn-<env>.secrets.yaml is replaced by the
//!      redaction marker, regardless of surrounding text.
//!   2. Multi-line strings with no secrets path are passed through unchanged.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use proptest::prelude::*;
use vpnd::commands::doctor::redact_secrets;

/// Strategy: a random ASCII identifier for the env segment (letters + digits + hyphens).
fn env_strategy() -> impl Strategy<Value = String> {
    "[a-z][a-z0-9-]{0,15}".prop_map(|s| s)
}

/// Strategy: a single non-empty line (no embedded newlines) with no secrets
/// path pattern. Empty lines are excluded because the `lines() + join("\n")`
/// idiom in `redact_secrets` is lossy on all-empty inputs (`"\n".lines()` is
/// a single empty line, but `[""].join("\n")` is the empty string — they
/// round-trip differently). Real bug-relevant inputs are never empty, so
/// constraining the strategy keeps the property meaningful.
fn safe_line_strategy() -> impl Strategy<Value = String> {
    "[ -~]{1,80}".prop_filter("must not contain secrets pattern", |s| {
        !(s.contains("/tmp/vpn-") && s.contains(".secrets.yaml"))
    })
}

proptest! {
    /// A line of the form `<prefix>/tmp/vpn-<env>.secrets.yaml<suffix>` must be
    /// replaced by the redaction marker no matter what surrounds the path.
    #[test]
    fn redact_masks_any_secrets_path(
        prefix in "[ -~]{0,40}",
        env in env_strategy(),
        suffix in "[ -~]{0,40}",
    ) {
        let line = format!("{prefix}/tmp/vpn-{env}.secrets.yaml{suffix}");
        let result = redact_secrets(line);
        prop_assert_eq!(
            result.as_str(),
            "<redacted: secrets file path>",
            "line containing secrets path must be fully replaced"
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
        let result = redact_secrets(input.clone());
        let input_lines: Vec<&str> = input.lines().collect();
        let result_lines: Vec<&str> = result.lines().collect();
        prop_assert_eq!(
            input_lines,
            result_lines,
            "every non-secrets line must pass through unchanged"
        );
    }
}
