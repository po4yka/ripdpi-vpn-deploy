# Runbook — incidents

> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-11-05

## Purpose and scope

Decide what to do when something goes wrong: match the symptom in the decision matrix, then follow the linked procedure for lost SSH access, a lost age key, state loss or a suspected compromise.

Decision matrix for things going wrong. Pick the row that matches the symptom; cross-reference the linked runbook for the recovery procedure.

## Preconditions

- The symptom is observed, not guessed: a failed `make verify`, a watchdog alert, a client report or a provider notice.
- Nodes are disposable. When management access is gone, recreation is the default; rescue consoles are an owner-chosen emergency path.

## Authorization

Every target below that uses cloud credentials, inventory, SSH or decrypted secrets needs the operator's authorization for this environment, target and plan before it runs ([decision boundaries](../../AGENTS.md#decision-boundaries)). A reviewable plan or dry-run precedes every mutation. Every row of the matrix names the verb it leads to; authorize that verb for the affected node only.

## Decision matrix

| Symptom | Likely cause | Action |
|---|---|---|
| Single client URI leaked / device lost | Per-device | `rotate.md` § 1; record via `make audit-log-append ACTION=revoke-client CLIENT=…` |
| REALITY private key leaked | Server-wide | `rotate.md` § 2, then reissue every client |
| Subscription URL leaked publicly | Token | add the leaked token to `subscription.revoked_tokens`, run `make deploy`; reissue via `make issue-bootstrap CLIENT=… --expires DATE` |
| Bootstrap URL leaked before client fetched | Token | re-issue with `make issue-bootstrap CLIENT=… --expires DATE` (old token returns 410 on first GET) |
| TLS handshake to VPS fails from many networks | IP burned | `make burn-check` confirms from the workstation, and `NODES=… scripts/burn-check.sh --third-party` from named vantage points (that service then holds the node address); warm-spare → `make promote-spare OTP=…` (if pre-provisioned), else blue-green to new ASN |
| Protocol sentinels report sustained authenticated failure while direct controls pass | Targeted path block | Inspect `make protocol-liveness LIVENESS_CONFIG=…`; after quorum and three consecutive evaluations, use the bound OTP from `watch-spare` to start the normal operator-confirmed warm-spare promotion |
| Slow / lossy on one access network only, fine elsewhere | Routing / path-specific policing | try Hysteria2 fallback; if persistent, blue-green to a different region; for the ~12-concurrent-TLS policing rule run `make test-tls-policing HOST=…` then flip the cohort to `xray_flow_mode: mux` |
| `xray run -test -config` fails after deploy | Config bug | `rollback.md` § 1 (config rollback, automatic via handler rescue); `make drift-since-tag` shows what changed since last known-good |
| New Xray release crashes / leaks | Binary | `rollback.md` § 2 (binary rollback) |
| watchdog alerts with `class=policy_reject_spike` | Spike of policy-blackholed or VLESS-rejected events from authenticated clients | `make probing-summary` for the rollup; review routing rules for unexpected blackhole hits; consider tightening `policy_ratelimit` thresholds if abuse is confirmed |
| watchdog alerts with `class=tcp_listen_wedge` | Xray hung | `systemctl restart xray`; if recurring, check `vpn.xray_flow_mode` cohort match |
| watchdog alerts with `class=nginx_403_spike` | Probe/scrape wave | usually benign; if rate climbs, `make check-ip-reputation` to see if IP appeared on a public blocklist |
| Primary Telegram monitoring alert | Monitoring-rule finding | Open the `Runbook` link in the message, or find its family in [monitoring alerts](monitoring-alerts.md) |
| `make asn-drift` alert | Provider IP reassignment | check `docs/reference/provider-notes.md` — if new ASN is in Avoid tier, blue-green now |
| REALITY target ASN/path signal | The active target failed filtered-path TLS/H2/SAN/HTTPS checks or its ASN/prefix set changed twice | confirm from a second filtered vantage; acknowledge healthy DNS movement with `ACCEPT_BASELINE=1`, otherwise evaluate a replacement through the normal scan/validate/deploy workflow; never auto-switch |
| `make check-ip-reputation` alert | IP on Spamhaus / optional FireHOL netset | blue-green or wait out the listing depending on which list and severity score |
| Operator workstation compromised | Operator | rotate SSH key + age key + REALITY key + restic password; full credential rotation; `make audit-log` shows every issuance from the compromised workstation |
| Lost SSH access (key deleted) | Operator | see § "Lost SSH access" below |
| Lost SOPS age private key | Operator | see § "Lost age key" below; if Shamir-split (`docs/how-to/age-recovery.md`) or YubiKey-backed (`docs/reference/secrets.md`), reconstruct first |
| Lost Terraform state file | Operator | see § "State loss" below |
| 3x-ui / Marzban / Remnawave panel exposed | Architecture deviation | no public VPN admin panel is permitted; isolate the exposed route and review credentials. The private Kuma panel does not authorize public access |
| Suspected DPI active probing | Threat-model | `make probing-summary` for class breakdown; rerun `make validate-target` for SNI hygiene; consider rotating SNI target; check honeypot textfile metrics |
| DPI rule-set drift suspected | Threat-model | `make tspu-canary` from an in-cohort test client (diff vs yesterday) |
| Access-network allowlist rolled out (only listed destinations reachable) | Threat-model | P3 reachability — automation can't help; switch to another access network or stand up a domestic relay |

## Lost SSH access

First distinguish a lost private key from an unreachable controller network, provider firewall, wrong listener port or unfinished bootstrap. Use read-only checks of the current address, approved image and provider state before choosing a recovery action. Recreating nodes cannot repair the controller's network; avoid consuming repeated VPS and keys while that path is unavailable.

For a disposable node, prefer exact-resource cleanup and fresh provisioning with a reviewed `admin_ssh_public_keys` list. Use `make staging-destroy` and its current manifest for owned disposable staging; permanent-node destruction/replacement must follow the authorized Terraform lifecycle and rollback runbook. Preserve state and evidence, verify provider absence and establish the recreated node's host-key identity independently. Do not bypass `prevent_destroy` or accept a changed SSH key merely because recreation was expected.

Rebuild through [fresh staging deployment](deploy.md#staging-first) or `../tutorials/quickstart.md`: inventory/wait, recovery foundation, positive Tailnet bootstrap, SSH ownership migration and private deploy mappings precede ordinary deployment. Then verify the required protocols and [complete cleanup](deploy.md#acceptance-scope-and-completion). Existing authorization covers bounded retries and replacement nodes within the approved resource/cost limits; ask again only when that scope is exceeded.

If retaining the existing node is required, explicitly choose provider rescue or console recovery within its emergency authorization. Install a reviewed SSH public key through that provider's recovery procedure, retire temporary access, and prove a fresh strictly pinned connection. `make rotate-credentials ANSIBLE_LIMIT=<alias>` acts on one node per run and only rerenders that node's per-device VPN configs; it does not rotate the administrator SSH key.

## Lost age key

The SOPS secrets file is unrecoverable.

If you encrypted to multiple recipients (recommended for teams), use the other operator's age key. `sops` tries each recipient until one succeeds.

> [!WARNING]
> Without another recipient key, Shamir shares or a YubiKey-backed identity, treat the loss as a complete credential leak and rotate everything.

If you didn't, treat this as a **complete credential leak**:

1. Provision a fresh VPS (new IP, ideally different ASN).
2. Generate a new age keypair, fresh REALITY keypair, fresh per-client UUIDs / shortIds / passwords / peer keys, fresh restic password.
3. Distribute new client URIs to every device.
4. Decommission the old VPS once every device has switched.

The encrypted SOPS blob may still be holding valid secrets in storage. age is computationally hard but not future-proof. Don't keep the old blob around.

## State loss

OpenTofu state lives encrypted in the operator's versioned, Object Lock bucket (key layout in the `<provider>.s3.tfbackend` files of the ops repository: `state/<provider>/terraform.tfstate` for `ENV=prod`, `state/workspaces/<ENV>/state/<provider>/terraform.tfstate` for any other environment). Every write keeps the earlier object version for at least the 30-day governance retention. Without readable state:

- `tofu plan` shows everything as "needs creating".
- `tofu destroy` does nothing (no resources to destroy).
- `make rollback-…` blue-green flows still work but become manual (you edit the UpCloud console / API directly).

Break-glass material, all held outside GitHub: the state passphrase (`TF_VAR_state_passphrase`; password manager and the kit document `config/tofu-state-passphrase.sops.json`), the operator state identity (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` of `tofu-state-operator`; password manager and `config/scw-state-operator.sops.json`), and the ops repository backend files. Export them into the shell environment only, for example through `sops exec-env`; never write them to a file.

Recovery path 0 — restore a bucket version after a bad apply (preferred):

```bash
# Lists the versions of the exact state object, newest first (metadata only).
make restore-state PROVIDER=upcloud ENV=prod
# Decrypts the selected version locally, refuses another lineage, and pushes it
# through the backend lock as the next serial. Earlier versions stay retained.
make restore-state PROVIDER=upcloud ENV=prod STATE_VERSION=<version-id>
make PROVIDER=upcloud ENV=prod plan
# Review each proposed change against the actual resources and the chosen recovery point.
```

`ALLOW_LINEAGE_CHANGE=1` replaces state with a version of another lineage (`tofu state push -force`). A forced push skips the serial check, so stop every other writer first, and use it only after confirming that the current state is the wrong one. A writer that died while holding the lock leaves `<state key>.tflock`; after confirming no writer runs, release it with `PROVIDER=upcloud ENV=prod ./scripts/terraform-env.sh force-unlock <lock-id>` using the operator identity (obtain the lock ID from the backend lock record).

Recovery path 1 — the bucket or its versions are lost: create a replacement bucket, point the `<provider>.s3.tfbackend` files of the ops repository at it, then restore the newest `make backup-state` snapshot into an initialized empty workspace. The producer publishes a timestamped name only after encryption completes; its private `.state-backup.*` staging files are not recovery snapshots.

```bash
set -o pipefail
# Snapshots live in ${BACKUP_DEST:-~/.config/vpn-provision/state-backups}/<provider>-<env>-<timestamp>.tfstate.age
# Make reads TF_BACKEND_ROOT and TFVARS_ROOT from the selected ops configuration.
# A change to the backend file selects a new initialization directory.
make PROVIDER=upcloud ENV=prod init
# Direct wrapper calls require TF_BACKEND_ROOT in the environment.
export TF_BACKEND_ROOT="${ops_repo:?set ops_repo to the private ops checkout}/config/backend"
age -d -i <age identity> <snapshot> | PROVIDER=upcloud ENV=prod ./scripts/terraform-env.sh state push -
make PROVIDER=upcloud ENV=prod plan
```

Recovery path 2 — re-import the existing VPS:

```bash
make PROVIDER=upcloud ENV=prod init
export TF_BACKEND_ROOT="${ops_repo:?set ops_repo to the private ops checkout}/config/backend"
export TFVARS_ROOT="${TFVARS_ROOT:?set TFVARS_ROOT to the selected ops tfvars directory}"
tfvars="$(python3 scripts/tofu_tfvars.py upcloud prod)"
PROVIDER=upcloud ENV=prod ./scripts/terraform-env.sh import -var-file="$tfvars" upcloud_server.vpn <SERVER_UUID>
PROVIDER=upcloud ENV=prod ./scripts/terraform-env.sh import -var-file="$tfvars" upcloud_firewall_rules.vpn <SERVER_UUID>
# Review the plan against the resources that you imported.
make PROVIDER=upcloud ENV=prod plan
```

Find `<SERVER_UUID>` in the UpCloud console (server details → "ID").

After restoration, run `make backup-state` so an age snapshot of the restored state exists outside the bucket.

### Backups from before the bootstrap identity guards

Use this procedure for a Hetzner, Vultr or Scaleway backup that contains
`terraform_data.ssh_port` and lacks `terraform_data.admin_user`. On Vultr and
Scaleway, `terraform_data.admin_ssh_public_key` must also be absent. On the
first full plan, OpenTofu can interpret creation of a lifecycle trigger as a
server replacement. Keep `prevent_destroy` enabled.

1. Select the exact backup, provider, environment and tfvars. Compare the
   server ID and account with the operator inventory. Set `admin_ssh_public_keys`
   to the single bootstrap key from the backup. Apply additional keys after recovery. Use a private shell
   with read-only provider credentials and the pinned CLI. Set `PROVIDER`,
   `ENV`, `TFVARS`, `SNAPSHOT`, `AGE_IDENTITY`, `AGE_RECIPIENTS` and
   `RECOVERED_SNAPSHOT`. Use absolute paths. Select a new private output
   file for `RECOVERED_SNAPSHOT`.
2. Restore the backup into a new private directory with a local encrypted
   backend. Keep the terminal free of state and plan JSON.

   ```bash
   set -eu -o pipefail
   umask 077
   repo="$(git rev-parse --show-toplevel)"
   scratch="$(mktemp -d)"
   root="$scratch/terraform/providers/$PROVIDER"
   git -C "$repo" archive HEAD terraform/shared "terraform/providers/$PROVIDER" | tar -x -C "$scratch"
   printf 'terraform {\n  backend "local" {}\n}\n' > "$root/recovery_override.tf"
   phrase="$(openssl rand -hex 32)"
   scratch_tofu() {
     TF_DATA_DIR="$root/.data" TF_WORKSPACE=default TF_VAR_state_passphrase="$phrase" \
       TF_VAR_plan_backend_scope="recovery/$PROVIDER/$ENV" tofu -chdir="$root" "$@"
   }
   scratch_tofu init -input=false -lockfile=readonly
   age -d -i "$AGE_IDENTITY" "$SNAPSHOT" | scratch_tofu state push -
   ```

3. Create and review a plan for only the missing built-in guards. The checker
   compares the proposed inputs with the retained server name, SSH port,
   administrator and public key. It refuses a different identity or any
   additional resource change.

   ```bash
   targets=(-target=terraform_data.admin_user)
   case "$PROVIDER" in
     vultr|scaleway) targets+=(-target=terraform_data.admin_ssh_public_key) ;;
     hetzner) ;;
     *) exit 2 ;;
   esac
   scratch_tofu plan -refresh=false -input=false -var-file="$TFVARS" "${targets[@]}" -out=guards.plan
   scratch_tofu show -json guards.plan | python3 "$repo/scripts/check-bootstrap-guard-plan.py" "$PROVIDER"
   scratch_tofu apply -input=false guards.plan
   scratch_tofu plan -input=false -var-file="$TFVARS"
   ```

4. Review the **full** plan with provider refresh. Verify the retained server
   ID, bootstrap identity and firewall. A legacy Hetzner state can contain
   `hcloud_firewall_attachment.vpn`. Accept its `forget` action only when
   the server retains the same firewall ID in `firewall_ids`. If the plan
   creates, replaces or deletes a server, or changes an SSH key, stop. An
   old Scaleway root disk can differ from the current volume specification.
   Qualify the storage change separately while the server remains protected.
5. With recovery authorization for the same provider, account and environment,
   seal the approved local state, then use recovery path 1 above. Keep the
   original backup. A serial or lineage conflict requires investigation.

   ```bash
   (
     set -eu -o pipefail
     sealed="$(mktemp "$(dirname "$RECOVERED_SNAPSHOT")/.recovered.XXXXXXXX")"
     trap 'rm -f -- "$sealed"' EXIT
     trap 'exit 1' HUP INT TERM
     scratch_tofu state pull | age -R "$AGE_RECIPIENTS" > "$sealed"
     # Link the completed file at the exact destination. An existing name is refused.
     python3 -c 'import os,sys; os.link(sys.argv[1], sys.argv[2])' "$sealed" "$RECOVERED_SNAPSHOT"
   )
   ```

   Run the canonical full plan against the restored backend. Remove the
   private scratch directory after you verify recovery.

## Suspected compromise of the VPS

> [!CAUTION]
> Do not log in to a node that you suspect is compromised. Every observation can let the attacker change or remove evidence.

If you suspect the running VPS has been compromised at the OS level (root escalation, persistent attacker, unknown process):

1. **Do not** SSH in to "look around" — every observation gives the attacker a chance to exfiltrate or alter logs.
2. Power off the VPS via the UpCloud API/console.
3. Snapshot the disk for forensic analysis (UpCloud has a snapshot feature; export to a separate region if you can).
4. Treat every credential the VPS could touch as compromised: REALITY private key, Hysteria server cert, AWG server private key, restic password, every client UUID/password/peer that was on it.
5. Provision a fresh VPS, full credential rotation.
6. Forensic the snapshot offline.

The "disposable nodes" property of this stack means step 5 is fast: it's the same procedure as a normal first-time deploy.

## Kernel or firewall security advisory

Inspect the running kernel separately from installed packages. Record the vendor patch status and the exact mitigation. A disabled MPTCP setting and an early IPv4 TCP-options drop are mitigations, not proof of a patched kernel. The [deployment snapshot](../reference/deployment-status.md#runtime-and-hardening) records the last accepted state and its remaining reboot qualification gap.

Before a firewall service restart or reload, check ownership of the VPN and independent host-guard tables. Preserve foreign tables and timed sets; do not flush the complete ruleset. Verify the effective systemd stop action as well as the rules on disk. Repeat the affected native packet and authenticated VPN checks after an authorized change. Package presence alone is not live protection.

## Verification

Each linked procedure ends in `make verify` for the affected node or in a recreated node that passes the full deploy acceptance.

## Rollback

Recovery procedures are forward-only: recreation, rotation and restore. There is no rollback of an incident response other than completing it.

## Evidence to record

The matrix row, the time of detection, the verb run and its result, and the rotation or recreation that followed. Suspected compromise also records what was rotated and when the old node was destroyed.
