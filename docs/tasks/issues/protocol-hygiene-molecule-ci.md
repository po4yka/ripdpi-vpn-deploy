---
id: TST-1793428205355254
title: Remove label and knowledge-store hygiene violations and host every Molecule scenario
kind: chore
status: doing
area: testing
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-31
updated: 2026-10-31
spec_reason: tooling-only
related_tasks: []
---

## Goal

Repository code, comments and operator messages name cohorts and paths by technical signature instead of geographic or censorship-apparatus labels. They no longer cite an external knowledge store. Hosted CI runs every committed Molecule scenario, and a guard keeps both properties from regressing.

## Acceptance criteria

- No geographic or apparatus label remains outside documented functional GeoIP data and the policy corpora. No knowledge-store citation remains outside `docs/archive/`.
- `tests/unit/test_repository_identifier_policy.py` fails on a reintroduced label or citation.
- Hosted CI runs `snell`, `split-hop-ingress`, `probe-matrix-target`, `policy-ratelimit` and `reality-self-steal` default scenarios, plus the `nginx-xhttp/fallback-on` and `reality-self-steal/disabled` scenarios, and `docs/reference/testing.md` lists them.
- Role notes that contradicted code are corrected.
- Renaming the `tspu-canary` script identifier is deferred: it changes installed operator cron entries.
