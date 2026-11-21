## Context

`terraform/providers/*/listeners.tf` resolves `public_listeners` and exports it to the inventory. `site.yml` refuses a deploy when the runtime manifest disagrees with that contract, the firewall role builds its accept rules from it, and `security-verify.yml` compares live rules with it. None of these layers knows an address family.

## Goals / Non-Goals

Goals: one family field that all four layers read; an absent field keeps the current dual-stack behaviour.

Non-goals: per-family ports, changes to the transport roles, a default other than `dual`.

## Decisions

- Add the field to the existing entry instead of a separate family map, so every layer keeps one list.
- Default `dual`, so existing tfvars and inventories need no change.
- The node ruleset adds `meta nfproto` to a single-family accept; the verifier treats an accept on the other family as a violation.
- Terraform stores the field as `family = optional(string)`; null means dual, so existing provider rule keys and attributes stay the same. The `public_listeners` output gains `family: null`, and every consumer treats an absent key and null as dual, because state written before this change has no key until the next apply.
- The runtime states its family in the Ansible map `public_listener_families` (role to family). The listener manifest carries it only when stated, and `check-listener-contract.py` compares it with the contract, as it already does for ports.
- The `listener_family` plan policy refuses a world-open provider rule that admits any port of a single-family listener on the closed family, so `make apply` refuses a saved plan that disagrees with its own contract.
- The node hopping redirect takes the family of the contract entry whose `port_range` equals `hysteria_port_range`, so the closed family cannot reach a dual Hysteria port through the redirect.
- AWG claims inherit the family of the contract entry with the same port.

## Contracts and ownership

Terraform owns the field; Ansible and the scripts only read it. The inventory export carries it unchanged.

## Risks / Trade-offs

- A provider whose firewall API has no family selector needs a documented limit; the node ruleset still enforces the family.
- A transport that binds dual-stack sockets keeps listening on the closed family; the firewall layers carry the restriction.
- UpCloud stateless return rules open `provider_return_ephemeral_ports` on both families, so the UpCloud root refuses a single-family listener inside that range.
- The runtime map is keyed by role, so two listeners of one role (for example two AWG instances) cannot state different families; the contract check refuses that case instead of guessing.
- The Tailnet network controller and the Vultr staging cleanup guard accept single-family provider rules; the cleanup guard no longer requires the same listener set in both families.

## Migration Plan

Ship with the `dual` default. The operator sets `family` per entry, applies Terraform, then deploys. Rollback removes the field.
