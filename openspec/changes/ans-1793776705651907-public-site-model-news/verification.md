---
task_id: ANS-1793776705651907
change: ans-1793776705651907-public-site-model-news
commit_sha: e56fc0d2ac26090bf47ef9c514bc7a9d14b7613b
local: passed
local_evidence: "pytest tests/unit/test_model_news.py tests/unit/test_public_site_contract.py (69 passed); make snapshot-check; scripts/check-secrets-coverage.py; scripts/check-templates-render.py; ansible-lint roles/nginx-xhttp; live script run against the pinned sources rendered 30 repository and 30 headline entries; every model tracker row matches its Hugging Face API createdAt month and license metadata on 2026-11-04. make molecule-test ROLE=nginx-xhttp could not run locally: the pinned molecule-debian13 image has no linux/arm64 manifest."
remote_ci: passed
remote_ci_evidence: "PR #485 checks passed on its final head, including molecule nginx-xhttp (new pages served, seeded /news.html owner and mode, systemd-analyze verify, timer enabled) and molecule full-stack. main CI run 42225715509 passed on e5b5a096, the revision now on node-b."
dry_run: passed
dry_run_evidence: "Full canonical dry-run of node-b at 491e2a35 with config/node-b-public-site-20261105-overrides.yml passed (decrypt, dry-run, clean exit 0) on 2026-11-06, and the fleet rollout repeated it at e5b5a096 before deploying."
staging: required
staging_evidence: null
live: passed
live_evidence: "node-b deploy of e5b5a096 with the owned site tree rendered from these templates (news page off, as REQ-NEWS-TOGGLE requires for an operator tree) passed deploy, verify, source-drift, security-verify, smoke-test and protocol-liveness on 2026-11-06. chinallmodel.com serves models.html, glossary.html, notes/ and the three new notes with HTTP 200 and /news.html with the site 404. The model news units run only on bundled-site hosts, and no fleet host serves the bundled site, so the refresh timer has not run on a host."
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
| REQ-NEWS-TOGGLE | ANS-1793777317745592 | `test_model_news_toggle_owns_link_location_and_sitemap_entry` (enabled, disabled, operator tree); Molecule verify checks the seeded page, user and timer in CI; node-b serves an operator tree without the news link, location or sitemap entry; removal tasks need staging | partly verified |
| REQ-NEWS-ISOLATION | ANS-1793777317745592 | `test_model_news_unit_runs_unprivileged_and_writes_only_its_state` | passed locally; `systemd-analyze security` on staging pending |
