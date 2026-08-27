---
task_id: SEC-1787843484501357
change: sec-1787843484501357-upcloud-firewall-activation
commit_sha: null
local: passed
local_evidence: "2026-08-27: make validate passed; all 96 native Terraform tests and 45 Conftest policy tests passed; 69 focused pytest regressions passed; actionlint, strict offline zizmor, task validation and diff checks passed."
remote_ci: required
remote_ci_evidence: null
dry_run: blocked
dry_run_evidence: Exact-source live plan requires separately authorized provider access; no apply is authorized.
staging: not_applicable
staging_evidence: Native mock tests exercise source behavior; the existing node rollout is a separate required live gate.
live: blocked
live_evidence: Recovery reported manually activated rules and restored DNS; that is not evidence of applying this source revision.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No distributable artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-UPCLOUD-FIREWALL-ACTIVE | SEC-1787848592308718 | Baseline RED: 21 pass / 2 fail; updated UpCloud suite: 38 pass / 0 fail | passed |
| REQ-UPCLOUD-DNS-REPLIES | SEC-1787848592308718 | Native rule shape/order/negative inputs; 13 listener tests; isolated primary-selector mutation rejected | passed |
| REQ-UPCLOUD-FIREWALL-SAFE-ROLLOUT | SEC-1787848592344772 | Separately authorized exact-source plan and live acceptance | blocked |

Source tests and independent review do not close the live acceptance step.

## Observed source checks

On 2026-08-27 the implementation agent observed 38 UpCloud native mock tests
passing after a baseline RED of two failures. Native mock interface addresses
are shared across repeated blocks, so the separate listener regression evaluates
the actual extracted HCL selector with distinct fixture addresses through an
isolated Terraform console. Changing its index from zero to one in a temporary
source copy failed as expected; this is offline behavior proof, not live proof.

The primary agent additionally observed 69 listener/provider/environment and
workflow regression tests passing, plus actionlint and strict offline zizmor.
Independent read-only review found no blocking defect. The primary agent ran
`make validate` successfully, including all four provider validations, gitleaks,
Ansible production lint (zero failures/warnings), and syntax checking. All
96 native Terraform tests and 45 Conftest policy tests passed. The additional
operator `tf-conftest` plan stopped before provider access because this isolated
worktree intentionally has no production tfvars; no live plan or apply was run.
Exact-SHA hosted CI remains required.
