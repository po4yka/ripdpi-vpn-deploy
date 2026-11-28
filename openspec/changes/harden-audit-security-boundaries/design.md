## Context

Xray source parsing and nginx error interception already have partial coverage. Extend management and method coverage at their existing boundaries.

## Goals / Non-Goals

Verify and repair all audited boundaries. Credential changes and fleet convergence require a separate execution window.

## Decisions

- Count canonical IP addresses from the source field. Admit approved Tailnet SSH before offender drops so prior set entries cannot lock out management.
- Treat complete transport candidate facts as sensitive even when an update only appends release metadata.
- Keep placeholders usable in draft secrets. Reject them at strict validation and cohort-token authority boundaries.
- Require inbound default drops per UpCloud family. Keep the checks in the current policy namespaces so the saved-plan evaluator applies them.

## Contracts and ownership

Ansible owns host rules, config staging, and nginx. Operator scripts and the schema own input validation and export. The Conftest policies cover provider plan JSON. The standard deployment controller can supply approved sources from its confirmed private handoff.

## Risks / Trade-offs

Unknown ingress attributes require explicit configuration before a plan can pass. Positive tests must preserve accepted provider plans and both HTTP and transport delivery.

## Migration Plan

Before rollout, provide approved Tailnet sources through the private deployment input. Fill enabled Salamander passwords and replace example token values. Run local checks and hosted CI before merge. Use the normal release revert for source rollback and keep the private inputs.
