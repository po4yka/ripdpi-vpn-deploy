---
id: SEC-1795086333272606
title: Ingest opt-in client field reports into bounded Prometheus metrics
kind: feature
status: review
area: security
priority: high
risk: high
owner: Implementer
parent: EPC-1795085241910080
blocked_by: [SCR-1795085709140075]
spec_mode: required
openspec_change: sec-1795086333272606-field-report-ingest-d2
created: 2026-11-19
updated: 2026-11-19
related_tasks: [po4yka/RIPDPI#DGN-1795085498592630]
status_detail: Re-review findings N1-N4 and L5 fixed and verified locally, Molecule included; independent review pending
---

## Goal

The subscription host accepts anonymous client field reports on one POST endpoint, validates and rate-limits them, and aggregates them into Prometheus metrics with bounded labels and alerts on failure rate by protocol and ASN.

## Acceptance criteria

- POST accepts a schema-valid report with a valid `cohort_token` and rejects invalid schema, bad token, oversize body and over-limit rate with distinct status codes.
- No request log line contains a client IP beyond the existing categorical log policy.
- Metrics use only the labels protocol, failure_stage, asn (top-N else "other"), country and server_ref.
- Alert rules fire on failure rate by protocol and ASN and pass promtool tests.
- The security-review skill checklist is recorded in verification.
