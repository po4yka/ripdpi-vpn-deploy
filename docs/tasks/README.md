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

## Find active work or terminal history

Start with the current portfolio and resolve the exact stable ID:

```bash
./taskctl list --json
./taskctl show --json '<TASK-ID>'
```

`show` reads the current portfolio. A missing or ambiguous query does not prove
that the task never existed: its terminal record may have been purged after a
separate committed closure. Continue the Git history lookup independently of
that failed command. This does not transition task state; the validation
preparation below creates a temporary local checkout and installs dependencies.

Pin the known local integrated history first. Stop if
`origin/main` is missing, is not an ancestor of this checkout, or the repository
is shallow. Do not search unrelated local branches or dirty archive files:

```bash
history_ref=$(git rev-parse --verify 'origin/main^{commit}') || exit 1
git merge-base --is-ancestor "$history_ref" HEAD || exit 1
[ "$(git rev-parse --is-shallow-repository)" = false ] || exit 1
task_id='MON-1788008977760206' # Replace with the exact ID being investigated.
git log "$history_ref" --format='%H %s' --name-status \
  -G "^id: ${task_id}$" -- docs/tasks/issues/
git grep -l -F -e "$task_id" "$history_ref" -- openspec/changes/archive
```

These are **candidate** paths and revisions, not accepted terminal outcomes.
The Git search identifies additions/removals of that ID; the archive search
reads only tracked files at the same pinned revision. For a candidate purge,
verify its ancestry and inspect its first parent using the exact SHA and path:

```bash
purge_revision='reviewed-purge-commit-sha'
portfolio_path='docs/tasks/issues/task-slug.md'
git merge-base --is-ancestor "$purge_revision" "$history_ref" || exit 1
git show "${purge_revision}^1:${portfolio_path}"
git log "$history_ref" --format='%H %s' -- "$portfolio_path"
```

Read `status`, `closed_reason`, `evidence_summary`, execution, and the matching
close/drop/archive receipts and verification. Find the first committed
transition into `done` or `dropped`; its parent must show the prior nonterminal
state. Validate from **before that transition**, not merely the purge parent,
which may already contain a terminal state trusted as the validation base:

```bash
terminal_revision='reviewed-first-terminal-transition-sha'
git merge-base --is-ancestor "$terminal_revision" "$history_ref" || exit 1
git merge-base --is-ancestor "$terminal_revision" "${purge_revision}^1" || exit 1
history_base=$(git rev-parse --verify "${terminal_revision}^1") || exit 1
```

Validate the fixed endpoint using that revision's own code, records and pinned
tools. Running `validate` in the caller's feature checkout instead would inspect
its `HEAD`, which may contain unrelated or unmerged changes. Start with Git,
Make and mise available. The following installs only local dependencies: Python
from the checkout's `mise.toml`, its hash-pinned `requirements.txt` into a private
venv, and its lock-pinned task tools with CI's Node selector. It does not install
Git hooks or modify shared Python packages. Review the pinned source first.

```bash
history_parent=$(mktemp -d "${TMPDIR:-/tmp}/task-history.XXXXXXXX") || exit 1
history_checkout="$history_parent/checkout"
git worktree add --detach "$history_checkout" "$history_ref" || exit 1
history_validation_status=0
bash -s -- "$history_checkout" "$history_ref" "$history_base" <<'BASH' || history_validation_status=$?
set -euo pipefail
cd "$1"
[ "$(git rev-parse HEAD)" = "$2" ]
history_worktree_status=$(git status --porcelain)
[ -z "$history_worktree_status" ]
mise trust
mise install python
history_python_root=$(mise where python)
"$history_python_root/bin/python3" -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: --require-hashes --no-deps -r requirements.txt
history_node=$(.venv/bin/python - <<'PY'
from pathlib import Path
import yaml
jobs = yaml.safe_load(Path('.github/workflows/ci.yml').read_text())['jobs']
print(next(step['with']['node-version'] for job in jobs.values()
           for step in job.get('steps', [])
           if 'node-version' in step.get('with', {})))
PY
)
mise install "node@$history_node"
history_node_root=$(mise where "node@$history_node")
export PATH="$PWD/.venv/bin:$history_node_root/bin:$PATH"
make task-tools
./taskctl validate --base "$3" --json
[ "$(git rev-parse HEAD)" = "$2" ]
history_worktree_status=$(git status --porcelain)
[ -z "$history_worktree_status" ]
BASH
```

Keep the exit status; accept nothing unless it is zero. Remove only this newly
created checkout and its private ignored dependencies, even after a failed
validation. Do not use `--force`: if removal refuses because the checkout was
modified, stop and inspect rather than discard that work.
If a required wheel is unavailable, bootstrap fails and the lookup remains
unresolved; do not silently compile a dependency outside the build gate.

```bash
git worktree remove "$history_checkout" || exit 1
rmdir "$history_parent" || exit 1
[ "$history_validation_status" -eq 0 ] || exit 1
```

The public validator checks the pinned endpoint and deleted history in
`base..history_ref`, including integrated merge lanes. Its implementation is in
[`scripts/tasks/taskctl.py`](../../scripts/tasks/taskctl.py):
`validate_deleted_history` checks transitions and terminal receipts;
`TerminalHistoryResolver` / `resolve_terminal_task` resolve historical references
through the integrated first-parent history and merged lanes, rejecting invalid
or ambiguous candidates. `show` has no standalone historical-ID query. A plain
current-state validation, or one based at today's `origin/main`, does not certify
an older candidate outside that checked history range.

Accept a terminal outcome only after successful validation that covers this
candidate's transition and purge, with matching exact-ID receipts. An absent
record, ambiguous history, missing archive, failed validation or uncovered
transition leaves the lookup unresolved; report the limitation. Never recreate
a task or bypass validation to make a lookup pass.

Simple execution and close receipts remain in Git history under
`docs/tasks/work/`; OpenSpec work retains them in its archive. `done` and
`dropped` remain distinct: cancelled acceptance is not passed acceptance.
Evidence applies only to its recorded source, requirements and environment;
it does not accept a replacement contract. Follow an explicitly linked
successor only after resolving its current record through `./taskctl show`.
All lifecycle transitions still go through `taskctl`.

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

## Portfolio objective and proportional evidence

The portfolio optimizes for a working, protected `main` and the shortest safe
path to an operator-usable result. Evidence is required at the layer changed by
the task, not repeated in every source task that contributes to a shared
deployment:

- Source-only bug fixes and refactors close on focused local coverage plus
  successful exact-SHA protected-main checks. They do not require a redundant
  live run when a linked operational acceptance task owns that behavior.
- Disabled-by-default features close when their source contract, refusal paths,
  rendering and protected-main checks pass. Enabling or promoting the feature
  remains a separate operator decision and is never implied by source closure.
- Dry-run is required only when the task changes the deploy controller or
  rendered deployment input and a dry-run exercises that change without a
  provider mutation.
- Staging or live evidence remains required when the task's positive capability
  is inherently external: provider mutation, real SSH migration, remote
  restore, alert delivery or production rollout.
- Authenticated client traffic requires `client: passed` in addition to every
  applicable staging or live category. Host-side staging or live evidence does
  not substitute for client evidence.
- One exact-SHA operational observation may satisfy multiple linked tasks when
  each mapped requirement and acceptance command is named in the owning
  verification records. The task graph must retain the corresponding links.
  An active operational owner may retain a `related_tasks` edge to a locally
  purged `done` source task; `taskctl` resolves that edge only through validated
  terminal Git history. Missing, dropped or malformed history fails closed.
  Existing `required` or `blocked` evidence cannot become `not_applicable`
  merely because another task exists. Duplicate fleet runs, duplicate vantages
  and duplicate provider rehearsals are not required without a distinct risk.
- An unavailable account, credential, client, host or provider blocks only the
  task that owns the corresponding operational requirement. A source task that
  still owns such a requirement remains open until the evidence passes or an
  OpenSpec update moves and maps that requirement before closure.

This policy is owned by `CIC-1788708456909496` and its linked OpenSpec change.
The repository project contract activates transition auditing with
`evidence_transfer_policy: 1`; an omitted or zero value exists only so history
before activation remains valid, and the activation transition is checked.
The companion `committed_review_policy: 1` field activates the committed
`review` prerequisite for `done` transitions. Activation is monotonic along a
terminal revision's first-parent config ancestry. A legacy `doing -> done`
transition is accepted only when its terminal commit is an ancestor of the
first version-1 activation already present in the trusted validation base; a
stale merged lane or a later activation in the change being validated cannot
manufacture legacy eligibility. Base-aware validation uses its `--base` ref;
purging a legitimate pre-policy terminal record requires an explicit
`close purge --trusted-base <protected-ref>` anchor. With no trust anchor,
including federation exports, unversioned history remains fail-closed. Other
pre-policy source states stay invalid, and removing or lowering the field after
version 1 is rejected rather than disabling the rule, even when the downgrade
range contains no terminal task candidate.
It does not relax authentication, authorization,
secret-handling, rollback, destructive-action confirmation, fail-closed input
validation or the distinction between local, remote CI, dry-run, staging, live,
client and artifact evidence.

## Lifecycle

```bash
./taskctl ready
./taskctl new --title "..." --kind bug --area ci --priority high --risk standard \
  --spec-mode not-required --spec-reason tooling-only
./taskctl start <TASK-ID> --owner "Role name"
./taskctl steps <TASK-ID> list
./taskctl steps <TASK-ID> add "Implement the guard"
./taskctl steps <TASK-ID> add "Verify rejection paths" --kind bug --priority high
./taskctl transition <TASK-ID> review
./taskctl verify <TASK-ID>
./taskctl generate-board
./taskctl validate
```

Completing all execution checkboxes advances the portfolio task at most to `review`; it does not prove acceptance.

`steps ... add` allocates the ID through the shared Git allocator and adds the
owning `@item` backlink; kind and priority default to the portfolio task. Titles
must be plain single-line text, without manual IDs or mdtask metadata. Existing
content is preserved. For the selected active OpenSpec task only, validated
proposal/specs/design can bootstrap `tasks.md` before verification mappings are
complete; subsequent adds remain available during authoring. Missing or
incomplete verification still blocks ordinary validation, start and closure.
Unrelated invalid records are never ignored. `add`, `done` and `set` share a
write lock; coordinate lifecycle transitions and external editors separately.
After editing steps and completing verification mappings, run `generate-board`
before `validate`; `add` does not rewrite the generated board.

Commit the completed task, execution, verification, and regenerated board in `review` before archival. Archive a completed OpenSpec change only through `./taskctl openspec archive`. Then run `close prepare`, commit the terminal record, run `close purge`, and commit the deletion separately. CI rejects deletion without the preceding terminal-state commit. Direct upstream archive, `--no-validate`, manual task IDs, and mdtask archive/ID assignment are unsupported.

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
