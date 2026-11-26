## Context

D3 exports client-direction authenticated probe results. D5 joins them with client reports. The node already runs textfile exporters.

## Goals / Non-Goals

- Goal: Record the result of node-initiated connections beside the client-direction result, so a block can be classed as one-way or two-way.
- Non-goal: any IP address, hostname, key or concrete evasion parameter in the repository.

## Decisions

- Assumption: a node-local timer and a textfile metric, like the existing node exporters. Rejected: sentinel-orchestrated SSH, because it adds a credentialed path.
- Assumption: targets are role variables supplied by the operator. The repository names none.
- Assumption: the direction label is a metric label with two values and does not add ASN or address labels.

## Contracts and ownership

- `ansible/roles/` exporter files, alert template annotations (serialized after D5), docs. One writer.

## Risks / Trade-offs

- A target outage looks like a block -> use several targets and a failure ratio, not one target.
- Probe traffic is itself observable -> keep the rate low and the target count small.

## Migration Plan

Forward only. Rollback reverts the change.
