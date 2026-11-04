---
task_id: ANS-1793776705651907
change: ans-1793776705651907-public-site-model-news
commit_sha: null
local: passed
local_evidence: "pytest tests/unit/test_model_news.py tests/unit/test_public_site_contract.py (69 passed); make snapshot-check; scripts/check-secrets-coverage.py; scripts/check-templates-render.py; ansible-lint roles/nginx-xhttp; live script run against the pinned sources rendered 30 repository and 30 headline entries; every model tracker row matches its Hugging Face API createdAt month and license metadata on 2026-11-04. make molecule-test ROLE=nginx-xhttp could not run locally: the pinned molecule-debian13 image has no linux/arm64 manifest."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: not_applicable
client_evidence: "No client, bundle or transport contract changes."
artifact: not_applicable
artifact_evidence: "No release artifact."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-NEWS-SOURCES | ANS-1793777317745592 | `test_plain_http_source_is_refused`, `test_redirect_away_from_https_is_refused`, `test_oversized_response_is_skipped`, `test_dtd_in_another_encoding_is_refused` | passed locally |
| REQ-NEWS-CONTENT | ANS-1793777317745592 | `test_page_lists_escaped_deduplicated_newest_first_entries` | passed locally |
| REQ-NEWS-NEUTRAL | ANS-1793777317745592 | same test drops "Proxy" and "VPN" entries; `test_site_copy_is_neutral_and_has_no_vpn_or_admin_surface` | passed locally |
| REQ-NEWS-FAILURE | ANS-1793777317745592 | `test_total_failure_keeps_the_previous_page_and_reports_it`; seed task uses `force: false` | passed locally; host behaviour needs staging |
| REQ-NEWS-TOGGLE | ANS-1793777317745592 | `test_model_news_toggle_owns_link_location_and_sitemap_entry` (enabled, disabled, operator tree); Molecule verify checks the seeded page, user and timer in CI; removal tasks need staging | partly verified |
| REQ-NEWS-ISOLATION | ANS-1793777317745592 | `test_model_news_unit_runs_unprivileged_and_writes_only_its_state` | passed locally; `systemd-analyze security` on staging pending |
