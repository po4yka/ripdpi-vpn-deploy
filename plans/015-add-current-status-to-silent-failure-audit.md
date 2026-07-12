# Plan 015: Add current status to the silent-failure audit

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, do not edit `plans/README.md`; the reviewer maintains the plan index in the advisory checkout.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- docs/AUDIT-SILENT-FAILURE.md docs/ROLE-TIERING.md tests/unit/test_governance_counts.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: docs
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`docs/AUDIT-SILENT-FAILURE.md` is valuable historical evidence, but its header and summary still present all eight June findings as currently broken even though six have since been resolved or deliberately superseded. One finding is only partially addressed by an explicit operator-owned alerting boundary, and one remains open. The linked role-tiering ADR repeats several obsolete remediation claims. Readers cannot reliably distinguish the dated audit verdict from current control status, so they may duplicate finished work, enable a still-incomplete signal, or assume the remaining burn-check gap was fixed. Preserve the original evidence while adding a compact, repository-backed current-status layer and a regression guard for future audits.

## Current state

- `docs/AUDIT-SILENT-FAILURE.md:3` says only `Status: complete — 2026-06-11`; it does not distinguish completion of the audit from remediation status.
- `docs/AUDIT-SILENT-FAILURE.md:12-25` presents all eight rows as `BROKEN` and says every control failed, without a current disposition column or reading rule.
- Only the combined watchdog section has a later `Resolution (2026-07-10)` note. The other detailed sections retain bare `Remediation` text that reads as outstanding even where the implementation and tests have landed.
- Finding 1 is resolved by scope correction and contract hardening: `ansible/roles/policy-ratelimit/templates/policy-ratelimit.py.j2` matches blackhole/VLESS rejection lines, explicitly disclaims REALITY probe defense, and emits `vpn_policy_ratelimit_dead_contract`; `tests/unit/test_policy_ratelimit.py` pins the behavior.
- Finding 2 is resolved/superseded: `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2` performs an authenticated REALITY round trip for node-local validation, while `docs/PROTOCOL-LIVENESS.md` defines the separate client-path, multi-vantage rotation authority. The existing audit resolution already states that local checks are non-authoritative for transit reachability.
- Finding 3 is resolved: the watchdog classifier now searches bracketed `block` or lowercase `rejected` events and calls the class `policy_reject_spike`, not `active_probing`; watchdog tests and snapshots cover the rendered script.
- Finding 4 is resolved: `scripts/check-singbox-killswitch.py` requires unified dual-stack TUN addresses, traverses outbound groups, and rejects direct/bypass `route.rules`; `tests/unit/test_check_killswitch.py` covers missing IPv6 and direct-rule cases.
- Finding 5 is partial, not fully resolved: `ansible/roles/monitoring/tasks/main.yml` enables the textfile collector and provisions shared writer access, but `ansible/roles/monitoring/CLAUDE.md` deliberately leaves alert routing to operator-side automation. `scripts/probing-summary-remote.py` still produces reports/metrics and returns success without an in-repo threshold pager. Do not label the end-to-end alert path resolved.
- Finding 6 is resolved: `ansible/roles/backup/templates/vpn-backup.sh.j2` runs `restic check`, validates snapshot recency, and uses `rclone check`; the default-enabled monthly isolated restore drill is rendered by the backup role and exercised by Molecule. `tests/unit/test_backup_integrity_contract.py` and `tests/unit/test_backup_restore_drill_contract.py` pin the contracts.
- Finding 7 is resolved: `scripts/check-certs.sh` compares certificate/private-key public-key DER digests for all supported key types; `tests/unit/test_check_certs_key_match.py` prevents regression to RSA modulus.
- Finding 8 remains open on `7bdba37`: `scripts/burn-check.sh` uses `set -e`, exits 2 when the request ID is missing, and writes `vpn_burn_last_run_unixtime` only near the end. It has no error trap or `vpn_burn_api_error` gauge, so the previous healthy textfile can still freeze on an API error. This plan documents that status; it does not implement the fix.
- `docs/ROLE-TIERING.md:85-90,119,176,199-205` repeats stale statements including missing backup integrity, all four honeypot links broken, eight currently broken controls, and policy-ratelimit remediation still required.
- `tests/unit/test_governance_counts.py` already owns repository documentation drift assertions. Extend its existing test function rather than creating a new test file or test function, keeping the documented unit-test collection count unchanged.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Focused governance test | `mise exec --no-deps -- python3 -m pytest tests/unit/test_governance_counts.py -q` | one test passes |
| Audit status structure | `python3 - <<'PY'` script from Step 3 | exactly eight numbered current-disposition rows; each has an allowed status; at least one PARTIAL and one OPEN |
| Stale linked claims | `rg -n '8 silently-broken controls|all four alert-chain links broken|Integrity check is missing|alert pipeline is broken|must have their AUDIT-SILENT-FAILURE remediations landed' docs/ROLE-TIERING.md` | no output |
| Focused control contracts | `mise exec --no-deps -- python3 -m pytest tests/unit/test_policy_ratelimit.py tests/unit/test_watchdog_protocol_probe.py tests/unit/test_check_killswitch.py tests/unit/test_backup_integrity_contract.py tests/unit/test_backup_restore_drill_contract.py tests/unit/test_check_certs_key_match.py -q` | all selected tests pass |
| Full unit regression | `mise exec --no-deps -- python3 -m pytest tests/unit/ -q` | all unit tests pass with unchanged collection count |
| Diff hygiene | `git diff --check --cached` | exit 0, no output |
| Commit-scoped secret scan | after commit, `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- `docs/AUDIT-SILENT-FAILURE.md`
- `docs/ROLE-TIERING.md`
- `tests/unit/test_governance_counts.py`

**Out of scope** (do not modify):

- Any script, Ansible role, template, defaults file, test fixture, snapshot, workflow, configuration, generated artifact, or runtime behavior.
- Implementing the remaining burn-check error metric/trap or adding in-repo honeypot paging, Prometheus rules, Alertmanager, notification credentials, or operator cron behavior.
- Reclassifying role tiers, changing enable defaults, renaming roles/controls, or revisiting the original audit methodology and evidence.
- Claiming live-node verification, production rollout, empirical alert delivery, or remediation not supported by current tracked code and tests.
- Deleting or rewriting the historical audit verdicts, evidence, failure modes, or recommendations. They remain a dated record; current status is layered above and beside them.
- Importing external citations, upstream excerpts, carrier/geography identifiers, new dependencies, or real operational values.
- Updating `CHANGELOG.md`, other audits, other docs, plans, or any fourth file.

## Git workflow

- Branch: `codex/advisor-015-current-silent-failure-status`.
- Create one focused Conventional Commit: `docs(audit): record current remediation status`.
- Do not push, merge, cherry-pick, or open a pull request.

## Steps

### Step 1: Add a current-disposition layer without erasing history

Update the opening of `docs/AUDIT-SILENT-FAILURE.md`:

1. Change the top status to say the audit was completed on 2026-06-11 and current dispositions were reviewed on 2026-07-11. Make clear that `BROKEN` in historical prose means the audit-date verdict, not necessarily current status.
2. Keep the original historical verdict summary intact, but retitle it explicitly as the audit-date summary.
3. Immediately after it, add `## Current disposition` with a short reading rule and exactly eight numbered Markdown table rows. Use only these current statuses: `RESOLVED`, `PARTIAL`, `OPEN`. Each row must name the current status, one concise repository-backed reason, and one or more checked-in evidence paths.
4. Classify the rows as follows:
   - 1 policy-ratelimit: **RESOLVED** — re-scoped to actual blackhole/VLESS-reject signals plus a dead-contract gauge.
   - 2 watchdog transport liveness: **RESOLVED** — local authenticated round trip is explicitly node-local; client-path authority is the separate `PROTOCOL-LIVENESS.md` quorum/OTP contract.
   - 3 watchdog log classifier: **RESOLVED** — real tokens and `policy_reject_spike` semantics replace the false active-probing claim.
   - 4 sing-box kill switch: **RESOLVED** — rule graph/direct routes and dual-stack TUN coverage fail closed.
   - 5 honeypot alert pipeline: **PARTIAL** — textfile collection/writer access fixed; report and metrics exist, but threshold paging/alert routing remains operator-owned and is not provided by this repo.
   - 6 backup integrity: **RESOLVED** — integrity, recency, remote comparison, and scheduled isolated restore drill exist.
   - 7 certificate key match: **RESOLVED** — key-type-independent public-key digest comparison exists.
   - 8 burn-check metric freshness: **OPEN** — early API failures can still precede the only metrics write; no explicit API-error gauge exists.

Do not use commit hashes as the only evidence: cite durable current file/test paths so the table remains navigable after rebases.

**Verify**: the status-structure script in Step 3 reports 8 rows, with six `RESOLVED`, one `PARTIAL`, and one `OPEN`.

### Step 2: Annotate every detailed finding and correct linked tiering claims

In each detailed finding section, add a short bold current-status paragraph immediately after the section's opening contract paragraph or before the historical remediation. The combined watchdog section must carry separate status statements for findings 2 and 3. Each annotation should point to the same current owner/test paths as the disposition table, state what changed, and preserve remaining limitations. Retitle each bare `Remediation.` label as `Historical remediation.` so it cannot be mistaken for the authoritative current backlog.

Keep the existing watchdog resolution note but reconcile it with the new status annotation; do not duplicate the full protocol-liveness explanation. For honeypot, explicitly say collection is repaired while alert delivery remains outside the repository and therefore partial. For burn-check, keep the remediation as still applicable and say the gap is open. At the start of `Generalization & systemic recommendations`, add one sentence explaining these are historical lessons that remain useful even when individual controls are resolved.

Update only the audit-linked stale claims in `docs/ROLE-TIERING.md`:

- Monitoring: collection is sound; alert routing is an explicit operator-owned boundary, not an unqualified broken pipeline.
- Backup: replace the missing-integrity statement with the current integrity/recency/restore-drill coverage while retaining why backup is CORE.
- Policy-ratelimit: say it is accurately scoped and contract-tested; remove the obsolete “enable after nftables-meter remediation” implication without changing its TACTICAL/default-off tier.
- Honeypot: say textfile collection is repaired but actionable threshold paging remains operator-owned/incomplete; retain TACTICAL/default-off.
- Audit doc classification: describe it as a historical eight-finding audit with a maintained current-disposition table, not “8 silently-broken controls.”
- Monitoring disagreement and ranked recommendations: distinguish historical findings from current open/partial work, name burn-check freshness as still open, and stop instructing readers to land already-completed policy/backup/certificate remediations.

Do not touch unrelated stale split-hop prose or other role-tier decisions; those belong to separate plans/commits.

**Verify**: stale linked-claims scan from the command table produces no output; review all remaining `AUDIT-SILENT-FAILURE` references in `docs/ROLE-TIERING.md` for current wording.

### Step 3: Extend the existing governance test with a structural audit contract

In `test_governance_counts_match_live_repository` in `tests/unit/test_governance_counts.py`, add a narrow parser for the text between `## Current disposition` and the next level-two heading:

```python
audit = (ROOT / "docs/AUDIT-SILENT-FAILURE.md").read_text()
current = audit.split("## Current disposition", 1)[1].split("\n## ", 1)[0]
rows = [line for line in current.splitlines() if re.match(r"\| [1-8] \|", line)]
```

Assert exactly eight rows; assert the first cell numbers are `1` through `8` in order; assert every row contains exactly one allowed bold status from `RESOLVED`, `PARTIAL`, `OPEN`; assert the status distribution is six resolved, one partial, one open. Also read `docs/ROLE-TIERING.md` and assert the five exact stale phrases from the command-table scan are absent. Do not assert whole explanatory paragraphs or line numbers, and do not add a new test function.

Run this equivalent one-off structure check before the focused test:

```bash
python3 - <<'PY'
import re
from pathlib import Path
audit = Path('docs/AUDIT-SILENT-FAILURE.md').read_text()
current = audit.split('## Current disposition', 1)[1].split('\n## ', 1)[0]
rows = [line for line in current.splitlines() if re.match(r'\| [1-8] \|', line)]
statuses = [next(status for status in ('RESOLVED', 'PARTIAL', 'OPEN') if f'**{status}**' in row) for row in rows]
assert len(rows) == 8, rows
assert [int(row.split('|')[1].strip()) for row in rows] == list(range(1, 9))
assert statuses.count('RESOLVED') == 6, statuses
assert statuses.count('PARTIAL') == 1, statuses
assert statuses.count('OPEN') == 1, statuses
print('8 current dispositions: 6 RESOLVED, 1 PARTIAL, 1 OPEN')
PY
```

**Verify**: script prints the exact expected summary; focused governance test passes as one test.

### Step 4: Run focused contracts, full regression, and commit normally

Run the focused control-contract tests from the command table. These do not prove production remediation, but they verify that every `RESOLVED` status is backed by the current repository contracts named in the audit. Run the full unit suite to catch documentation-count and governance drift.

Inspect the complete diff. Confirm the historical evidence is preserved, current status is not overstated, only the three in-scope files changed, and the test structurally protects the status layer without pinning prose. Stage exactly those paths and run `git diff --check --cached`.

Commit normally with hooks enabled using `docs(audit): record current remediation status`; never skip hooks. After commit, run the commit-scoped gitleaks scan and confirm the isolated worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the three in-scope paths; scoped gitleaks exits 0; `git status --short` is empty.

## Test plan

- The governance test enforces one numbered current disposition per historical finding and a reviewed status distribution, preventing the audit from silently reverting to all-currently-broken framing.
- Exact stale-phrase guards protect the linked role-tiering ADR while allowing explanatory prose to evolve.
- Focused tests validate the current code contracts cited for the six resolved findings; the partial/open rows are intentionally supported by direct source inspection rather than false positive tests.
- Full unit regression preserves the existing collection count because the governance contract extends an existing test function.
- Human review confirms that historical verdicts and lessons remain intact and that no runtime implementation is smuggled into this documentation-only slice.

## Done criteria

- [ ] The audit header clearly separates audit completion from current remediation review.
- [ ] The historical all-BROKEN summary is explicitly dated and preserved as history.
- [ ] A current-disposition table contains exactly eight ordered rows: six RESOLVED, one PARTIAL, one OPEN, each backed by checked-in paths.
- [ ] Every detailed finding has a current-status annotation; historical remediation labels cannot be mistaken for the current backlog.
- [ ] Honeypot alert delivery is not overstated, and burn-check freshness remains explicitly open.
- [ ] `docs/ROLE-TIERING.md` no longer repeats the five obsolete audit/remediation claims and does not change any tier.
- [ ] The existing governance test structurally protects the disposition table and stale linked phrases without adding a test function.
- [ ] Focused governance/control tests, full unit tests, diff hygiene, hooks, and scoped gitleaks pass.
- [ ] Exactly three in-scope paths are committed; the executor reports the commit SHA; the isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any in-scope file drifted from `7bdba37` or no longer matches the current-state excerpts.
- A claimed RESOLVED control lacks the cited live implementation or focused regression test on the audited base.
- Burn-check already has an error-path metrics write/API-error gauge, or honeypot now has an in-repo threshold paging route, making the required distribution inaccurate.
- Correcting current status requires changing a role tier, runtime control, script, template, snapshot, configuration, workflow, or file outside the three-file scope.
- Preserving the original audit requires restoring external citations or importing unavailable upstream evidence.
- Focused/full tests, hooks, status parser, or stale-claim scan fail twice after one reasonable in-scope correction.
- Any fourth file, generated artifact, dependency change, secret, real operational value, network lookup, or runtime behavior change is required.

## Maintenance notes

The audit-date verdicts are immutable evidence; the current-disposition table is the maintained layer. Future remediation changes should update the relevant row and annotation in the same commit as the owning control where practical, while structural tests guard row completeness and role-tiering references against drift.
