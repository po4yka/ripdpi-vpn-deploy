# Change: Gate credentialed CI deploys behind environment approval

Task ID: `CIC-1787415665884975`

## Why

The `ci-real-deploy` PR label executed credentialed deployment jobs whose
environment carries `UPCLOUD_USERNAME`, `UPCLOUD_PASSWORD`, `CI_SOPS_AGE_KEY`,
and `CI_SSH_PRIVATE_KEY`. The only fork defense was a runtime branch
comparison, which a same-repo branch passes by construction: any pushed branch
whose scripts exfiltrate job env reached production-minting credentials with a
single approving label click. Separately, two steps interpolated
`${{ secrets.CI_SSH_PRIVATE_KEY }}` and `${{ secrets.CI_SOPS_AGE_KEY }}`
directly into `run:` blocks; GitHub expands templates before the shell parses
the script, so metacharacters in a secret value become command execution and
transformation of the expanded text can defeat log masking. The audit that
surfaced both findings rated them the top CI security gaps.

## What Changes

- Both credentialed deployment jobs (`real-vps-deploy.yml`,
  `transport-reachability-matrix.yml`) reference the `ci-real-deploy` GitHub
  Environment, which requires a reviewer-approved deployment before any step
  runs — for label, `workflow_dispatch`, and scheduled triggers alike.
- The repository-owned environment is provisioned via the GitHub API with one
  required reviewer (the maintainer); workflow references to a missing
  environment would otherwise auto-create an unprotected one.
- Deploy key material is staged through step-level `env:` and quoted shell
  variables instead of direct `${{ secrets.* }}` expansion inside `run:`.
- Fork short-circuit steps are retained as defense in depth.
- A focused contract test asserts both invariants so regressions fail the
  fast local gate.

## Capabilities

### New Capabilities

- `ci/credentialed-deploy-gating`: Approval-gated execution and secret-handling
  contract for workflows that run with provider credentials or CI key material.

### Modified Capabilities

- None

## Impact

- `.github/workflows/real-vps-deploy.yml` and
  `.github/workflows/transport-reachability-matrix.yml` job definitions.
- Repository settings: new protected GitHub Environment `ci-real-deploy`.
- Operator experience: every trigger of either workflow now pauses for an
  explicit deployment approval before provisioning resources.
- No runtime VPN, cloud-init, Ansible, secrets-schema, or vpnd changes.
