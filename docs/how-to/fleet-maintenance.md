# Maintain existing nodes and verify operator recovery

> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-11-05

Use the canonical Make commands below from a clean controller checkout without `.fleet.mk`. Store private configuration, plans, receipts and working identities under the [local operator kit](local-operator-kit.md). Configuration files must be owner-only regular files; operation and runtime directories must be mode 0700. The operation requires the exact-node authorization described in [deploy](deploy.md#authorization), including an explicit expiry.

## Prepare an existing-node operation

First run `make check-prereqs` with a clean Make environment. This command does not load `.fleet.mk` or inventory. It checks the active and child Python environments, the exact tool pins in `mise.toml`, and the installed package pins in `requirements.txt`. Exit status 2 means the environment is not ready; it is separate from a failed behavior test. Use the pinned Python installation and install the hash-locked requirements before repeating the check.

For Docker-based validation, also run `mise exec -- python3 scripts/check-prereqs.py --docker`. It checks the existing Linux daemon and Python SDK connection without creating a container. If the CLI works but the SDK cannot connect, select the active context endpoint with `DOCKER_HOST`. This check does not prove image architecture support or Molecule success.

Restore the reviewed state for each selected provider workspace, then run `make PROVIDER=<provider> ENV=<workspace> init` in this controller checkout. This prepares local workspace metadata; it does not create a VPS. Client profile export reads these workspace outputs. `make validate` uses a separate, backend-free data directory and does not prepare them.

Create a private JSON configuration with these fields:

| Field | Value |
|---|---|
| `schema_version` | `2` |
| `catalog` | Absolute private catalog path for accepted core-state reconciliation |
| `id` | A stable lowercase operation name |
| `expires_at` | An explicit timezone-aware authorization deadline |
| `state_directory` | An existing empty private directory for this operation |
| `runtime_parent` | A separate private directory excluded from backups |
| `age_identity` | The existing working age identity path |
| `log_recipient` | That identity's public age recipient |
| `nodes` | An ordered list of exact existing-node selections |
| `liveness_config` | Private canonical protocol-liveness policy with the expected candidate runtime |
| `liveness_inputs` | Complete private SSH configuration, pin and identity dependencies of its probe transports |

Each node has `host`, `environment`, `provider`, `sops_file`, `extra_vars`, `known_hosts`, `ssh_contexts`, and `inputs`. `inputs` lists all additional private files used by the profile, including referenced certificates and probe inputs. Preparation also discovers the complete `nginx_xhttp_public_site_dir` tree and enabled network-exposure artifact/key inputs. Other external dependencies remain an explicit review obligation: check the `inputs` closure before approving the preview. The command does not claim discovery of arbitrary script dependencies. The optional `promotion_config`, `tailnet_handoff` and `failure_receipts` fields map to the existing canonical deployment inputs. Use absolute literal paths. The command also freezes the generated inventory and its selected SSH keys. The canonical controller compares the bytes it consumes with those approved hashes, including the public site tree. Each attempt decrypts verified private copies of the encrypted secrets and age identity. A concurrent replacement of an original file cannot become a new deployment authority.

```bash
make maintenance ACTION=prepare CONFIG="$MAINTENANCE_CONFIG" PLAN="$MAINTENANCE_PLAN"
make maintenance ACTION=preview PLAN="$MAINTENANCE_PLAN"
make maintenance ACTION=status PLAN="$MAINTENANCE_PLAN"
```

Preview runs in a detached local worker. Wait until status reports `previewed`, then decrypt and review the recorded `.log.age` files. Review must establish the exact affected nodes and changes. Authorize the recorded `review_sha256` only after that review:

```bash
make maintenance ACTION=start PLAN="$MAINTENANCE_PLAN" APPROVAL="$REVIEW_SHA256"
make maintenance ACTION=status PLAN="$MAINTENANCE_PLAN"
```

The worker runs canonical decrypt, full dry-run, full deploy, verify, security-verify, smoke-test, fresh authenticated protocol acceptance and cleanup per node. Strict SSH inspection first confirms the target's exact deployed source revision and digest. A separate fresh protocol report must match the frozen probe generation, target address and alias, expected client runtime and complete positive profile proofs, including tunnel DNS. Static probe provenance does not establish the server's current source. A changed wire profile that the supported client cannot use fails this gate and needs canonical client refresh before further rollout. A failure stops before the next node. Probe transports use the canonical liveness policy; review and freeze every SSH dependency in `liveness_inputs`. Shared resource locks prevent two admitted operations from using the same node or inventory concurrently. The worker retains intent before each stage. Logs are encrypted before disk write and have a finite output and execution limit. A temporary plaintext file belongs to one attempt; it is removed after failure as well as success.

The worker inherits your `PATH`. The probe installation after convergence parses profiles with the local `sing-box` and `xray`, so each engine that the policy's required profiles need must report the version that `expected_runtime` pins. The deploy controller checks this before any site write and refuses with `onboarding capability refused: local-runtime-pin-mismatch`, or `local-runtime-engine-unavailable` when the engine is not on `PATH`. Put the pinned engines first on `PATH` before `preview` and `start`.

Each run locks every target node address and the generated inventory before its worker reports ready. When another run holds one of these locks, `preview`, `start` and `resume` refuse with `node-lock-busy: alias=<alias> held-as=target` or `node-lock-busy: resource=inventory held-as=shared-inventory`. Every maintenance run holds the shared inventory lock, so this refusal means that another maintenance run is active. Wait until `ACTION=status` of that run reports `worker_active: false`, then retry. Other refusals print their category as `operation refused (<category>)`. In a fresh worktree, `prepare` and the deploy controller refuse with `generated-inventory-missing` until you render the gitignored `ansible/inventory/generated.ini` with `make inventory PROVIDER=<provider> ENV=<env>`.

## Resume after failure

Inspect status and the encrypted diagnostics. Resolve the reported connection failure without changing frozen inputs, then use the same reviewed plan:

```bash
make maintenance ACTION=resume PLAN="$MAINTENANCE_PLAN" APPROVAL="$REVIEW_SHA256"
```

Resume retains accepted node boundaries. It repeats the complete canonical preview before another deploy; an interrupted stage is not inferred successful. When the failed node had already completed its deploy stage for the same plan source, and a fresh read-only probe shows that the live node manifest still reports the plan revision and deployable digest, resume skips that node's dry-run and deploy. It still runs decrypt, `verify`, `security-verify`, `smoke-test` and the protocol gate. When the probe cannot reach the node or reports another source, resume runs the complete sequence, which first discards the recorded convergence. A retained runtime transaction that refuses preview needs the separate reviewed [canonical recovery procedure](deploy.md#ordinary-re-deploy-recipe). This command does not convert a refused preview into authority to recover or deploy. Changed source, changed inputs or an expired grant require a new plan and preview. `status` reads historical local evidence; it does not refresh live acceptance. An abrupt process or machine loss can leave its owned temporary plaintext until the next admitted resume cleans that exact retained directory.

## Generate maintenance configuration

Configuration schema 2 requires `catalog`; schema 1 is no longer accepted. Add a
`maintenance` mapping to the existing private catalog. Its `defaults` contains
`age_identity`, `log_recipient`, `liveness_config` and `liveness_inputs`. Its `nodes`
maps exact node aliases to the node fields listed above. Keep one mapping per
node. Paths in this mapping can be absolute or relative to the catalog directory.
Never put credential values in the catalog.

Create a private generation request with `schema_version: 1`, `catalog`, `id`,
`expires_at`, `state_directory`, `runtime_parent`, and `nodes` (an ordered list of
exact aliases). Both directories must already exist with mode 0700. For example:

```json
{
  "schema_version": 1,
  "catalog": "/private/operator/catalog.json",
  "id": "core-refresh",
  "expires_at": "2027-01-01T12:00:00Z",
  "state_directory": "/private/operator/receipts/core-refresh",
  "runtime_parent": "/private/operator/runtime",
  "nodes": ["node-a", "node-b"]
}
```

Set the deadline to the actual authorization deadline. Generate configuration,
then use the existing preparation and preview flow:

```bash
make maintenance ACTION=generate CONFIG="$GENERATION_REQUEST" PLAN="$MAINTENANCE_CONFIG"
make maintenance ACTION=prepare CONFIG="$MAINTENANCE_CONFIG" PLAN="$MAINTENANCE_PLAN"
make maintenance ACTION=preview PLAN="$MAINTENANCE_PLAN"
```

Generation checks selected private dependencies and discovered site/exposure
inputs without contacting hosts or decrypting credentials. It does not replace
inventory preparation, dependency review, or authorization of the preview digest.
Missing mappings, duplicate nodes and unsafe or missing files refuse publication.

After source, protocol and cleanup checks pass for a node, maintenance writes an
immutable acceptance receipt and updates only these fields under
`current_actual_configuration.<alias>`:

- `core_source_revision` and `core_deployable_digest`;
- `current_core_verified_at`;
- `current_operation_receipt` and `current_operation_receipt_sha256`.

Monitoring records and unrelated catalog entries remain intact. Publication copies
the receipt to `receipts/maintenance/<id>-<plan digest prefix>/accepted-<alias>.json`
beside the catalog, creating private directories as needed, and the catalog
references that copy. Complete-kit backups therefore seal the referenced evidence
wherever the maintenance state directory lives. The receipt is
historical evidence, not a live status check. Preview, start and resume refuse
before any host mutation when a node not yet accepted by this plan no longer has
the core fields bound at preparation; prepare a new plan from the current catalog.
A competing core update during the run refuses
publication and stops before the next node. Review that conflict before resume.
An accepted node whose catalog write failed remains accepted in the journal;
resume retries its publication without deploying it again. Do not edit the frozen
plan or receipt to bypass a conflict.

## Schedule drift checks and verified backups

`operator-schedule` manages only the drift and complete-kit backup jobs. Existing
operator watcher jobs remain under `install-operator-crons.sh`. The new command
uses cron on Linux and launchd on macOS. It never installs a schedule implicitly.

The drift job runs canonical `dry-run`, `verify` and `security-verify`, checks the
fresh deployed source manifest, and cleans its temporary plaintext. It does not
deploy, repair drift or update accepted deployment state. A controller-owned callback records aggregate check-mode counts. Any changed,
failed or unreachable task refuses a clean drift result. Missing statistics also
refuse. Encrypted dry-run logs retain configuration differences for review.
Cloud resource drift remains a separate Terraform plan operation.
`ACTION=check` is terminal for its plan, so it accepts only a freshly prepared
plan and refuses one that was previewed, started or already checked. At
`timeout_seconds` the drift child cancels its running stage and cleans node
plaintext; the scheduler allows 300 seconds for that cleanup before it stops the child.

Create a private schedule configuration:

```json
{
  "schema_version": 1,
  "id": "operator-checks",
  "expires_at": "2027-01-01T12:00:00Z",
  "state_directory": "/private/operator/runtime/scheduled",
  "maintenance_config": "/private/operator/config/maintenance.json",
  "backup_config": "/private/operator/config/kit-backup.json",
  "backup_profile": "/private/operator/config/routine-backup.sops.json",
  "jobs": {
    "drift": {"interval_seconds": 86400, "timeout_seconds": 14400, "max_age_seconds": 172800},
    "backup": {"interval_seconds": 86400, "timeout_seconds": 1200, "max_age_seconds": 172800}
  }
}
```

Use the approved finite deadline; it cannot exceed the maintenance deadline.
The state directory must start empty, be private and be outside the backup selection (under
`runtime/` when it is inside the kit). Each interval must divide an hour in whole
minutes or divide a day in whole hours. Timeouts range from 60 to 14400 seconds.
The freshness window must cover at least one interval plus its timeout.

```bash
make operator-schedule ACTION=prepare CONFIG="$SCHEDULE_CONFIG" OUTPUT="$SCHEDULE_PLAN"
make operator-schedule ACTION=render CONFIG="$SCHEDULE_PLAN"
make operator-schedule ACTION=install CONFIG="$SCHEDULE_PLAN"
make operator-schedule ACTION=run CONFIG="$SCHEDULE_PLAN" JOB=drift
make operator-schedule ACTION=run CONFIG="$SCHEDULE_PLAN" JOB=backup
make operator-schedule ACTION=status CONFIG="$SCHEDULE_PLAN"
make operator-schedule ACTION=remove CONFIG="$SCHEDULE_PLAN"
```

Preparation discovers and binds the controller revision, inventory, private
inputs, site trees, backup configuration and routine credential profile. Installed
jobs bind the exact schedule plan digest. The drift job rechecks the clean controller
revision and every maintenance input. The backup job rechecks only its deadline, the
backup configuration, routine profile and identity, and the repository modules its
process executes: the scheduler, `operator-context.py`, `operator-kit.py` and their
import-time dependencies. It runs `operator-context.py` directly, so the Makefile and
fleet configuration are not part of it. Commits, local edits and inventory or secret
changes stop drift checks but not backups. Changed bound inputs or code require a new
reviewed plan; remove the old schedule before installing its replacement. Keep the
controller checkout available at the recorded path. Linux daily jobs
run at 03:00 in the scheduler's local timezone; macOS uses the configured interval.
A sleeping or offline controller can miss checks; status reports overdue evidence.

Each job has an overlap lock and atomic private status. `never-run`, `running`,
`interrupted`, `failed`, `different-plan` and `succeeded` are distinct. `overdue` and
`authorization_expired` are independent flags. A failed run preserves the previous
`last_success_at`. Read status from the approved operator workflow or monitoring
consumer; this command does not install a notification channel.

Backups use the existing restricted routine credential loader and complete
upload/download/decrypt/manifest verification. Command exit zero without the
matching positive remote-verification receipt is a failure. Backup diagnostics
are encrypted, and working identity copies are removed on ordinary completion or
failure. An interrupted backup retains its owned runtime for inspection; the next
admitted run removes the exact unchanged working identity before proceeding.

## Prepare component release inputs

Create a private JSON file with `schema_version: 1`, `component`, stable `version` and `artifacts`. Supported components are `prometheus`, `alertmanager`, `rclone`, `xray`, `vmagent` and `hysteria`. Both `amd64` and `arm64` entries require an HTTPS `url`, local artifact `path`, independently reviewed `sha256`, and `format` (`tar`, `zip`, `binary` or the project's XZ-compressed `deb`). Formats are fixed by the actual consumer: Prometheus/Alertmanager/vmagent use tar, Xray uses zip, Hysteria uses a raw binary and rclone uses the admitted Debian package. Hysteria also requires its distinct `runtime_release_version`. Obtain artifacts through the existing reviewed release procedure before running:

```bash
make release-inputs ACTION=prepare CONFIG="$RELEASE_CONFIG" OUTPUT="$RELEASE_INPUTS"
make release-inputs ACTION=verify CONFIG="$RELEASE_CONFIG"
```

Preparation derives version-specific archive members and verifies the actual checksum-pinned archive and ELF architecture. It rejects duplicate names, links, unsafe paths, missing members and expanded-size overflow. The output's `ansible_variables` mapping is the input fragment for the owning Ansible component. Merge it into the reviewed prepared profile; retain its other private inputs. Debian validation also verifies package name, version, architecture and the actual binary hash. Actual native version and client traffic checks remain separate release gates.

## Seal and verify the operator kit

Create a private JSON configuration with `schema_version: 1`, `kit`, `recipient`, `identity`, `rclone`, `rclone_sha256`, `bucket_id`, `bucket_name` and `required_paths`. `required_paths` lists the current authoritative recovery files relative to the kit, including each current encrypted state; a missing input refuses backup. Keep a working identity inside `runtime/` or outside the kit. Use the admitted pinned rclone binary and its reviewed SHA-256. The kit must contain its README, catalog, config, plans, receipts, recovery and state-backup directories.

```bash
make operator-kit ACTION=audit CONFIG="$KIT_CONFIG"
make operator-kit ACTION=seal CONFIG="$KIT_CONFIG" OUTPUT="$LOCAL_RESTORE_RECEIPT"
```

`seal` creates an age archive and checks it by real decryption and full manifest comparison. It includes recursive encrypted Terraform-state backups and excludes `runtime/`, working identities and previous complete operator-kit archives. The audit verifies filesystem authority and snapshot coverage; it does not independently establish that every remote account or grant is catalogued.

For offsite delivery, select a dedicated Backblaze key restricted to the exact bucket and `operator-kit/` prefix, with `listBuckets`, `readBucketEncryption`, `listFiles`, `readFiles` and `writeFiles` capabilities. Load only `B2_APPLICATION_KEY_ID` and `B2_APPLICATION_KEY` into the selected process environment from the encrypted operator authority. Use the approved scoped credential loader or SOPS `exec-env` with an authority containing exactly those two environment fields. Keep provider values in process memory and out of the kit configuration, command arguments and plaintext credential files.

```bash
make routine-backup PROFILE="$ROUTINE_SOPS_PROFILE" CONFIG="$KIT_CONFIG" OUTPUT="$OFFSITE_RESTORE_RECEIPT"
make operator-kit ACTION=backup CONFIG="$KIT_CONFIG" OUTPUT="$OFFSITE_RESTORE_RECEIPT"
make operator-kit ACTION=verify CONFIG="$KIT_CONFIG" ARCHIVE="$LOCAL_KIT_ARCHIVE"
```

`routine-backup` is the fixed credential-loading entry point. It decrypts the selected SOPS JSON profile in memory, requires exactly the two routine fields, drops inherited provider credentials and starts only the kit backup command. The backup then checks the actual remote grant before upload. Administrative provider profiles stay separate and cannot be passed to this routine context. This does not claim fine-grained API permissions for providers that do not support the required grant scope.

Backup requires a private bucket with SSE-B2 AES256, uploads only encrypted data, downloads the exact uploaded object and verifies its plaintext manifest in RAM. Anonymous download must be denied. A concurrent input change refuses a current coverage claim. The receipt acknowledges the preceding snapshot; it is not claimed to be part of its own archive. The command updates only the matching local/offsite acknowledgement in the private catalog after receipt verification; a concurrent catalog change refuses replacement. Retain the prior recovery set until the new restore passes.
