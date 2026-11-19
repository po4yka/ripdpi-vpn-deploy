---
task_id: MON-1795086175387484
change: mon-1795086175387484-continuous-protocol-probes-d3
commit_sha: 7b029144
local: passed
local_evidence: Second security review fixes at d2abaf37, b9783d95 and cba6b1e8 pass the local checks in the section of that name at cba6b1e8. Implementation at 81734fb5 and 7b029144. Focused pytest of 85 observability, monitoring, AWG, Hysteria, transport-admission, governance and agent-instruction files exit 0 after the CLAUDE.md path fix (2475 tests, one stale-path failure fixed before commit); full `tests/unit` plus `scripts/tests` exit 1 with 12290 passed and one failure (`test_transport_p2_lifecycle[amneziawg]`), fixed by moving the AWG exporter include into the monitoring role and rerun green; `scripts/render-snapshots.py` exit 0 (193 templates); `ansible-lint --offline ansible` exit 0; yamllint on the touched roles exit 0; `make docs-check` exit 0; `./taskctl openspec cli validate --strict` exit 0. Logs under the run directory named in the task handoff. The Molecule scenarios for amneziawg and hysteria were not run: they pull a registry image that is not present locally. `test_adapter_accepts_shared_textfile_directory_and_publishes_collector_readable_output` fails locally with capability-unavailable and fails identically on a clean export of the base revision.
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
| REQ-PROBE-ORIGIN | MON-1795086235920434 | `test_relay_accepts_each_family_only_from_its_owner`, `test_an_enrolled_node_cannot_send_probes_by_spoofing_the_collector`, `test_the_ingress_label_name_is_private_and_shared_by_ingress_and_relay` (relay model with vmagent duplicate-label order) | passed (local, cba6b1e8) |
| REQ-PROBE-MANIFEST | MON-1795086307543709 | `test_probe_metric_families_are_declared_in_canonical_manifest` (failed before the manifest entries existed), `_assert_declared` in the exporter tests | passed (local, 81734fb5) |

## Second security review (1a159bc1..0f3b138b)

An independent security review of the whole field-analytics range returned REQUEST CHANGES. The findings that this change owns are fixed below, each in its own commit with a regression test that fails before the fix. Verdict after the fixes: APPROVE for local evidence; staging, remote CI and Molecule stay open as listed above.

- Finding 2 (MEDIUM), fixed in b9783d95: the probe node exception read the first `ingress_node`, which a payload can supply; safety rested on vmagent's duplicate collapse. The identity now travels under the private ingress label, the relay drops payload `node` and `ingress_node`, and the unit relabel model represents duplicate labels in vmagent order. The private-label and ingress tests fail before; the dependency on vmagent adding extra labels is recorded in `ansible/roles/observability_control_plane/CLAUDE.md`.
- Finding 1 (MEDIUM), fixed in cba6b1e8: the relay drops probe series from every identity except the collector agent and field-report series from every identity outside `field_report.source_nodes` (enable refuses an unenrolled entry); `vpn_awg_*` and `vpn_hysteria_*` stay open to every node under its own identity, which is all they describe. The owner and spoofing tests fail before.
- Finding 10 (MEDIUM), fixed in d2abaf37: the Hysteria traffic exporter runs as `vpn-hysteria-exporter` with `SystemCallFilter`, `MemoryDenyWriteExecute`, `ProtectProc=invisible`, `ProcSubset=pid` and `UMask=0027`; a textfile left by the root exporter is handed to the account. `test_hysteria_exporter_unit_runs_unprivileged_with_the_hardening_floor` fails before.

At cba6b1e8 (logs in the session run directory runs-secfix-d7, verify-*.log): focused pytest of 17 files (contract, ingest, rotation, exporters, relay render, alert rules with promtool 3.15.1, observability contract, agent render, retention, secrets schema, audit hooks, agent instructions, governance, docs index, journald, operator) exit 0, 895 passed; `ansible-lint --offline` on subscription-host, observability_control_plane and hysteria exit 0; yamllint on the same roles exit 0; shellcheck exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; every contract fixture validates and every negative fixture is rejected exit 0; `./taskctl openspec cli validate --strict` exit 0 for D1 to D5 and D7; `./taskctl validate` exit 0. Each fix commit carries a regression test that failed on the code before it (red runs in the same directory). `make molecule-test` and `make check` were not run.
