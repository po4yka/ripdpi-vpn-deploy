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
| `schema_version` | `1` |
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

## Resume after failure

Inspect status and the encrypted diagnostics. Resolve the reported connection failure without changing frozen inputs, then use the same reviewed plan:

```bash
make maintenance ACTION=resume PLAN="$MAINTENANCE_PLAN" APPROVAL="$REVIEW_SHA256"
```

Resume retains accepted node boundaries. It repeats the complete canonical preview before another deploy; an interrupted stage is not inferred successful. A retained runtime transaction that refuses preview needs the separate reviewed [canonical recovery procedure](deploy.md#ordinary-re-deploy-recipe). This command does not convert a refused preview into authority to recover or deploy. Changed source, changed inputs or an expired grant require a new plan and preview. `status` reads historical local evidence; it does not refresh live acceptance. An abrupt process or machine loss can leave its owned temporary plaintext until the next admitted resume cleans that exact retained directory.

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
