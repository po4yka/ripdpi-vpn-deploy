# Task management — RIPDPI VPN deployment

This repository uses a two-level, Git-native workflow. Portfolio state lives in Markdown records; changes to infrastructure behavior or contracts additionally use OpenSpec. Execution checkboxes are indexed by mdtask.

## Canonical structure

| Path | Contract |
|---|---|
| `issues/<slug>.md` | Portfolio source of truth: state, priority, ownership, dependencies, and acceptance criteria |
| `work/<TASK-ID>.md` | mdtask execution for work that does not require OpenSpec |
| `../../openspec/changes/<change>/tasks.md` | mdtask execution for OpenSpec-backed work |
| `board.md` | Generated local portfolio view; never edit by hand |

Install the exact repository tools with `make task-tools`. Run `./taskctl --help` for the lifecycle CLI and `make task-check` for the complete contract gate. No global mdtask or OpenSpec installation is required. `taskctl` always disables OpenSpec telemetry.

## Portfolio schema

```yaml
---
id: ANS-1786234567890123
title: Imperative task title
kind: feature
status: doing
area: ansible
priority: high
risk: high
owner: Role name
parent: null
blocked_by: []
related_tasks: []
spec_mode: required
openspec_change: ans-1786234567890123-change-name
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

- `kind`: `feature | bug | chore | research | epic`.
- `status`: `backlog | todo | doing | review | blocked | done | dropped`.
- `priority`: `critical | high | medium | low`.
- `risk`: `standard | high`; high-risk work cannot waive OpenSpec.
- `area`: `ansible | terraform | vpnd | xray-config | operations | monitoring | security | secrets | testing | ci | scripts | sbom | docs | epic`.
- `parent` and entries in `blocked_by` accept a local stable ID or a qualified peer ID such as `po4yka/RIPDPI#TRN-1786234567890456`.
- `related_tasks` contains non-blocking qualified peer IDs. `blocked_by` is canonical; reverse `blocks` is derived.
- A blocked task needs a blocker or a non-empty `status_detail` describing its external gate.
- `done` and `dropped` additionally require `closed_at`, `closed_reason`, and `evidence_summary`.

The numeric suffix is UTC epoch milliseconds multiplied by 1000 plus three random digits. It is unique across portfolio and execution IDs within this repository. Cross-repository identity is the pair `project + ID`. Area prefixes and the federation allowlist are defined by `tools/tasking/project.json`.

## OpenSpec decision

`spec_mode: required` is mandatory for features, behavioral epics, operator-visible behavior, breaking contracts, Terraform or Ansible runtime changes, secrets/configuration schemas, public `vpnd` CLI changes, cross-layer and cross-repository contracts, and security, network, or deployment-lifecycle behavior.

`spec_mode: not-required` is limited to bugs, chores, or research with one explicit reason: `regression-tested-single-module`, `test-only`, `docs-only`, `dependency-only`, `mechanical-refactor`, `tooling-only`, or `research-only`. Features and epics cannot waive OpenSpec.

Required changes use `ripdpi-deploy-change`: `proposal.md -> delta specs -> design.md -> tasks.md -> verification.md`. Verification records exact-SHA evidence for `local`, `remote_ci`, `dry_run`, `staging`, `live`, `client`, and `artifact`, each in `required`, `passed`, `not_applicable`, or `blocked` state.

## Lifecycle

```bash
./taskctl ready
./taskctl new --title "..." --kind bug --area ci --priority high --risk standard \
  --spec-mode not-required --spec-reason tooling-only
./taskctl start <TASK-ID> --owner "Role name"
./taskctl steps <TASK-ID> list
./taskctl transition <TASK-ID> review
./taskctl verify <TASK-ID>
./taskctl generate-board
./taskctl validate
```

Completing all execution checkboxes advances the portfolio task at most to `review`; it does not prove acceptance.

Archive a completed OpenSpec change only through `./taskctl openspec archive`. Then run `close prepare`, commit the terminal record, run `close purge`, and commit the deletion separately. CI rejects deletion without the preceding terminal-state commit. Direct upstream archive, `--no-validate`, manual task IDs, and mdtask archive/ID assignment are unsupported.

## Federation

Each repository is authoritative for its own tasks. `./taskctl export --json` emits the versioned local portfolio contract. Federation commands consume a peer checkout without copying peer state into this repository:

```bash
./taskctl federation list --peer-root ../RIPDPI
./taskctl federation ready --peer-root ../RIPDPI
./taskctl federation graph --peer-root ../RIPDPI
./taskctl federation validate --peer-root ../RIPDPI
```

Without a peer checkout an external blocker remains unresolved. Strict validation accepts an active peer record or a `done` terminal record found in peer Git history; a `dropped`, missing, incompatible, or unavailable peer is not a satisfied blocker. Cross-repository cycles are errors.

## Tool licenses

OpenSpec 1.8.0 is MIT-licensed. mdtask 0.1.17 uses PolyForm Shield 1.0.0 and is pinned solely as an internal development tool; its notice and merge-time legal gate are recorded in `tools/tasking/THIRD_PARTY_NOTICES.md`.
