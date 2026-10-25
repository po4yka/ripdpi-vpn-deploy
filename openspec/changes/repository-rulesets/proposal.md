# Change: Apply layered repository rules and release protection

Task ID: `CIC-1792911952227614`

## Why

The classic-protection workflow can restore an obsolete policy and block the owner CI exception. Release tags and published assets need stable identities. Dependency updates omit active manifests.

## What Changes

- Separate branch integrity from CI requirements. Retain the owner bypass only for CI and only through pull requests.
- Protect release tags and enable immutable future releases.
- Replace classic protection automation with reviewed, repeatable ruleset configuration and readback.
- Reduce required contexts to the complete CI aggregate and both CodeQL results.
- Cover all active dependency manifests with grouped updates.
- Use squash merges, PR-title commit subjects, title validation, and automatic merged-branch deletion.
- BREAKING: remove the classic-protection workflow and use the repository-policy Make commands.

## Capabilities

### New Capabilities

- `repository-policy`: layered rulesets, release integrity, merge settings, and dependency update coverage.

### Modified Capabilities

- None.

## Impact

- GitHub repository settings, Actions, operator scripts, tests, and runbooks.
- No fleet, VPN credentials, infrastructure deployment, or new production dependency.
