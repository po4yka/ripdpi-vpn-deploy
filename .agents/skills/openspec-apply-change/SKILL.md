---
name: openspec-apply-change
description: Implement tasks from an OpenSpec change. Use when the user wants to start implementing, continue implementation, or work through tasks.
allowed-tools: Bash(./taskctl:*)
license: MIT
compatibility: Requires the repository-pinned ./taskctl wrapper.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.8.0"
---

RIPDPI VPN deployment policy: use only the local repository planning home. OpenSpec stores, global configuration changes, direct archive, and telemetry are out of scope; `./taskctl` enforces the pinned tool and disables telemetry.

Implement tasks from an OpenSpec change.

**Repository root:** Work only in the current RIPDPI VPN deployment checkout. Do not select or register OpenSpec stores. Run every CLI lookup through `./taskctl openspec cli` from the repository root.

**Input**: Optionally specify a change name (e.g., `$openspec-apply-change (Codex) or /openspec-apply-change (other agents) add-auth`). If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `./taskctl openspec cli list --json` to get available changes and ask the user to select one

   Always announce: "Using change: <name>" and how to override (e.g., `$openspec-apply-change (Codex) or /openspec-apply-change (other agents) <other>`).

2. **Check status to understand the schema**
   ```bash
   ./taskctl openspec cli status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - `planningHome`, `changeRoot`, and `actionContext`: planning scope and edit constraints
   - Which artifact contains the tasks (typically "tasks" for spec-driven, check status for others)

3. **Get apply instructions**

   ```bash
   ./taskctl openspec cli instructions apply --change "<name>" --json
   ```

   This returns:
   - `contextFiles`: artifact ID -> array of concrete file paths (varies by schema - could be proposal/specs/design/tasks or spec/tests/implementation/docs)
   - Progress (total, complete, remaining)
   - Task list with status
   - Dynamic instruction based on current state
   - Optional `context`: current required project instruction input from the selected root
   - Optional `operationGuidance`: current advisory guidance for apply

   **Handle states:**
   - If `state: "blocked"` (missing artifacts): implementation remains blocked. When implementation is already authorized, use `$openspec-propose` for this linked change to fill the missing artifacts according to its schema, then validate them with `./taskctl openspec cli validate "<name>" --strict --no-interactive`. Re-fetch status and apply instructions; resume only when the CLI no longer reports blocked. Do not send the user away to invoke proposal again. Ask only for materially missing scope or authority decisions. For a planning-only request, fill the requested planning artifacts and stop before implementation. This repository has no `openspec-continue-change` skill.
   - If `state: "all_done"`: all task checkboxes are complete. Verify the actual capability and required acceptance evidence; this state alone does not prove shipped behavior or authorize task closure or archival. Report gaps as incomplete work and use the taskctl lifecycle only when its acceptance conditions and existing authorization are satisfied.
   - Otherwise: proceed to implementation

   Treat `context` as a required prompt-level input. Read and consider it, and
   apply relevant project facts, conventions, and constraints while implementing.
   Treat `operationGuidance` as optional additive advice. Read and consider every
   entry, and follow entries that are applicable and compatible with the built-in
   workflow.

   Keep both fields separate from CLI-returned state, missing artifacts, tasks,
   progress, `contextFiles`, and the built-in `instruction`. They are not
   evidence of task completion, do not replace the built-in instruction, and do
   not permit bypassing a blocked state. If context conflicts with the built-in
   instruction, an explicit user choice, or a CLI-controlled value, report the
   conflict and preserve the controlling value. If guidance is inapplicable or
   conflicts with those controlling inputs, do not follow it and explain why.
   These are prompt-level behavior contracts, not enforceable checks.

4. **Read context files**

   Read every file path listed under `contextFiles` from the apply instructions output.
   The files depend on the schema being used:
   - **spec-driven**: proposal, specs, design, tasks
   - Other schemas: follow the contextFiles from CLI output

   Do not copy `context` or `operationGuidance` verbatim into implementation
   files or planning artifacts unless the user separately asks for that content.

5. **Show current progress**

   Display:
   - Schema being used
   - Progress: "N/M tasks complete"
   - Remaining tasks overview
   - Dynamic instruction from CLI

6. **Implement tasks (loop until done or blocked)**

   For each pending task:
   - Show which task is being worked on
   - Make the code changes required
   - Keep changes minimal and focused
   - Run the step's relevant verification and retain observed evidence before marking it complete.
   - Mark the step complete with `./taskctl steps <task-id> done <step-id>`. `done` TOGGLES the checkbox (`- [ ]` <-> `- [x]`) rather than setting it, so run `./taskctl steps <task-id> view <step-id>` first to confirm the step is still open, and never call `done` on the same step twice without re-checking its state in between. Never hand-edit the checkbox in the tasks file.
   - Continue to next task

   **Pause if:**
   - A materially missing scope or authority decision → ask one focused question
   - Implementation reveals a design issue → update coherent planning artifacts through `$openspec-update-change` within existing authorization, validate, then resume; ask if this changes the authorized bounds
   - An error or blocker remains after safe in-scope diagnosis and alternatives → report the blocker and concrete options
   - User interrupts

7. **On completion or pause, report status**

   Keep progress updates short. Report the change and schema, `N/M` steps complete, completed behavior and observed checks, and any required evidence still missing. Distinguish checkbox progress from source/CI, provider, host, protocol/client and human acceptance. Recommend `$openspec-archive-change` only after the capability is complete and reviewed; an authorized lifecycle handoff can continue without a new user turn. Otherwise report the next required check or the blocker with concrete options.

**Guardrails**
- Keep going through tasks until done or blocked
- Always read context files before starting (from the apply instructions output)
- Ask before implementing when ambiguity materially changes scope, authority or acceptance; resolve minor details within the approved scope
- If implementation reveals issues, keep planning coherent and validated before resuming dependent work
- Keep code changes minimal and scoped to each task
- Update the step's checkbox immediately after completing each task, via `./taskctl steps <task-id> done <step-id>` (view its state first; never hand-edit `- [ ]`/`- [x]`, and never call `done` twice in a row without re-checking)
- Exhaust safe in-scope diagnosis and alternatives before reporting a blocker; do not guess material requirements or bypass a failed gate
- Use contextFiles from CLI output, don't assume specific file names
- Do not use context or operation guidance as proof that a task is complete
- Apply relevant project context; report conflicts with controlling workflow inputs
- Consider every guidance entry; explain any inapplicable or conflicting advice
- Do not copy runtime context or operation guidance into implementation files or planning artifacts
- Preserve CLI-controlled blocked/ready/all-done behavior and completion criteria; artifact repair must clear blocked through revalidation, and all_done is checkbox progress rather than proof of shipped or closed capability

**Fluid Workflow Integration**

This skill supports the "actions on a change" model:

- **Can be invoked anytime**: Before all artifacts are done (if tasks exist), after partial implementation, interleaved with other actions
- **Allows artifact updates**: Keep artifacts coherent through validated updates within existing authorization; request a decision when those bounds change
