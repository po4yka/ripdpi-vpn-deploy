---
task_id: EPC-1788891270457728
change: epc-1788891270457728-complete-critical-high-external-acceptance
commit_sha: b5682b9a8b0c30515a1e2576ac4ab385fb29d077
local: passed
local_evidence: Exact protected-main source b5682b9a8b0c30515a1e2576ac4ab385fb29d077 is clean and has deployable digest 5e2512c8a029a92cffc14251daea2ac56e6299ba7d358b536379d17c05753082. Task contracts passed for 9 tasks and 38 steps, strict OpenSpec validation passed, and the owner-only mode-0600 no-write preflight report has SHA-256 58868c86e0785a3d68290a8ab1685068bcfec88fcbfe742e9f90ab342558b1e1. The preflight performed zero provider reads, SSH connections, or mutations.
remote_ci: passed
remote_ci_evidence: Exact post-merge source b5682b9a8b0c30515a1e2576ac4ab385fb29d077 passed push CI run 34263738849 with all 75 jobs successful, CodeQL run 34263737976, Scorecard run 34263738091, and release-please run 34263738004.
dry_run: blocked
dry_run_evidence: Three-host generated inventory plus encrypted production secrets and a private age key are available and no-output SOPS decryption passed. The required mode-0600 exact-alias SSH-context snapshot is absent, the Tailnet backend is Stopped with the local node offline, and no dry-run was started.
staging: blocked
staging_evidence: No provider credential mode is present and no current provider account binding, owner-approved cost ceiling or expiry, unique staging identity, or cleanup reservation exists. No provider read or resource creation was attempted.
live: blocked
live_evidence: The required strict SSH-context and promotion-config snapshots are absent and the Tailnet backend is Stopped with the local node offline. No host or network mutation was attempted.
client: blocked
client_evidence: No current signed RIPDPI artifact or invocation-bound signer or relay handoff is available. Prior source, fixture, and server evidence cannot satisfy current-client four-transport or recurring AmneziaWG acceptance.
artifact: blocked
artifact_evidence: No authenticated primary or independent alert-delivery capability, offsite-storage capability, or isolated restore target is available. No alert, copy, restore, rotation, or pruning action was attempted.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EPC-1788891270457728-001 | EPC-1788891640190305 | Exact protected-main source `b5682b9a` and deployable digest `5e2512c8` passed push CI 75/75, CodeQL, and Scorecard | passed |
| REQ-EPC-1788891270457728-002 | EPC-1788891643660976 | Maintain separate category states and reject closure while any required category lacks scope-matching evidence | pending |
| REQ-EPC-1788891270457728-003 | EPC-1788891640866927 | Guarded staging manifest, account and state binding, approved cost and expiry, exercised node, and post-destroy provider absence | blocked: provider capability and authorization not verified |
| REQ-EPC-1788891270457728-004 | EPC-1788891641535013 | Canonical precheck, fleet dry-run, serial convergence, verify, security-verify, and source-drift outcomes | blocked: strict SSH contexts and online management reachability unavailable |
| REQ-EPC-1788891270457728-005 | EPC-1788891641535013 | Isolated custom-listener rehearsal, recovery path, listener and firewall parity, and unchanged VPN paths before promotion | blocked: isolated staging and SSH capabilities unavailable |
| REQ-EPC-1788891270457728-006 | EPC-1788891642225067 | Current signed artifact and independent authenticated REALITY, XHTTP, Hysteria2, and AmneziaWG traffic observations | blocked: current client and signer or relay handoff unavailable |
| REQ-EPC-1788891270457728-007 | EPC-1788891642225067 | Fresh recurring nonce, revision, source, artifact, traffic, recovery, and cleanup evidence with replay negatives | blocked: current client and disposable executor inputs unavailable |
| REQ-EPC-1788891270457728-008 | EPC-1788891642969936 | Fresh expected-target metrics plus controlled primary and independent alert firing, recovery, rotation, rollback, and cutover | blocked: alert-delivery capability not verified |
| REQ-EPC-1788891270457728-009 | EPC-1788891642969936 | Observed offsite copy and isolated non-pruning restore | blocked: storage capability and restore target not verified |
| REQ-EPC-1788891270457728-010 | EPC-1788891640190305 | Owner-only mode-0600 preflight report `58868c86` checked credential classes and private inputs without values; zero external calls or mutations | passed |
| REQ-EPC-1788891270457728-011 | EPC-1788891640190305 | Successor remains active as blocked with exact provider, SSH, Tailnet, client, alert, and restore capability gaps | passed |
| REQ-EPC-1788891270457728-012 | EPC-1788891643660976 | Thirteen-row predecessor matrix, exact evidence, rollback and cleanup reconciliation, strict validation, and archive readiness | pending |
