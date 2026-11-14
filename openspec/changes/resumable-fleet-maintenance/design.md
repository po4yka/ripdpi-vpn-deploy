## Context

The canonical controller already fences inputs, supervises child processes and
recovers protected runtime transactions. Fleet rotation already has an exact-plan
journal. The new surface connects these facilities; it does not replace them.

## Goals / Non-Goals

- Deliver all ten requirements, starting with resume, release inputs and kit recovery.
- Keep operator authority and private values outside Git and remote logs.
- Do not provision servers, add a remote command daemon, bypass preview gates or
  automatically repair drift.

## Decisions

- Use a detached local worker and fixed canonical Make stages. Reject arbitrary
  commands and Make injection. Bind a clean revision, effective inventory, private
  inputs and a finite deadline. Prefer a clean controller without `.fleet.mk`.
- Hold sorted locks for shared nodes, inventory and owned plaintext destinations.
  Journal intent before mutation. Reuse the existing owned-process supervisor.
- Stream logs through an owned, bounded age process; require successful encryption
  separately from command success. Always run canonical cleanup and prove absence.
- Resume accepted boundaries only after source/input checks. An uncertain mutation
  requires canonical state reconciliation. A refused preview never becomes a
  generic success; retained runtime journals follow the documented recovery path.
- Derive archive members from one release identity, then verify downloaded archive
  contents and checksum. Use one version for package installation and APT policy.
- Snapshot only admitted kit roots. Enforce file authority and archive bounds,
  authenticate decrypted manifests, rescan inputs before a current-coverage claim,
  and publish a separate post-delivery acknowledgement.
- Reuse native protocol verification, backup restore drills and passive inspection
  for serial rollout and periodic checks. Notifications are limited to actionable
  state changes through the private monitoring path.
- Address changes require a private exact-scope grant. Terraform owns provider
  firewall state; runtime firewall changes use the existing canonical transaction.
- Routine credential contexts exclude administrative provider keys. Verify narrow
  provider grants before switching consumers; preserve independent recovery.

## Contracts and ownership

Primary owns new maintenance/release/kit scripts, matching tests, Make wiring,
documentation and CI. Existing Ansible role changes stay in their owning roles.
Shared Make and CI edits are serialized. Independent review is read-only.
Terraform state and provisioned resources remain unchanged unless a reviewed
address-only plan is necessary and within current authorization.

### Resume after convergence

The deploy stage is the costly part of a node attempt. A completed deploy records `converged` with the host and the plan source in the journal. On resume, the controller skips dry-run and deploy for that host only after `protocol_gate`'s own fresh read-only manifest probe returns the plan revision and digest. It never skips decrypt or an acceptance stage, because acceptance must be fresh evidence. Any mismatch or probe failure runs the full sequence, so a node changed between attempts is converged again. A preview never skips a stage. A complete sequence on start or resume first clears `converged`: the node manifest is written inside the site playbook, so a deploy that fails later can leave a matching live manifest, and only the journal record proves the stage finished. A skip records `resumed_at_acceptance`. Only a failed observation (transport error or source mismatch) falls back to a full sequence; local input errors fail the node, because a second deploy cannot repair them. The probe runs after its own `recheck(plan)`.

## Risks / Trade-offs

- Lost responses can conceal completed writes: retain uncertain intent and
  reconcile through the existing canonical controller.
- Concurrent operator work can change recovery inputs: resource locks and complete
  manifest comparison refuse a false current-coverage claim.
- Secret-bearing diagnostics can outlive a process: encrypt before disk write,
  bound output and retain encryptor/descendant ownership until cleanup completes.
- Periodic jobs can outlive grants: check deadlines before each mutation, never
  merely at startup. Passive checks need no mutation authority.

## Migration Plan

Validate planning, implement and test points 1–3, review and integrate. Continue
serial rollout, scheduled verification, bounded address management and CI against
the resulting contracts. Observe hosted checks on exact merged revisions. Apply
only required runtime changes to existing hosts with canonical previews and
acceptance. Refresh ignored configuration, encrypted recovery and offsite readback.
Retain prior recovery until the new restore proof succeeds.

## Catalog and scheduled operations

- Maintenance configuration schema 2 requires the private catalog. Generation
  selects exact node IDs from its maintenance mapping and resolves relative paths
  against the kit. Missing private dependencies fail before preview. Generation
  does not authorize deployment, decrypt credentials or invent dependency mappings.
- Preparation binds each selected node's current core fields. Successful source,
  protocol and cleanup gates create an immutable acceptance receipt. Reconciliation
  updates only those core fields with compare-and-swap, preserves other metadata,
  and refuses a competing core observation. Journaled acceptance survives a failed
  catalog write; resume reconciles it before another node, without redeployment.
- The new check action uses canonical dry-run, verify and security-verify plus a
  fresh source-manifest check. It neither deploys nor updates accepted core state.
  It retains encrypted configuration-diff diagnostics for review. A source-owned
  callback requires zero changed tasks and positive host coverage; missing counts
  fail closed. Callback discovery remains isolated from ambient plugins.
- A private schedule configuration selects a clean controller revision, exact
  maintenance configuration and restricted backup profile, deadline, intervals,
  and private state directory. Each run rechecks its frozen dependencies. Jobs
  use stable locks, bounded encrypted diagnostics and atomic start/result status.
  Backup success requires the canonical remote-download/decrypt/manifest receipt.
- Render and install use launchd on macOS and a managed crontab block on Linux.
  Installation is explicit. Status reports never-run, running, failed and overdue
  separately from success; a scheduler exit code cannot refresh prior evidence.
- This extension does not complete the older live fleet, device, address-rotation
  or notification requirements of the parent task.
