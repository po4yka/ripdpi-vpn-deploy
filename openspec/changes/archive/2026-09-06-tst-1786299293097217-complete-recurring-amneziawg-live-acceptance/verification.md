---
task_id: TST-1786299293097217
change: tst-1786299293097217-complete-recurring-amneziawg-live-acceptance
commit_sha: ca5be8c841139ffa3d2a544e64d13b76f57bc694
local: not_applicable
local_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
staging: not_applicable
staging_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
live: not_applicable
live_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
client: not_applicable
client_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
artifact: not_applicable
artifact_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TST-1786299293097217-001 | TST-1786299379871208 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-TST-1786299293097217-002 | TST-1786299379871208 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-TST-1786299293097217-003 | TST-1786299379854550 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-TST-1786299293097217-004 | TST-1786299379836822 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |

## Offline deploy-side safeguards

The combined source candidate requires a root-private, no-follow client
identity descriptor beside the local runner configuration. The descriptor binds
a 40-hex RIPDPI source SHA and immutable artifact SHA-256 into every runner
manifest, and validators can bind both expected values. Invalid or absent
descriptors fail as non-PASS. Local launcher preflight refusals for missing
tools, lock contention, invalid configuration or runner, unsafe source, and
source mismatches create redacted `INFRA_UNAVAILABLE` evidence without replacing
`latest.json`.

Focused local contract evidence passed in
`tests/unit/test_real_vps_awg_nat_lane.py`. This is offline source evidence only;
it does not provide a client descriptor, artifact, VPS, provider credentials,
real traffic, or an observed recurring run.
