# Change: restore dependency PR CI compatibility gates

Task ID: `CIC-1787209937108078`

## Why

Dependency pull requests #75 and #76 are blocked by required checks that do
not reflect the changes under review. The task-contract job checks out a peer
portfolio whose current default branch no longer exposes the configured
federation contract. The pinned Debian 13 Molecule image also contains
fixed HIGH vulnerabilities, so the image-security gate correctly rejects it.

## What Changes

- Validate this repository's task contract without checking out an obsolete
  peer contract. BREAKING: this CI job no longer treats the retired peer
  portfolio as part of its validation input.
- Build and use a repository-owned, digest-pinned Debian 13 Molecule test
  image with current security updates so the security gate validates the
  image that Molecule actually uses.

## Capabilities

### New Capabilities

- `ci/molecule-image-security-baseline`: CI can build, pin, scan, and use a
  refreshed Debian 13 Molecule base image.

### Modified Capabilities

- `ci/task-contract-validation`: validates the local portfolio contract and
  its history without the retired cross-repository checkout.

## Impact

- GitHub Actions CI workflows, Molecule platform definitions, and the
  repository image-security supply chain are affected.
- No Terraform, cloud-init, Ansible runtime role behavior, secrets, or live
  deployment configuration changes.
