---
task_id: EPC-1788891270457728
change: epc-1788891270457728-complete-critical-high-external-acceptance
commit_sha: 52eda3d97feb4b697e1465beee55df2e9f5b3eed
local: blocked
local_evidence: "The clean frozen protected source has deployable digest a86591e11b5fc6d1f5b2b9405089353cc5e177e66ebe85c65062e6a4952fb983 and its complete local checks recorded in the linked bootstrap verification. Current permanent-node strict SSH contexts and promotion inputs remain unavailable; the production certificate also fails the fourteen-day deployment floor."
remote_ci: passed
remote_ci_evidence: "Exact protected source 52eda3d97feb4b697e1465beee55df2e9f5b3eed completed ci, codeql, scorecard and release-please successfully, with 80 post-merge check runs and no failures. Later CI-only integration is not substituted for this runtime source."
dry_run: blocked
dry_run_evidence: "The isolated staging dry-run passed on the frozen source. Permanent-fleet dry-run remains unperformed because strict management access has not been restored."
staging: required
staging_evidence: "The manifest-bound ordinary staging lifecycle passed on 52eda3d9: positive pinned bootstrap, observed dual-path handoff, SSH ownership transaction, dry-run, deploy, verify, security-verify, four authenticated profiles, provider-firewall promotion with state-bound manifest reissue, repeated profiles and fresh AWG handshake, guarded retirement and authenticated server/root-storage absence. A separate fresh controller-loss invocation passed on the same exact source and digest and was provider-cleaned before expiry. The exact-source reboot proof is recorded in the bootstrap verification. The broader custom-listener/live prerequisite still requires reconciliation."
live: blocked
live_evidence: "P0 and P1 provider allowlists were changed only by specifically approved plans; strict public SSH still timed out. P0 rescue returned the original boot and storage without mounting or writing the root disk because both console paths were unavailable. P2 provider credential returned 401. No permanent-node Ansible deploy, verify, security-verify or source-drift was performed."
client: blocked
client_evidence: "Isolated current profiles and pinned runtimes proved authenticated REALITY, XHTTP, Hysteria2 and AmneziaWG before and after provider-firewall promotion, with distinct fresh AWG handshakes. Permanent-fleet traffic and the complete recurring acceptance contract remain unproved."
artifact: required
artifact_evidence: "The owned staging client was canonically de-onboarded, its executor was retired, temporary DNS records and own Tailnet nodes are absent, and private disposable capabilities were removed. Shared temporary ACL and provider capability are preserved for the unrelated active invocation. Production VNC is disabled; a credential exposed during console inspection requires owner rotation. No excluded Android, alert or restore observation is credited."
---

# Verification

## Owner-approved scope

On 2026-09-28 the owner excluded Android installation/device testing, primary
and independent alert drills, and offsite copy/restore. These are exclusions,
not passes. Current profiles and pinned client runtimes still require real
authenticated REALITY, XHTTP, Hysteria2, and AmneziaWG traffic, including a fresh
AWG invocation. Historical category snapshots above remain historical; final
closure must replace them with observed in-scope evidence. The artifact category
now covers post-firewall traffic and guarded client/executor retirement.

## Observed staging lifecycle — 2026-09-28

The frozen runtime source is `52eda3d97feb4b697e1465beee55df2e9f5b3eed`
and its deployable digest is
`a86591e11b5fc6d1f5b2b9405089353cc5e177e66ebe85c65062e6a4952fb983`.
The ordinary disposable invocation completed positive bootstrap and handoff,
SSH ownership, dry-run, deployment, verify and security-verify. Its eight
recorded command log hashes were independently matched after completion.
Authenticated REALITY, XHTTP, Hysteria2 and AWG profiles succeeded both before
and after provider-firewall promotion; both invocations observed fresh AWG
handshakes. The firewall transition preserved resource identities and used a
new state-bound cleanup manifest without extending its deadline.

Canonical de-onboarding retired the owned client and executor. Authenticated
cleanup evidence reports server and root storage absent, no active owned
billing resources, and completion within the approved expiry. Separate current
observations supersede the intermediate checkpoint's remaining-node count:
the ordinary invocation's own ephemeral node and temporary DNS records are
absent; unrelated nodes remain intact.

A separate fresh disposable controller-loss invocation killed durable pending
without confirmation or explicit rollback and passed autonomous recovery,
idle, strict preinstall, pinned public SSH and SFTP on the same source/digest.
Its distinct diagnostic remained absent; the success file and parent retained
modes 0600/0700 and its wrapper input hash matched. It was guardedly destroyed
at 17:32:34 UTC, with fresh provider 404 responses for server and root storage;
its ephemeral node disappeared automatically. The existing exact-source reboot
proof remains a distinct observation.

Only the isolated-resource lifecycle step is completed here. Permanent-fleet
management recovery, custom-listener prerequisite reconciliation, serial
convergence, source drift, production client traffic and final predecessor
closure remain open. No staging source-drift result was observed.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EPC-1788891270457728-001 | EPC-1788891640190305 | Frozen protected-main source `52eda3d9` and deployable digest `a86591e1` passed exact post-merge CI, CodeQL, Scorecard and release-please | passed |
| REQ-EPC-1788891270457728-002 | EPC-1788891643660976 | Maintain separate category states and reject closure while any required category lacks scope-matching evidence | pending |
| REQ-EPC-1788891270457728-003 | EPC-1788891640866927 | Guarded staging manifest, account and state binding, approved cost and expiry, exercised node, and post-destroy provider absence | passed: owned ordinary staging and separate controller-loss resources were exercised and provider-cleaned within the approved window |
| REQ-EPC-1788891270457728-004 | EPC-1788891641535013 | Canonical precheck, fleet dry-run, serial convergence, verify, security-verify, and source-drift outcomes | blocked: all three public and management SSH transports time out and strict contexts are unavailable |
| REQ-EPC-1788891270457728-005 | EPC-1788891641535013 | Isolated custom-listener rehearsal, recovery path, listener and firewall parity, and unchanged VPN paths before promotion | pending: isolated recovery and VPN paths passed; custom-listener prerequisite and live management remain unreconciled |
| REQ-EPC-1788891270457728-006 | EPC-1788891642225067 | Current profiles, pinned runtimes, and independent authenticated REALITY, XHTTP, Hysteria2, and AmneziaWG traffic observations | pending: current fleet client-path evidence required |
| REQ-EPC-1788891270457728-007 | EPC-1788891642225067 | Fresh recurring nonce, revision, source, artifact, traffic, recovery, and cleanup evidence with replay negatives | blocked: current client and disposable executor inputs unavailable |
| REQ-EPC-1788891270457728-008 | EPC-1788891643660976 | Owner-approved scope exclusion dated 2026-09-28; no alert proof claimed | excluded by owner; not passed |
| REQ-EPC-1788891270457728-009 | EPC-1788891643660976 | Owner-approved scope exclusion dated 2026-09-28; retained copies remain intact | excluded by owner; not passed |
| REQ-EPC-1788891270457728-010 | EPC-1788891640190305 | Historical no-write preflight checked credential classes, SOPS inputs and plaintext removal; current console exposure requires owner rotation while VNC is disabled | pending: owner VNC credential rotation |
| REQ-EPC-1788891270457728-011 | EPC-1788891640190305 | Successor remains active with exact permanent-node management, provider, certificate, production-client and final reconciliation gaps | passed |
| REQ-EPC-1788891270457728-012 | EPC-1788891643660976 | Thirteen-row predecessor matrix, exact evidence, rollback and cleanup reconciliation, strict validation, and archive readiness | pending |
