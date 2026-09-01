---
task_id: TST-1786299293097217
change: tst-1786299293097217-complete-recurring-amneziawg-live-acceptance
commit_sha: b8948b427388e21a48cfbf99d521e787783b950d
local: passed
local_evidence: focused AWG identity and refusal tests plus make -j1 check passed; the full gate recorded 2948 Python tests, one existing skip, 55 Bats tests, Rust release tests and Clippy; no live client or VPS was used
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
