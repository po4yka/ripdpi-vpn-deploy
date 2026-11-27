---
id: SEC-1795706124070316
title: Assess TLS-in-TLS classifier exposure of the XHTTP transport
kind: research
status: review
area: security
priority: low
risk: standard
owner: Planner
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-26
updated: 2026-11-27
spec_reason: research-only
related_tasks: ["po4yka/RIPDPI#TRN-1795705033979683"]
status_detail: Assessment in docs/research/xhttp-tls-in-tls-exposure-2026-11.md; go suggestion for VLESS Encryption with Vision on P1, filing left to the owner
---

## Goal

A short written assessment says whether the XHTTP transport (P1) is exposed to a TLS-in-TLS traffic classifier and what shaping options exist. Research tier only. No delivery commitment.

Evidence: a preprint dated 2026-11-23 reported that shaping a proxy to mimic one TLS server cut a classifier detection rate from over 85 percent to about 3 percent at a 1 percent false-positive rate. The data came from an ISP outside the filtered path, and only the abstract was read. Treat it as single-source and unverified. The P0 Vision flow partly addresses encapsulated-handshake fingerprints. P1 does not.

## Acceptance criteria

- The assessment states which TLS-in-TLS features apply to P1 and which Vision already covers for P0.
- Each claim names its source class and confidence. Abstract-only evidence stays marked as such.
- The assessment lists shaping options as design-level notes, with no concrete evasion parameters.
- The assessment ends with a go or no-go suggestion for a follow-up feature task. Filing that task is a separate decision.
