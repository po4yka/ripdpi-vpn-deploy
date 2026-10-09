---
name: vpn-acceptance
description: Verify and report a scoped VPN deployment or monitoring outcome using current source, host and authenticated client evidence. Use for staging/fleet acceptance and incomplete rollout checks; it does not authorize deployment or remediation.
---

# Accept a scoped VPN outcome

Start with [acceptance scope and completion](../../../docs/RUNBOOK-deploy.md#acceptance-scope-and-completion). Establish the exact nodes, changed capability, required protocols, client vantage and authorized checks. Continue existing bounded authority; request a decision only for missing access or changes beyond it. An evidence-only request remains inspection.

## Gather the required evidence

1. Run workspace discovery. Identify the tested source revision and deployable digest, exact deployed identities and artifact freshness. Read [deployment status](../../../docs/DEPLOYMENT-STATUS.md) for recorded limitations, then distinguish that historical snapshot from observations in this run.
2. Inspect existing local/hosted checks at their exact source revision. Run only missing checks needed for the changed layer. Record failure or unavailable tooling; another validation lane cannot replace a failed required gate.
3. With host-access authority, use `make verify` for the exact inventory alias, applicable `make security-verify`, and current source parity. For passive scoped inspection, [the inspection contract](../../../docs/PROTOCOL-LIVENESS.md#passive-fleet-inspection) supports `make inspect INSPECT_HOSTS=<exact-names>` against existing inventory. Services, listeners and local manifests establish their own claims, not authenticated external VPN traffic.
4. For full P0/P1/P2 acceptance, follow [protocol acceptance](../../../docs/PROTOCOL-LIVENESS.md#staging-acceptance): `p0-reality`, `p1-xhttp`, `p2-hysteria2` and `p2-amneziawg` must all return fresh `ok` for the assigned nodes and current identity, with authenticated traffic and tunnel DNS; AWG also requires a fresh handshake. Use the canonical configured `make protocol-liveness`, or `make protocol-liveness-disposable` with its exact prepared manifest and binding. A required `throttled`, failed, stale, unknown or untested result leaves that acceptance incomplete.
5. State the actual vantage. One all-four-profile disposable consumer-uplink run proves that staging node from that vantage. Fleet coverage, a second physical vantage, filtered-path behavior, Android and recurring uptime need their own observations when required. Recovery fault injection, quorum/OTP, backup restore and personal-client tests apply when the selected capability requires them, rather than as universal staging prerequisites.

For monitoring acceptance, read [current topology and task history](../../../docs/OBSERVABILITY-OPERATIONS.md#current-contract-and-task-history) and its migration/acceptance section. Check admitted co-hosted collector/agents and independent Kuma, current expected coverage and freshness, required queue/restart delivery, real rule-to-relay/API results and separately observed human Telegram receipt. Local render, healthy processes, retained old dedicated-host receipts and API acknowledgement cannot accept the replacement design. Respect its staging environment and rollout hold.

## Close the run honestly

Record each required claim as observed, failed or unverified with its exact source/target, observation time and artifact. Reused evidence keeps its original scope and date; equal deployable digests alone do not satisfy strict source parity.

When a required claim fails, preserve it and continue authorized rollback/cleanup through `vpn-cleanup`. Do not deploy, rotate credentials, inject production faults or widen the run merely to produce a pass. Cleanup can succeed while acceptance remains failed.

The handoff names local/hosted gates, provider identity, guest/recovery/parity checks, protocol/client results and any human observation separately, plus remaining blockers or resource/credential residuals. Mark complete only when every required scoped claim has current supporting evidence and the requested cleanup is finished.
