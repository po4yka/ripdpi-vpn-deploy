---
task_id: ANS-1794214330785468
change: ans-1794214330785468-client-routing-lists
commit_sha: null
local: passed
local_evidence: On the working tree over 066bc817, tests/unit/test_routing_lists_refresh.py passes 40 tests, including the admission refusals, generation retention and the rendered nginx route. An offline run admitted a real feed. Local subscription-host Molecule fails at the shared nginx publication step on this Mac with the feature disabled as well, so that scenario relies on CI.
remote_ci: passed
remote_ci_evidence: PR CI passed for each change to the feature (PRs 548, 551 and 605), and main CI run 43687588270 passed on fd5d4e03, the commit that added deny-list block rules.
dry_run: passed
dry_run_evidence: On 2026-11-15 the production node-b dry-run at da6fb86d passed with 5 changed and 0 failed tasks, including the routing list refresher and its policy.
staging: required
staging_evidence: null
live: passed
live_evidence: On 2026-11-15 the node-b deploy at da6fb86d passed deploy, verify, source-drift, security-verify, smoke-test and protocol-liveness. The served profile.json lists the 6 expected deny-listed domains in BlockSites, an empty BlockIp, RouteOrder block-proxy-direct and a newer LastUpdated.
client: required
client_evidence: null
artifact: required
artifact_evidence: docs/reference/subscription-plane.md documents the route, admission and the deliberate unpinned feed.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ROUTING-LISTS-ADMISSION | ANS-1794218690815722 | test_unsafe_candidate_keeps_the_previous_generation, test_duplicate_tag_refuses, test_inverted_geoip_tag_refuses, test_digest_mismatch_refuses, test_download_stops_at_the_byte_cap, test_sudden_size_change_refuses | passed |
| REQ-ROUTING-LISTS-KEEP | ANS-1794218690815722 | test_unsafe_candidate_keeps_the_previous_generation | passed |
| REQ-ROUTING-LISTS-SERVED | ANS-1794218690815722 | test_nginx_serves_client_files, test_nginx_does_not_serve_other_paths, test_unchanged_feed_keeps_the_timestamp_clients_compare, test_new_address_republishes_an_unchanged_feed | passed |
| REQ-ROUTING-LISTS-BLOCK | ANS-1794218690815722 | test_denied_names_and_ranges_on_direct_rules_are_blocked_on_the_client, test_deny_entry_above_direct_rules_blocks_only_their_direct_names, test_unchanged_deny_data_keeps_the_timestamp, test_changed_deny_data_republishes_an_unchanged_feed, test_unusable_deny_data_keeps_the_previous_generation; an offline run on the current feed and the pinned production deny data produced 6 block names and no block ranges in 0.5 s | passed |
| REQ-ROUTING-LISTS-RETIRE | ANS-1794218690815722 | routing-lists-disable.yml and disable.yml retire exact owned paths and preserve masks; nginx-xhttp Molecule in CI | required |
