# Change: Repair deployment security and lifecycle defects

Task ID: `SEC-1791471757439452`

## Why

The deployment audit found secret-bearing diagnostics, incomplete policy evaluation,
broken operator entry points, false drift success, and runtime lifecycle errors.
Operators need working replacement, validation, rotation and maintenance paths
that preserve the existing controller and least-privilege boundaries.

## What Changes

- Prevent private-key and malformed-secret disclosure.
- Evaluate provider firewall policies against the plan that will be applied.
- Repair supported runtime DNS, forwarding, port-hopping, upgrade and disable behavior.
- Route deployment callers through the canonical controller and compare actual drift.
- Validate rollback candidates before publishing and initialize validation dependencies.
- Revalidate the ingress reload fix already present on the integration base.

## Capabilities

### New Capabilities

- `deployment-integrity`: consistent security, policy and lifecycle behavior across operator surfaces.

### Modified Capabilities

- None; the integrated regression contract supplements existing layer specifications.

## Impact

Terraform policies; Ansible roles and maintenance/rollback playbooks; operator scripts,
Make, vpnd and credentialed CI orchestration. No production dependencies are added.
The PR changes source behavior only; infrastructure rollout remains separately authorized.
Broken direct-playbook callers migrate to the existing controller contract without a bypass.
