---
id: ANS-1787422293187845
title: Decommit the production decoy domain from group_vars
kind: bug
status: done
area: ansible
priority: high
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1787422293187845-decommit-public-site-domain
created: 2026-08-22
updated: 2026-08-23
related_tasks: []
closed_at: "2026-08-23T04:56:03Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "All 54 required CI checks green on PR #84 final SHA 9aa0e5e, merged to main as 4e26e7e; full pytest green (925 passed); make validate green; OpenSpec change archived with requirement evidence in verification.md"
---

## Goal

The production decoy domain no longer exists anywhere in the committed tree:
cohort profiles carry only the neutral placeholder, the real origin is
supplied per deploy through the validated `ANSIBLE_EXTRA_VARS_FILE` channel,
and rotating the decoy identity never touches version control.

## Acceptance criteria

- No file in the working tree contains the previously committed decoy domain.
- Committed group_vars profiles pin `public_site_canonical_url` to
  `https://vpn.example.com`; a contract test enforces it.
- The extra-vars validator accepts only well-formed https origins for the new
  allowlisted key and rejects every other shape.
- docs/DEPLOY-PROFILES.md documents the override workflow; convergence stays
  fail-closed via the existing nginx-xhttp / hysteria role asserts.
