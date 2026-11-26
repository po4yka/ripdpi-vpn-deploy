## Context

`scripts/emit-bundle.sh` publishes node addresses. `make burn-check` and the liveness sentinel observe nodes after publication. `docs/explanation/threat-model.md` states that CI measures only the unfiltered half.

## Goals / Non-Goals

- Goal: Refuse to publish a node address that a filtered-side vantage cannot reach, and keep ICMP out of admission and liveness evidence.
- Non-goal: any IP address, hostname, key or concrete evasion parameter in the repository.

## Decisions

- Assumption: the vantage is the existing liveness executor path. Step 1 confirms that it can run a TCP and TLS check toward a node that has no client traffic yet. Rejected: a new vantage service.
- Assumption: the /24 decision uses the same two-control-point rule as the public report: a block counts as closed only when two independent control points fail. Step 1 sets the control points and the failure count.
- Assumption: the gate runs as a refusal step in the emit path, not as a Terraform hook, so the layer boundaries stay unchanged.

## Contracts and ownership

- `scripts/` (emit path and the check script), `docs/how-to/deploy.md`, `docs/explanation/threat-model.md`. One writer.

## Risks / Trade-offs

- A false refusal costs one node recreation -> the node is disposable, and the operator message names the cause.
- A vantage outage blocks admission -> fail-closed is the stated behaviour; the operator can retry.

## Migration Plan

Forward only. Rollback reverts the change.
