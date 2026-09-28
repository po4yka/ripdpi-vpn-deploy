---
id: EPC-1788891270457728
title: Complete Critical and High external acceptance gates
kind: epic
status: doing
area: epic
priority: critical
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: epc-1788891270457728-complete-critical-high-external-acceptance
created: 2026-09-08
updated: 2026-09-28
related_tasks: []
status_detail: Owner scope excludes Android, alert drills, and offsite restore as of 2026-09-28; no excluded check is credited as passed. Ordinary staging and cleanup were observed on protected source 52eda3d97feb4b697e1465beee55df2e9f5b3eed. Current controller-loss proof and permanent-fleet management access remain incomplete; serial fleet and authenticated transport acceptance remain required.
---

## Goal

Complete the still-unproven external acceptance for every previously delivered
Critical and High capability from one clean protected-main source revision.
Source and hosted CI remain prerequisites, while dry-run, isolated staging,
live-fleet, authenticated transport, recovery, and cleanup evidence stay
distinct and must be observed in their owning environments.

The owner narrowed this acceptance on 2026-09-28: Android installation and
device testing, alert-delivery drills, and offsite copy/restore are excluded.
These exclusions are scope decisions, not successful observations. Existing
alerting and retained backups are not removed by this decision.

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
- Current client profiles and pinned client runtimes prove authenticated REALITY,
  XHTTP, Hysteria2, and AmneziaWG traffic with invocation-bound evidence; recurring
  AmneziaWG publication proves fresh success, recovery, and cleanup rather than
  reusing a previous PASS.
- Post-firewall transport proof and guarded de-onboarding retire only the
  invocation-owned client, executor, and temporary access capabilities.
- Evidence reconciles the unfinished requirements from predecessor tasks
  ANS-1786277767052693, MON-1788008977760206, TST-1786299293097217,
  OPS-1787496414433523, TST-1787850553468536, SEC-1787916931540401,
  SEC-1787496747898735, SEC-1787496881680472, ANS-1787495907091073,
  TST-1787497001212692, SCR-1786299499104067,
  VPD-1787497317352770, and VPD-1787497252303967.
- If an external account, credential, target, client runtime, or authorized
  executor required by this scope is unavailable, this task remains open with the
  exact blocker and the last safe completed boundary; source or CI evidence is
  never credited as staging, live, client, or operational closure.
