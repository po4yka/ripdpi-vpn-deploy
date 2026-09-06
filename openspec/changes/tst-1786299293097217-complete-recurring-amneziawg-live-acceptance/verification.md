---
task_id: TST-1786299293097217
change: tst-1786299293097217-complete-recurring-amneziawg-live-acceptance
commit_sha: e265689c83ca3ea16b8d84b19574000ea597bd3d
local: passed
local_evidence: focused AWG identity and refusal tests plus the combined-tree make -j1 check passed; the full gate recorded 2969 Python tests, one existing skip, 55 Bats tests, 184 Rust release tests and Clippy; log SHA256 0f31ada651e9c771887691eebb5701add05ac7894f25f0f37840385f38454fe5; no live client or VPS was used
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

The deploy-side v4 candidate provisions only a root-private Ed25519 verification
key. Each invocation creates an atomic five-minute nonce request and consumes
one canonical, single-link, mode-`0600` signed handoff bound to that nonce and
invocation. Its embedded acceptance binds exact
RIPDPI source, APK, report and correlation digests, a bounded time window,
AmneziaWG transport and all required outcomes. Engine commit/binary identity is
derived separately from the immutable `amneziawg-go` toolchain. Invalid,
mutated, stale, replayed or incomplete descriptors fail as non-PASS. Local
launcher preflight and runtime unavailable outcomes do not replace
`latest.json`; recurring publication also requires a later, distinct
invocation/report/correlation.

The client signer/relay is not implemented by this deploy-side candidate.
Therefore this is not live client evidence and neither the initial nor recurring
acceptance execution step is closed.

Focused local contract evidence passed in
`tests/unit/test_real_vps_awg_nat_lane.py`. This is offline source evidence only;
it does not provide the client signer/relay, artifact, VPS, provider credentials,
real traffic, or an observed recurring run.
