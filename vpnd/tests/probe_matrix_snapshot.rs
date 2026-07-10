//! Snapshot test for the probe-matrix JSON report shape.
//!
//! Locks in the schema so a future change to the cell/window struct
//! shape surfaces as a clear diff rather than silently breaking
//! downstream analysis tooling that consumes the JSON.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use vpnd::commands::probe_matrix::{report_to_json, synthetic_report_for_snapshot};

#[test]
fn probe_matrix_report_snapshot() {
    let report = synthetic_report_for_snapshot();
    let json = report_to_json(&report).expect("MatrixReport serialises");
    insta::assert_snapshot!("probe_matrix_report", json);
}

#[test]
fn probe_matrix_report_carries_required_top_level_fields() {
    let report = synthetic_report_for_snapshot();
    let json = report_to_json(&report).expect("MatrixReport serialises");
    for required in [
        "\"schema_version\"",
        "\"vantage\"",
        "\"started_at_unix_ms\"",
        "\"finished_at_unix_ms\"",
        "\"poll_interval_seconds\"",
        "\"cells\"",
        "\"windows\"",
    ] {
        assert!(
            json.contains(required),
            "probe-matrix JSON must include {required}, got:\n{json}"
        );
    }
}

#[test]
fn probe_matrix_destination_classes_are_technical_signatures() {
    let report = synthetic_report_for_snapshot();
    let json = report_to_json(&report).expect("MatrixReport serialises");
    // Enforces the repo hard rule: destination labels must describe
    // technical signature, not operator / geography / carrier.
    for forbidden in [
        "carrier-name", "operator-name", "region-name",
        "network-brand", "provider-brand", "geographic-label",
    ] {
        assert!(
            !json.to_lowercase().contains(forbidden),
            "probe-matrix JSON must not contain operator/carrier label '{forbidden}', got:\n{json}"
        );
    }
    // And it must use the technical-signature class names.
    for required_class in [
        "domestic-allowlisted",
        "foreign-non-allowlist",
    ] {
        assert!(
            json.contains(required_class),
            "probe-matrix JSON must use technical-signature class '{required_class}'"
        );
    }
}
