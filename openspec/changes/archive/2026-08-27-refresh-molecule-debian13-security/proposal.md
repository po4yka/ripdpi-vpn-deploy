# Change: Refresh the Debian Molecule image to clear the vulnerability gate

Task ID: `SEC-1787810718115433`

## Why

The immutable Debian 13 Molecule image currently referenced by the test scenarios has a HIGH or CRITICAL vulnerability detected by the image-security gate. This blocks dependency updates even though their own checks pass. The published image must be rebuilt with current Debian security packages and every scenario must consume the resulting immutable digest.

## What Changes

- Rebuild and scan the repository-owned Debian 13 Molecule image with its existing security-upgrade Dockerfile.
- Replace every Molecule reference to the vulnerable Debian image digest with the scanned published digest.
- Preserve digest pinning and the existing HIGH/CRITICAL Trivy gate. No exceptions are introduced.

## Capabilities

### New Capabilities

- `molecule-image-security-refresh`: Repository-owned Molecule scenarios consume a freshly scanned, immutable Debian 13 base-image digest.

### Modified Capabilities

- `molecule-test-images`: Debian 13 scenario image references advance only to a successfully published and scanned digest.

## Impact

- Affects the CI container-image publishing and scanning lifecycle and all Debian 13 Molecule scenarios.
- Does not alter Terraform, cloud-init, Ansible runtime behavior, secrets, or public contracts.
