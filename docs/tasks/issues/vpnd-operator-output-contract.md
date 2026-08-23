---
id: VPD-1787497426503364
title: "Align vpnd operator output contract: man page, json flag, clip flag, doctor resilience"
kind: bug
status: backlog
area: vpnd
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: vpd-1787497426503364-vpnd-operator-output-contract
created: 2026-08-23
updated: 2026-08-23
related_tasks: []
---

## Goal

vpnd's documented surface equals its actual surface: man page generated from the real CLI, no dead global flags, explicit flag dependencies, and doctor diagnostics that survive partial failure with stderr captured.

## Audit evidence

| Finding | Evidence |
|---|---|
| Man page from hand-built replica drifts | build.rs:61 default 1h vs cli.rs:172-173 default 4h; build.rs:47-51 share missing --token-stdin/--token-file; build.rs omits env bindings cli.rs:16-45 |
| Global --json accepted, never read | cli.rs:39-41; stored config.rs:77; zero readers in src/ |
| --clip without --ai silently ignored | help "(requires --ai)" cli.rs:143-145 but no clap requires; consulted only inside ai branch doctor.rs:43-56 |
| Doctor aborts on first failing step | capture `?` in loop doctor.rs:20-31 discards report/bundle/prompt |
| stderr lost from report and bundle | capture pipes stdout only process.rs:132-133; report embeds out.stdout only doctor.rs:22-26 |

## Acceptance criteria

- Parity gate fails when a flag is added to cli.rs without reaching the man page.
- --json either emits JSON for host list/show and probe-matrix path or is removed; tests pin the decision.
- `doctor --clip` without `--ai` errors at parse time.
- Injected mid-run failure keeps all completed outputs plus the failed step's stderr in the report, marks it failed, exits nonzero.
