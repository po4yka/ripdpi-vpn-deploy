# SEC-1791471757439452: Repair deployment audit security and lifecycle defects

## Objective

Restore secure positive deployment, policy, drift and runtime lifecycle behavior for all audited cases.

## Ownership

- Runtime worker: ansible roles/playbooks except honeypot, role CLAUDE notes and dedicated runtime regression tests; confirmed CI Tailnet-source binding in deploy-controller, disposable promotion and Linux sentinel integration, and dedicated tests.
- Infrastructure worker: terraform/policy, scripts/validate-secrets.py, scripts/tf-policy-test.sh, scripts/check-tf-plan.sh, ansible/roles/honeypot, dedicated policy/secrets/honeypot tests and subtree notes; per-run private SSH seed helper, UpCloud seed storage/import and cloud-init key installation, cleanup-manifest support, dedicated tests and affected subtree notes.
- Primary: Makefile, remaining operator scripts, vpnd, tf-policy workflow, shared tests/snapshot files, root/shared docs and scripts/CLAUDE.md; unattended CI orchestrator, real-VPS and matrix workflows, workflow tests and CI runbook; all task/spec lifecycle and commits.
- Shared-file changes are requested from the primary before editing. Workers preserve each other's changes and do not stage or commit.

## Execution

- [x] SEC-1791471911428987 Repair runtime security and lifecycle behavior with regressions #bug !high @item:SEC-1791471757439452
- [x] SEC-1791471912312773 Repair provider policy and secret validation with regressions #bug !high @item:SEC-1791471757439452
- [x] SEC-1791471912998245 Repair operator controller integration drift and initialization with regressions #bug !high @item:SEC-1791471757439452
- [x] SEC-1791471913677997 Integrate independent review and exact source validation for the pull request #bug !high @item:SEC-1791471757439452

## Verification

Targeted executable regressions per slice, reviewed template snapshots, make check,
independent source review and exact-head hosted PR checks. Dry-run controller
orchestration uses isolated synthetic inputs; real staging/live/client acceptance
is not part of source-only PR delivery and is not claimed.
