use include_dir::{include_dir, Dir};

/// All markdown files from the repo's `docs/` directory, bundled at compile time.
pub static DOCS: Dir<'static> = include_dir!("$CARGO_MANIFEST_DIR/../docs");

/// Keywords that trigger runbook excerpt injection in `doctor --ai` output.
const KEYWORD_MAP: &[(&str, &[&str])] = &[
    (
        "fleet-status",
        &["RUNBOOK-incident.md", "RUNBOOK-rollback.md"],
    ),
    ("asn-drift", &["RUNBOOK-incident.md"]),
    ("burn-check", &["RUNBOOK-incident.md", "RUNBOOK-rotate.md"]),
];

/// Return runbook excerpts relevant to the diagnostic report text.
///
/// Scans `report` for known keywords and appends the first 60 lines of each
/// matched runbook file.  Duplicates are suppressed.
pub fn relevant_runbook_excerpts(report: &str) -> String {
    let mut seen: Vec<&str> = Vec::new();
    let mut out = String::new();

    for (keyword, files) in KEYWORD_MAP {
        if !report.contains(keyword) {
            continue;
        }
        for &fname in *files {
            if seen.contains(&fname) {
                continue;
            }
            seen.push(fname);
            if let Some(f) = DOCS.get_file(fname) {
                if let Some(text) = f.contents_utf8() {
                    let excerpt: String = text.lines().take(60).collect::<Vec<_>>().join("\n");
                    out.push_str(&format!(
                        "\n---\n### Runbook excerpt: {fname}\n\n{excerpt}\n"
                    ));
                }
            }
        }
    }

    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_report_produces_empty_excerpts() {
        let result = relevant_runbook_excerpts("");
        assert!(
            result.is_empty(),
            "empty report must yield empty excerpts, got: {result:?}"
        );
    }

    #[test]
    fn report_with_no_keywords_produces_empty_excerpts() {
        let result = relevant_runbook_excerpts("everything looks fine, no issues detected");
        assert!(
            result.is_empty(),
            "no-keyword report must yield empty excerpts, got: {result:?}"
        );
    }

    #[test]
    fn fleet_status_keyword_triggers_excerpt() {
        let result = relevant_runbook_excerpts("fleet-status check failed on host");
        // If the runbook file exists in DOCS, we get content; either way the fn must not panic.
        // When docs are bundled, we expect some output:
        if DOCS.get_file("RUNBOOK-incident.md").is_some() {
            assert!(
                !result.is_empty(),
                "fleet-status must produce excerpts when runbook exists"
            );
            assert!(
                result.contains("RUNBOOK-incident.md"),
                "must cite incident runbook, got: {result:?}"
            );
        }
    }

    #[test]
    fn asn_drift_keyword_triggers_incident_runbook() {
        let result = relevant_runbook_excerpts("asn-drift detected");
        if DOCS.get_file("RUNBOOK-incident.md").is_some() {
            assert!(
                result.contains("RUNBOOK-incident.md"),
                "asn-drift must cite incident runbook, got: {result:?}"
            );
        }
    }

    #[test]
    fn burn_check_keyword_triggers_multiple_runbooks() {
        let result = relevant_runbook_excerpts("burn-check alert");
        if DOCS.get_file("RUNBOOK-incident.md").is_some()
            && DOCS.get_file("RUNBOOK-rotate.md").is_some()
        {
            assert!(
                result.contains("RUNBOOK-incident.md"),
                "burn-check must cite incident runbook, got: {result:?}"
            );
            assert!(
                result.contains("RUNBOOK-rotate.md"),
                "burn-check must cite rotate runbook, got: {result:?}"
            );
        }
    }

    #[test]
    fn duplicate_runbook_suppressed_for_two_matching_keywords() {
        // Both fleet-status and asn-drift match RUNBOOK-incident.md — it must appear only once.
        let result = relevant_runbook_excerpts("fleet-status asn-drift");
        let count = result.matches("RUNBOOK-incident.md").count();
        assert!(
            count <= 1,
            "duplicate runbook must be suppressed, got count={count} in: {result:?}"
        );
    }

    #[test]
    fn missing_runbook_file_silently_skipped() {
        // KEYWORD_MAP references files that may not exist; fn must not panic.
        // We force a report that would trigger a lookup regardless.
        let result = relevant_runbook_excerpts("fleet-status asn-drift burn-check");
        // No panic = pass. Result may or may not be empty depending on bundled docs.
        let _ = result;
    }
}
