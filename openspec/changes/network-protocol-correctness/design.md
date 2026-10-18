## Context

The source base is PR #328 at a14c339c. Its native SAN matcher already checks
certificate dates. This change preserves those checks and closes the remaining
audit defects. Other active sessions own Hysteria transit redirect, SSH, storage,
and deployment recovery changes in separate worktrees.

## Goals / Non-Goals

- Goal: close all confirmed audit defects with focused regression evidence.
- Non-goal: deploy, access private fleet inputs, change protocol versions, add
  deployed dependencies, or treat conditional audit risks as proven outages.

## Decisions

- UpCloud exports its accepted NAT source-port range only when the provider
  firewall is enabled. Inventory carries that bounded public value to AWG and
  split-hop NAT, which remap TCP/UDP source ports into it. This preserves the
  existing SSH CIDR guard and stateless return rules. Other protocols retain
  their ordinary masquerade rule; other providers retain current behavior.
  All five Terraform roots keep the same output names. Roots without this
  provider constraint publish an empty range. Validate the range only in the
  split-hop enable path so malformed enabled-role inputs cannot block retirement.
- Full-device certification rejects partial TUN capture and malformed shape.
- Certificate checks use OpenSSL trust and server-purpose verification and
  effective profile selection. Synthetic CA tests use an isolated trust store.
- DNS-Morph records managed stub migration ownership and restores it only after
  listener retirement. Custom resolvers are never adopted or rewritten.
- Keep deployed name handling dependency-free. Accept lossless Unicode codec
  round-trips after lowercase normalization before encoding; refuse lossy
  mappings and require explicit ASCII A-label input. The same policy must hold
  across supported Python patch releases.
- Relay FINs independently and keep bounded buffers and idle budgets. Empty UDP
  is data; it is not EOF.
- HSTS depends on a compatible public HTTPS/443 identity for the same hostname.
  Clear cached policy on alternate-port-only identities without weakening a
  compatible same-host 443 site.
- Reuse already merged and separately owned fixes through source integration,
  not cherry-picked duplicate implementations.
- Pass non-null Git metadata input through a private temporary file. Native
  samples from the complete gate show Python and Git blocked in writes beyond
  the 30-second timeout. A seekable input removes the duplex pipe cycle while
  preserving UTF-8 surrogateescape, output capture, deadlines and filter refusal.

- A packet-level experiment confirms that the pinned AWG userspace runtime
  writes a computed UDP checksum of zero as 0000 instead of ffff. Correct both
  checksum-completion paths with a strictly admitted source correction. Bind
  correction bytes to source-build receipts and immutable acquisition paths;
  native acceptance must use the same correction. Preserve TCP checksums,
  offload behavior, authentication, and all packet guards. Refuse unreviewed
  source shapes rather than apply a fuzzy correction.

## Contracts and ownership

- Network worker: NAT outputs and related tests/docs in all provider roots
  and the inert cascade root; inventory NAT range
  metadata, AWG/firewall and split-hop-egress NAT admission and templates;
  nginx HSTS template, role notes, and public-site tests/docs.
- Certificate worker: check-certs, its profile-aware callers, certificate tests
  and operator certificate documentation.
- Client worker: kill-switch checker, destination name policy, cascade relay,
  normalizer UDP payload path, matching tests and client documentation.
- Client worker also owns the checkout metadata input transport and its tests.
  Its separate scripts/CLAUDE.md paragraph is serialized with the primary.
- Primary: AWG source correction, production role integration and build
  identity. Certificate worker: focused source-admission tests and independent
  review. Client worker: native build
  consumers and deterministic checksum packet regression. Coordinate their
  shared helper interface before edits; primary owns shared notes and evidence.
- Primary: resolver role and site retirement ordering, task artifacts, shared
  scripts/tests notes, evidence ledger, snapshots, integration and publication.
- Workers leave shared scripts/CLAUDE.md and tests/CLAUDE.md to the primary.
  Shared-file conflicts with other sessions use normal integration and reviewed
  taskctl board regeneration. No force push or foreign worktree edits.

## Risks / Trade-offs

- NAT source-port remapping must preserve ICMP, per-device routing and guest
  input denial. Native tests cover low/high client ports and both AWG families.
- Public trust checks can expose incomplete chains or private CA configuration;
  report categorical failure and retain explicit trust-store ownership.
- An alternate-port hostname may have an old HSTS cache; max-age zero clears it
  only after a successful visit. Document existing browser recovery limits.
- Restoring a stub before bridge retirement can cause DNS failure. Test the
  complete enable-disable sequence and preserve custom resolver authority.
- Lossy Unicode inputs now refuse; explicit A-label input preserves identity.

## Migration Plan

Run focused pytest, provider tests, template snapshots and native regressions,
then the complete make check under the shared build gate. Run security review
and structured review on the final diff. Open a PR, integrate concurrently
merged source, require protected checks, and merge the exact reviewed candidate.
No rollout occurs in this task. A later authorized deployment must separately
verify effective resolver, provider rules, TLS identity, and client traffic.
