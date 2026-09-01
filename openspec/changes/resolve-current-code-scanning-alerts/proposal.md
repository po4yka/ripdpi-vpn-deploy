# Change: Resolve current CodeQL and Scorecard code scanning alerts

Task ID: `SEC-1788275314490012`

## Why

The default branch has eight open code-scanning alerts at source SHA
`bb889ed478d858e3606f60c8041e3c0d72bd8795`: three Python exception handlers
silently discard descriptor-close failures, one probe retains an unused parsed
value, and two image-publishing workflows grant write permissions at workflow
scope. The causes must be removed without dismissing alerts, weakening scanning,
changing promotion failure categories, or breaking image publication and SARIF
upload.

## What Changes

- Make the three best-effort descriptor-close paths explicit and test their
  fail-closed outer behavior without exposing paths, state, or exception text.
- Remove the unused protocol-liveness parse result while preserving validation
  and side effects.
- Keep both affected image workflows read-only by default and grant `packages: write`
  plus `security-events: write` only to their publishing jobs.
- Add focused regression and workflow-policy coverage, then require hosted
  CodeQL and Scorecard evidence for the exact implementation SHA.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `secure-code-scanning-baseline`: Extend source-level alert closure to the
  current Python findings and require explicit handling of cleanup failures.
- `ci/github-actions-security`: Require the affected image workflows to remain
  read-only at top level and scope unavoidable write permissions to the job
  that performs publication and SARIF upload.

## Impact

- Python operator scripts for Tailnet network promotion and protocol liveness.
- Focused unit tests for safe file-descriptor cleanup and AWG probe validation.
- Debian 13 and Ubuntu 24.04 Molecule image publication workflows and their
  repository-owned workflow-policy checks.
- Hosted CodeQL and Scorecard are the authoritative closure evidence; no live
  infrastructure, provider state, secrets, or deployment contract changes.
