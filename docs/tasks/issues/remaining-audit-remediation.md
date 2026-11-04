---
id: SEC-1793790940328939
title: Remediate remaining audit and remediation findings
kind: bug
status: backlog
area: security
priority: medium
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793790940328939-remaining-audit-remediation
created: 2026-11-04
updated: 2026-11-04
related_tasks: []
---

## Goal

The zone can publish mail and certificate authority policy. Recipients cannot reach benchmarking, NAT64 or 6to4 destinations. Xray runs in the transport sandbox. An expiring self-steal certificate and relay sample drops raise alerts.

## Acceptance criteria

- The Vultr root plans TXT, CAA and `_dmarc` records and rejects malformed ones.
- The recipient policy, the AWG drop set and the gateway filter refuse `198.18.0.0/15`, `64:ff9b::/96` and `2002::/16`.
- The Xray unit passes the transport sandbox test.
- Promtool tests show the certificate expiry alerts firing for an expiring self-steal certificate, and the relay drop alert firing.
- `scripts/release-inputs.py` emits the relay pin.
