## Context

Thirteen deploy-path findings from the audit (2026-08-23) share a theme: the safety rails exist but are skippable, unbounded, or inconsistent across invocation paths. Evidence citations live in the linked portfolio record. All fixes are local to playbooks, scripts, the Makefile dependency graph, one Terraform variable validation block, and group_vars defaults.

## Goals / Non-Goals

- Goal: make the canonical operator path self-enforcing on every invocation shape without changing what gets deployed.
- Non-goal: reworking role internals, listener contracts, or adding new guard systems — existing guards get tags and parity, not replacements.

## Decisions

- Bootstrap gate as a Makefile prerequisite rather than an Ansible pre_task: it keeps the wait outside converge, avoiding dpkg-lock contention by construction.
- Cohort validation against the group_vars file set rather than a second allowlist: single source of truth for profile names.
- SSH allowlist enforced in both Terraform validation and site.yml assert: plan-time failure plus defense in depth for hand-rendered inventories.
- Rotation .prev via copy before template write: reuses the exact contract rollback-config already consumes; no new artifact format.
- Rollback ordering fix is reorder-only plus a no-op guard; no new validation machinery.
- Toggle-default parity enforced by pytest sweep instead of convention: drift becomes a red test.

## Contracts and ownership

- Playbooks owned here: site.yml, smoke-test.yml, os-maintenance.yml, rotate-credentials.yml, rollback-xray.yml.
- Scripts owned here: wait-cloud-init.sh, render-inventory.sh (shellcheck-gated).
- Makefile targets touched: deploy, dry-run, new bootstrap-readiness target.
- terraform/providers/*/variables.tf: additive validation block only; no output schema change.

## Risks / Trade-offs

- Deploy now blocks on bootstrap completion → slower but honest; SKIP-style escape hatch intentionally NOT added (the runbook already sequences manual steps).
- Stricter renderer failures can break ad-hoc HOSTS strings that previously half-worked → intended fail-loud behavior.
- Restart-based AWG/rollback changes briefly interrupt service during maintenance windows → acceptable; documented.

## Migration Plan

- Forward: single commit per concern; no state migration required.
- Rollback: revert playbook/script commits independently.
- Gates: named pytest cases, shellcheck, `make ci-fast`, `make validate`, live-inventory dry-run before merge.

## Smoke cleanup slice — 2026-08-28

- The existing smoke play owns only its temporary clients and tmpfs workdir. It atomically creates `/run/vpn-smoketest`; an occupied directory fails before entering any cleanup block. A fresh random invocation suffix gives each transient client a private unit name. The fixed workdir claim serializes canonical invocations sharing the existing loopback SOCKS ports, while unique unit names avoid ownership races with unrelated services. No stale-resource adoption or automatic recovery is introduced.
- Each enabled protocol uses block/rescue/always, stops only a uniquely named client whose start returned success to this invocation, and reports probe failure even when cleanup succeeds. Unexpected stop errors remain fatal. The enclosing owned block removes the workdir only when no start was attempted or the current run confirmed client cleanup. An unconfirmed start/stop retains the private claim and configs, reports manual recovery, and blocks retries from accidentally probing a lingering client on the fixed SOCKS ports. A removal failure is also fatal. A failed or ambiguous start is never treated as ownership proof; in particular, a foreign unit reported as already existing is never stopped. Credential-bearing tasks retain no_log and diff suppression.
- While holding the claim, require every configured smoke SOCKS port to be vacant with a one-second bounded stopped-state wait before starting a client. After listener readiness and after the complete protocol probe (all Snell variants), check that this invocation's unique unit is active. An occupied port or early client exit must fail instead of accepting a foreign listener's HTTP 204. Every curl probe also sets `--noproxy ''`, forcing the configured SOCKS proxy even when the target service environment contains `NO_PROXY` or `no_proxy`. A direct HTTP 204 must not substitute for a working smoke proxy. These checks cover existing occupants and observed client death, not a privileged external actor racing socket replacement.
- Transient clients receive a bounded RuntimeMaxSec as a backstop if the controller disconnects. Ansible always blocks cannot guarantee execution after an unreachable host or controller termination; the private workdir may remain and must cause a subsequent invocation to refuse. This is not a disconnect-cleanup guarantee.
- Ports, transport defaults, deployed services and Make entrypoints are unchanged. Tests execute the actual Ansible task graph locally with temporary executables at the systemd/network boundary, including positive runs, start/wait/curl failures, cleanup failures, occupied resources and concurrent claims. Real Linux systemd and fleet acceptance remain separate.
