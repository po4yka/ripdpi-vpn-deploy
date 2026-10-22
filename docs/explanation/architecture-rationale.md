# Architecture rationale

> **Status:** Current · **Type:** explanation · **Tier:** CORE · **Reviewed:** 2026-10-21

[The architecture reference](../reference/architecture.md) records what each
layer owns and which role listens where. This page records why.

## Disposable nodes

Every node is replaceable. When an IP burns or a configuration drifts, do
not hand-repair a snowflake server; recreate it from git, the encrypted
secrets and a Terraform plan. The state lives in two places:

1. The encrypted secrets file outside Git tracking: normally under
   `~/.config/vpn-provision/`, or in the repository's git-ignored
   `secrets/local/config/` operator layout.
2. The Terraform state file, local and scoped per provider and `ENV`. Back
   it up out of band. `prod` uses the legacy `default` workspace; other
   environments live in same-named Terraform workspaces.

Lose the secrets file and you must rotate every credential. Lose the
Terraform state and you can re-import the VPS, but blue-green becomes
manual. See [the incident runbook](../how-to/incident.md#state-loss).

## Why direct nginx and no CDN

[Decision 0001](../decisions/0001-cdn-not-filtered-path-baseline.md) is the
record. The short version: as of April–May 2026 the major CDN's in-country
points of presence sit behind the same DPI enforcement point, one regional
CDN closed its write methods and another dropped anonymous endpoints. A
CDN-fronted P1 is no longer a baseline; it is a tactical option that the
`cdn-front` role keeps off by default.

## Why one Terraform root per provider

Terraform module sources cannot be variable-driven, so a clean drop-in is a
separate root per provider with identical outputs. The Ansible layer is
provider-neutral; only `scripts/render-inventory.sh` reads the
provider-specific outputs (`server_ipv4`, `server_ipv6`, `admin_user`,
`ssh_port`, `server_hostname`). The SSH port is a single Terraform input
that also configures cloud-init, provider-edge rules, the rendered
`ansible_port` and the effective nftables allowlist.

## Why Ansible and systemd own runtime state

Containers add a second scheduler, a second network namespace model and a
second supply chain to a host whose whole job is to look like an ordinary
web server. Ansible roles render files and systemd units that a person can
read on the box, Molecule tests each role in isolation, and the full-stack
scenario tests their order and handlers together. The data plane therefore
has no Docker or Kubernetes, and a pull request that adds one is closed
with a pointer here.

## Why there is no admin panel and no auto-deploy

A web panel is a second public surface with its own authentication, and the
threat model treats every public surface as a probe target. Deployment is
operator-driven from a reviewed plan and a reviewed dry-run because the
fleet is small, the blast radius of a bad push is total loss of access for
the people who depend on it, and recreation is cheap.

## What is intentionally not here

- Multi-region fleet automation. v1 is single-VPS; second-VPS guidance is
  in [the fallback runbook](../how-to/add-fallback.md).
- Subscription delivery as a dynamic API service. `subscription-host` ships
  static token payloads with a revoked-tokens map and a rate-limit zone;
  there is no application server behind the vhost.
- P3 reachability-layer automation. The reachability layer is
  network-specific and operator-judged, not deterministically deployable.
- Per-role Molecule coverage for every supported role; selected red-path
  scenarios run in CI and the coverage matrix in
  [the testing reference](../reference/testing.md) names the gaps.
