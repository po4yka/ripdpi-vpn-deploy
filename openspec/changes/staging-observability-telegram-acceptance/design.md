## Context

The observability roles, contracts, schemas, operator controller, Make targets,
tests, and operations runbook already exist. Their strongest evidence is local,
Molecule, fixture, and hosted CI; the former live staging execution step was
not performed and was explicitly dropped. Two source gaps block safe execution:
fresh control/dead-man hosts have no exact-host baseline/firewall bootstrap,
and the current operator has no bounded commands for central queries, long
critical drills, controlled faults, restoration, or revocation-negative proof.
This change implements those missing surfaces and then performs component and
Telegram acceptance without treating it as the complete runbook matrix, fleet,
client-path, or production cutover evidence.

The authoritative source for execution is the protected-main revision after
this change's planning artifacts merge. The working checkout, rendered
inventory, private variables, materialized SOPS document, provider state, and
installed generation must all bind to that revision. Secret values, provider
addresses, Telegram destinations, and private inventory remain outside Git and
outside captured command output.

## Goals / Non-Goals

- Goal: deploy a disposable control plane, independent dead-man, and one
  canary agent and prove fresh authenticated telemetry from exact source.
- Goal: provide tested exact-host host bootstrap and staging-only acceptance
  commands so live proof is reproducible and cannot degrade into raw SSH or
  caller-selected provider faults.
- Goal: obtain machine evidence and separate human observation for the primary
  and secondary Telegram firing, reminder, and recovery lifecycles.
- Goal: exercise bounded failure, credential rotation, exact rollback, and
  cleanup with fail-closed stop conditions.
- Goal: leave redacted verification that another operator can audit against the
  selected source revision.
- Non-goal: roll out agents to the permanent fleet.
- Non-goal: claim authenticated REALITY, XHTTP, Hysteria2, or AmneziaWG
  availability from two external vantages.
- Non-goal: cut over production paging, remove legacy production delivery, or
  change retention policy.
- Non-goal: add an observability dashboard, public administration interface,
  production dependency, or alternate notification channel.

## Decisions

### 1. Use three provider roots with `ENV=staging` and preserve cross-provider dead-man placement

A new canary VPN node is created from the UpCloud `staging` root because the
operator requires inventory `env=staging`; the existing task-specific CI
staging node has a different environment identity and is not reused or mutated.
The control plane is created from the Hetzner `staging` root and the dead-man
from the Scaleway `staging` root. All three use distinct technical
failure-domain aliases; the dead-man therefore differs from the control plane
by provider and failure domain as the existing topology contract requires.

The control plane uses at least 40 GiB available storage and publishes only the
declared TCP 9443 authenticated ingestion listener. The dead-man publishes only
the declared TCP 9444 pulse listener. SSH remains source-restricted by the
Terraform and guest-firewall contracts. The canary retains its reviewed VPN
listener contract. Prometheus, Alertmanager, exporters, status endpoints, and
silence administration remain loopback or private-access only.

The exact provider tuple is not silently substituted. UpCloud, Hetzner, and
Scaleway credentials and account scope are explicit preflight prerequisites;
if either non-UpCloud authority is unavailable, live provisioning remains
blocked. The topology validator is not weakened to accommodate one provider.

### 2. Preserve layer ownership and use one provider state per node

Each disposable node is created from its existing provider root with
`ENV=staging`; the one-server-per-root shape avoids inventing a logical
environment/workspace alias and remains compatible with the operator's strict
`staging` scope. Terraform owns servers, provider firewalls, SSH keys, and
public listener contracts; cloud-init owns only initial access and hardening;
Ansible owns every observability runtime file and unit. Before any provider
plan or apply, preflight proves that each selected `staging` state is empty or
already bound to this task's immutable manifest. A non-empty state without that
binding is treated as unrelated operator state and refuses without mutation.
Multi-host inventory is rendered from the three provider/environment pairs with
`OBSERVABILITY_HOST_CLASSES` and `OBSERVABILITY_FAILURE_DOMAINS`; it is never
hand-edited.

Two sentinel technical identities and path signatures remain in the topology
contract because topology validation requires them, but this change does not
install or claim their two-vantage protocol-liveness evidence.

### 3. Separate repository-routed provider state from owner-private live material

Provider tfvars and workspace data remain in each provider root at the ignored
paths required by the Make/`terraform-env.sh` contract; they are not relocated
or symlinked. The operator separately prepares a task-specific mode-0700 root
for materialized SOPS YAML, role-variable snapshots, known-hosts, approvals,
rollback manifests, bounded receipts, and the resumable execution journal.
These are regular same-owner files with the modes required by repository
controllers. No plaintext secret, state, or endpoint is copied into task,
OpenSpec, audit, or CI artifacts.

The staging secret document supplies unique sender mTLS identity, ingestion
authority, relay credential, primary Telegram bot authority, pulse authority,
reverse-health identity, and secondary Telegram bot authority. Equality and
coverage validators run before host mutation. Telegram bot creation or topic
selection and later BotFather token revocation are separate operator-owned
external prerequisites. Each revocation requires its own approval record and a
private old-token file; absence blocks before the action rather than producing
placeholder credentials or an inferred rejection.

### 4. Implement exact-host bootstrap and bounded staging acceptance before live work

The source change exposes three named Make surfaces:

- `make observability-host-bootstrap`: an exact-host verb in
  `scripts/observability-operator.py` for only `control-plane` and `deadman`
  inventory classes, backed by `observability-host-bootstrap.yml`, which
  converges `baseline`,
  `auto_updates`, host-class-aware `firewall`, loopback `monitoring`, and
  `node_manifest` without any VPN transport role;
- `make observability-staging-acceptance`: a fixed resumable coordinator in
  `scripts/observability-staging-acceptance.py` that consumes one private
  mode-0600 manifest and journal, invokes only exact-host lifecycle commands and
  allowlisted staging actions, and serializes central metric queries, critical
  primary lifecycle, control-plane service loss, Hetzner control-host power
  loss/recovery, dead-man service loss, forced primary canary, authority
  rotation checkpoints, and categorical old-material rejection;
- `make observability-staging-cleanup`: a separate coordinator in
  `scripts/observability-staging-cleanup.py` that consumes the completed
  acceptance journal plus a later exact destructive-data approval, removes
  components, performs identity-bound provider-routed destruction, verifies
  absence of every separately addressable provider resource, and only then
  permits private material retirement.
  This change implements missing Hetzner and Scaleway guards alongside the
  UpCloud path: each manifest freezes account/project, environment, exact state
  path/digest, every Terraform address, every separately addressable provider
  identity, source revision, expiry, and approval; the controller accepts only
  a reviewed plan that deletes exactly that complete set with no create,
  update, replace, or unrelated delete and obtains independently authenticated
  provider-specific absence results before completion. Hetzner primary storage
  is implicit in the server lifecycle, while any separately addressable storage
  remains an independent manifest and absence-check entry.

The firewall uses the existing provider listener contract but derives its
runtime manifest from `observability_host_class`: only TCP 9443 for the control
plane, only TCP 9444 for the dead-man, plus the separately managed effective
SSH listener. The acceptance manifest contains only fixed
provider/environment/host aliases, private file paths, maximum row deadlines,
and approval bindings; it cannot carry a remote command, arbitrary unit,
endpoint, or credential value. The controller owns an atomic resumable journal
so interruption restores or records an ambiguous row before a later row can
run. Hetzner power control is bound to the exact Terraform output identity and
uses the reviewed provider API without placing its token in argv, logs, state,
or receipts.

Every new surface rejects `prod`, wildcards/groups, arbitrary unit or command
names, debug output, missing private authorization/restore records, unsafe
receipt paths, and source/inventory drift. Focused unit, role/Molecule,
fail-before-mutation, timeout, interruption, rollback, and redaction tests
precede live use.

### 5. Deploy in dependency order with explicit preflight and exact-host scope

After local `make check` and protected-main hosted CI succeed, execution runs:

1. UpCloud, Hetzner, and Scaleway provider API/authentication and cost-scope
   preflight;
2. Terraform plan/apply for control plane and dead-man, plus canary creation or
   exact-source reconciliation;
3. cloud-init, strict SSH, inventory, topology, and secret validation;
4. exact-host baseline/firewall bootstrap and live listener/no-public-admin
   verification for control plane and dead-man;
5. `observability-validate` and `observability-render` for each exact host;
6. dead-man deploy, control-plane deploy, then canary-agent deploy;
7. bounded central query and component status proving fresh advancing metrics
   before any failure injection.

These named Make targets remain the canonical surface. Each external row
consumes a private approval record that binds exact target, action, restore
action, deadline, cancellation condition, and window. A planning approval never
substitutes for row authority. The controllers must not expose a general
production fault selector or call the all-host `site.yml` playbook.

### 6. Execute the component/Telegram matrix serially and restore baseline after every row

The staging matrix is reduced to evidence this task can legitimately prove:

- valid canary write plus wrong identity/path/method rejection;
- bounded canary WAL behavior while the receiver is unavailable;
- canary target/family absence and stale-producer truthfulness;
- grouping/inhibition and finite silence behavior;
- watchdog/backup malformed, failed, future, and stale producer evidence;
- primary Telegram firing, reminder, independently detected authority loss,
  and resolved behavior;
- control-plane service loss and the separate provider host/network loss,
  observed through secondary dead-man firing, reminder, and stable recovery;
- dead-man service loss observed through primary firing and stable recovery;
- canary sender, primary bot, and secondary bot authority rotation;
- invalid candidate refusal, valid generation activation, and exact
  control-plane last-known-good rollback.

| Live row | Bound and independent observation | Required restore / stop condition |
|---|---|---|
| control-plane service | secondary dead-man fires within ten minutes after five missed pulses | restore the recorded unit states; require fresh advancing pulses and stable recovery; otherwise abort |
| control-plane host/network | secondary dead-man fires within ten minutes of the exact provider stop/isolation action | execute the recorded provider start/reconnect action; require strict SSH, component readiness, fresh pulses, and stable recovery; otherwise use the provider-console fallback and abort |
| dead-man service | primary `ObservabilityDeadmanReverseMissing` fires within ten minutes | restore recorded dead-man unit states; require fresh reverse health and stable resolved delivery; otherwise abort |
| primary Telegram authority | forced primary canary records failure, pulse publication becomes unhealthy, and the secondary route reports authority loss | activate the prevalidated replacement, force a successful primary canary, require fresh advancing pulses and stable secondary recovery; otherwise restore retained authority and abort |

Every row's authorization record is created only after its exact target and
restore commands are reviewed. The controller freezes that input and emits an
`incomplete` categorical receipt if interruption or deadline expiry makes the
outcome ambiguous.

The live reminder interval remains the production contract: one hour for a
critical primary or dead-man reminder. Acceptance waits for the real interval;
it does not weaken interval validation or install a staging-only timing branch.
Deterministic 429, 5xx, redirect, timeout, replay, future, and malformed cases
remain source/fixture evidence and are referenced separately, not mislabeled as
live Telegram or network proof.

Every row begins with a healthy baseline receipt and ends with the same or a
declared new accepted generation. A missing expected signal, missed deadline,
restore failure, or ambiguous remote outcome aborts later rows. Recovery is
accepted only from fresh advancing evidence, never from service liveness or an
API response alone.

### 7. Separate transport evidence from human Telegram receipt

The controller records only categorical delivery results, timestamps, technical
aliases, and generation digests. The user confirms visible messages in the
intended private primary and secondary chat/topics. Message bodies, chat IDs,
topic IDs, bot names, and tokens are never committed. If human observation is
not supplied, the corresponding acceptance remains blocked even when the API
returns success.

### 8. Rotate one authority at a time and revoke only after replacement proof

The canary sender is rotated first, followed by the primary bot authority and
the secondary bot authority. For each authority, complete replacement material
is validated, deployed with the existing `observability-rotate` transaction,
and exercised before old material is revoked. Telegram candidate proof includes
a clearly labelled direct staging canary observed by the owner. BotFather token
revocation is then performed as a separately authorized human action. The
bounded negative checker reads the old token from a private file, disables
proxy/redirect behavior, caps response size/time, and emits only `rejected` or
`still-valid`; it never prints the token, request, or response. Candidate
failure relies on the role's captured-generation restore and is verified before
continuing.

`still-valid` is a hard nonzero refusal. It keeps the rotation and cleanup steps
open, preserves prior recovery material, and requires another separately
authorized upstream revocation plus a fresh rejection observation.

There is no dual-send paging window. Exactly one active primary route and one
active secondary route remain after each transaction.

### 9. Roll back only the control plane through the public rollback command

The task captures the control plane's exact private previous generation and a
mode-0600 digest-bound rollback manifest. After a valid candidate generation is
active, `observability-rollback` must restore that retained generation,
authority snapshot, and prior service states. Agent and dead-man do not claim
operator-command rollback because the current public surface does not provide
it; their activation-failure transaction restore is tested during rotation.
Adding broader rollback semantics is outside this acceptance task.

### 10. Cleanup preserves the TSDB until separately approved destruction

After evidence is complete, component-scoped removal runs in canary,
control-plane, and dead-man order. Control-plane removal intentionally preserves
the TSDB and retained rollback state. Provider destruction is a distinct
destructive-data action and runs only after the evidence is complete, the
rollback/retention window is explicitly closed, and a private approval binds
the complete managed resource set frozen from the task-owned state and reviewed
plan. Without that approval the resources remain in their last safe state and
cleanup acceptance stays blocked. After approved destruction, every separately
addressable provider identity is queried independently before local sensitive
state is retired; absence of a Hetzner server also proves absence of its
implicit primary storage.

## Contracts and ownership

- `terraform/providers/upcloud/`, `terraform/providers/hetzner/`, and
  `terraform/providers/scaleway/`: existing `staging` server, disk, firewall,
  SSH, and listener resources; no credentials or live tfvars enter Git.
- `scripts/terraform-env.sh` and provider Make targets: mandatory workspace
  routing for init, plan, apply, and output. The new staging-cleanup coordinator
  owns guarded destroy and provider-specific absence checks; raw Terraform is
  not used.
- `scripts/render-inventory.sh`: canonical multi-host inventory and
  observability topology generation from provider outputs.
- `scripts/observability-contract.py`: topology, listener, sentinel, and source
  validation before deployment.
- `ansible/playbooks/observability-host-bootstrap.yml` and the baseline,
  `auto_updates`, `firewall`, `monitoring`, and `node_manifest` roles: new
  exact-host non-VPN preparation path for control-plane and dead-man hosts.
- `scripts/observability-operator.py` and
  `make observability-host-bootstrap`: existing exact-host controller plus the
  narrow non-VPN host preparation verb.
- `scripts/observability-staging-acceptance.py` and
  `make observability-staging-acceptance`: fixed resumable source/metric,
  critical-drill, fault/restore, forced-canary, rotation-checkpoint, and
  revocation-negative sequence with bounded receipts.
- `scripts/observability-staging-cleanup.py` and
  `make observability-staging-cleanup`: post-evidence component removal,
  per-provider immutable cleanup manifests, delete-only plan validation,
  separately approved destruction of the complete managed resource set, and
  authenticated provider-specific absence proof for UpCloud, Hetzner, and
  Scaleway.
- `ansible/roles/observability_agent/`: canary scrape, bounded WAL, mTLS sender,
  and local producer adaptation.
- `ansible/roles/observability_control_plane/`: write-only receiver, bounded
  Prometheus storage, rules, Alertmanager, relay, silence gateway, pulse sender,
  immutable generations, and retained control-plane rollback.
- `ansible/roles/observability_deadman/`: independent pulse validation,
  reverse-health summary, secondary delivery, and immutable generations.
- `secrets/schema.json`, `scripts/validate-secrets.py`, and
  `scripts/check-secrets-coverage.py`: staging secret structure, separation,
  completeness, and safe materialization gates.
- `docs/OBSERVABILITY-OPERATIONS.md`: authoritative matrix, evidence classes,
  and operator safety boundaries.
- `verification.md`: redacted source/local, hosted, dry-run, staging, Telegram,
  rotation, rollback, and cleanup evidence for this change.

The Make operator contract gains explicit staging-only verbs and is therefore
documented and tested as an operator-visible change. No production dependency
is added. Private tfvars, inventory, secrets, endpoints, approvals, and receipts
remain operator-local.

## Risks / Trade-offs

- UpCloud, Hetzner, Scaleway, or Telegram credentials are absent or invalid ->
  fail in preflight before provisioning or notification; request only the
  missing operator input and do not substitute a same-provider dead-man.
- Three live nodes incur temporary cost -> use the smallest validated plans and
  disable provider backups, but destroy only after the separately approved
  rollback/retention closure; otherwise retain the safe state and report cost.
- Three provider accounts enlarge credential and cleanup scope -> validate each
  independently, keep the dead-man provider distinct, and serialize provider
  mutation/absence proof through the fixed coordinators.
- A one-hour real reminder makes acceptance slow -> keep the normative interval
  and use resumable bounded observation rather than weakening production
  behavior.
- Fault injection can strand a host -> pre-bind each row to a restore action,
  stop condition, private approval/journal entry, deadline, bounded receipt, and
  provider-console fallback.
- Telegram API success can be mistaken for delivery -> require separate human
  confirmation and keep the step open without it.
- Rotation may destroy the only working notification authority -> validate and
  exercise candidate material before separately authorized BotFather
  revocation; rotate serially and retain the previous generation until the
  rollback window closes.
- Provider destroy would delete the preserved TSDB -> require a second
  post-evidence approval that binds every Terraform address and separately
  addressable provider identity in the complete managed resource set and closes
  the rollback/retention window; otherwise retain the resources and leave
  cleanup blocked.
- Hetzner/Scaleway generic destroy lacks the existing guarded cleanup lifecycle
  -> implement identity/state/account-bound manifests, delete-only plan checks,
  independent absence probes, and regression tests before live provisioning.
- Evidence capture may leak secrets or endpoints -> record only allowlisted
  categories, aliases, timestamps, revision/generation digests, and provider
  absence; run redaction checks before commit.

## Migration Plan

1. Implement and test the exact-host observability-host bootstrap, host-class
   firewall reconciliation, bounded staging acceptance verbs/receipts, and
   UpCloud/Hetzner/Scaleway guarded cleanup/absence adapters.
2. Merge that source revision through protected main and select it only after
   hosted checks are terminal green.
3. Preflight UpCloud, Hetzner, and Scaleway access, SSH ownership, SOPS
   materialization, Telegram destinations, current canary ownership, each row's
   authority/window, cleanup authority, and user availability for message
   observation.
4. Create private task inputs and plan all three `staging` provider roots;
   review cost, zones, storage, listener contracts, and exact cleanup targets.
5. Apply or reconcile the disposable nodes, render the exact inventory and
   topology, and complete cloud-init/SSH checks.
6. Bootstrap control/dead-man baselines, then validate/check-render and deploy
   dead-man, control plane, and canary agent; prove fresh advancing metrics.
7. Run the serial component/Telegram matrix, restoring baseline after every row
   and recording human Telegram observations separately.
8. Rotate the sender, primary bot, and secondary bot authorities serially;
   prove replacement success, separately authorized upstream revocation, and
   categorical old-material rejection.
9. Activate a reviewed control-plane candidate and prove exact last-known-good
   rollback with storage and schedule integrity.
10. Remove components, capture all evidence, explicitly close the
    rollback/retention window, obtain exact destructive-data approval, then run
    guarded provider destruction and independent provider-absence checks.
11. Complete redacted verification, run repository validation and hosted CI,
    then archive the change. The remaining protocol-liveness runbook row,
    fleet rollout, and production cutover start only as separate portfolio
    tasks.

If deployment fails before any role publishes state, destroy the newly created
resources after provider review. If a role or drill fails after publication,
restore the last healthy component state first, collect only redacted
diagnostics, and then remove/destroy. If the control-plane rollback manifest or
retained generation is inconsistent, do not improvise symlink repair; preserve
the host for diagnosis and leave the task blocked.
