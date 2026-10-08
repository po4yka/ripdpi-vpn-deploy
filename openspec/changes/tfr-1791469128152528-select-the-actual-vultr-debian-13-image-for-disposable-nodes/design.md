## Context

The examples pass a mislabeled image ID; the actual Debian 13 ID is rejected.
The provider's current catalog and the created instance identity are independent
evidence. Mock-provider tests only prove validation and plan wiring.

## Goals / Non-Goals

- Goal: make disposable Debian 13 nodes selectable with a correct provider ID.
- Non-goal: modify cloud-init firewall ownership, provider pins or existing servers.

## Decisions

- Pin the verified Debian 13 x64 ID in validation and examples.
- Correct descriptive names using the provider catalog: 1743 is Ubuntu 22.04,
  2136 is Debian 12, 2284 is Ubuntu 24.04, and 2625 is Debian 13.
- Remove 1869, which selects Rocky Linux 9 outside the Debian/Ubuntu runtime contract.
- Test exact planned IDs and refusal of an unapproved image; never loosen validation.

## Contracts and ownership

- Terraform owns the Vultr instance image selection and approved ID validation.
- Only Vultr variables, examples, mock tests and adjacent notes change.
- Ansible runtime, SSH foundation, SOPS, DNS opt-in and CLI contracts remain enforced.

## Risks / Trade-offs

- Image names can drift: independently check provider catalog and actual first boot.
- A correct plan cannot prove SSH availability: keep strict live foundation separate.

## Migration Plan

Merge after focused Terraform tests, policy checks and hosted exact-head CI.
Provision only the already authorized isolated replacement environment after source
acceptance. Verify the actual Debian version, pinned host key and SSH/2222 foundation.
The approved input 1869 is removed; configurations using it must select a supported
Debian/Ubuntu image for a new disposable node. Existing nodes remain available until
full cutover. Retire a failed candidate by exact
reviewed destruction after encrypted state backup; never replace a server in place.
