---
id: ANS-1794807418945435
title: Present one TLS identity on the live split-hop Node A
kind: feature
status: done
area: ansible
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1794807418945435-split-hop-live-single-tls-identity
created: 2026-11-16
updated: 2026-11-16
related_tasks: []
closed_at: "2026-11-16T17:55:18Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Merged as 95dce88b with CI run 43812776555 green. The live Node A was deployed at 441c02b4 with REALITY self-steal: deploy, verify, source-drift and security-verify exit 0, one certificate on TCP/443, TCP/8443 and QUIC/443, and a passed liveness proof from the sentinel on Node B. The device imported the changed entries, and REALITY, XHTTP, Hysteria2 and AmneziaWG each connected from it with the Node B address as egress."
---

## Goal

The live split-hop Node A presents one TLS identity on its production address: TCP/443 shows the operator certificate that nginx-xhttp and Hysteria already show. Its committed profile then passes the production TLS identity preflight without a recorded exception.

## Acceptance criteria

- The profile `vpn-split-hop-family-egress-live` enables REALITY self-steal and sets a self-steal port that the role's port guard admits beside the public nginx-xhttp port.
- The TLS identity preflight passes for that profile on a production host; the onboarding and staging split-hop profiles keep their result.
- The live Node A is deployed from the merged revision after a reviewed full dry-run, `make verify` and `make security-verify` pass, the sentinel on Node B gives a fresh liveness proof, and the refreshed device reaches Node B through each transport.
