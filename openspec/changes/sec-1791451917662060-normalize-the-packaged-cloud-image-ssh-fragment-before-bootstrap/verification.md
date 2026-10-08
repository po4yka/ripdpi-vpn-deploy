---
task_id: SEC-1791451917662060
change: sec-1791451917662060-normalize-the-packaged-cloud-image-ssh-fragment-before-bootstrap
commit_sha: bb171af8385396729a0d75a9e0ca1f9aa435d008
local: passed
local_evidence: "Full make check exit 0 at bb171af8385396729a0d75a9e0ca1f9aa435d008; 5194 Python tests, 20 subtests and remaining portable gates passed."
remote_ci: passed
remote_ci_evidence: "CI run 37760701503 at bb171af8385396729a0d75a9e0ca1f9aa435d008: terminal success, 38 successful and 9 dependency-selected skipped checks."
dry_run: passed
dry_run_evidence: "Exact repair check-mode passed; clean replacement plan confirmed five creates, current SSH /32 and exact reviewed helper bytes."
staging: not_applicable
staging_evidence: No new paid staging; real first-boot candidate and interruption regression cover this narrow helper change.
live: passed
live_evidence: "Fresh replacement a89c0033-78e4-4b72-b545-659033b6b53c: cloud-init exit 0, actual marker, canonical fragments, effective hardening and independently pinned SSH passed."
client: not_applicable
client_evidence: Bootstrap changes no VPN protocol or client interface; fleet client acceptance remains separate.
artifact: passed
artifact_evidence: "Implemented helper and 67 focused regressions committed at bb171af8385396729a0d75a9e0ca1f9aa435d008."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-IMAGE-OWNER | SEC-1791452040981214 | Focused positive/idempotent regression | passed |
| REQ-IMAGE-REFUSAL | SEC-1791452040981214 | Changed content, unsafe file and unknown owner regressions | passed |
| REQ-IMAGE-ROLLBACK | SEC-1791452040981214 | Validation failure and process interruption regressions | passed |
| REQ-IMAGE-OWNER | SEC-1791452041489847 | Exact source local/CI gates and real clean first-boot readiness | passed |

## Observed limitation

The failed candidate's final-stage retry returned nonzero and skipped the
per-instance script; it is not positive bootstrap evidence. The fresh
replacement completed actual first boot from the validated helper source.
Full P0/P1/P2 protocol and publication acceptance remains separate.
