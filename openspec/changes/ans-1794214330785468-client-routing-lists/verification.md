---
task_id: ANS-1794214330785468
change: ans-1794214330785468-client-routing-lists
commit_sha: null
local: passed
local_evidence: On the working tree over 066bc817, tests/unit/test_routing_lists_refresh.py passes 40 tests, including the admission refusals, generation retention and the rendered nginx route. An offline run admitted a real feed. Local subscription-host Molecule fails at the shared nginx publication step on this Mac with the feature disabled as well, so that scenario relies on CI.
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
| REQ-ROUTING-LISTS-RETIRE | ANS-1794218690815722 | routing-lists-disable.yml and disable.yml retire exact owned paths and preserve masks; nginx-xhttp Molecule in CI | required |
