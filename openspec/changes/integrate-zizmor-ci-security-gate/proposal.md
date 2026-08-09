# Change: Integrate the GitHub Actions security gate

Task ID: `CIC-1786295418152915`

## Why

The repository has no dedicated semantic security analysis for GitHub Actions,
Dependabot, or repository-owned action definitions. A default-persona `zizmor`
audit currently reports actionable risks including template expansion into
shell contexts, persisted checkout credentials, and insufficient dependency
cooldowns. These gaps can expose CI credentials or allow untrusted input to
change executed commands, and they are not fully covered by the existing YAML,
policy, secret, or supply-chain checks.

## What Changes

- Operators and contributors can run one repository-pinned command that audits
  repository-owned GitHub Actions, Dependabot, and pre-commit inputs.
- Pull requests and changes to the default branch are blocked when the strict
  security audit reports an actionable finding or cannot collect a supported
  repository-owned input.
- Existing actionable findings are removed without disabling audit rules or
  weakening workflow permissions, immutable action references, or other gates.
- Vendored and third-party test fixtures are excluded from the production gate.
- No runtime VPN, cloud resource, managed host, secret schema, or deployment
  behavior changes.
- BREAKING: workflows that introduce a default-persona `zizmor` finding will no
  longer pass the required CI validation surface.

## Capabilities

### New Capabilities

- `ci/github-actions-security`: Reproducible local and CI enforcement of the
  repository's GitHub Actions security baseline.

### Modified Capabilities

- None.

## Impact

- Affects the repository toolchain, Makefile validation surface, GitHub Actions
  definitions, Dependabot configuration, and focused validation tests.
- Adds a pinned development-tool dependency, but no production or deployed
  runtime dependency.
- Changes only CI and contributor contracts; Terraform, cloud-init, Ansible,
  SOPS+age, `vpnd`, fleet state, and network paths remain unchanged.
