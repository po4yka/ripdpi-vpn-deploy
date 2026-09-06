---
task_id: TST-1786299293097217
change: tst-1786299293097217-complete-recurring-amneziawg-live-acceptance
commit_sha: e265689c83ca3ea16b8d84b19574000ea597bd3d
local: passed
local_evidence: focused AWG identity and refusal tests plus the combined-tree make -j1 check passed; the full gate recorded 2969 Python tests, one existing skip, 55 Bats tests, 184 Rust release tests and Clippy; log SHA256 0f31ada651e9c771887691eebb5701add05ac7894f25f0f37840385f38454fe5; no live client or VPS was used
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: "Protocol acceptance does not require a deployment-controller dry-run."
staging: required
staging_evidence: null
live: not_applicable
live_evidence: "One current-revision isolated client/server staging run plus one repeated observation is sufficient; production use is not required."
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TST-1786299293097217-001 | TST-1786299379871208 | Pending | required |
| REQ-TST-1786299293097217-002 | TST-1786299379871208 | Pending | required |
| REQ-TST-1786299293097217-003 | TST-1786299379854550 | Pending | required |
| REQ-TST-1786299293097217-004 | TST-1786299379836822 | Pending | required |

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

## Proportional verification decision — 2026-09-06

Verification follows the portfolio proportional-evidence policy. Source closure does not claim staging or live operation; any delegated operational requirement remains open in the task named in the front matter evidence above.
