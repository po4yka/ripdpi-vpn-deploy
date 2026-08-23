---
task_id: OPS-1787496414433523
change: ops-1787496414433523-deploy-path-integrity
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: no separate staging environment exists; CI molecule plus a live-inventory dry-run cover gate behavior
live: required
live_evidence: null
client: not_applicable
client_evidence: no client-facing emitter or vpnd surface changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TAGGED-GUARDS | OPS-1787496118906514 | pytest tagged-guard case + manual --tags p0 run showing assert firing | pending |
| REQ-BOOTSTRAP-GATED-DEPLOY | OPS-1787496118906556 | make -n deploy showing readiness prerequisite before playbook | pending |
| REQ-BOUNDED-WAIT | OPS-1787496118906208 | wait script bound test with unreachable marker fixture | pending |
| REQ-COHORT-SLUG-VALIDATION | OPS-1787496118906369 | render-inventory negative test with unknown slug | pending |
| REQ-SSH-ALLOWLIST-FAILFAST | OPS-1787496118906156 | terraform plan with empty allowlist failing validation block | pending |
| REQ-UNIQUE-HOST-ALIASES | OPS-1787496118906901 | render-inventory duplicate-alias negative test | pending |
| REQ-ROTATION-PREV-CONTRACT | OPS-1787496118906340 | rotation run leaving .prev byte-identical to pre-rotation config | pending |
| REQ-ROLLBACK-VALIDATE-FIRST | OPS-1787496118906432 | rollback rehearsal with incompatible target failing before symlink flip | pending |
| REQ-SMOKE-CLEANUP | OPS-1787496118906646 | smoke-test failure-path run leaving no transient units/workdir | pending |
| REQ-MAINTENANCE-SERVICE-GATE | OPS-1787496118906956 | os-maintenance check-mode run on host without the external unit | pending |
| REQ-TOGGLE-DEFAULT-PARITY | OPS-1787496118906821 | pytest parity sweep over playbooks vs all.yml | pending |
| REQ-LOCALE-INDEPENDENT-GATE | OPS-1787496118906614 | simulation under non-English LC_ALL passing the gate | pending |
| REQ-DECLARED-TOGGLE-SURFACE | OPS-1787496118906731 | grep of consumed enable_* keys vs all.yml defaults in pytest | pending |

## Gates

- Local: pytest named cases, shellcheck on touched scripts, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Dry-run: `make dry-run` against live inventory including the new gates.
- Live: one deploy-path cycle exercising wait gate, rotation .prev, and rollback rehearsal order.
