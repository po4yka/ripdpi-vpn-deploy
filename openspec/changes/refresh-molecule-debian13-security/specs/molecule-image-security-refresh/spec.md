## Purpose

Keep the immutable Debian 13 image used by Molecule free of fixable HIGH and CRITICAL vulnerabilities so dependency and infrastructure changes are evaluated by the repository security gate.

## MODIFIED Requirements

### Requirement: REQ-DEBIAN-MOLECULE-IMAGE-SECURITY — refreshed digest is security-gated

The repository MUST publish a refreshed Debian 13 Molecule image from the owned Dockerfile, scan that exact immutable digest with Trivy for HIGH and CRITICAL vulnerabilities while ignoring only unfixed findings, and fail publication when a fixable finding remains.

#### Scenario: current package upgrade clears a stale-image finding

- **GIVEN** the existing published Debian 13 image has a fixable HIGH or CRITICAL vulnerability
- **WHEN** the owned Dockerfile is rebuilt with current Debian security packages
- **THEN** publication MUST succeed only if the resulting image passes the existing Trivy policy

### Requirement: REQ-DEBIAN-MOLECULE-DIGEST-CONSISTENCY — scenarios use the scanned digest

Every Debian 13 Molecule scenario MUST reference the immutable digest produced by the successful security-gated publication.

#### Scenario: image references are advanced

- **GIVEN** publication reports a new scanned digest
- **WHEN** the repository updates Molecule scenario configuration
- **THEN** each Debian 13 image reference MUST use that digest and no previous vulnerable digest may remain

### Requirement: REQ-DEBIAN-MOLECULE-SECURITY-NO-BYPASS — vulnerability policy remains enforced

The refresh MUST NOT add a Trivy ignore entry, lower the severity threshold, disable scanning, or use an administrator merge bypass.

#### Scenario: a fixable severe vulnerability remains

- **GIVEN** the rebuilt image contains a fixable HIGH or CRITICAL vulnerability
- **WHEN** the publication or image-scan workflow runs
- **THEN** the workflow MUST fail and block merge until the image is remediated
