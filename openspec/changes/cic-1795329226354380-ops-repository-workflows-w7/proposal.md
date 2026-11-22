# Change: Run plan, deploy, verify, rotate and issue from ops repository workflows

Task ID: `CIC-1795329226354380`

## Why

W1 to W6 give CI a private configuration home, encrypted remote state, scoped identities, a fixed egress address and DNS as code, but nothing yet runs the operations. A Claude cloud session holds no secrets and reaches GitHub only through a proxy that allows branch pushes and pull requests but whose workflow-dispatch permission is unknown. The operator needs every operation (plan, apply, destroy, dry-run, deploy, verify, acceptance, rotation, device issuance, DNS) to run from the ops repository with approvals from a phone. Part of W7 of epic `EPC-1795327697650892`.

## What Changes

- Request files: an operation is a reviewed file `requests/<request-id>.yaml` (operation, targets, parameters, public recipient key where needed) added by pull request. A Claude cloud session needs only to push a branch and open a pull request; no workflow dispatch is required.
- Automatic PR previews overlay only allowed typed fields on trusted targets. Other changes require review of the exact head before any credentialed preview.
- Merged plan and dry-run requests stay read-only. Mutations require approval. The executor claims immutable requests, reconciles interrupted work and verifies the approved saved plan before apply.
- Scheduled workflows: daily drift plan per root and daily verify and acceptance, writing receipts.
- CI prepares encrypted credential changes offline. A separate reviewed deploy activates them.
- Device client configurations are encrypted to the recipient's age public key before upload; plaintext client artifacts are refused.
- Record attempts on a protected, executor-written `ops-receipts` branch readable by the cloud session.
- `workflow_dispatch` stays available for the operator and, if the proxy permits it, for read-only operations from the cloud session.
- A Claude cloud environment with the ops and public repositories, no environment variables or secrets, a limited network allowlist and a toolchain setup script kept in the public repository.

## Capabilities

### New Capabilities

- `ci/ops-repository-workflows`: request format, triggers, environments per operation, receipts, artifact encryption and the cloud-session path.

### Modified Capabilities

- None.

## Impact

- Ops repository: `.github/workflows/*`, `requests/`, `ops-receipts` branch, branch protection.
- Public repository: `scripts/validate-ops-request.py` with tests, `scripts/encrypt-client-artifact.sh` with tests, `scripts/cloud-env-setup.sh`, `docs/how-to/ops-workflows.md`, `docs/how-to/deploy.md` (CI path), skills `vpn-deploy`/`vpn-acceptance` notes on the CI path.
- External (authorized live steps): ops repository branch protection, workflows enabled, Claude cloud environment, the workstation-off drill.
