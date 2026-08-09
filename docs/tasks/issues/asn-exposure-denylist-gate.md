---
id: ANS-1786277767052693
title: Implement a disabled-by-default network exposure denylist gate
kind: feature
status: backlog
area: ansible
priority: high
risk: high
owner: Infrastructure security role
parent: null
blocked_by: []
related_tasks: []
spec_mode: required
openspec_change: ans-1786277767052693-add-network-exposure-denylist-gate
created: 2026-08-09
updated: 2026-08-09
---

# Implement a disabled-by-default network exposure denylist gate

## Goal

Deliver a fail-closed, disabled-by-default Ansible gate that can validate a reviewed network-exposure feed, render separate ingress and egress policy intent, and produce a redacted dry-run or log-only result without shipping deployable address data in the repository.

## Ownership

- Primary paths: a new Ansible role, its defaults/templates/tests, placeholder-only fixtures, and operator documentation.
- Integration paths: `ansible/group_vars/`, `ansible/playbooks/site.yml`, firewall render inputs, and optional `vpnd` dry-run review.
- Serialized lanes: firewall role templates, secrets schema, and shared group variables require one writer at a time.

## Acceptance criteria

- The default configuration does not change the rendered firewall or any managed host.
- Feed metadata and policy intent have validated schemas and placeholder-only fixtures; the repository contains no address ranges or ready-to-load rule payloads.
- Ingress, host-originated egress, and forwarded-traffic decisions remain explicit and independently reviewable.
- Invalid, stale, unsigned, or unreviewed inputs fail closed before render or apply.
- Dry-run output exposes only counts, repository-local source identifiers, policy direction, validation state, and content digest.
- Log-only and canary modes have explicit promotion, false-positive monitoring, rollback, and expiry criteria.
- Feed refresh is a reviewed artifact update; no hidden updater or apply path exists.

## Verification commands

- `make task-check`
- `make molecule-test ROLE=<denylist-role>`
- `python3 -m pytest tests/unit/ -q`
- `make dry-run` against an isolated staging inventory with the feature disabled and in log-only mode

## Context

The prior record referred to external source locations. Repository policy now requires durable knowledge and provenance to live in-repository, so the implementation will use reviewed metadata and content digests without externally hosted citations or deployable network data.
