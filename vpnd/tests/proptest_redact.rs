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

/// Unix runtime paths can contain whitespace, quotes, Unicode, and line breaks.
fn resolved_path_strategy() -> impl Strategy<Value = String> {
    prop::collection::vec(
        prop_oneof![
            Just("runtime"),
            Just("space dir"),
            Just("O'Brien"),
            Just("данные"),
            Just("line\nbreak"),
            Just("tab\tpath")
        ],
        1..5,
    )
    .prop_map(|parts| format!("/{}/vpn-test.secrets.yaml", parts.join("/")))
}
fn safe_line_strategy() -> impl Strategy<Value = String> {
    "[ -~]{0,80}".prop_filter("no historical secret path", |s| {
        !(s.contains("/tmp/vpn-") && s.contains(".secrets.yaml"))
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

    /// Empty lines and trailing newline are part of the input contract.
    #[test]
    fn redact_preserves_non_secret_lines(
        lines in prop::collection::vec(safe_line_strategy(), 0..10),
        trailing_newline in any::<bool>(),
    ) {
        let mut input = lines.join("\n");
        if trailing_newline { input.push('\n'); }
        let result = redact_secrets(input.clone(), "/nonexistent/resolved.secrets.yaml");
        prop_assert_eq!(result, input);
    }
}
