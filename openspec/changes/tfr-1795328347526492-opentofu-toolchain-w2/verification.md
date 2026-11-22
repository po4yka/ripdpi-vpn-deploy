---
task_id: TFR-1795328347526492
change: tfr-1795328347526492-opentofu-toolchain-w2
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No Ansible input changes.
staging: not_applicable
staging_evidence: The production read-only plan is the live gate; staging roots use the same code.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TOFU-PIN | TFR-1795328401186589 | toolchain-pin test; stub-only `PATH` script test | planned |
| REQ-TOFU-LOCKS | TFR-1795328413365163 | `tofu init` on a clean checkout in CI | planned |
| REQ-TOFU-CHECKS | TFR-1795328425689060 | `make tf-test`, `make tf-policy-verify`, `make tf-conftest` | planned |
| REQ-TOFU-STATE-COMPAT | TFR-1795328448740009 | no-change plan receipts per root in the ops repository | planned |
