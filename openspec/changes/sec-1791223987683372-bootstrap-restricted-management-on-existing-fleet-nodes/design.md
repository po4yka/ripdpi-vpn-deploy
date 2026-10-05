## Context

The accepted bootstrap protects fresh disposable nodes and the current managed
layout. Existing permanent nodes expose two uncovered inputs: a named Terraform
workspace and an older managed firewall. Temporary console recovery established
real pinned SSH and installed the separate SSH recovery foundation, but cannot be a
durable operator interface. See proposal.md and the capability requirements.

## Goals / Non-Goals

- Goal: positive restricted enrollment of the existing managed fleet without
  changing resource identity, SSH authentication, resolver or default routes.
- Goal: preserve existing VPN listeners during policy conversion and recover the
  reviewed original policy after interruption or failed proof.
- Non-goal: adopt foreign firewalls, create a public panel, share client material,
  bypass source/CI or dual-path gates, or preserve deprecated request contracts.
- Non-goal: migrate an already installed older Tailnet recovery bundle or identity.
  Unknown, partial, generation-v3, pending and confirmed older installations
  remain untouched and refuse; exact current-source or absent bundles qualify.
- Non-goal: replace VPS resources or silently reinterpret disposable ownership.

## Decisions

### Workspace and build environment are separate bindings

Keep `environment` as the exact routed Terraform workspace. Add required
`build_environment` to bootstrap input and emit `vpn_build_environment` from
the canonical inventory renderer using the existing typed Terraform console
reader for `var.build_env`. Match both fields to inventory and the root-owned
cloud-init build marker before access changes. Update every caller and fixture.

A `ci-staging-*` workspace always takes the existing disposable manifest path,
regardless of a misleading build label. Named permanent workspaces require the
production build marker, reject reserved disposable names/identity, and reject
a supplied cleanup manifest. Unknown or contradictory classes refuse. The
secret/observability workspace scope retains its existing meaning.

### Console access is an explicit source-owned emergency interface

Add a credential-free Make renderer and a fixed guest lease implementation.
The private render request binds the exact inventory alias, public endpoint,
verified host-key digest, verified root filesystem identity, source identity,
approved operator addresses, nonce and absolute deadline. It contains no
password, private key, enrollment key or provider credential.

The artifact can be executed only through separately authorized console/GRUB
access. It validates identity and read-only-root/tmpfs preconditions. Shared
systemd parents are created with mode 0755; existing foreign or unsafe paths
refuse. Private application files and receipt stay root-owned mode 0600 under
an application directory mode 0700. The renderer never changes the global
directory permissions of an existing installation.

An exact-source, same-port static ingress rule has a unique nonce marker. A
boot-bound monotonic lease and an absolute deadline independently revoke it;
ordinary reboot discards RAM state. The root-owned receipt records the original
and leased policy digests and the exact rule. Removal validates the full marker
and rule identity, never a potentially reused nft handle alone. No packet
capture, authentication changes or additional listeners are part of the lease.

### Managed policy conversion stays inside the existing transaction

Extend the read-only plan/preflight to produce a private reviewed-policy
approval bound to node, source, file hashes and normalized effective rules.
The three operator verbs are render-console-bootstrap, inspect-tailnet-bootstrap,
and bootstrap-tailnet; inspection publishes a private exact plan digest.
Managed legacy input requires root-owned regular files, the known managed
header, supported complete tables/chains, safe includes, namespace compilation
and exact file/runtime agreement. A declared console lease may account for
only its exact independently verified ingress delta; arbitrary drift refuses.

The firewall-owned adapter converts reviewed legacy policy to one canonical
layout: typed Tailnet sets, exact interface-scoped accepts and the explicit
overlay SSH drop. It preserves existing public SSH rules, VPN listeners and
unrelated owned policy. It does not maintain a parallel legacy runtime mode.
The existing package conffile-only empty baseline keeps its guarded path.

Arm the existing durable transaction before any policy/enrollment write. Record
the original files, service state, effective rules and ingress lease metadata.
The lease must have enough remaining time for the complete transaction/proof
budget. Confirmation requires fresh actual public and Tailnet SSH/SFTP with the
original host key and preserved SSH/resolver/routes.

### Recovery cannot resurrect expired ingress

Retain exact original policy and service restoration. Rollback always restores the bridge-free original policy, including before
the console deadline. This retires emergency ingress early and removes replay
authority from recovery. Expiry and policy replacement share a RAM coordination
lock to prevent nft handle reuse races. Preserve the existing graph/drift checks and refuse unexplained
concurrent changes. Stop/cancel the consumed lease only after successful
confirmation or verified recovery; never let lease removal race an armed
transaction. Public emergency policy in the confirmed canonical configuration
comes only from the explicitly approved bootstrap request, and the invocation
retires its separately owned provider rule.

## Contracts and ownership

- Terraform keeps resources and provider firewall ownership; this change does
  not replace resources or embed credentials in vars, outputs or state.
- `scripts/render-inventory.sh` emits the build classification. Bootstrap,
  staging harnesses, docs and tests adopt the required request field together.
- Ansible installs the firewall/Tailnet helpers and existing recovery units.
  The console renderer is the documented limited emergency bootstrap boundary.
- Bootstrap probe, firewall adapter and domain/controller modules own approved
  snapshot validation, conversion, confirmation and recovery. The canonical
  Make surface remains the operator entry point.
- One primary writer owns implementation, tests and this task's artifacts in
  the dedicated worktree. Provider/state/inventory/lease actions are serialized.
  Reviews own no files. Foreign work and policy are preserved.
- Existing acceptance evidence stays in its owning task; no source or fixture
  result is credited as live or authenticated client acceptance.

## Risks / Trade-offs

- Misclassified disposable target: cross-bind workspace, canonical build marker,
  identity and cleanup authority before mutation.
- Overbroad legacy adoption: require explicit snapshot approval, owned complete
  graph and independent compilation; reject foreign includes/tables/drift.
- Expired public access restored by rollback: boot/deadline-aware bridge-free
  recovery and native reboot/controller-loss tests are mandatory.
- Network failure from runtime permissions: verify shared directory traversal
  and private-file isolation in a real Linux startup test.
- Source/runtime mismatch: freeze the protected source and run the relevant
  local/native and hosted gates before any accepted rollout.

## Migration Plan

1. Ship the new request/inventory contract and update all producers atomically.
2. Render and review one exact-node lease and policy approval when public SSH
   is unavailable; separately authorize console execution.
3. Install the exact recovery foundation through the existing Make target.
4. Run canonical existing-node bootstrap with a fresh one-node enrollment key.
5. Observe independent rollback/reboot/controller-loss and positive dual-path
   acceptance on protected source before production rollout.
6. Render inventory from the confirmed handoff, run ordinary dry-run/deploy and
   verify/security/source-drift, then retire invocation-owned access.
7. Keep the task and parent open while any positive or cleanup gate is missing.
