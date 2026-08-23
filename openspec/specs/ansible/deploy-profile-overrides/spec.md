# ansible/deploy-profile-overrides Specification

## Purpose
Define how deploy-time variable overrides work outside version control, and
pin the decoy public-site identity as operator-supplied material that never
enters git.
## Requirements
### Requirement: REQ-SITE-OVERRIDE — Decoy origin is operator-supplied at deploy time

Committed group_vars profiles MUST carry only the neutral placeholder for
`public_site_canonical_url`, and the real decoy origin MUST reach deploys
exclusively through the validated `ANSIBLE_EXTRA_VARS_FILE` override.

#### Scenario: Committed profile is inspected

- **WHEN** any file under `ansible/group_vars/` declares
  `public_site_canonical_url`
- **THEN** its value is exactly the neutral placeholder origin shared by
  `group_vars/all.yml` and no registered domain appears anywhere in committed
  profile defaults

#### Scenario: Production deploy supplies the decoy origin

- **WHEN** an operator runs a deploy with an `ANSIBLE_EXTRA_VARS_FILE`
  declaring `public_site_canonical_url`
- **THEN** the validator accepts a well-formed https origin and rejects every
  other shape (wrong scheme, host-only string, path-bearing URL, non-string)

#### Scenario: Override is forgotten

- **WHEN** a deploy on a cohort profile that enables `nginx-xhttp` or
  `hysteria` runs without the override
- **THEN** convergence fails closed on the existing role asserts before any
  listener configuration changes

### Requirement: REQ-SITE-OVERRIDE-HISTORY — Rotation stays out of history

Rotating the decoy identity MUST be possible by editing only untracked,
operator-owned files and secrets, without touching committed files.

#### Scenario: Decoy domain rotation

- **WHEN** the operator registers a new decoy domain and updates the secrets
  `nginx_xhttp.server_name` plus their extra-vars override
- **THEN** no committed file under version control changes and no new
  association between this repository and the old or new domain is created

