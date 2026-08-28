## Context

The existing liveness installer assumes every proxy profile is emitted for stock
sing-box, while XHTTP is intentionally excluded from that format. A production
Xray XHTTP adapter already exists in `probe-matrix-driver.py`. AWG onboarding
currently resolves a default provider independently of fleet HOSTS, and passes
the private key through environment. Existing inspection surfaces use Ansible,
accept-new SSH keys, or the repair watchdog. See proposal and normative specs.

## Goals / Non-Goals

- Goal: deliver a passive inspector and a working four-profile active sentinel,
  preserving explicit transport identity and evidence boundaries.
- Non-goal: provider firewall changes, SSH migration, new public collectors,
  credentials rotation, automatic repair/promotion, Android integration, or new
  probe-matrix evidence schemas. Offsite storage selection is operator-owned.

## Decisions

- Add `make inspect` with a small Python controller/collector. The controller
  reads the explicit existing inventory without calling Terraform, secrets
  decryption, bootstrap readiness, or fleet-wide Make prerequisites. It requires
  an explicit host subset and uses strict SSH with stdin Python (`-B -S`) rather
  than Ansible or remote upload. Reject unsafe aliases/options and duplicate host
  identities. Use `ssh -F /dev/null`, explicit identity/known_hosts/alias options,
  `IdentitiesOnly=yes`, `ClearAllForwardings=yes`, `PermitLocalCommand=no`,
  `RemoteCommand=none`, no agent forwarding, and no user `ssh -G` discovery.
  This excludes `Match exec`, local commands, and hidden forwarding. Connect
  timeout is 10 seconds, total per-host timeout 30 seconds; no retries or fallback.
- The collector allows only bounded file reads, selected `systemctl show`
  properties, listener metadata, and non-secret manifest/backup marker fields.
  No arbitrary command supplied in config; no root secret content, process argv,
  full environment, journal dump, `restic`, `sshd -t`, or `nginx -t`. Reading the
  result of a previous active check does not rerun it. Versioned JSON uses
  observed/unknown/stale/error fields, timestamps, and categorical errors.
  File reads are no-follow regular-file reads, maximum 64 KiB, with every parent
  owned by root and not group/world writable. Initial allowlist is the node
  manifest, `/var/lib/vpn-backup/restore-drill-last-success.json`, and existing
  backup status metadata only when its exact schema/path is established by
  source. No restic invocation to compensate for absent backup metadata.
  Manifest fields: schema/source revision/deployable digest. Restore fields:
  version/source/snapshot time/verified time; no snapshot ID is necessary.
  Service fields: LoadState, ActiveState, SubState, Result, ExecMainStatus,
  ExecMainExitTimestamp. Listener output is protocol/address/port, no process
  argv. Snapshots older than 36 hours are stale; monthly restore evidence is
  stale after 35 days; future-dated evidence is unknown, including small clock
  skew, as required by REQ-OBS-EVIDENCE. A
  30-second collection is timestamped as observation, never a protocol verdict.
- Keep `make verify` an explicitly active legacy operation and label its
  watchdog effect in help/docs. Do not silently reroute it through inspection or
  change its deployment acceptance meaning. Active liveness and restore remain
  separate commands; only inspection is passive.
- Reuse the narrow Xray VLESS/XHTTP runtime adapter, not the matrix orchestration
  or Rust schema work. Stock sing-box continues to serve REALITY/Hysteria2. Add
  Xray profile/version fields and explicit AWG provider/environment/instance
  fields to the liveness contract and all callers. Validate production XHTTP
  host/path/SNI against named-client source, not research-target secrets.
- In both existing curl builders, put `--disable` first, clear upper/lowercase
  proxy variables, explicitly disable proxy for control, and override noproxy
  for SOCKS. Test with a real loopback HTTP proxy/target and hostile curlrc/env;
  a closed SOCKS listener must fail even when direct control is healthy.
- Materialize secrets once through `decrypt-secrets.sh` into an owned private
  directory; render only the chosen client. AWG key input is stdin/FD, then a
  private file; derive and compare the public key before any remote mutation.
  Refuse revoked clients and registry assignment conflicts. Do not recover a
  missing key by reusing another client or generating a replacement silently.
- Use the current AWG userspace/netns adapter with IPv4 HTTPS on port 443 and a
  fresh handshake; validate this restricted URL contract explicitly. Pin and
  validate both AWG tooling and userspace runtime provenance through the existing
  immutable installer inputs. Broader UDP/IPv6/Android proof is separate work.
- Source provenance has separate fields for controller commit, installed runner
  SHA256, opaque client generation ID, and a digest of public endpoint settings
  with credential fields excluded. Server manifest revision/digest is a separate
  observed field; neither checkout identity nor profile generation implies a
  server deployment. Credential values and hashes of credential material are
  never included in reports.
- Installation uses immutable generation directories containing runner, profiles,
  and metadata, activated by one root-owned `current` symlink rename. A fixed
  no-arguments launcher resolves one generation once, preventing mixed files.
  A root-owned remote flock serializes install and run; an operator lock
  serializes the corresponding registry update. Stage and validate any fixed
  launcher/sudoers migration before activation; preserve their previous contents
  for rollback and keep sudoers limited to the one fixed launcher.
- A bounded remote installer job owns validation, activation, and the initial
  probe independently of the SSH connection. Persist a private pending receipt
  before activation; commit a generation receipt only after the probe passes.
  If the job fails, restore the previous generation and bootstrap files; if
  interrupted beyond normal cleanup, the next installer/run resolves a pending
  receipt by rolling back before it can serve evidence. Lost SSH means unknown
  locally until the exact generation receipt is reread; it never means success.
  Publish the operator registry only after that receipt, so a retry reconciles
  the same committed generation instead of generating new credentials.

## Contracts and ownership

- Primary serialized lane: Makefile, `contract/protocol-liveness.schema.json`,
  `scripts/{install-liveness-sentinel.sh,vpn-protocol-liveness.py,protocol-liveness.py,
  probe-matrix-driver.py}`, inspector implementation, related operator docs.
- Extend existing unit suites for installer, sentinel, evaluator, monitor, and
  matrix driver. New inspector tests have no natural existing passive suite.
- Backup restore cleanup remains confined to the restore-drill template:
  atomically claim a missing private target before arming its cleanup; keep
  ownership of each temporary artifact explicit. Existing target or symlink is
  a failure, not permission to remove prior data. Preserve the existing success
  marker until all restored secrets have been removed.
- Add a dedicated `backup-configure.yml` intent behind `make backup-configure`.
  It never imports `site.yml` or the backup role's main task list. A shared
  configuration slice installs only rclone (`state: present`, no cache refresh
  or upgrades), stages and validates rclone configuration and the two existing
  scripts, then installs them in config/backup-script/drill-script order. The
  normal role uses this same slice; its repository initialization, password,
  units, notifications, and scheduling remain outside the slice.
- Configuration requires clean committed controller source, one explicit exact
  inventory alias (no groups/patterns/exclusions/unknown names), strict canonical
  SOPS plaintext validation, and an existing
  root-owned local repository, password, restic binary, and backup units. Compare
  the supplied restic password with the existing file without exposing it; never
  initialize a repository or overwrite its password. Reject unsafe remote/path
  fields before rendering shell scripts. Do not bypass prechecks or select tags.
  Before claiming the lock, validate decryption with the installed restic's
  `--no-cache --no-lock -r /var/backups/vpn-restic --password-file
  /etc/restic/password cat config` (15-second timeout, stdout/stderr captured
  and discarded). Clear inherited RESTIC_* inputs for this exact local read.
  This is not integrity/restore proof. Controller debug uses Ansible's boolean
  parser: reject true, accept false, and forward `ANSIBLE_DEBUG=false` to prevent
  inherited config-file debug from bypassing private task output.
- Build the controller child environment from an allowlist before checking Git
  cleanliness and deriving source identity; ambient Git routing cannot select a
  different checkout. The dedicated Make goal suppresses early recursive source
  identity exports. Validate one immutable private inventory snapshot with the
  existing selector, then retain only the selected alias and cohort membership.
  Disable automatic vars plugins and load tracked AWG defaults as data, then
  all/vpn/cohort vars explicitly through ordered Ansible include_vars (replace),
  followed by the private SOPS snapshot and validated
  extra-vars. Pin SSH host identity, transport, user, key and port independently of
  ambient config/plugins/callbacks. Approved transport overrides preserve the
  selected host-key alias. This breaks external host_vars and arbitrary inventory
  backup overrides; they are not a supported configuration API for this intent.
  Actual Ansible parity fixtures cover p0, p1p2, fullstack and allowed overrides.
- The owner persistently disables/stops both backup timers and stops services before the configuration
  command and maintains an exclusive maintenance window. Check all four units
  are inactive with no queued jobs and both timers disabled before changes and
  again before/after install. Reject pending, incomplete, or malformed persistent
  recovery bundles before claiming a new lock, including after reboot clears
  `/run`. This prevents automatic timer execution, not power-loss atomicity of
  three distinct file replacements.
  An owned, private per-host directory lock serializes configuration invocations;
  an existing or stale lock fails closed, without automatic removal. Normal
  failure cleans only the invocation's staging and lock. No masks, drop-ins,
  daemon reloads, start/stop/restart, backup, prune, sync, or restore are invoked.
  The canonical automatic triggers are these timers; concurrent privileged
  manual starts or another deploy are outside this exclusive-window guarantee.
- Stage every candidate and validate it before replacing any live file. Preserve
  existing bytes, modes, and absence in a private recovery directory before
  atomic per-file writes. Any publication or postcheck failure rolls back all
  three paths. If rollback cannot be confirmed, retain the recovery bundle and
  lock, fail explicitly, and require the owner to keep timers stopped until
  repair. Never implicitly execute or delete pre-existing recovery resources.
  Configuration reports its narrow result, not full deployment parity, backup
  freshness, or offsite proof; do not rewrite the node's whole-site manifest or
  require the new controller digest to equal that historical manifest.
- No Terraform root, secrets schema, vpnd public CLI, retention, or sandbox
  changes. Destination selection and actual first copy/isolated restore remain
  separately authorized owner operations. Existing rclone dependency is reused.

## Risks / Trade-offs

- Passive SSH still causes authentication/accounting side effects. Promise no
  explicit managed-state mutations, not zero kernel or audit writes.
- Unit stubs cannot prove protocol compatibility. Require real pinned parser
  checks and external traffic; report blocked prerequisites without closure.
- Current client sentinel may be offline; an ordinary external VPS cannot prove
  a filtered user path. Record the actual vantage and preserve that distinction.
- Restores can write repository locks and local temporary files. Passive
  inspection reads markers only; isolated restore is separately authorized and
  must never run the full backup script, whose retention path prunes snapshots.
- Existing restore cleanup installs its trap before checking the target is
  absent. No operational restore may run over a pre-existing target. This issue
  is fixed by the bounded backup cleanup slice in this change.

## Migration Plan

1. Extend tests first: bypass controls, real emitter/runtime seam, scoped SSH,
   malformed/stale evidence, key mismatch/revocation, timeout and cleanup paths.
2. Implement passive inspection and compatible XHTTP/client onboarding. Candidate
   installation uses a private staging directory, validates permissions and all
   runtime profiles, then publishes the complete set with rollback metadata.
   Preserve existing assignment until the first authenticated probe succeeds.
3. Update schema/examples/callers together. Reject old ambiguous fullstack config
   with migration guidance; do not maintain an alternate unsafe legacy branch.
4. Run targeted tests, `make validate`, `make ci-fast`, independent review, then
   exact runtime parser checks. Heavy suites run through `build-gate --`.
5. With reachable approved sentinel and dedicated material, run one external
   four-profile probe without scheduling or production repair. Capture redacted
   source/runtime/path evidence; leave missing transport acceptance open.
6. If installation or its initial probe fails, restore the complete previous
   sentinel files and assignment; clean only this attempt's temporary resources.
   Removing the new inspector is local rollback, never a production network change.
