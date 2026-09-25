---
name: mdtask-create
description: Create a RIPDPI VPN deployment portfolio task and its mdtask or OpenSpec execution scaffold. Use when the user asks to file, create, or track new work.
---

# Create tracked work

1. Search with `./taskctl list --json` to avoid duplicates.
2. Classify risk explicitly as `standard` or `high`. High-risk work always uses `spec_mode: required`; see `$sdd` for the full criteria on which other work also requires OpenSpec.
3. Use `./taskctl new` with title, kind, area, priority, risk, owner, and explicit spec mode/reason. For `spec_mode: required` this also scaffolds the linked OpenSpec change; its name is recorded in the new task's `openspec_change` field.
4. For a required change, complete proposal, delta specs, design, mdtask `tasks.md`, and verification through `$openspec-propose` before committing.
5. Regenerate the board with `./taskctl generate-board` and run `./taskctl validate`.

Do not invent IDs, create execution files outside the canonical directories, or use upstream mdtask ID assignment.
