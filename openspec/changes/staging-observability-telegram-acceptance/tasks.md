# MON-1790650904289505: Deploy and accept staging observability and Telegram alerting

## Objective

Implement the missing exact-host bootstrap and bounded staging acceptance
surfaces, deploy centralized observability to a disposable cross-provider
topology, and produce live evidence for fresh canary telemetry, primary and
secondary Telegram lifecycles, bounded failure/recovery behavior, authority
rotation, exact control-plane rollback, and separately approved provider
cleanup. Completion does not claim the remaining two-vantage protocol row,
fleet-wide monitoring, full staging-matrix acceptance, or production cutover.

## Ownership

- Portfolio and OpenSpec state:
  `docs/tasks/issues/staging-observability-telegram-acceptance.md` and
  `openspec/changes/staging-observability-telegram-acceptance/`.
- Operator/runtime contracts with explicit staging-only additions:
  `Makefile`, `scripts/terraform-env.sh`, `scripts/render-inventory.sh`,
  `scripts/observability-contract.py`, `scripts/observability-operator.py`,
  `ansible/playbooks/observability-*.yml`, and
  `ansible/roles/observability_*`, plus the baseline, `auto_updates`,
  `firewall`, `monitoring`, and `node_manifest` roles.
- Existing provider and secret contracts:
  `terraform/providers/upcloud/`, `terraform/providers/hetzner/`,
  `terraform/providers/scaleway/`, `secrets/schema.json`,
  `scripts/validate-secrets.py`, and `scripts/check-secrets-coverage.py`.
- Ignored live tfvars and Terraform workspace data remain at repository-routed
  provider paths; private inventory, variables, secrets, approvals, rollback
  manifests, receipts, and journals remain outside Git. They are
  single-operator serialized state and are never edited concurrently.
- Shared repository task/board files are updated only through `./taskctl`.
- Parallel source-slice ownership for the implementation wave is explicit:
  the primary agent owns `Makefile`, the staging acceptance coordinator,
  shared documentation, task/OpenSpec lifecycle files, and final integration;
  the bootstrap worker owns the exact-host operator/playbook and its focused
  tests; the cleanup worker owns the guarded provider cleanup coordinator and
  its focused tests. Shared files are changed only in the primary lane, and no
  worker reverts or rewrites another lane.

## Execution

- [x] MON-1790652096462210 Implement and test exact-host observability baseline and host-class firewall bootstrap #feature !high @item:MON-1790650904289505
- [x] MON-1790652096934376 Implement and test bounded staging acceptance actions and redacted receipts #feature !high @item:MON-1790650904289505
- [x] MON-1790652346357417 Implement and test identity-bound guarded UpCloud Hetzner and Scaleway cleanup and absence proof #feature !high @item:MON-1790650904289505
- [ ] MON-1790651216954415 Preflight provider, SSH, SOPS, Telegram, cleanup, and exact protected-main execution authority #feature !high @item:MON-1790650904289505
- [ ] MON-1790651217409733 Provision or reconcile the disposable three-host staging topology and render validated private inventory #feature !high @item:MON-1790650904289505
- [ ] MON-1790651217861152 Deploy independent dead-man, control plane, and canary agent from one exact source revision #feature !high @item:MON-1790650904289505
- [ ] MON-1790651218327983 Prove fresh authenticated canary telemetry and the bounded ingestion, WAL, staleness, grouping, and silence matrix #feature !high @item:MON-1790650904289505
- [ ] MON-1790651218798773 Prove the human-observed primary Telegram firing, reminder, delivery-failure, and resolved lifecycle #feature !high @item:MON-1790650904289505
- [ ] MON-1790651219261781 Prove the independent dead-man control-plane-loss, reminder, refusal, and stable-recovery lifecycle #feature !high @item:MON-1790650904289505
- [ ] MON-1790652097417200 Prove separate control-plane service and provider host-network loss with bounded dead-man recovery #feature !high @item:MON-1790650904289505
- [ ] MON-1790652097923534 Prove dead-man service loss through the primary route with bounded restoration #feature !high @item:MON-1790650904289505
- [ ] MON-1790652098418969 Prove primary Telegram authority loss through the secondary dead-man and fresh-canary recovery #feature !high @item:MON-1790650904289505
- [ ] MON-1790651219743990 Rotate the canary sender and primary and secondary notification authorities with old-material rejection #feature !high @item:MON-1790650904289505
- [ ] MON-1790651220194212 Prove invalid candidate refusal and exact control-plane last-known-good rollback #feature !high @item:MON-1790650904289505
- [ ] MON-1790651220644401 Remove observability components, destroy disposable resources, and verify provider absence #feature !high @item:MON-1790650904289505
- [ ] MON-1790651221104630 Reconcile redacted acceptance evidence with local and hosted gates without claiming fleet or production cutover #feature !high @item:MON-1790650904289505

## Verification

- Source/local gate: clean selected protected-main revision, task/OpenSpec
  strict validation, secret schema/coverage/redaction checks, bootstrap,
  staging-controller, guarded-cleanup, timeout/interruption, provider-absence,
  unit and role tests, and `make check` through `build-gate --` when required by
  the invoked toolchain.
- Hosted gate: terminal green required checks for the exact planning and final
  evidence revisions; queued or unrelated runs are not acceptance.
- Dry-run gate: reviewed UpCloud, Hetzner, and Scaleway `staging` plans; exact
  three-host inventory/topology; cross-provider dead-man; distinct failure
  domains; proof each state is empty or task-bound; exact-host baseline/firewall
  check mode; private administration; `observability-validate` and
  `observability-render` per component.
- Staging deployment gate: exact installed source/generation parity for the
  control plane, dead-man, and canary; fresh advancing canary metrics; valid
  write accepted and invalid identity/path/method writes rejected.
- Failure gate: serial ingestion/WAL/staleness/watchdog/backup/grouping/silence,
  separate control service and provider host/network loss, dead-man service
  loss, and primary authority loss rows, with healthy baseline restored after
  every row and no inference from local process state.
- Telegram gate: separately human-observed primary firing/reminder/resolved and
  independent secondary loss/reminder/recovery in the intended private
  destinations; API success alone is insufficient.
- Credential gate: replacement canary sender, primary bot, and secondary bot
  each work before separately authorized upstream revocation; private bounded
  checks categorically reject old material; `still-valid` exits non-success and
  blocks rotation/cleanup; no duplicate route remains.
- Rollback gate: invalid candidate refuses before mutation; valid candidate is
  followed by exact retained control-plane generation restoration with storage
  and schedule integrity.
- Cleanup gate: TSDB-preserving component removal, explicit rollback/retention
  closure, separate approval binding the complete managed resource set,
  delete-only proof for every Terraform address, independent absence of every
  separately addressable provider resource, and safe plaintext retirement.
- Artifact gate: `verification.md` contains only redacted technical aliases,
  categorical outcomes, timestamps, exact source revision, generation digests,
  and explicit remaining fleet/client/cutover gaps.
