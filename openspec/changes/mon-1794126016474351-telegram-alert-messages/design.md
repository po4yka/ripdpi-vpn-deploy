## Context

The relay receives bounded Alertmanager webhooks and already sends `parse_mode: HTML`. Alertmanager groups by alert name, environment, node, component and severity. Kuma monitors are configured only in its authenticated UI.

## Goals / Non-Goals

- Goal: an operator can act from the message without opening a dashboard.
- Non-goal: changing alert expressions, routing, repeat intervals or Kuma heartbeat timing.
- Non-goal: automated Kuma provisioning.

## Decisions

- Rules own the text and the relay owns the layout. Rejected: a text table in the relay, because a second place would have to track every rule.
- The first alert of a group supplies shared fields, because `group_by` makes them identical.
- The relay treats `action` as optional and the rule tests require it. Rejected: a required relay field, because the role activates the relay before Prometheus and a failed activation would refuse every alert.
- Firing messages show only the start time, so that rendering needs no clock input.
- Links target `main` of the public repository. Rejected: pinning to the source revision, because a deployed revision may not exist on the remote.
- Kuma uses its native Liquid template. Rejected: patching the image.

## Contracts and ownership

- `observability_control_plane`: relay rendering, rule annotations.
- `docs/how-to/monitoring-alerts.md`: one section per `incident_family`; the section heading is the anchor.

## Risks / Trade-offs

- A link can target a section that is not yet on `main` until the change merges. Deploy from merged sources.
- A relay refusal loses an alert. Only the `runbook` pattern adds a new refusal; every current and previous rule value matches it.

## Migration Plan

Deploy `observability_control_plane` through the normal lifecycle with a dry-run first. The relay accepts both rule generations, so activation order does not matter. Rollback uses the existing collector rollback. The Kuma template is an optional UI step.
