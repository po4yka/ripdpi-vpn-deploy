---
name: openspec-propose
description: Generate the full OpenSpec artifact set (proposal, specs, design, tasks) for a portfolio task's linked change. Use when the user wants a ready-for-implementation proposal; creates the portfolio task first if none exists.
allowed-tools: Bash(./taskctl:*)
license: MIT
compatibility: Requires the repository-pinned ./taskctl wrapper.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.8.0"
---

RIPDPI VPN deployment policy: use only the local repository planning home. OpenSpec stores, global configuration changes, direct archive, and telemetry are out of scope; `./taskctl` enforces the pinned tool and disables telemetry.

Propose a new change - create the change and generate all artifacts in one step.

**Planning boundary**: This workflow creates planning artifacts only. The user request that selected or triggered this workflow authorizes planning only, even if it asks to build or fix something. Do not edit project code. After the planning artifacts are complete, stop. Do not start implementation in the same response, even if the initial request asks for it. Wait for a new user request after the artifacts are presented; then start the apply workflow.

I'll create a change with the artifacts your schema defines. With the default spec-driven schema that is:
- proposal.md (what & why)
- `specs/<capability-path>/spec.md` (what the system must do - a delta, not the main spec)
- design.md (how)
- tasks.md (implementation steps)

`<capability-path>` is the spec directory relative to `specs/` (for example, `user-auth` or `identity/user-auth`). Preserve an existing capability's full path and follow the project's established organization for new capabilities.

When the user is ready to implement, they must start the apply workflow explicitly.

---

**Repository root:** Work only in the current RIPDPI VPN deployment checkout. Do not select or register OpenSpec stores. Run every CLI lookup through `./taskctl openspec cli` from the repository root.

**Input**: The user's request should include a change name (kebab-case) OR a description of what they want to build.

**Steps**

1. **Understand the request and clarify material ambiguity**

   If no clear input is provided, ask the user (open-ended, no preset options):
   > "What change do you want to work on? Describe what you want to build or fix."

   From their description, derive a kebab-case name (e.g., "add user authentication" → `add-user-auth`).

   Make sure you understand what the user wants to build before creating anything.

   If the request contains ambiguity that would materially affect scope, externally observable behavior, compatibility, or acceptance criteria, ask the user before creating the change. For minor details, make a reasonable assumption and record it in the planning artifacts.

2. **Confirm the workflow schema**

   Task-linked changes always use the project schema (`openspec_schema` in `tools/tasking/project.json`, currently `ripdpi-deploy-change`), which `./taskctl new` applies when it scaffolds the change; `taskctl` accepts no other schema. If the user explicitly asks for a different schema or workflow, explain that this task-backed flow supports only the project schema and stop before creating anything, rather than silently producing the default artifact graph. To show the available schemas, run `./taskctl openspec cli schemas --json`.

3. **Resolve the linked portfolio task**

   Every OpenSpec change here is linked to a portfolio task, and checkbox IDs in `tasks.md` are never hand-written - they come from that task's execution file. Before creating or reusing a change directory:
   - Search `./taskctl list --json` for a task with a non-null `openspec_change` (only `spec_mode: required` tasks have one) whose change name or title matches the user's description. A matching task without `openspec_change` is not a match: it waived OpenSpec and cannot be linked afterwards, so tell the user and continue as if no task exists.
   - If exactly one match is found, use that task's `openspec_change` value as `<name>` for the rest of this workflow; `./taskctl new --spec-mode required` already scaffolded it (see step 4).
   - If more than one plausible match is found, ask the user which task this proposal belongs to.
   - If no matching task exists, create it first with `$mdtask-create` (`./taskctl new --title "<title>" --kind <kind> --area <area> --priority <priority> --risk <risk> --spec-mode required`). Read the new task's `openspec_change` field back with `./taskctl show <task-id> --json` and use that value as `<name>`; the change directory is already scaffolded (see step 4).

4. **Do not create a separate change directory**

   Step 3 always ends with a change that `./taskctl new` scaffolded with the project schema. Never run `./taskctl openspec cli new change` in this flow: it would create a change that no portfolio task links to.

5. **Get the artifact build order**
   ```bash
   ./taskctl openspec cli status --change "<name>" --json
   ```
   Parse the JSON to get:
   - `applyRequires`: array of artifact IDs needed before implementation (e.g., `["tasks"]`)
   - `artifacts`: list of all artifacts, each with its `status` and its `requires` edges (the artifact IDs it directly depends on)
   - `planningHome`, `changeRoot`, `artifactPaths`, and `actionContext`: path and scope context. Use these instead of assuming repo-local paths.

6. **Create every artifact in the required set**

   Use a todo list to track progress through the artifacts.

   Loop through artifacts in dependency order (artifacts with no pending dependencies first):

   a. **For each artifact that is `ready` (dependencies satisfied)**:
      - Get instructions:
        ```bash
        ./taskctl openspec cli instructions <artifact-id> --change "<name>" --json
        ```
      - The instructions JSON includes:
        - `context`: Project background (constraints for you - do NOT include in output)
        - `rules`: Artifact-specific rules (constraints for you - do NOT include in output)
        - `template`: The structure to use for your output file
        - `instruction`: Schema-specific guidance for this artifact type
        - `skipped`/`warning`: present when the change declares skip_specs and this artifact must NOT be created - stop and pick another artifact
        - `resolvedOutputPath`: Resolved path or pattern to write the artifact
        - `dependencies`: Completed artifacts to read for context
      - Read any completed dependency files for context - always re-read them from disk, even if you saw them earlier in the conversation (the user may have edited them)
      - If the `instruction` field delegates creation to a specific skill or command, invoke it to produce the artifact instead of writing the file yourself, then verify the artifact file exists at `resolvedOutputPath`
      - **For the `tasks` artifact specifically**: this file's checkbox IDs are never hand-written. Use `template` and `instruction` to decide what implementation steps are needed, then allocate each one with `./taskctl steps <TASK-ID> add "<step title>"` (optionally `--kind <kind>` / `--priority <priority>`, defaulting to the portfolio task's own values). This appends a properly ID'd checkbox to the change's `tasks.md`, creating the file if it does not exist yet - do not write `- [ ] ...` lines or invent step IDs yourself.
      - Otherwise create the artifact file using `template` as the structure and write it to `resolvedOutputPath`. If `resolvedOutputPath` is a glob, follow `instruction` to choose the concrete file path
      - Apply `context` and `rules` as constraints - but do NOT copy them into the file
      - Show brief progress: "Created <artifact-id>"

   b. **Continue until every artifact in the required set exists (not just `apply.requires`)**
      - After creating each artifact, re-run `./taskctl openspec cli status --change "<name>" --json`
      - The required set is `applyRequires` plus every artifact reachable from those by following the `requires` edges in `status --json` - walk them transitively (spec-driven closes over proposal, specs, design, tasks). Leave artifacts outside that set alone
      - `status` is file-existence only, so an `applyRequires` artifact reading `done` does NOT mean its dependencies exist - writing `tasks.md` early marks `tasks` done while `specs` was never written. Use each artifact's `requires` edges, not its `status`, to build the required set: a `done` artifact still lists what it depends on
      - An artifact already reading `status: "skipped"` is satisfied: the change declares `skip_specs` in `.openspec.yaml`, so its files must NOT exist. Never try to create one
      - Create every artifact in the required set that is missing, then re-check - creating one can unblock others
      - Skip one only when `status` already reports it `skipped`, or when its own `instruction` says it is conditional: run `./taskctl openspec cli instructions <artifact-id> --change "<name>" --json` and skip only if its `instruction` field marks it optional (e.g. "create only if..."). Spec-driven's `design.md` qualifies; `specs` qualifies only via the `skipped` status above, never by your own judgment. Tell the user, and do not reconsider it
      - Dependencies are enablers, not gates: if a required artifact is still `blocked` only because you skipped a conditional dependency, write it anyway
      - Stop when every artifact in the required set is `done`, `skipped`, or was deliberately skipped

   c. **If an artifact requires user input** (unclear context):
      - Ask the user to clarify
      - Then continue with creation

7. **Show final status**
   ```bash
   ./taskctl openspec cli status --change "<name>"
   ```

**Output**

After completing all artifacts, summarize:
- Change name and location
- List of artifacts created with brief descriptions, plus any conditional artifact you skipped and why
- What's ready: "All artifacts needed for implementation are ready."
- Prompt: "The artifacts are ready for review. When you are ready, run `$openspec-apply-change (Codex) or /openspec-apply-change (other agents)` or ask me to apply this change."

**Artifact Creation Guidelines**

- Follow the `instruction` field from `./taskctl openspec cli instructions` for each artifact type - it is the authoritative guidance, even for familiar artifact names
- If the `instruction` field directs you to use a specific skill or command to create the artifact, invoke it instead of writing the artifact directly
- The schema defines what each artifact should contain - follow it
- Read dependency artifacts for context before creating new ones
- Use `template` as the structure for your output file - fill in its sections
- **IMPORTANT**: `context` and `rules` are constraints for YOU, not content for the file
  - Do NOT copy `<context>`, `<rules>`, `<project_context>` blocks into the artifact
  - These guide what you write, but should never appear in the output

**Guardrails**
- The request that invoked this workflow authorizes planning only. Any implementation or apply instruction in that request does not carry forward. Do NOT implement the change, start the apply workflow, or edit project code during this workflow. After presenting the artifacts, stop and wait for a new user request to start the apply workflow
- Create every artifact the apply phase transitively depends on, not just the ids listed in `apply.requires`
- Always read dependency artifacts before creating a new one - re-read from disk, not from conversation memory (files may have changed since you last saw them)
- Ask about ambiguities that would materially change scope, externally observable behavior, compatibility, or acceptance criteria; for minor details, make reasonable assumptions and record them
- If a change with that name already exists, ask if user wants to continue it or create a new one
- Verify each artifact file exists after writing before proceeding to next
