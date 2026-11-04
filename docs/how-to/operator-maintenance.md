# Operator maintenance

> **Status:** Current · **Type:** how-to · **Tier:** — · **Reviewed:** 2026-11-03

Use this guide after an interruption, before a component update, or when checking
private diagnostics and recovery material. The Make targets below read one
explicit private JSON plan. They do not load `.fleet.mk`, inventory or secrets
implicitly. They do not replace the canonical deployment transaction.

For a resumable existing-node transaction, use
[fleet maintenance](fleet-maintenance.md#prepare-an-existing-node-operation).
For a complete-kit backup, use its
[operator-kit commands](fleet-maintenance.md#seal-and-verify-the-operator-kit).
The selected-file commands below retain their narrower coverage.

## Continue after an interruption

1. Run workspace discovery. Find the checkout that owns the selected Terraform
   environment state; a convenient source worktree is not automatically its owner.
2. Read the private kit's current catalog and the relevant latest receipts. Select
   the active inventory, SOPS input, profile, SSH identity and reviewed host pins.
   Keep old candidates and failed attempts as history, not active authority.
3. Resolve each changed component's accepted source and digest. VPN core, agents,
   collector, observer application and host policy can have different revisions.
   A later `main` commit does not imply a later deployment.
4. Inspect any pending deployment, ingress, recovery or publication journal before
   retrying. After a disconnect, determine whether the operation failed, completed
   or remains active. Do not rerun an uncertain mutation or delete its journal.
   Follow the corresponding recovery branch in [deploy](deploy.md).
5. Reuse explicit authorization within its action, resource, cost and time bounds.
   A standing authorization for related PRs does not require another identical
   question. Expired grants, a new target, broader access or unapproved replacement
   need a new decision. A changing address is covered only by a still-valid exact
   rotation grant; it never authorizes broad subnets. Record grants in the existing
   private catalog/receipts, not a competing authorization ledger.
6. Reuse checks whose inputs and required freshness have not changed. Run the
   missing checks for the selected capability. Keep local, hosted, host, protocol,
   physical-client and human-notification results separate.

Select panel-only or Telegram monitoring explicitly. The accepted panel-only
mode has N node monitors and one pipeline monitor. It has no bot, delivery
monitor or human-notification gate. Use [current monitoring operations](../reference/observability-operations.md),
not a historical rollout hold.

## Private plans and authorization

Read [the local kit contract](local-operator-kit.md). Plans are owner-controlled
mode-0600 regular files. Keep paths and references private. Do not put passwords,
tokens or private key values in argv or Make assignments. Durable secrets remain
in their existing encrypted authority. The commands do not issue or rotate keys.

Export `OPERATOR_MAINTENANCE_PLAN` with the selected plan path. Run one goal at a
time. Clear inherited Make input before it can be parsed:

```bash
env -u MAKEFILES -u MAKEFLAGS -u GNUMAKEFLAGS -u MFLAGS make operator-release-check
```

Set `OPERATOR_CONFIRM_COMMAND=1` only for an already approved diagnostic command.
Set `OPERATOR_CONFIRM_OFFSITE_READ=1` only for an approved B2 read. These flags
record caller intent; they do not grant missing deployment or provider authority.
The source tests use generated test identities and an isolated transport boundary;
they do not access the production service.

## Check a release bundle

`operator-release-check` accepts this plan shape:

```json
{
  "schema_version": 1,
  "releases": [{
    "source": "/private/operator/component-vars.yaml",
    "source_sha256": "<reviewed source SHA256>",
    "pointer": "/observability_control_plane/prometheus",
    "archives": {"amd64": "/private/operator/prometheus.tar.gz"}
  }]
}
```

The source is the actual private prepared JSON/YAML component profile. Its
selected mapping supplies `version`, `urls`, `sha256`, `archive_members`, and
all additional `*_archive_members` maps, such as `promtool_archive_members`.
The checker derives every selected member from this authority instead of
accepting a competing hand-written list. The reviewed source hash must match.
Each selected archive architecture (`amd64` or `arm64`) needs values in every
map. The version must match a complete HTTPS URL path segment (an optional leading
`v` is allowed). A longer or prerelease segment does not match; filename-only
version URLs are outside this check contract.

Tar, gzip-compressed tar and zip are supported. The checker verifies archive
checksum, safe regular selected members and bounded expanded size without
extracting files. A correct archive with stale member paths in the prepared
profile fails before installation. This does not qualify binary version or
architecture at runtime; retain native parsing and deployment acceptance.

An optional `apt` object has exactly `package`, `version`, and `preference` (the
selected preference-file path). On the selected Linux host, it compares the real
`dpkg-query` result, APT Installed/Candidate versions and the version preference
with priority 1001. It does not install packages or refresh APT metadata. A stale
bootstrap pin can propose a downgrade even while the new daemon is running.
Changing a package requires updating and checking both states. An APT-only
plan can contain `schema_version` and `apt` without `releases`; it checks no
archive. A supplied `releases` list must remain nonempty.

## Capture encrypted diagnostics

`operator-diagnostics` accepts `schema_version: 1`, `argv` (an argument array),
`recipient` (public age recipient), `output` (a new ciphertext path), `timeout`
(1–3600 seconds), and `max_bytes` (1–16777216 combined stdout/stderr bytes).
Optional `input_file` selects private stdin, at most 4 MiB. Optional
`environment_names` selects existing environment variables by name; values stay
out of the plan and argv. The LD, DYLD, PYTHON and GIT variable families and selected shell/Make
loader variables are refused.

The output directory must be owned mode 0700; output must not exist. Recipient
and destination admission precede the selected command. Capture uses a fresh
owned process group. It encrypts stdout, stderr, the actual child exit code and
capture status directly from memory. It never creates a plaintext log.

A complete child failure returns its exit code. A signal exit uses 128 plus the
signal. Timeout returns 124, output limit or incomplete stdin 125, and SIGINT/SIGTERM/SIGHUP cancellation
130. These incomplete captures retain partial encrypted bytes and their actual
child status. Encryption, publication or cleanup failure returns a wrapper
failure; it cannot turn child success into accepted diagnostics. SIGKILL of the
capture controller cannot guarantee a final artifact. Reconcile the selected
operation before retrying. Only run trusted foreground commands; this tool is
not a sandbox for commands that deliberately escape their process group.

## Check, seal and verify selected recovery material

The three kit goals use the same private plan:

```json
{
  "schema_version": 1,
  "catalog": "/private/operator/catalog.json",
  "observed_at": "<actual timezone-aware observation time>",
  "max_age_seconds": 3600,
  "entries": [{
    "name": "config/active.sops.yaml",
    "pointer": "/active/configuration",
    "kind": "secrets",
    "sha256": "<reviewed current file SHA256>"
  }],
  "backup": {
    "ciphertext": "/private/operator/recovery/selected-kit.tar.age",
    "recipient": "<approved public age recipient>"
  }
}
```

Each JSON pointer selects an existing string path in the current catalog. Relative
paths resolve from its directory. Entry names are unique safe archive names;
`kind` is `configuration`, `secrets`, `state`, `receipt` or `source`. Include all
material in the intended scope, including required encrypted state and source
recovery. Results report selected coverage, not completeness of an arbitrary
catalog. A fresh plan timestamp does not refresh the underlying host observations.

- `operator-kit-check` checks references, selected hashes, authority and freshness.
- `operator-kit-seal` publishes a new age-armored tar with every selected file and
  `manifest.json`. It revalidates sources before publication and reports the
  ciphertext SHA256. Keep prior archives. This does not upload anything.
- `operator-kit-verify-backup` reads the exact B2 object with checksum-pinned
  rclone, compares ciphertext, decrypts in memory and verifies all members and
  their manifest against current selected material. It revalidates authority
  before success. It does not check bucket privacy or fresh service health.

For verification, add `identity` (private age identity path), `sha256` (the sealed
ciphertext checksum), `bucket`, `object`, `rclone` (absolute reviewed executable
path), and `rclone_sha256` to `backup`. Supply only the selected B2 credentials
through `RCLONE_B2_ACCOUNT` and `RCLONE_B2_KEY` from the approved loader. Rclone
uses the B2 backend and no ambient config file. Age receives no cloud credentials.

The format is bounded to 256 MiB of decoded tar and 10000 selected files. Selected
files must remain private regular files with one link. Working age/OpenSSH
identities and the output archive must not be selected. Do not include the plan
whose checksum will be updated, or the acknowledgement written after verification,
in the payload it describes. Existing differently formatted backups remain intact;
use their recorded verifier rather than silently accepting another format.

Record ciphertext checksum, selected scope, time and result in the private catalog
after publication/verification. Keep this acknowledgement separate from its
snapshot. For actual host or physical-client acceptance follow [deploy](deploy.md)
and [the scoped completion boundary](deploy.md#acceptance-scope-and-completion).
