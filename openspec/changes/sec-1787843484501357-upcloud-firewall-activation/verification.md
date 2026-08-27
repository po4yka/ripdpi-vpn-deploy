---
task_id: SEC-1787843484501357
change: sec-1787843484501357-upcloud-firewall-activation
commit_sha: null
local: passed
local_evidence: "2026-08-27: make validate passed; 96 native Terraform tests, 45 Conftest policy tests and 1056 unit tests passed (one existing network-scanner skip). These checks do not prove complete stateless return paths."
remote_ci: passed
remote_ci_evidence: "PR 110 at 4110fa1dddb81d070c4c05c05b23c4f6a47cc9a9: CI 33095973167 passed; 62 checks succeeded and one was neutral. Merge remains blocked by a valid P1 review finding."
dry_run: passed
dry_run_evidence: "Operator-owned isolated plan at 9b02486ee76819e2a69447e26a94c2753340d06b exited 2 (successful diff): server and SSH trigger no-op, only 16-rule update, no replacement, policy equal after optional-field normalization. No apply."
staging: not_applicable
staging_evidence: Native mock tests exercise source behavior; the existing node rollout is a separate required live gate.
live: blocked
live_evidence: "No source apply or complete forwarding acceptance. Review found missing generic TCP/UDP and IPv6 return paths; unconditional activation is not deployment-ready."
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
The initial independent review approval was withdrawn after the P1 finding below.
The primary agent ran
`make validate` successfully, including all four provider validations, gitleaks,
Ansible production lint (zero failures/warnings), and syntax checking. All
96 native Terraform tests and 45 Conftest policy tests passed. The additional
operator `tf-conftest` plan stopped before provider access because this isolated
worktree intentionally has no production tfvars; no live plan or apply was run.
The full local unit suite subsequently passed: 1056 passed and one existing
network-scanner skip. The original CI failed only because the documented test
count had not been incremented; the documentation fix passed CI 33095973167.

## Blocking review finding

PR 110 review correctly identified that the provider's Public/Utility firewall
is stateless. A reply from remote TCP/443 to guest TCP/40000 matches neither a
listener rule nor a DNS reply rule, then reaches the terminal deny. Generic
TCP/UDP VPN forwarding and IPv6 return traffic need a complete policy too.
Documenting this as a residual risk was insufficient for unconditional activation.
The source is not approved for merge or apply; the task stays open.

The operator-owned exact-source plan confirms that the existing live policy
matches the candidate after rule-order/comment/optional-field normalization.
It does not prove that either policy supports every required traffic path.
Changing the default to disable the firewall would weaken an already-enabled
node and is not an acceptable workaround. A broader return policy requires
explicit network-owner coordination and separate live forwarding acceptance.
