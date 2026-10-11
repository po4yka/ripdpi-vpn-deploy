---
task_id: SCT-1791617687019287
change: transport-input-semantics
commit_sha: 6202c7ec93c075b6b5fd3b40065204e4f59d9461
local: required
local_evidence: complete affected tests, exact native cases and full source gates after implementation
remote_ci: required
remote_ci_evidence: terminal required checks on the exact integrated implementation SHA
dry_run: not_applicable
dry_run_evidence: source-only capability; no controller or provider execution in this task
staging: not_applicable
staging_evidence: isolated native source acceptance owns this change; fleet rehearsal requires separate authorization
live: not_applicable
live_evidence: no production rollout is part of this source task
client: required
client_evidence: real isolated consuming-client behavior named in the requirements; not host activity alone
artifact: required
artifact_evidence: validated contracts, private redacted outputs and requirement-to-test evidence on the exact implementation SHA
---

# Verification

## Requirement evidence

Source observations below were obtained in the dedicated implementation worktree based on `8828ffebdbe42ad17d5f98433db78db1a0aa95eb` and committed at `6202c7ec93c075b6b5fd3b40065204e4f59d9461`. Terminal hosted checks on the integrated implementation remain pending; this record does not claim deployment or fleet acceptance.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-INPUT-COHORT | SCT-1791617711124536 | Complete affected portable suite: 383 passed, zero skips; missing/empty/unknown/duplicate cohort and actual controller early-refusal cases. Exact Xray 26.3.27 accepted the rendered candidate in the complete native suite. | source cases passed |
| REQ-PROTO-INPUT-AWG | SCT-1791617712074772 | Complete portable consumer/semantic cases plus real AWG TUN/setconf host and explicit routed-prefix acceptance using source-pinned Go v0.2.12 and tools v1.0.20241018. Existing legacy consumers validate their consumed view; instance-selection changes remain separately tracked. | source cases passed |
| REQ-PROTO-INPUT-HYSTERIA | SCT-1791617711124536 | Complete lifecycle/schema negative and privacy cases; exact Hysteria v2.9.0 accepted the installed validator and started the owned HTTPS proxy candidate. | source cases passed |
| REQ-PROTO-INPUT-PRIVACY | SCT-1791617713075181 | Complete floor/schema/marker cases passed in the 383-test portable suite; coverage resolves 119 variables across 236 references; all 152 snapshots match. Complete affected Molecule scenarios passed; final full source gate passed with 5907 portable tests and 22 subtests. | source cases passed |

## Observed validation

- Complete 13-file affected portable suite: 383 passed with `--fail-on-skip`; pinned Python 3.12 and genuine SOPS/age binaries were used.
- Complete `test_transport_semantics_native.py`: 3 passed with `--fail-on-skip` on owned Debian 13 Linux amd64 / Python 3.13.5, with checksum-verified Xray/Hysteria and exact source-pinned AWG builds. This proves parser/startup and real AWG control-client behavior, not fleet protocol traffic.
- `scripts/check-secrets-coverage.py`: passed (119 variables, 236 references).
- `scripts/render-snapshots.py`: passed (152 templates); no snapshot refresh needed.
- Independent security/spec review: APPROVE after correction of duplicate names, consumed AWG view and native fixture prerequisites.
- Strict OpenSpec validation, shellcheck and `git diff --check`: passed.
- Complete Molecule scenarios: Xray, Hysteria and AmneziaWG passed convergence, idempotence, verification and destruction. Hysteria also passed predictive check mode, malformed-candidate refusal and fixture upgrade. Existing optional missing-prepare warnings were observed; no cases were focused or disabled.
- Final `make check` through `build-gate` and pinned `mise`: passed. Complete portable suite: 5907 passed, 126 native cases deselected into their separate lane, 22 subtests passed, zero skips; Terraform validation/mock tests/policies, shell tests, workflow checks, secrets/schema/render checks, clippy, MSRV and complete Rust CLI tests passed.
- The complete exact native three-test file was rerun against the final duplicate-name guard: 3 passed, zero skips.
- Independent review approved globally unique client-name admission and its real normal/check-mode refusal regression; the complete semantics/schema suite passed 175 tests.
- An earlier complete run reported one blocked result in the unchanged REALITY monitor target-change case. Complete module reruns and 12 bounded diagnostic sequences passed; the final full run passed. No cause was confirmed. Its unchanged assertion now includes the existing redacted report on failure, and the final runner retained isolated diagnostic state. No retries, timeout changes, scanner changes or assertion weakening were introduced.
- Isolated inventory/topology/controller/bootstrap/SOPS repair coverage: 273 passed; ownership/native-CI/semantic fixture coverage: 166 passed; complete emitter coverage: 33 passed. Genuine jq avoided inactive-shim startup latency without changing the 20-second test timeout.
- Staged gitleaks after those test corrections: passed, no leaks found.
- Ruff through the workstation shim was unavailable; no Ruff result is claimed.
