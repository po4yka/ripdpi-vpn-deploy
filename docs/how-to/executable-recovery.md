# Recreate a lost node and resume after failure

> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-10-22

## Purpose and scope

Run Path A recovery from committed source and private SOPS authority. The
controller provisions one new UpCloud environment, admits management access,
deploys the canonical runtime, updates device delivery through a surviving
publisher and checks device migration readiness. It retains each external
operation's intent before execution and reconciles observed state after a lost
response. It does not destroy the old node.

This workflow supports UpCloud and a separate surviving subscription publisher.
Other providers, a lost publisher, topology-wide observability replacement and
Path B restic restoration are outside this execution contract. Their inputs
refuse before provider mutation. Use a separate authorized procedure for them.

## Preconditions

Use a clean exact source revision and pinned tools. Read the local operator kit
contract before collecting recovery inputs. Prepare a new, explicitly named
replacement environment and its Terraform variables. The environment must not
be `prod`, `default`, `staging` or a disposable CI environment. The planned
server must have the operation's recovery label and the canonical managed label.

Create an empty owner-only state directory with mode `0700`. Keep its private
journal, saved plans, review artifacts and command diagnostics together. They
may contain sensitive data. Manifest and private input files need mode `0600`.
The controller never prints their contents.

Prepare these exact manifest fields:

| Field | Required content |
|---|---|
| `schema_version`, `id` | Version `1` and the unique recovery operation name |
| `provider`, `environment` | `upcloud` and the new replacement selector |
| `source_revision`, `account` | Exact clean commit and authenticated provider account |
| `hostname`, `cohort` | Planned inventory alias and canonical runtime profile |
| `state_directory` | Empty private durable operation directory |
| `sops_file`, `age_key_file`, `ssh_key_file` | Separate target authority and its admitted private inputs |
| `known_hosts_file`, `bootstrap_config` | Independently authenticated host pin and schema-2 Tailnet bootstrap inputs |
| `promotion_configs_file` | Per-alias production recovery promotion intent |
| `migration_plan` | Exact source/target migration plan using the surviving publisher |
| `inventory` | Complete desired set of 3–10 rows with `host`, `cohort`, and optional private `handoff` path |

Use absolute canonical paths without shell expansion. Each inventory row must
name one provider/environment pair. Include the source, replacement and surviving
publisher. Existing peers retain their confirmed management handoff; the
controller generates the replacement handoff. The migration target must use the
same target SOPS document and known-hosts authority as the recovery manifest.

After provisioning reveals the new address, complete the bootstrap inputs and
host pin using an independently authenticated source. A provider API response
or an unauthenticated SSH scan is not a host-key proof.

Production promotion uses one reviewed existing dedicated SSH sentinel and a
pre-issued target client. Its `recovery-promotion-intent` contains the target
identity, host, cohort, client, liveness configuration and private input paths.
The liveness target must omit `applied_at`; the final post-deployment hook creates
the real epoch and obtains an actual installer receipt. For AWG, include the
exact target device private-key input. Do not manufacture a deployment time or
reuse a receipt for another target.

## Authorization

Authorize the exact provider account, replacement resources, cost, environment,
management changes, sentinel installation and device migration. Source delivery
through a PR does not authorize live execution. Review each concrete action
artifact before approving its digest. An approval applies to one bound phase;
it does not authorize a changed plan, account, resource or source revision.

## Steps

1. Set `RECOVERY_MANIFEST` to the private manifest and request the next action:

   ```bash
   make recovery ACTION=run RECOVERY_MANIFEST="$RECOVERY_MANIFEST"
   ```

2. When the command returns `review-required`, inspect the private `review`
   artifact. Set `RECOVERY_APPROVAL` to its exact returned digest and resume:

   ```bash
   make recovery ACTION=resume RECOVERY_MANIFEST="$RECOVERY_MANIFEST" RECOVERY_APPROVAL="$RECOVERY_APPROVAL"
   ```

3. Repeat the review step for each distinct action. A saved Terraform plan,
   orphan import, authenticated pin, device migration and deployment have
   separate bound reviews. Deployment dry-run evidence expires after 900 seconds.

4. After an interruption, keep the same source, manifest and state directory:

   ```bash
   make recovery ACTION=resume RECOVERY_MANIFEST="$RECOVERY_MANIFEST"
   ```

5. Inspect retained progress without a new live acceptance claim:

   ```bash
   make recovery ACTION=status RECOVERY_MANIFEST="$RECOVERY_MANIFEST"
   ```

Exit `0` means the requested command completed; `status` remains historical.
Exit `3` means a concrete review or device acceptance is pending. Exit `2` means
a refusal or interruption. Read the categorical result and retain the journal.

## Verification

The controller compares the current account, unique live resource, Terraform
state, immutable saved plan and source identity before mutation. A lost apply
response does not authorize duplicate creation. An orphan must match the owned
attempt and receive a separate import review; remaining resources then converge
through another admitted plan.

Management requires pinned SSH, real bootstrap and ownership checks. Runtime
convergence uses canonical dry-run, deployment and traffic verification. The
sentinel receipt binds the new target and actual generation. Published device
profiles remain distinct from received profiles and a fresh tested device path.
Import the explicit device receipts through the migration workflow, then resume
recovery until readiness succeeds. The final check re-observes provider identity,
source and pins after long guest and device checks.

## Rollback

Do not delete the journal, replay a saved plan without its controller, replace
pins with `accept-new`, or destroy the target automatically. An incomplete
operation can contain a usable partial resource. Reconcile it through the same
manifest. A conflict or unavailable authoritative input remains unfinished.
Retiring the lost/source node is a separate authorized operation after device
acceptance and a reviewed provider plan.

## Evidence to record

Record the operation name, source revision, completed phase and categorical
verification outcome. Keep provider credentials, private manifests, Terraform
state and plans, SOPS plaintext, host pins, device payloads and raw diagnostics
inside the private operator kit. Local fixtures and isolated CI do not prove a
live recovery or acceptance on a physical device.
