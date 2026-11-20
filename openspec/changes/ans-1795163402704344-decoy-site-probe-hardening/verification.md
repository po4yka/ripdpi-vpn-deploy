---
task_id: ANS-1795163402704344
change: ans-1795163402704344-decoy-site-probe-hardening
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DSP-BUNDLED-BYTES | ANS-1795164066655530 | `test_operator_tree_that_repeats_a_bundled_file_refuses_under_any_label` and `test_operator_tree_that_repeats_a_bundled_page_refuses_under_any_label` run the real role tasks | pending |
| REQ-DSP-DOT-PATHS | ANS-1795164066655530 | `test_operator_tree_publishes_no_dot_path_except_well_known` in both test files | pending |
| REQ-DSP-TLS-DEFAULT-SERVER | ANS-1795164144591321 | `test_each_tls_port_has_a_default_server_that_hides_the_certificate_and_the_tunnel`; Molecule `nginx-xhttp` verify tasks for no SNI, foreign SNI and foreign Host | pending |
| REQ-DSP-TLS-POLICY | ANS-1795164144591321 | `test_primary_and_fallback_vhosts_share_the_hardened_tls_http_identity`, `test_self_steal_tls_site_is_loopback_only`; Molecule handshakes with TLS 1.2, TLS 1.3 and each group | pending |
| REQ-DSP-TARGET-LIMITS | ANS-1795164238196044 | Molecule `reality-self-steal` verify task for `nginx -T` and the worker file limit, and its idempotence step | pending |
| REQ-DSP-CERT-LIFETIME | ANS-1795164238196044 | `test_certificate_needs_thirty_days_of_remaining_lifetime` runs the role task on generated 20-day and 45-day certificates | pending |
| REQ-DSP-HTTP-REDIRECT | ANS-1795164238196044 | `test_opt_in_port_80_redirects_the_owned_name_and_leaves_one_default_server`, `test_self_steal_tls_site_is_loopback_only` | pending |
| REQ-DSP-XHTTP-EDGE | ANS-1795164360045220 | `test_xhttp_locations_answer_upstream_errors_with_the_site_404`, `test_routing_list_base_url_omits_the_default_https_port` | pending |
