---
task_id: SEC-1791471757439452
change: deployment-audit-remediation
commit_sha: null
local: required
local_evidence: Targeted regressions, 104 Terraform native mock tests, 52 Rego tests and 148 template snapshots passed; full make check remains pending.
remote_ci: required
remote_ci_evidence: PR 278 head ad474c842afc7a2a29d9ffac1391bf7b4dd21ec4 completed 80 successful checks and one neutral scan; the fresh-node CI integration awaits a new exact-head run.
dry_run: not_applicable
dry_run_evidence: Source PR only; controller positive and failure orchestration is exercised locally with synthetic inputs, without live inventory or SSH.
staging: not_applicable
staging_evidence: No provider or runtime rollout requested; hosted credential-free Molecule checks validate affected runtime contracts.
live: not_applicable
live_evidence: Production rollout is outside this source remediation PR.
client: not_applicable
client_evidence: No client traffic acceptance is claimed by source remediation.
artifact: required
artifact_evidence: https://github.com/po4yka/ripdpi-vpn-deploy/pull/278 (draft; final source validation in progress)
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-SECRETS | SEC-1791471911428987 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-SECRETS | SEC-1791471912312773 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-POLICY | SEC-1791471912312773 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-RUNTIME | SEC-1791471911428987 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-RUNTIME | SEC-1791471912312773 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-LIFECYCLE | SEC-1791471911428987 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-OPERATORS | SEC-1791471912998245 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-ROLLBACK | SEC-1791471911428987 | Targeted regressions and full source gate pending | required |
| REQ-AUDIT-OPERATORS | SEC-1791471913677997 | Targeted regressions and full source gate pending | required |

## Observed source checks

- Terraform native mock tests: 104 passed across the four provider roots;
  Conftest policy suite: 52 passed. These are credential-free tests, not provider
  or deployed firewall acceptance.
- Template snapshot check: all 148 renders matched after reviewing the affected
  resolver, firewall, Hysteria, honeypot and watchdog outputs.
- Operator regression suite: saved-plan identity and rejection, complete Xray
  comparison, malformed/private configuration redaction, scoped controller calls,
  zone forwarding, version pins and report failure handling passed locally.
- Additional real Ansible service-ownership regressions passed for self-steal,
  CDN, subscription hosting and subscription-only profiles.
- `build-gate -- cargo test --jobs 4 --test deploy_lifecycle`: eight lifecycle
  tests passed. No live inventory, provider or SSH operation was performed.
- `make validate` passed Terraform initialization/validation, secret scanning,
  Ansible production lint and playbook syntax. A subsequent `make check` exposed
  missing coverage declarations for computed honeypot variables; those explicit
  declarations were added and the coverage check passed. Full runs remain incomplete: one exposed a collection-time expiry test defect
  and local Ansible timeouts; the expiry test is fixed and focused reruns passed.
  A later run was stopped after 536 passes while hosted failures were being fixed.
  No complete local make check pass is claimed.
- Native hosted honeypot, baseline and full-stack Molecule passed on the initial
  PR head. The local amd64-on-arm64 Molecule attempt was superseded by that
  native evidence. Current-head hosted validation remains required.

## Fresh-node deployment integration

Both credentialed workflows now call the same protected fresh-node lifecycle.
It imports a per-run private SSH host-key seed through the pinned provider,
checks its digest before SSH bootstrap, executes recovery exercises and the
canonical Tailnet/ownership controllers, then deploys with actual protocol
promotion and exact-resource teardown. Each matrix profile owns a new guest.

The protected environment currently lacks the four required CI secrets. No live
provider run is claimed. The positive capability is implemented and receives
portable orchestration, native loopback SSH/seed mount, real credential-generator,
Terraform mock and workflow coverage. Native and exact-head hosted checks remain
required before this source PR is marked ready.

Independent infrastructure and runtime reviews triggered fixes for shell
precedence after failed seed installation, duplicate seed state records,
structural SNI YAML parsing and repeated soft cancellation during cleanup.
The final reviewed source has no outstanding confirmed findings. A hard runner
termination can still prevent cleanup; the runbook requires provider inspection.

## Hosted regression follow-up

The first hosted Python shards exposed effective-default mismatches in maintenance,
standalone TLS fallback lookup and old isolated Xray fixture assumptions. These are
corrected with 165 profile/service/Tailnet tests and 25 Xray tests passing locally.
The Xray tests execute the production validation helper and now reject malformed
rotation candidates instead of replacing validation with a copy-only command.

Native split-hop verification now checks the shared forwarding file and actual
kernel forwarding. Observability failure tests retain their original activation
phase through the outer rescue and still verify restored runtime readiness.
The related runtime suite passed 91 tests; affected-role lint passed 49 files.
All hosted failures must pass on the updated PR head before source verification
can be accepted.
