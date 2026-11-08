# Change: Make Telegram alert messages readable and actionable

Task ID: `MON-1794126016474351`

## Why

Primary alerts use Telegram HTML mode but carry no markup. They show internal rule names, full hashes and raw timestamps, and every rule links to a general incident page that has no section for the alert. The operator cannot tell from the message what failed or what to check first. Secondary Kuma notifications have the same problem.

## What Changes

- Primary alerts render as structured Telegram HTML with the status, the summary, the node, one bullet per alert, readable UTC times and a link to the exact runbook section.
- Every alert rule gains an `action` annotation and an anchored `runbook`. Rules whose expression value is the measured quantity gain a `value` annotation.
- A new runbook page describes each incident family.
- The repository documents a Kuma Liquid template and monitor descriptions for the secondary channel. An operator applies them in the Kuma UI.

## Capabilities

### New Capabilities

- None

### Modified Capabilities

- `operations/observability-alerting-reliability`: adds requirements for alert message content and secondary message guidance.

## Impact

- `observability_control_plane` relay and rule templates, their promtool cases and snapshots.
- The operator drill annotations in `scripts/observability-operator.py`.
- Operator documentation. Deployment and Kuma UI changes need separate authorization.
