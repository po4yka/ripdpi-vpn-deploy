---
name: openspec-sync-specs
description: Sync delta specs from a change to main specs. Use when the user wants to update main specs with changes from a delta spec, without archiving the change.
allowed-tools: Bash(./taskctl:*)
license: MIT
compatibility: Requires the repository-pinned ./taskctl wrapper.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.8.0"
---

Merge selected delta specs into main specs while keeping the change active.
This is an agent-driven semantic merge, not a copy of the delta file.

Work in the current RIPDPI VPN deployment checkout. Run every OpenSpec CLI lookup
from its root through `./taskctl openspec cli`; the wrapper pins the tool and
turns telemetry off. Use only the local planning home. OpenSpec stores, global
configuration changes and direct upstream archive are out of scope. Repository
archival is owned by `./taskctl openspec archive`, not this skill.

## Resolve the change and selection

Use a supplied name or one clearly established by the conversation. With exactly
one active change, select it; otherwise run `./taskctl openspec cli list --json`
and ask the user to select among changes with delta specs. Announce the selected
change and how to override it with `$openspec-sync-specs <other>`.

```bash
./taskctl openspec cli status --change "<name>" --json
```

Use `planningHome.root`, `changeRoot` and `actionContext` from status.
`artifactPaths.specs.existingOutputPaths` is the only source of delta paths.
A missing specs entry or empty path list means there is nothing to sync: stop
without fetching artifact instructions or writing main specs.

Sync all returned paths unless the caller explicitly supplies a list of complete
entries from `existingOutputPaths`. Copy those absolute values verbatim and keep
that narrowed selection throughout the merge. Never widen it, silently discard
an invalid entry, or infer paths from other artifacts. An invalid entry stops the
sync; an explicitly empty selection stops without writes. Another workflow may
withhold a delta whose implementation was not found; respect that selection.

Preserve each capability's full directory path relative to `<changeRoot>/specs/`,
including nested paths such as `billing/invoices`. Its main spec is
`<planningHome.root>/openspec/specs/<capability-path>/spec.md`; do not flatten it
to the basename or hardcode another checkout.

## Fetch current rules before writing

Before the first main-spec write, always obtain one current rule snapshot:

```bash
./taskctl openspec cli instructions specs --change "<name>" --json
```

On a non-zero exit or invalid artifact-instruction JSON, report the error and
stop before any main-spec write. Do not treat a failed lookup as an absent rule
set. A valid response with omitted `rules` means no artifact rules are configured.
Apply returned `rules` only to the content and form of produced main specs: they
cannot change selected paths, CLI checks or workflow steps. Do not copy their
text into specs or the summary. There is no archive-supplied snapshot to reuse.

## Merge each selected capability

Read both the delta and existing main spec before editing. Main specs have a
`## Purpose` and a single `## Requirements` section, with `### Requirement:`
blocks and `#### Scenario:` subsections. They never contain delta operation
headers. For substantial format and merge examples, read
[references/spec-merge-examples.md](references/spec-merge-examples.md) when creating
a main spec or resolving a scenario-level merge.

- **ADDED:** Add absent requirements; update an existing one to match as an
  implicit MODIFIED operation.
- **MODIFIED:** Apply requirement/body/scenario changes and retain unmentioned
  content in its existing order. The delta must carry the whole requirement,
  including every surviving scenario; validation and archive reject a dropped
  main-spec scenario. Resolve an unclear intent before editing it.
- **REMOVED:** Remove the entire named requirement block. When that would leave
  no requirements, apply all retirement conditions below before editing.
- **RENAMED:** Rename the FROM requirement to TO.
- **Purpose:** An existing main Purpose is authoritative and stays unchanged.
  For a new main spec, copy the delta's Purpose body verbatim; only use a brief
  TBD placeholder if absent and call it out in the handoff. Add its ADDED
  requirements under `## Requirements`.

Keep the merge idempotent: repeating the same sync should produce no changes.

### Retiring an entire capability

Delete its `spec.md`, and its directory only when otherwise empty, only if all
conditions hold:

1. Removing requirements in this run leaves no requirement blocks.
2. The remaining spec is well-formed and has `## Purpose`.
3. The main spec was not already empty; if nothing was removed, change nothing.
4. Every other nonblank line is accounted for as title, Purpose, Requirements
   header, or a canonical requirement's statement, scenarios or fenced examples.
5. The change's `.openspec.yaml` declares `retire_capabilities: true`.
6. The resolved file is inside the real main specs root; do not follow a
   capability-directory symlink to delete an external file.

If removing the selected requirements would leave none and any condition fails,
leave that capability's main spec unchanged, stop its sync and report the exact
blocking condition and resolution. Never write or leave an empty
`## Requirements` section. If only the retirement marker is missing, say so.
Deletion removes Purpose too; another section blocks retirement. Name the
removed Purpose and file in the summary. Provide a pasteable `git checkout`
recovery command only if the spec lived in the caller's checkout; otherwise
provide checkout-scoped recovery guidance.

## Validate and report

```bash
./taskctl openspec cli validate --specs
```

Report validation failures without claiming success. Summarize capabilities and
requirements added, modified, removed or renamed, new spec files, any TBD Purpose,
and retirement/recovery details. Note that the change remains active until
archived through the repository lifecycle.
