## Context

The six P1 groups affect edge management isolation, immutable cloud-init identity,
Hetzner provisioning and operator policy enforcement. Provider roots remain
independent and the Makefile remains the canonical operator entry point.

## Goals / Non-Goals

- Goal: implement all six P1 groups and remaining actionable P2 groups with
  positive and failure-path regression proof in PR 281.
- Non-goal: optional DNS/image/default-backup refactors, live resource changes
  or fleet acceptance.

## Decisions

- Reject numeric zero-prefix management networks, including noncanonical host bits.
- Require integer ssh_port inputs and validate them against effective explicit or legacy TCP selectors. Require
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

## Integration with current main

The deployment-security change adds the canonical check-tf-plan.sh and
policy-plan.sh operator surfaces plus firewall.rego normalization. This change
uses those surfaces and one Python evaluator, retains complete policy-family
coverage and readonly snapshot custody, and extends conservative selector and
integer-port checks. Duplicate apply and port-helper paths are removed. Incoming
bootstrap seed, deployment and runtime fixes are preserved without deployment.

## Migration Plan

Review private Terraform inputs before an authorized deployment. Apply uses a
saved plan and mandatory policy evaluation. The former Hetzner attachment is
forgotten without deletion; existing firewall membership is owned by the server.
No deployment occurs in this change. Source rollback is reversible; resource
rollback requires an independently reviewed plan and explicit authorization.

Run targeted native/policy/subprocess regressions, then build-gate -- mise exec --
make check. Obtain independent diff and security review before commit/push/PR.
Record exact-head hosted checks separately from local and live evidence.

## P2 follow-up decisions and ownership

- Lifecycle worker owns Vultr main.tf and firewall.tf plus new
  tests/provider-adapter.tftest.hcl. Canonical listener values and resource keys
  stay hyphen-based; only Vultr resource.port converts hyphens to colons.
  enable_backups keeps its positive behavior with a conditional daily schedule
  at 03:00 UTC, and disabled backups produce no schedule block.
- Port worker owns all four variables.tf files, existing firewall.tftest.hcl
  files and new port-validation.tftest.hcl files. Preserve null/exactly-one
  selector rules and existing bounds, add integer checks, and select legacy
  mode explicitly when testing its distinct-port and collision behavior.
- Primary owns shared cloud-init, its CI renderer, serialization tests,
  executable-coverage native registration,
  generated READMEs, all subtree guidance, planning and PR integration.
  Primary also owns the narrow Scaleway retained-key whitespace normalization;
  the lifecycle worker applies the equivalent Vultr change in its owned main.tf.
  Encode username/key scalar values and the complete metadata string with
  Terraform jsonencode. CI uses equivalent encoding for its fixed synthetic
  values; tests execute real Terraform template rendering and YAML parsing.
- Input encoding does not add administrator/key policy restrictions. It
  preserves the supplied scalar as data, including punctuation and newlines.
  Format strings before JSON encoding so the previous null-input refusal remains;
  the fixed CI renderer also rejects null scalar fixtures rather than encoding null.
  Numeric SSH interpolation remains guarded by the existing integer input.
  Retained authorized-key comparisons normalize surrounding whitespace on the
  complete typed list, preserving refusal of extra keys or malformed structures.
- Already repaired P2 findings: ordinary UpCloud dual-stack policy, Hetzner
  guest floating-IP convergence from current main and fractional SSH ports.
  The original Debian 11 finding is withdrawn: Vultr OS 1743 is Ubuntu 22.04.
- Shared guidance and metadata remain serialized through primary. Workers
  share the dedicated PR worktree, do not commit and preserve each other's edits.
