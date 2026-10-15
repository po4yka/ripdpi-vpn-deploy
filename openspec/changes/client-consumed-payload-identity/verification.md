---
task_id: "SCR-1791618188806822"
change: "client-consumed-payload-identity"
commit_sha: null
local: "required"
local_evidence: "127 final drift/registry/emitter/expiry cases, 279 transaction regressions and 49 caller/gate cases passed without selected skips; full source gate remains in progress"
remote_ci: "required"
remote_ci_evidence: "Initial source e08957b987d5dd4c49e3c4cf33420f846deb8c84 exposed same-second refresh and obsolete shell-reader fixtures; corrected exact-source checks remain required"
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "isolated native source acceptance owns this change; fleet rehearsal requires separate authorization"
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "required"
client_evidence: "real test-only SOPS/age issuance, canonical payload comparison, multi-host refresh and official sing-box parser passed locally; hosted native clients pending"
artifact: "required"
artifact_evidence: "schema, bundle, secrets coverage, encrypted synthetic fixture parity and private marker/authority regressions passed; exact committed source and remote checks pending"
---

# Verification

## Requirement evidence

The named local tests below were observed on the implementation worktree. Exact committed-source CI evidence and the complete local source gate remain required; no provider, fleet or production acceptance is claimed.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DRIFT-CHECK | SCR-1791618347514825 | test_client_drift.py executes the shared renderer and real SOPS/age for consumed credentials, endpoints, bindings, parameters, expiry and unrelated edits. | passed locally |
| REQ-PROTO-IDENTITY-ISSUANCE | SCR-1791618349798761 | Real test-only SOPS issuance/refresh compares exact canonical delivery, selected AWG host and persisted private per-host sources; candidate encryption failure preserves original authority before remote publication. | passed locally |
| REQ-PROTO-IDENTITY-PRIVACY | SCR-1791618352269556 | Private marker checks cover subprocess argv/environment and diagnostics; unsafe modes, links, FIFOs, malformed reads and a real child deadline refuse categorically. Authority lifecycle is documented in docs/SECRETS.md. | passed locally |
| REQ-PROTO-IDENTITY-AUTHORITY | SCR-1791618352269556 | Actual SOPS authority creation, loss, valid rotation, mismatched generation, malformed key/version and ciphertext-only re-encryption are exercised. Inspection retains ciphertext and creates no authority. | passed locally |

## CI follow-up

The first hosted unit run exposed an idempotent refresh boundary: when the
registry is identical within the same timestamp second, encrypted publication
has no candidate but delivery still needs its verified callback. The callback
now runs under the stable lock for unchanged state, with a real SOPS fixed-clock
regression that proves ciphertext retention and actual redelivery. Candidate
write failure also retains existing authority and the previous delivered bytes.
Audit, SOPS-selection and retirement assertions follow the actual Python writer;
the expiry fixture now supports encrypted registry staging and verification.
The affected suites passed 279 cases, the caller/gate suite passed 49 cases,
and the explicit same-second/atomic-failure rerun passed both cases.

Final dispatcher validation passed 127 complete drift, registry, emitter,
host-selection and expiry cases without selected skips. Real SOPS cases retain
leading-dash device names through both emitters, issuance and Make inspection;
a leading-dash bearer remains one literal refresh value. Dispatchers preserve
the client-first shell surface and delimit data before Python parsing.
