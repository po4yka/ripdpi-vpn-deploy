## Context

The six P1 groups affect edge management isolation, immutable cloud-init identity,
Hetzner provisioning and operator policy enforcement. Provider roots remain
independent and the Makefile remains the canonical operator entry point.

## Goals / Non-Goals

- Goal: implement all six groups with positive and failure-path regression proof.
- Non-goal: unrelated P2 findings, live resource changes or fleet acceptance.

## Decisions

- Reject numeric zero-prefix management networks, including noncanonical host bits.
- Validate ssh_port against effective explicit or legacy TCP selectors. Require
  UpCloud SSH outside the stateless return range in both activation phases.
- Preserve terraform_data.ssh_port addresses. Add separate username and public-key
  digest guards where provider-native identity replacement is missing; retain
  prevent_destroy and ignored user_data. Migration must not replace unchanged nodes.
  First adoption checks retained Vultr/Scaleway cloud-init identity. Hetzner's
  hashed user-data requires an existing key-name attribute trigger instead; this
  also makes server-name edits protected creation-time changes.
- Use current curated Hetzner types. Make server.firewall_ids the sole attachment
  owner and forget the old attachment with removed.destroy=false to avoid detach.
- Share one all-namespace Conftest evaluator. Refuse failed, malformed or empty
  evaluation and inspect only private JSON files. Make apply snapshots the saved
  binary plan privately and evaluates/applies that exact copy, preserving its exit
  status and cleaning temporary material. Standalone tf-conftest uses the evaluator.
- Count UpCloud public IPv4 interfaces for secondary-IP opt-in. Policy management
  checks recognize singleton and inclusive range selectors in each provider shape.

## Contracts and ownership

- Management worker: four provider variables.tf files, Hetzner type examples and
  native management tests. Provider main/firewall files are owned by lifecycle worker.
- Lifecycle worker: Hetzner, Vultr and Scaleway main.tf, Hetzner firewall.tf,
  provider lifecycle tests and credential-free state migration/transition harness.
- Primary: Makefile, policy files, operator scripts, policy/gate tests, generated
  provider READMEs, subtree guidance, task/spec metadata, integration and PR.
- Shared metadata and subtree guidance edits are serialized through primary.

## Risks / Trade-offs

- The pinned ShellCheck hook runs natively through mise instead of a Docker bind
  mount, so managed worktrees remain visible without changing VM sharing policy.
  Its version, script selection and warning severity remain unchanged.

- Retired private type inputs now fail; reviewed replacements may require a
  disruptive resize, so document the disposable-node path rather than auto-migrate.
- Identity edits now hit prevent_destroy; existing users must review and create
  a replacement node rather than assume guest keys/users were updated in place.
- Correct policy enforcement can reveal previously accepted plans. Repair the
  dual-stack policy first and prove safe plans pass, while ranges covering SSH fail.
- Added identity guards and attachment ownership must preserve unchanged existing
  nodes; migration tests are required before delivery.

## Migration Plan

Review private Terraform inputs before an authorized deployment. Apply uses a
saved plan and mandatory policy evaluation. The former Hetzner attachment is
forgotten without deletion; existing firewall membership is owned by the server.
No deployment occurs in this change. Source rollback is reversible; resource
rollback requires an independently reviewed plan and explicit authorization.

Run targeted native/policy/subprocess regressions, then build-gate -- mise exec --
make check. Obtain independent diff and security review before commit/push/PR.
Record exact-head hosted checks separately from local and live evidence.
