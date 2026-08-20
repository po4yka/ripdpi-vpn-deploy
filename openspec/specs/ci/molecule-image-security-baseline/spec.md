# ci/molecule-image-security-baseline Specification

## Purpose
Ensure each Debian 13 Molecule base image used in CI is reproducible and free
of fixed HIGH or CRITICAL vulnerabilities at its verified build point.
## Requirements
### Requirement: REQ-CIC-1787209937108078-002 — use a repository-owned refreshed image

CI MUST build a repository-owned Debian 13 Molecule image from a digest-pinned
upstream base, install current security updates, and publish its immutable
digest for Molecule scenarios. The image scan MUST fail when the selected
digest has a fixed HIGH or CRITICAL vulnerability.

#### Scenario: Refreshed image has no fixed high-severity finding

- **WHEN** CI scans the published Debian 13 Molecule image with the
  HIGH,CRITICAL policy and `ignore-unfixed` enabled
- **THEN** the scan exits successfully and Molecule scenarios use that exact
  immutable digest

#### Scenario: A refreshed image becomes vulnerable

- **WHEN** a scan finds a fixed HIGH or CRITICAL vulnerability in the pinned
  Debian 13 Molecule image
- **THEN** the image-security job fails and does not silently allow the image
