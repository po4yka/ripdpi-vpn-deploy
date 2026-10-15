## Context

See `proposal.md` for motivation. Re-verification at `82b14824`:

- `ansible/roles/nginx-xhttp/files/nginx_transaction.py` `site_transaction` refuses `begin` (and check-mode admission) with `recovery-required` whenever `site.json` or `pending.json` exists under `/var/lib/vpn-nginx-publication/nginx.service`. `restore` already recovers an interrupted site completely (owner pending journal, witnesses, files, receipts, prior service state) but is reachable only through `ansible/playbooks/tasks/transport-ingress-restore.yml`, gated on `transport_site_transaction_active`, which `transport-ingress-begin.yml` sets only after a successful `begin` in the same run. The controller (`scripts/deploy-controller.py`) kills the Ansible process group on timeout or cancellation, so the rescue never runs on an interrupt. Egress next-run recovery exists (`transport-egress/tasks/runtime-prepare.yml`) but runs after ingress `begin`, which refuses first.
- The ordinary nginx publisher self-recovers its `pending.json` on next entry, but `cdn-front`, `subscription-host` and `probe-matrix-target` share the `nginx.service` state root and run after the protected block, so a pending-only journal left by them also blocks the next protected `begin`.
- `Makefile` `rotate-credentials`, `rollback-xray`, `rollback-config` have no prerequisites and no `--limit`; the plays are `hosts: vpn` with `forks = 5`. `ansible-config list` has no `ANSIBLE_LIMIT`. `scripts/render-inventory.sh` stamps every host with `env=` and `provider=`.
- `transport_runtime_rollback.py` (from `ab21b7fc`) resolves `<ver>-archive` / `<ver>-source-<commit>`, verifies the release receipt and digest, rewrites `XRAY_RUNTIME_BINARY` and `ExecStart` of `xray.service`, and the shared acceptance checks `/proc/<MainPID>/exe`. The private gateways also execute the pinned release but are owned by the egress transaction.

## Goals / Non-Goals

- Goal: the next deploy after an interrupted protected ingress transaction restores accepted authority through the existing compensation owner, and dry-run reports the condition without mutation.
- Goal: the three operator incident verbs cannot act on more than one named node or across environments.
- Goal: the runtime rollback branch is tested at its ownership boundary and documented truthfully.
- Non-goal: a new recovery verb, playbook, deploy-level lock, or second compensation sequence.
- Non-goal: rolling back private gateway units (separate task; needs a single-owner decision for gateway unit publication).
- Non-goal: closing the ingress-commit versus egress-finish window introduced by `ab21b7fc` (separate task).
- Non-goal: any provider, inventory, SSH or live action.

## Decisions

- Detect the interrupted site journal with a playbook-side `ansible.builtin.stat` (`follow: false`) of `/var/lib/vpn-nginx-publication/nginx.service/site.json` inside `transport-ingress-begin.yml`, after the desired request is declared and before capture. This mirrors the egress journal detection in `transport-egress-prepare.yml`, adds no helper CLI surface, and `--site restore` re-validates the journal and fails closed on a malformed one. Rejected: a new helper `status` action, which adds an argparse choice whose omission would fail every deploy and is caught only by Molecule.
- On an open site journal (non-check run): stat the egress outer helper, read its `status` when present, set `transport_site_transaction_active: true` and `_transport_egress_transaction_started` from the outer route's `open` flag (the same adoption `runtime-prepare.yml` performs for egress), then `ansible.builtin.fail` with a categorical message. The block's existing rescue performs quiesce, `--site restore` and egress rollback unchanged. Rejected: recover-and-continue in the same run, which would create a second recovery sequence and continue converging on a node whose accepted state has just been rewritten.
- In check mode the categorical fail fires without setting adoption facts; the rescue's terminal message must not claim compensation was attempted.
- Outer-route `status` failures are surfaced with the same categorical stderr extraction `transport-egress/tasks/rollback.yml` uses rather than a bare `no_log` failure.
- Pending-only journals are recovered by the helper: in `site_transaction`, before receipt pre-admission and only for non-check `begin` with no `site.json`, call the existing `recover(state / "pending.json", "nginx.service")` under `unit_lock`. The in-lock refusal keeps checking both journals: recovery and capture take the lock separately (receipt pre-admission sits between them), so a pending journal that appears in that gap still fails closed. Recovery precedes receipt admission because an interrupted publish can leave disk bytes that disagree with prior receipt witnesses. Site journals stay the playbook's job because they need egress ordering.
- Exact-node targeting reuses one shared pre-task file, `ansible/playbooks/tasks/exact-node.yml`, tagged `always`, asserting `ansible_play_hosts_all | length == 1`, `ansible_limit is defined`, a strict alias pattern, and `ansible_limit == inventory_hostname`. Each of the three plays imports it as its first `pre_tasks` entry and sets `serial: 1` and `any_errors_fatal: true`. Make adds `require-exact-node` (`$(strip $(ANSIBLE_LIMIT))` non-empty) and passes `--limit "$(ANSIBLE_LIMIT)"`. Rejected: routing the verbs through `scripts/deploy-controller.py`, which requires SSH contexts and promotion inputs these incident verbs do not have.
- `rotate-credentials` additionally depends on `require-clean-source require-inventory pre-deploy-check` and asserts `hostvars[inventory_hostname]['env'] == lookup('env', 'ENV')` after the shared guard; its audit note records `node=$(ANSIBLE_LIMIT)`. The rollback verbs get `require-inventory` only; they restore retained on-node authority and do not consume new secrets.
- Runtime rollback: extract the runtime branch of `transport_runtime_rollback.py` `main()` into `runtime_candidates(...)` without behaviour change so the candidate set is testable without root. No change to `transport_runtime_accept.py`, `release_versions` or gateway units.

## Contracts and ownership

- Ansible protected block (`ansible/playbooks/site.yml`): unchanged; `transport-ingress-begin.yml` gains detection and adoption pre-steps; the rescue remains the single compensation owner.
- nginx publication helper: `site_transaction` begin recovers pending-only journals; check mode, `restore`, `commit` and the site-journal refusal are unchanged.
- Make interface: three verbs gain required `ANSIBLE_LIMIT`; `rotate-credentials` gains clean-source, pre-check and environment binding. This is a deliberate breaking change with no compatibility path.
- Runtime publisher: operator runtime rollback candidate set contains only runtime-publisher-owned nodes; egress owns gateway units.
- Secrets: no schema change; `rotate-credentials` still reads `VPN_SECRETS_FILE` from `SECRETS_FILE`.

## Risks / Trade-offs

- Recovery requires a mutating `make deploy` after a refused dry-run, which runs the pre-block roles (baseline, firewall and others) before compensating. Mitigation: the runbook documents this as the single narrow exception, only when dry-run reports the interrupted-transaction category, and requires a full dry-run and deploy afterwards.
- Adoption assumes no other live deploy targets the node; the old refusal was the only guard and the repository has no deploy-level lock. Mitigation: state the precondition in the runbook; do not claim races are benign.
- Per-node rotation turns fleet revocation into N invocations, and a forgotten node keeps a revoked credential valid. Mitigation: runbook and `new-client.sh` state revocation is incomplete until every node is rotated and verified.
- Residual: the ingress-commit versus egress-finish window and gateway runtime rollback remain open and are tracked as separate tasks.

## Migration Plan

Forward: merge the source change; no node migration is required. Existing nodes without journals see only a read-only stat. A node already wedged by an old interruption is compensated by its next `make deploy`, after which the operator repeats dry-run and deploy. Operators update scripts that call the three verbs to pass `ANSIBLE_LIMIT=<alias>`.

Rollback: revert the commit; behaviour returns to fail-closed refusal on journals and unscoped verbs.

Gates: focused unit tests for the helper, the Ansible harness, the operator verb scope and the runtime rollback adapter; `ansible-lint` on changed playbooks; `make shellcheck`; `make check`; the native runtime lane in CI for the strengthened native assertions.
