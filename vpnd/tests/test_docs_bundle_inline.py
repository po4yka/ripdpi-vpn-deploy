from vpnd import docs_bundle as docs


# Rust test: vpnd/src/docs_bundle.rs::empty_report_produces_empty_excerpts
def test_empty_report_produces_empty_excerpts():
    assert docs.relevant_runbook_excerpts("") == ""


# Rust test: vpnd/src/docs_bundle.rs::report_with_no_keywords_produces_empty_excerpts
def test_report_with_no_keywords_produces_empty_excerpts():
    assert docs.relevant_runbook_excerpts("everything looks fine, no issues detected") == ""


# Rust test: vpnd/src/docs_bundle.rs::fleet_status_keyword_triggers_excerpt
def test_fleet_status_keyword_triggers_excerpt():
    result = docs.relevant_runbook_excerpts("fleet-status check failed on host")
    assert result and "RUNBOOK-incident.md" in result


# Rust test: vpnd/src/docs_bundle.rs::asn_drift_keyword_triggers_incident_runbook
def test_asn_drift_keyword_triggers_incident_runbook():
    assert "RUNBOOK-incident.md" in docs.relevant_runbook_excerpts("asn-drift detected")


# Rust test: vpnd/src/docs_bundle.rs::burn_check_keyword_triggers_multiple_runbooks
def test_burn_check_keyword_triggers_multiple_runbooks():
    result = docs.relevant_runbook_excerpts("burn-check alert")
    assert "RUNBOOK-incident.md" in result and "RUNBOOK-rotate.md" in result


# Rust test: vpnd/src/docs_bundle.rs::duplicate_runbook_suppressed_for_two_matching_keywords
def test_duplicate_runbook_suppressed_for_two_matching_keywords():
    assert (
        docs.relevant_runbook_excerpts("fleet-status asn-drift").count(
            "Runbook excerpt: RUNBOOK-incident.md"
        )
        == 1
    )


# Rust test: vpnd/src/docs_bundle.rs::missing_runbook_file_silently_skipped
def test_missing_runbook_file_silently_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(docs, "docs_path", lambda: tmp_path)
    assert docs.relevant_runbook_excerpts("fleet-status asn-drift burn-check") == ""


def test_runbook_excerpts_preserve_lf_boundaries_and_unicode_separators(tmp_path, monkeypatch):
    text = (
        "first\vsecond\fthird\u0085fourth\u2028fifth\u2029sixth\rseventh\r\n"
        + "\r\n"
        + "\n".join(f"line-{i}" for i in range(61))
    )
    (tmp_path / "RUNBOOK-incident.md").write_bytes(text.encode())
    monkeypatch.setattr(docs, "docs_path", lambda: tmp_path)
    result = docs.relevant_runbook_excerpts("asn-drift")
    first = "first\vsecond\fthird\u0085fourth\u2028fifth\u2029sixth\rseventh"
    assert first in result and "\r\n" not in result
    assert "line-57" in result and "line-58" not in result
    from vpnd.text import lf_lines

    for value, expected in [
        ("", []),
        ("\n", [""]),
        ("a\r\nb\r", ["a", "b\r"]),
        ("a\u2028b", ["a\u2028b"]),
    ]:
        assert lf_lines(value) == expected
