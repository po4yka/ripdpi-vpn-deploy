---
task_id: MON-1795086175387484
change: mon-1795086175387484-continuous-protocol-probes-d3
commit_sha: 7b029144
local: passed
local_evidence: Implementation at 81734fb5 and 7b029144. Focused pytest of 85 observability, monitoring, AWG, Hysteria, transport-admission, governance and agent-instruction files exit 0 after the CLAUDE.md path fix (2475 tests, one stale-path failure fixed before commit); full `tests/unit` plus `scripts/tests` exit 1 with 12290 passed and one failure (`test_transport_p2_lifecycle[amneziawg]`), fixed by moving the AWG exporter include into the monitoring role and rerun green; `scripts/render-snapshots.py` exit 0 (193 templates); `ansible-lint --offline ansible` exit 0; yamllint on the touched roles exit 0; `make docs-check` exit 0; `./taskctl openspec cli validate --strict` exit 0. Logs under the run directory named in the task handoff. The Molecule scenarios for amneziawg and hysteria were not run: they pull a registry image that is not present locally. `test_adapter_accepts_shared_textfile_directory_and_publishes_collector_readable_output` fails locally with capability-unavailable and fails identically on a clean export of the base revision.
remote_ci: required
remote_ci_evidence: Not run; no push is authorized.
dry_run: required
dry_run_evidence: Not run; needs operator authorization and a live inventory. Rendered inputs change only behind opt-in toggles (exporters) and on the collector (adapter, relay, rules).
staging: required
staging_evidence: Not run; no staging node or deployment is authorized. Needed: enable the adapter, the AWG and Hysteria2 exporters on a staging node, then show the four protocol series with the probed node label, a stopped-sentinel staleness alert, and exporter textfiles without peer keys or user names.
live: not_applicable
live_evidence: Enabling on production is a separate operator decision.
client: not_applicable
client_evidence: Server-side metrics; client evidence is owned by D7.
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROBE-CONTINUOUS | MON-1795086235920434 | `test_stale_probe_is_unknown_and_leaves_other_vantages_unaffected`, `test_unknown_verdict_publishes_no_success_value`, promtool case for `ObservabilityProtocolProbeStale` | passed (local, 81734fb5) |
| REQ-PROBE-AUTH | MON-1795086235920434 | `test_probe_success_uses_protocol_node_and_vantage_labels_only` (amneziawg `error` verdict records 0 for that protocol only) | passed (local, 81734fb5) |
| REQ-AWG-AGGREGATE | MON-1795086265502933 | `test_awg_exporter_publishes_only_fresh_and_total_counts` (3 peers, 2 fresh; no key or interface in output or logs) | passed (local, 7b029144) |
| REQ-HY2-AGGREGATE | MON-1795086286466850 | `test_hysteria_exporter_sums_traffic_without_user_identifiers`, `test_hysteria_exporter_reports_failure_metric[api-down]` | passed (local, 7b029144) |
| REQ-PROBE-MANIFEST | MON-1795086307543709 | `test_probe_metric_families_are_declared_in_canonical_manifest` (failed before the manifest entries existed), `_assert_declared` in the exporter tests | passed (local, 81734fb5) |
