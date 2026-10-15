---
id: SCR-1792057680449496
title: Route operator-supplied Make variables through literal environment capture
kind: bug
status: backlog
area: scripts
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-15
updated: 2026-10-15
spec_reason: tooling-only
related_tasks: []
---

## Goal

The exact-node verbs (`rotate-credentials`, `rollback-xray`, `rollback-config`) now capture `ANSIBLE_LIMIT` as literal data and hand it to their recipes through the environment, but the other operator-supplied Make variables these verbs interpolate into recipe shell text are still expanded as Make and shell syntax: `ROLLBACK_XRAY_VERSION`, `ENV`, `PROVIDER`, `SECRETS_FILE`, `SKIP_PRECHECK` and `ANSIBLE_DIR` in the verb recipes and the prerequisites and audit-log line they run, and `ANSIBLE_LIMIT` itself in `require-inventory` and in the `verify` and `os-maintenance` recipes when those run outside the exact-node verbs. A hostile spelling such as `$(shell ...)`, a command substitution, a quote or a backtick in any of them executes on the operator machine or rewrites the command line. Each must be captured as literal data before recipes expand, validated against its grammar where it has one, and reach recipe shell code only as a quoted environment reference.

## Acceptance criteria

- For every variable named in the Goal, a hostile spelling (`$(shell touch MARKER)`, `$$(touch MARKER)`, an embedded quote followed by `; touch MARKER`, a backtick substitution) never creates the marker and never appears in the printed recipe (`make -n`) for the affected targets, in the style of `tests/unit/test_operator_verb_scope.py`.
- Values with a grammar (`ENV`, `PROVIDER`, `ROLLBACK_XRAY_VERSION`, `SKIP_PRECHECK`) are refused with a named message when they do not match it, and where a consuming script or play already enforces a grammar, Make uses the same one, with a test that compares the two.
- Valid spellings, including `SECRETS_FILE` and `ANSIBLE_DIR` paths that contain spaces, still reach the real recipes unchanged: a run against recording stand-ins for `ansible-playbook`, `ansible-inventory` and `audit-log.sh` receives the exact values.
- `mise exec -- python3 -m pytest tests/unit/test_operator_verb_scope.py -q`, `make shellcheck` and `make task-check` pass.
