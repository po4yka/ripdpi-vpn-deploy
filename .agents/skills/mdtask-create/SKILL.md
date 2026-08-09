---
name: mdtask-create
description: Create a RIPDPI VPN deployment portfolio task and its mdtask or OpenSpec execution scaffold.
---

# Create tracked work

1. Search with `./taskctl list --json` to avoid duplicates.
2. Classify risk explicitly as `standard` or `high`. High-risk work always uses `spec_mode: required`; features, behavioral epics, operator-visible behavior, schemas, contracts, security, network, deployment lifecycle, and cross-repository work also require OpenSpec.
3. Use `./taskctl new` with title, kind, area, priority, risk, owner, and explicit spec mode/reason.
4. For a required change, complete proposal, delta specs, design, mdtask `tasks.md`, and verification through `$openspec-propose` before committing.
5. Regenerate the board with `./taskctl generate-board` and run `./taskctl validate`.

Do not invent IDs, create execution files outside the canonical directories, or use upstream mdtask ID assignment.
