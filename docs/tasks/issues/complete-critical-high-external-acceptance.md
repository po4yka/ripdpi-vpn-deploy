---
id: EPC-1788891270457728
title: Complete Critical and High external acceptance gates
kind: epic
status: blocked
area: epic
priority: critical
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: epc-1788891270457728-complete-critical-high-external-acceptance
created: 2026-09-08
updated: 2026-09-08
related_tasks: []
status_detail: Exact protected source b5682b9a passed push CI 75/75, CodeQL and Scorecard; no-write and secret prechecks passed. Blocked on provider credentials and cost approval; all three exact fleet targets time out on both public and management SSH transports and strict SSH contexts are absent; current client handoff, alert delivery, and isolated restore capabilities are unavailable.
---

## Goal

Complete the still-unproven external acceptance for every previously delivered
Critical and High capability from one clean protected-main source revision.
Source and hosted CI remain prerequisites, while dry-run, isolated staging,
live-fleet, current-client, alert-delivery, recovery, and cleanup evidence stay
distinct and must be observed in their owning environments.

## Acceptance criteria

- A clean protected-main commit passes its exact hosted required checks before
  any staging or live action, and every later evidence record names that commit
  and the deployed source digest.
- A provider-bound isolated staging node is created only through the guarded
  manifest lifecycle, remains within the owner-approved spend and lifetime,
  exercises SSH migration and recovery plus required transport/security
  behavior, and is destroyed with provider-confirmed absence evidence.
- The configured fleet completes serial dry-run, deploy or reconvergence,
  verification, security verification, and source-drift checks without losing
  the emergency SSH or VPN paths.
- A current signed client artifact proves authenticated REALITY, XHTTP,
  Hysteria2, and AmneziaWG traffic with invocation-bound evidence; recurring
  AmneziaWG publication proves fresh success, recovery, and cleanup rather than
  reusing a previous PASS.
- Central and independent dead-man alert paths fire and recover under a
  controlled drill, and the required offsite backup copy is restored in an
  isolated location without pruning retained data.
- Evidence reconciles the unfinished requirements from predecessor tasks
  ANS-1786277767052693, MON-1788008977760206, TST-1786299293097217,
  OPS-1787496414433523, TST-1787850553468536, SEC-1787916931540401,
  SEC-1787496747898735, SEC-1787496881680472, ANS-1787495907091073,
  TST-1787497001212692, SCR-1786299499104067,
  VPD-1787497317352770, and VPD-1787497252303967.
- If an external account, credential, target, current client artifact, signer,
  relay, or human executor is unavailable, this task remains open with the
  exact blocker and the last safe completed boundary; source or CI evidence is
  never credited as staging, live, client, or operational closure.
