# Change: Harden deploy-path integrity: guards, rollback, rotation

Task ID: `OPS-1787496414433523`

## Why

The audit found the operator deploy path can bypass its own safety rails or leave inconsistent state behind: tag-scoped `site.yml` runs skip the secrets assert and tier guards entirely, `make deploy` does not wait for first-boot completion before converging, the cloud-init wait phase can hang forever, cohort typos silently deploy the wrong profile, an empty SSH allowlist locks operators out after apply, duplicate inventory aliases merge silently into wrong-target deploys, credential rotation skips the backup-before-write contract that rollback depends on, xray rollback repoints the runtime symlink before validating, failed smoke tests leak transient proxy services and credential-bearing workdirs, fleet maintenance hard-fails on a service no role manages, playbook inline toggle defaults disagree with the declared surface, the residual-package gate parses locale-dependent output, and two governance-gated cascade toggles are missing from the declared toggle surface.

## What Changes

- Guard pre_tasks in `site.yml` carry `tags: [always]` so tag-scoped runs cannot skip them.
- `make deploy` and `make dry-run` depend on a bootstrap-readiness step invoking `scripts/wait-cloud-init.sh`.
- The remote cloud-init wait runs inside a bounded retry loop and distinguishes error state from marker absence.
- Cohort slugs validate against the known `group_vars/vpn-*.yml` set at render time.
- An empty SSH allowlist fails at plan time (Terraform variable validation plus a site.yml assert).
- Inventory rendering aborts on duplicate host aliases across HOSTS pairs.
- Credential rotation copies the outgoing xray config to `.prev` before rewriting.
- Xray rollback validates the target binary against the current config BEFORE flipping `/opt/xray/current`, and refuses no-op rollbacks.
- Smoke-test protocol blocks wrap in block/rescue/always to stop transient units and remove the workdir on failure.
- The os-maintenance service list drops the externally managed unit from the unconditional base list.
- Ordinary transport-selection defaults in playbooks align with `group_vars/all.yml`; fail-closed configuration prerequisites remain unchanged.
- The apt simulation gate runs under `LC_ALL=C`.
- `enable_cascade_ingress`/`enable_cascade_egress` join the declared toggle surface in `all.yml`.

## Capabilities

### New Capabilities

- `operations/deploy-path-integrity`: Observable contract that deploy-path guards always execute, deploys wait for bootstrap, renderer inputs are validated fail-closed, rollback and rotation preserve restore points, and maintenance gates are deterministic.

### Modified Capabilities

- None

## Impact

- Ansible playbooks: site.yml, verify-adjacent pre_tasks consumers, smoke-test.yml, os-maintenance.yml, rotate-credentials.yml, rollback-xray.yml.
- Scripts: wait-cloud-init.sh, render-inventory.sh. Makefile deploy/dry-run dependency graph.
- Terraform provider variables (validation block for the SSH allowlist input).
- group_vars/all.yml gains explicit defaults only; no behavior change where keys are defined.
