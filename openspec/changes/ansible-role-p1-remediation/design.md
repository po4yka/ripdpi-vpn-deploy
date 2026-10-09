## Context

The source PR repairs the eleven critical audit findings against current main.
DNS resolver migration and isolated collector ingress restart already exist;
the retained dead-man receiver remains source-maintained but is not an approved
monitoring topology. All development uses one dedicated worktree.

## Goals / Non-Goals

- Goal: positive safe startup, backup, delivery and pulse behavior with failure regressions.
- Goal: verify integrated DNS and collector activation instead of duplicating them.
- Non-goal: provider or fleet mutation, live notification, monitoring cutover, or P2 remediation.

## Decisions

- Remove privileged Xray startup pathname repair. Keep log directory entries
  controlled by root while giving the runtime write access to its actual logs;
  provisioning must reject symlinks/hardlinks before ownership changes.
- Use controlled active-service restart for log rotation and geodata activation;
  unsupported HUP/version heuristics are not a hot-reload contract.
- The subscription server validates pre-provisioned revocation authority and
  refuses missing/unsafe state. Token-bearing Ansible operations are censored.
- Render backup inputs from the full effective transport/service profile and
  retain explicit failure for absent required inputs.
- TLS admission bounds work before handshake and limits active workers. Replay
  state is durable and bound to configured authority generation; mismatched
  pulses never authorize changing it. Old unbound state is refused rather than
  implicitly granted a new epoch.
- A small role-owned Python notification sender reads a private JSON systemd
  credential, constructs bounded requests internally and logs categorical
  errors. Existing secret input names stay unchanged. The watchdog shell
  retains probe/recovery ownership, and notification failure cannot block
  durable supervision state beyond its budget.

## Contracts and ownership

- Host worker: xray, monitoring, geodata, backup, subscription-host and directly
  associated tests; inspect and verify baseline resolver without unrelated edits.
- Receiver worker: observability_deadman and its tests; verify existing
  observability_control_plane CRL restart without reactivating retired senders.
- Primary: watchdog and its tests, planning/task records, shared snapshot fixture
  lanes, all final snapshots, security review and PR delivery.
- All workers preserve concurrent edits and never stage or commit.
- Terraform, cloud-init, production secret structure and vpnd are unchanged.

## Risks / Trade-offs

- Controlled Xray restart interrupts active connections; positive listener
  recovery is preferable to an unsupported signal leaving the service stopped.
- Root-owned log entries remove runtime file creation authority; convergence
  creates validated log files before startup and tests rotation afterward.
- Retained receiver state contract breaks unbound legacy state deliberately.
  Refusal requires explicit owner-authorized private-state retirement, never
  automatic deletion or replay-counter weakening.
- Network tests use controlled local endpoints and synthetic credentials.
  They are source/runtime regressions, not external delivery or human receipt.

## Migration Plan

The PR changes local runtime configuration on the next separately authorized
deployment. Watchdog convergence replaces its generated secret environment
surface with a systemd credential. Existing input schema is retained.
Retained receiver unbound state must be explicitly retired by its owner before
using the new contract; the retired monitoring topology stays disabled.
Rollback is a reviewed source/configuration redeployment, not a PR merge or
fleet action in this request. Focused tests, intended rendered snapshots,
available Molecule, full make check and independent security review gate the PR.
