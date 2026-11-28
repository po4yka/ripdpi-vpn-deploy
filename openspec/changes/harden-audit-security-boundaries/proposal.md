# Change: Enforce deployment security boundaries

Task ID: `SEC-1795866391476569`

## Why

The deployment audit identified gaps in source attribution, credential handling, transport configuration and provider plan checks. Close each gap and verify the protections already present.

## What Changes

- Use the source field in Xray access logs and protect approved management traffic from policy bans.
- Suppress output for all tasks that update the complete transport plan.
- Reject public placeholders and invalid secret types. Require a password when Salamander is enabled.
- Verify the uniform nginx response for unsupported methods on protected routes.
- Require private Tailnet SSH source input and explicit provider firewall safeguards.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `audit-boundary-correctness` adds validation and runtime safeguards for the audit findings.

## Impact

Ansible roles, client export, secret checks, token rotation and provider plan validation. **BREAKING** Enabled Tailnet management requires explicit private sources. Enabled Salamander requires a nonempty password.
