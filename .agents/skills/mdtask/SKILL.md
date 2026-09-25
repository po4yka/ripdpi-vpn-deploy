---
name: mdtask
description: Inspect and update RIPDPI VPN deployment execution steps through the repository-pinned mdtask wrapper. Use when checking or correcting execution steps of an existing task outside an implementation run; while implementing an OpenSpec change, openspec-apply-change checks off its steps.
---

# RIPDPI VPN deployment mdtask workflow

Portfolio state lives in `docs/tasks/issues/`; mdtask owns only execution checkboxes in `docs/tasks/work/` and active OpenSpec `tasks.md` files.

- Discover portfolio work with `./taskctl list`, `./taskctl ready`, `./taskctl show <task-id>`, and `./taskctl graph`.
- Inspect or update execution steps with `./taskctl steps <task-id> list|view|done|set|validate ...`.
- Never run `mdtask archive`, `move`, `ids`, or `install-skills`; taskctl owns IDs, paths, archive policy, and generated skills.
- `done` toggles a step's checkbox (`[ ]` <-> `[x]`), it does not set it. Run `./taskctl steps <task-id> view` first to confirm the current state, and never call `done` on the same step twice without re-checking it in between.
- Mark a step complete only after the behavior and named check were observed. Completed steps advance portfolio work at most to `review`.
- Run `./taskctl validate` before handoff.
