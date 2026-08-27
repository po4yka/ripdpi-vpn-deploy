//! Integration tests for commands::doctor — redact_secrets contract.
//!
//! Exercises the real exported helper: the resolved runtime path is
//! masked wherever it appears (including non-/tmp locations such as a
//! user cache dir), and the historical /tmp default pattern stays
//! covered for older captures.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use vpnd::commands::doctor::redact_secrets;

#[test]
fn redact_masks_historical_default_tmp_path() {
    let input = "loading /tmp/vpn-prod.secrets.yaml for client phone";
    let result = redact_secrets(
        input.to_string(),
        "/cache/vpn-provision/vpn-prod.secrets.yaml",
    );
    assert_eq!(result, "<redacted: secrets file path>");
    assert!(!result.contains("/tmp/vpn-"), "secret path must be masked");
}

#[test]
fn redact_masks_resolved_path_outside_tmp() {
    // XDG_RUNTIME_DIR unset resolves into a user cache dir; that shape
    // must be masked via the resolved-path argument.
    let resolved = "/Users/op/Library/Caches/vpn-provision/vpn-prod.secrets.yaml";
    let input = format!("reading secrets from {resolved} (env=prod)");
    let result = redact_secrets(input, resolved);
    assert_eq!(result, "<redacted: secrets file path>");
    assert!(
        !result.contains("Library/Caches"),
        "resolved path must be masked"
    );
}

#[test]
fn redact_leaves_innocent_lines_unchanged() {
    let input = "fleet-status: all systems operational\nasn-drift: none";
    let result = redact_secrets(input.to_string(), "/cache/vpn-prod.secrets.yaml");
    assert_eq!(result, input, "non-secret lines must be unchanged");
}
