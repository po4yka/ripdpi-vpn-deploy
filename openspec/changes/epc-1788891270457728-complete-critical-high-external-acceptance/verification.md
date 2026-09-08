---
task_id: EPC-1788891270457728
change: epc-1788891270457728-complete-critical-high-external-acceptance
commit_sha: null
local: required
local_evidence: "Planning-time preflight on 2026-09-08 confirmed the pinned prerequisites are installed and current origin/main 3a7a48220e89e99e4d2f96125941eecfcf281479 has successful push CI, CodeQL, Scorecard, and release-please runs. This successor change is not yet committed or integrated, so no exact-source local acceptance is claimed."
remote_ci: required
remote_ci_evidence: null
dry_run: blocked
dry_run_evidence: "The clean successor worktree has no generated inventory or runtime secrets, the standard SOPS age key file is absent, strict SSH contexts have not been selected, and the local Tailscale backend reports Stopped with no online self or peers. No dry-run was started."
staging: blocked
staging_evidence: "No provider credential is present in this task environment; no current provider account, cost ceiling, expiry, unique staging identity, cleanup reservation, or state ownership has been verified. No provider read or resource creation was attempted."
live: blocked
live_evidence: "No current reachable inventory or strict SSH-context set is available in the clean worktree, runtime secrets cannot yet be decrypted there, and Tailscale is stopped. No host or network mutation was attempted."
client: blocked
client_evidence: "No current signed RIPDPI artifact or invocation-bound signer or relay handoff has been provided to this task. Prior source, fixture, and server evidence cannot satisfy current-client four-transport or recurring AmneziaWG acceptance."
artifact: blocked
artifact_evidence: "No authenticated alert-delivery or offsite-storage capability and no isolated restore target has been verified in this task environment. No alert, copy, restore, rotation, or pruning action was attempted."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EPC-1788891270457728-001 | EPC-1788891640190305 | Freeze a clean protected-main commit, deployable digest, and exact required-check runs before external execution | pending |
| REQ-EPC-1788891270457728-002 | EPC-1788891643660976 | Maintain separate category states and reject closure while any required category lacks scope-matching evidence | pending |
| REQ-EPC-1788891270457728-003 | EPC-1788891640866927 | Guarded staging manifest, account and state binding, approved cost and expiry, exercised node, and post-destroy provider absence | blocked: provider capability and authorization not verified |
| REQ-EPC-1788891270457728-004 | EPC-1788891641535013 | Canonical precheck, fleet dry-run, serial convergence, verify, security-verify, and source-drift outcomes | blocked: inventory, secrets, SSH contexts, and reachability unavailable |
| REQ-EPC-1788891270457728-005 | EPC-1788891641535013 | Isolated custom-listener rehearsal, recovery path, listener and firewall parity, and unchanged VPN paths before promotion | blocked: isolated staging and SSH capabilities unavailable |
| REQ-EPC-1788891270457728-006 | EPC-1788891642225067 | Current signed artifact and independent authenticated REALITY, XHTTP, Hysteria2, and AmneziaWG traffic observations | blocked: current client and signer or relay handoff unavailable |
| REQ-EPC-1788891270457728-007 | EPC-1788891642225067 | Fresh recurring nonce, revision, source, artifact, traffic, recovery, and cleanup evidence with replay negatives | blocked: current client and disposable executor inputs unavailable |
| REQ-EPC-1788891270457728-008 | EPC-1788891642969936 | Fresh expected-target metrics plus controlled primary and independent alert firing, recovery, rotation, rollback, and cutover | blocked: alert-delivery capability not verified |
| REQ-EPC-1788891270457728-009 | EPC-1788891642969936 | Observed offsite copy and isolated non-pruning restore | blocked: storage capability and restore target not verified |
| REQ-EPC-1788891270457728-010 | EPC-1788891640190305 | Environment or encrypted credential inputs and owner-only identity-bound private evidence preflight | pending |
| REQ-EPC-1788891270457728-011 | EPC-1788891640190305 | Current blockers remain explicit and task status remains active rather than done or dropped | pending |
| REQ-EPC-1788891270457728-012 | EPC-1788891643660976 | Thirteen-row predecessor matrix, exact evidence, rollback and cleanup reconciliation, strict validation, and archive readiness | pending |
