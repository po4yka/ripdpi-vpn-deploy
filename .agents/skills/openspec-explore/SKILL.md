---
name: openspec-explore
description: Enter explore mode - a thinking partner for exploring ideas, investigating problems, and clarifying requirements. Use when the user wants to think through something before or during a change; hand off to `$sdd` or `$mdtask-create` when it is time to formalize.
allowed-tools: Bash(./taskctl:*)
license: MIT
compatibility: Requires the repository-pinned ./taskctl wrapper.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.8.0"
---

Explore ideas, investigate the codebase and clarify requirements without implementing.
There is no required artifact or fixed sequence; ground the discussion in current
code, constraints and unresolved risks. Use diagrams or comparisons when useful.
For entry-point examples, read [references/exploration-examples.md](references/exploration-examples.md)
when the user brings a vague idea, a concrete failure, an implementation obstacle
or a choice between approaches.

## Planning and implementation boundary

A planning-only request permits inspection and discussion, not code changes.
Capture planning artifacts only when requested; otherwise offer to record decisions.
A later explicit build or fix request authorizes the implementation handoff within
its existing bounds: complete the linked proposal, validate it with
`./taskctl openspec cli validate "<name>" --strict --no-interactive`, then use
`$openspec-apply-change`. Do not require a ceremonial exit from exploration or a
separate user invocation. Ask only when a missing decision materially changes
scope, authority, cost or external impact. Planning does not grant infrastructure
or credential authority.

## Repository context

Work in the current RIPDPI VPN deployment checkout. Run every OpenSpec CLI lookup
from its root through `./taskctl openspec cli`; the wrapper pins the tool and
turns telemetry off. Use the local planning home only. OpenSpec stores, global
configuration changes and direct upstream archival are outside this workflow.

Start with:

```bash
./taskctl openspec cli list --json
```

Read project context from `<root.path>/openspec/config.yaml` or `config.yml`, using
`root.path` from that JSON; skip it if neither file exists. `context` supplies
project constraints. Artifact-keyed `rules` apply only when writing that artifact.
Use them as constraints without copying them into conversation or artifacts.

For a relevant existing change, resolve its current files:

```bash
./taskctl openspec cli status --change "<name>" --json
```

Use `changeRoot`, `artifactPaths` and `actionContext` from the response. Read
existing files from `artifactPaths.<artifact>.existingOutputPaths`, rather than
assuming artifact names or locations. Clarify a materially ambiguous change
selection before writing.

## Capture or hand off

For a requested new change, use `$sdd` for the repository's specification policy
and `$mdtask-create` to create the linked portfolio task and scaffold together:

```bash
./taskctl new --title "<title>" --kind <kind> --area <area> --priority <priority> --risk <risk> --spec-mode required
./taskctl show <task-id> --json
```

Use the returned `openspec_change` with `$openspec-propose`. Never manually create
a change directory under `openspec/changes/` or create an unlinked upstream change.
Drive the requested handoff yourself; if only scaffolding was requested, stop
there and report its status.

For requested updates to an existing change, use `$openspec-update-change` to keep
its artifacts coherent. Preserve each capability's full path relative to `specs/`,
including nested paths such as `identity/user-auth`, and follow the existing
organization for new capabilities:

| Decision | Artifact |
|---|---|
| Requirement or scenario | `specs/<capability-path>/spec.md` |
| Design choice | `design.md` |
| Scope | `proposal.md` |
| Work identified | `tasks.md` through `./taskctl steps` |
| Invalidated assumption | Affected artifacts |

End when the user's question or requested capture is handled. Report material
unknowns and the next action if useful. Continue to validated proposal/apply only
when implementation is explicitly authorized.
