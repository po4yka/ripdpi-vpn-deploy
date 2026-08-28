## Context

Thirteen deploy-path findings from the audit (2026-08-23) share a theme: the safety rails exist but are skippable, unbounded, or inconsistent across invocation paths. Evidence citations live in the linked portfolio record. All fixes are local to playbooks, scripts, the Makefile dependency graph, one Terraform variable validation block, and group_vars defaults.

## Goals / Non-Goals

- Goal: make the canonical operator path self-enforcing on every invocation shape without changing what gets deployed.
- Non-goal: reworking role internals, listener contracts, or adding new guard systems — existing guards get tags and parity, not replacements.

## Decisions

- Bootstrap readiness and convergence belong to one Make-dispatched controller, outside runtime role execution. A standalone prerequisite followed by rereading the original inventory could validate one target and deploy another. The controller snapshots inventory privately, resolves empty selection to all canonical vpn hosts or resolves exact aliases/cohort groups/comma unions, and calls the unchanged strict select_hosts API once for the final aliases. HOSTS and Terraform outputs do not participate in deploy selection.
- The private selected inventory preserves cohort membership and runtime host metadata. Canonical all/vpn/sorted-cohort variables are loaded independently per host, then host metadata, secrets and approved overrides. Actual Ansible tests must establish types, Jinja evaluation, precedence and controller-local delegation; Python must not emulate Ansible's recursive variable semantics. Ambient host/group vars, plugins, callbacks, collections and Git routing cannot add authority.
- Configured plugin paths alone do not disable Ansible's playbook/role directory discovery. Reject the installed loader's plugin subdirectories at those source bases, symlinked role paths and playbook-relative shadow roles before any SSH. This repository has no custom plugins in those locations. Canonical roles and the explicitly configured trusted collection installation remain supported; this is not an installation-wide Python sandbox.
- Approved address/port overrides apply before readiness. Every selected key, known-host file, transport and private local input is validated before the first SSH process. The same frozen transport records are used for readiness, site.yml and source-drift.yml; final transport controls must not redirect delegate_to: localhost tasks. A clean-source recheck after waiting precedes mutating convergence. Audit remains best effort and follows successful convergence plus source parity.
- The shared bootstrap engine bounds local process groups, remote cloud-init status waits and cancellation cleanup. The standalone Terraform wait retains its first-boot SSH policy; deployment uses the unchanged strict ssh_command builder. Fatal/recoverable cloud-init errors, missing marker, remote deadline exhaustion and local transport/session failures remain distinct, without raw cloud-init output.
- Cohort validation against the group_vars file set rather than a second allowlist: single source of truth for profile names.
- SSH allowlist enforced in both Terraform validation and site.yml assert: plan-time failure plus defense in depth for hand-rendered inventories.
- Rotation .prev via copy before template write: reuses the exact contract rollback-config already consumes; no new artifact format.
- Rollback ordering fix is reorder-only plus a no-op guard; no new validation machinery.
- Toggle-default parity enforced by pytest sweep instead of convention: drift becomes a red test.

## Contracts and ownership

- Playbooks owned here: site.yml, smoke-test.yml, os-maintenance.yml, rotate-credentials.yml, rollback-xray.yml.
- Scripts owned here: wait-cloud-init.sh, bootstrap_readiness.py, deploy-controller.py, render-inventory.sh (shell adapters are shellcheck-gated). The readiness slice does not edit fleet_inspection.py, backup-configure.py or SSH migration entry points.
- Makefile targets touched: deploy/dry-run dispatch, matching literal inputs and target-specific identity export suppression before controller validation; canary dispatch only where needed. Other targets and documented multiple-goal workflows retain their behavior.
- terraform/providers/*/variables.tf: additive validation block only; no output schema change.

## Risks / Trade-offs

- Deploy now blocks on bootstrap completion → slower but honest; SKIP-style escape hatch intentionally NOT added (the runbook already sequences manual steps).
- Stricter renderer failures can break ad-hoc HOSTS strings that previously half-worked → intended fail-loud behavior.
- Complex Ansible selection patterns are no longer accepted by deploy/dry-run. Repository callers using empty limits, exact hosts and canonical groups remain supported. Unknown, empty-result or ambiguous selections fail before SSH.
- Full local, hosted and authorized live-inventory checks remain required independently of isolated process/Ansible fixtures; source completion does not establish deployment acceptance.
- Restart-based AWG/rollback changes briefly interrupt service during maintenance windows → acceptable; documented.

## Migration Plan

- Forward: single commit per concern; no state migration required.
- Rollback: revert playbook/script commits independently.
- Gates: named pytest cases, shellcheck, `make ci-fast`, `make validate`, live-inventory dry-run before merge.
