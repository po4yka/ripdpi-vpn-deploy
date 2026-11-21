## Context

`terraform/providers/*/listeners.tf` resolves `public_listeners` and exports it to the inventory. `site.yml` refuses a deploy when the runtime manifest disagrees with that contract, the firewall role builds its accept rules from it, and `security-verify.yml` compares live rules with it. None of these layers knows an address family.

## Goals / Non-Goals

Goals: one family field that all four layers read; an absent field keeps the current dual-stack behaviour.

Non-goals: per-family ports, changes to the transport roles, a default other than `dual`.

## Decisions

- Add the field to the existing entry instead of a separate family map, so every layer keeps one list.
- Default `dual`, so existing tfvars and inventories need no change.
- The node ruleset adds `meta nfproto` to a single-family accept; the verifier treats an accept on the other family as a violation.

## Contracts and ownership

Terraform owns the field; Ansible and the scripts only read it. The inventory export carries it unchanged.

## Risks / Trade-offs

- A provider whose firewall API has no family selector needs a documented limit; the node ruleset still enforces the family.
- A transport that binds dual-stack sockets keeps listening on the closed family; the firewall layers carry the restriction.

## Migration Plan

Ship with the `dual` default. The operator sets `family` per entry, applies Terraform, then deploys. Rollback removes the field.
