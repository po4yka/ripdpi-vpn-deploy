---
task_id: SEC-1795086333272606
change: sec-1795086333272606-field-report-ingest-d2
commit_sha: 872d171c
local: passed
local_evidence: Second security review fixes at bdb65566, b03e3681, c51db768, 7c7a4957, c29c085c and 8778448c pass the local checks in the section of that name at cba6b1e8. Implementation at bd31813d with the security fix e84aec57 and the alert label fix 872d171c (the relay refuses an alert without a node label; the rule now sets node field-reports, and the promtool case and `make snapshot-check` pass at 872d171c). At e84aec57 focused pytest of 10 files (field-report ingest, bundle and report contract, alert rules with promtool 3.15.1, agent render, metric contract, retention, secrets coverage, governance, agent instructions, docs index) exit 0, 449 passed; `make snapshot-check` exit 0; `make docs-check` exit 0; `ansible-lint --offline` on subscription-host, observability_control_plane and observability_agent exit 0; yamllint on the same roles exit 0; `./taskctl openspec cli validate --strict` exit 0. At bd31813d a wider run of 28 files had 978 passed and 4 failures, all in `test_subscription_nginx_native.py`, which asserts root and a local nginx (native lane; environment gap, not a regression). The new regression tests fail on bd31813d (6 failed) and pass on e84aec57. `make molecule-test ROLE=subscription-host` exit 2: the pinned Debian 13 image digest returns 404 from the registry on this machine, so the extended scenario (ingest active on loopback, 202/401/403 through nginx, textfile aggregate, no token in logs) did not run. `make check` was not run. Logs are in the session run directory runs-d2d4d5 (d2-*.log).
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Enabling on production is a separate operator decision.
client: not_applicable
client_evidence: Client traffic is proven by D7 with RIPDPI R3.
artifact: not_applicable
artifact_evidence: No release artifact is produced by this change.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-INGEST-VALIDATE | SEC-1795086432958533 | `test_status_codes_and_only_an_accepted_report_changes_metrics` (202, 400, 401, 413, 429, 404), `test_rejections_leave_metrics_unchanged`, `test_previous_token_is_accepted_only_during_its_overlap`, `test_previous_token_is_rejected_after_its_overlap` | passed (local, e84aec57) |
| REQ-INGEST-AUTHFIRST | SEC-1795086432958533 | `test_unauthenticated_requests_never_starve_a_valid_report` (300 requests with a bad token get 401, then a valid report gets 202); `test_nginx_location_limits_size_and_rate_and_keeps_body_in_memory` (nginx `limit_req` and `limit_req_status 429`) | passed (local, b03e3681) |
| REQ-INGEST-NOIP | SEC-1795086432958533 | `test_no_address_or_token_reaches_logs_metrics_or_state` (process stdout/stderr and the textfile directory searched for 127.0.0.1 and both tokens); `test_nginx_location_limits_size_and_rate_and_keeps_body_in_memory` | passed (local, e84aec57) |
| REQ-INGEST-LABELS | SEC-1795104397840245 | `test_labels_stay_bounded_for_many_networks_and_unknown_endpoints` (1000 ASNs over two windows: only the top 20 `as<asn>` and `other`, unknown `server_ref` is `other`, series under the budget); `test_network_label_follows_the_report_source_and_operators_rank_apart_from_asns`, `test_sim_and_none_reports_are_accepted_and_a_report_with_two_identities_is_not`; `test_label_strings_with_a_newline_or_quote_are_rejected`, `test_rendered_label_values_are_escaped` | passed (local, e84aec57) |
| REQ-INGEST-MINATTEMPT | SEC-1795086432958533 | `test_a_bucket_under_the_contract_floor_rejects_the_report_without_counting`, `test_buckets_under_the_configured_floor_are_dropped_and_counted` | passed (local, e84aec57) |
| REQ-INGEST-ALERT | SEC-1795104397840245 | promtool case for `FieldReportClientFailureRatioHigh` (60 percent for an ASN and 70 percent for a SIM operator fire with node, protocol, network and value annotation; 5 percent does not) in `test_promtool_rule_cases_cover_firing_stale_recovery_and_absent` | passed (local, 872d171c) |
| REQ-INGEST-POISON-BOUNDS | SEC-1795086432958533 | `test_one_report_adds_at_most_the_attempts_cap`, `test_labels_stay_bounded_for_many_networks_and_unknown_endpoints` (a 100000-attempt single report is not promoted) | passed (local, c29c085c) |
| REQ-INGEST-SECREVIEW | SEC-1795086456490841 | security-review checklist below | APPROVE at e84aec57, tracked items listed |

## Security review

Scope: `git diff 1eccaca7...e84aec57` for the D2 paths (ingest, role tasks and templates, nginx location, allowlists, manifest, alert rule, validator). No staged, unstaged or untracked D2 files remained at review time.

An independent review of bd31813d returned REQUEST CHANGES with two findings, both fixed in e84aec57 with regression tests:

1. HIGH, fixed: the attempts floor ran before validation (`vpn-field-report.py` `Ingest.handle`), so a report whose buckets all fell under it got 202 and grew a counter without validation. Now the whole report is validated first and the floor applies only to an accepted report.
2. HIGH, fixed: Python `$` matches before a trailing newline, so `"ZZ\n"` passed `^[A-Z]{2}$` and reached the exposition text. `validate-field-report.py` `validator()` anchors at end of input for the CLI and the ingest, a negative fixture pins it, and `render()` escapes label values.

Checklist at e84aec57:

- Secrets in Git: pass. Fixture tokens are low-entropy test strings or hashes of fixed text in the Molecule vars; gitleaks passed in the commit hook.
- Secret schema: tracked. The role reads the SOPS key `field_report` (`cohort_token`, `previous_cohort_token`, `previous_cohort_token_valid_until`), but `secrets/schema.json` and the example do not declare it yet; D4 step SCR-1795086581871015 owns that. The ingest ships disabled.
- Terraform and cloud-init: not touched.
- Ansible: pass. The token assert and the credential file copy set `no_log: true` and `diff: false`; the file is root 0600 and reaches the unit through `LoadCredential`.
- Layer boundaries: pass.
- Per-device material: pass. The cohort token is shared per cohort by contract and never derives from a device identity; no device id reaches the ingest.
- Exposure: pass. No new public listener: the route is on the existing subscription vhost and port; the backend binds 127.0.0.1 with `IPAddressDeny=any` and `IPAddressAllow=localhost`. Rate limiting is nginx `limit_req` per address; the app bucket is process-wide and holds no client state.
- Authentication: pass. `hmac.compare_digest` against both slots on every request; the previous token is accepted only before `previous_valid_until`.
- Input validation: pass. Body limit at nginx (`client_max_body_size`) and the app (Content-Length before read); JSON errors and `RecursionError` give 400; the shared contract validator runs on the whole report.
- Log content: pass. The handler logs nothing; `handle_error` prints only the exception type; nginx keeps the categorical format and forwards no address.
- Denial of service: fixed by the second review. The process-wide bucket is gone (b03e3681), the token check runs first, and each connection has a 5-second deadline (c51db768). The label budget keeps the textfile far below the node scrape sample limit.
- Retention: pass. No raw report is stored; nginx buffers the body in memory (`client_body_buffer_size` equals the size limit). nginx keeps limiter addresses in shared memory until its LRU evicts them.
- Versions: fixed by the second review (8778448c): `python3-jsonschema` is pinned per release.
- Bypass markers: pass.
- Transport baseline: not affected.

Tracked follow-ups: the secret schema entries (D4); the RIPDPI client should anchor its vendored patterns at end of input (Java `$` also matches before a final line terminator); `scripts/validate-bundle.py` uses the same Python `pattern` semantics for operator-produced bundles.

## Not done here

- Remote CI: no push is authorized.
- Dry run: `make dry-run` for the subscription host needs operator authorization and a live inventory.
- Staging: no staging node or deployment is authorized. Needed: enable `subscription_field_report` on a staging subscription host, post one valid and one invalid report through the public vhost, show the aggregate series at the collector with the node label and no address, and fire the alert from a replayed series (D7 owns the full chain).
- Molecule: blocked locally by the unavailable image digest; CI must run it.

## Second security review (1a159bc1..0f3b138b)

An independent security review of the whole field-analytics range returned REQUEST CHANGES. The findings that this change owns are fixed below, each in its own commit with a regression test that fails before the fix. Verdict after the fixes: APPROVE for local evidence; staging, remote CI and Molecule stay open as listed above.

- Finding 3 (MEDIUM), fixed in b03e3681: the process-wide rate bucket ran before `token_ok()`, so unauthenticated floods starved token holders. The bucket is removed; nginx `limit_req` per address is the only rate limit (single-layer rule) and the token check runs first. `test_unauthenticated_requests_never_starve_a_valid_report` fails before.
- Finding 4 (MEDIUM, accepted with bounds), fixed in c29c085c: per-report attempts cap, report-count top-N promotion, `vpn_field_report_network_reports_total` and distinct-report floors on both alerts (`min_reports`, `block_min_reports`); the runbook and the rotation hint name the data unauthenticated client input. `test_one_report_adds_at_most_the_attempts_cap`, the strengthened label-bound test and the single-report promtool case fail before.
- Finding 6, fixed in bdb65566: the settings assert used `$`; it now uses `\Z`. `test_settings_assert_refuses_a_trailing_newline` evaluates the real assert and fails before.
- Finding 9, fixed in 7c7a4957: the ingest no longer joins the textfile writer group; it writes its own `StateDirectory` and the role links the file into the textfile directory as root. The unit and task tests fail before.
- Finding 10 (package pin), fixed in 8778448c: `python3-jsonschema=4.19.2-6` on trixie and `4.10.3-2ubuntu1` on noble, read from the distribution package indexes on 2026-11-19; other releases refuse. `test_validator_package_is_pinned_for_each_supported_release` fails before.
- Finding 12, fixed in c51db768: each connection has a 5-second total deadline. `test_a_slow_connection_cannot_hold_the_ingest_past_its_deadline` fails before (the valid report waited over 20 seconds).
- Finding 1 also covers this change's alert: `FieldReportClientFailureRatioHigh` reads only `field_report.source_nodes` (cba6b1e8).

At cba6b1e8 (logs in the session run directory runs-secfix-d7, verify-*.log): focused pytest of 17 files (contract, ingest, rotation, exporters, relay render, alert rules with promtool 3.15.1, observability contract, agent render, retention, secrets schema, audit hooks, agent instructions, governance, docs index, journald, operator) exit 0, 895 passed; `ansible-lint --offline` on subscription-host, observability_control_plane and hysteria exit 0; yamllint on the same roles exit 0; shellcheck exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; every contract fixture validates and every negative fixture is rejected exit 0; `./taskctl openspec cli validate --strict` exit 0 for D1 to D5 and D7; `./taskctl validate` exit 0. Each fix commit carries a regression test that failed on the code before it (red runs in the same directory). `make molecule-test` and `make check` were not run.
