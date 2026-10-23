# Issue, refresh or revoke a device

> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-10-22

## Purpose and scope

Use one private operation manifest to issue a device, refresh every active
subscription, or revoke its credentials across the complete declared fleet.
The controller preserves unrelated devices and server identities. It does not
provision nodes or change provider resources.

Issuance creates device credentials only for the selected enabled transports.
The private recipient artifact contains the subscription URL, rendered profile,
AWG configurations with the device private key, and any Naive URI. Refresh keeps
each existing URL, format and expiry. Revocation removes matching credentials
from all declared authorities, including disabled variants and former migration
sources. It also revokes all discovered subscription grants.

## Preconditions

Use a clean committed checkout with its pinned toolchain. Each inventory VPN
node must have one distinct encrypted SOPS document. Supply the complete strict
inventory and pinned SSH host keys. Every configured or retained subscription publisher must
appear in the manifest and support the migration publisher protocol. Drain
active single-use bootstrap grants first. Reconcile an unexpected retained
publisher before starting a device operation.

Read the local operator kit contract before collecting private inputs. Keep the
manifest and encrypted documents owner-only. The new recipient artifact must
have an unused path in a directory with mode `0700`. The controller refuses to
overwrite it. An exact-byte artifact from the same operation can be resumed.

Prepare a JSON manifest with these exact fields. Do not commit its values.

| Field | Required content |
|---|---|
| `schema_version`, `id` | Version `1` and a new lowercase operation UUID |
| `action`, `device` | `issue`, `refresh` or `revoke`, and the exact device name |
| `inventory`, `known_hosts` | Absolute private input paths |
| `journal_host` | One declared provider/environment host identity |
| `nodes` | Every inventory VPN node: `host`, `alias`, `cohort`, `secrets_file`, `awg_instance`, `xray_cohorts` |
| `publishers` | Every publisher: `host`, `directory`, HTTPS `origin` |
| `delivery` | For issue/refresh: `hosts`, `awg_host`, `format`, `expires`, `output`; for revoke: `null` |
| `probe` | Controlled HTTPS `url`, expected 2xx `status`, exact `body_sha256`, and `timeout_seconds` from 1 to 30 |

Use `null` for an unused `awg_instance`; use an empty list for absent named
Xray cohorts. Select memberships explicitly when named cohorts exist. Delivery
format is `ripdpi`, `singbox`, or `native`. Native delivery supports AWG/Naive-only
cohorts and writes official-client configurations without a subscription URL.
It requires an empty expiry and a private output path for both issue and refresh.
The publisher list may be empty when the fleet has no configured publishers. Select the AWG host explicitly for multi-host
AWG delivery. Empty expiry means no expiry; otherwise use a date or RFC 3339
instant. Refresh preserves each grant's own expiry. For subscription refresh, `output` must be `null`.

The probe origin must serve stable bytes and be reachable through each selected
transport. Managed nodes need their canonical protocol binaries. AWG probing
uses an owned network namespace and requires its canonical toolchain and TUN.
A missing tool, unavailable node or failed cleanup leaves the operation pending.

## Authorization

Obtain approval for the exact device, fleet nodes, publishers, credential action
and recipient delivery. A source PR does not authorize these live steps. The
preview digest binds the source revision, manifest, authority fingerprints and
publisher snapshots. Review it again if those inputs change.

## Steps

1. Set `DEVICE_MANIFEST` to the private manifest path and inspect the operation:

   ```bash
   make device-lifecycle ACTION=plan DEVICE_MANIFEST="$DEVICE_MANIFEST"
   ```

2. Review the device, affected protocol categories, publisher counts and source
   identity. Set `DEVICE_APPROVAL` to the returned approval digest, then prepare
   the encrypted intent:

   ```bash
   make device-lifecycle ACTION=prepare DEVICE_MANIFEST="$DEVICE_MANIFEST" DEVICE_APPROVAL="$DEVICE_APPROVAL"
   ```

3. Apply and verify the exact prepared operation:

   ```bash
   make device-lifecycle ACTION=run DEVICE_MANIFEST="$DEVICE_MANIFEST"
   ```

4. After an interruption, retain the same manifest and source checkout:

   ```bash
   make device-lifecycle ACTION=resume DEVICE_MANIFEST="$DEVICE_MANIFEST"
   ```

5. Inspect recorded progress without claiming a new runtime observation:

   ```bash
   make device-lifecycle ACTION=status DEVICE_MANIFEST="$DEVICE_MANIFEST"
   ```

## Verification

Completion requires exact encrypted postimages, canonical runtime adoption and
fresh native access checks. Issuance and refresh require authenticated traffic.
Revocation requires absent runtime credentials plus rejected old authenticated
traffic, a healthy independent HTTPS control and confirmed probe cleanup.
A timeout or a generic connected state is insufficient.
Revocation reconciles every declared runtime even when its source document no
longer has a device row. If only published grants remain after prior cleanup,
it still revokes them and verifies canonical runtime state on every node.
`native_credential_profiles` reports the number of retained credential profiles
available for native checks; zero does not claim an old-key traffic probe.

The publisher check first serves an owned private canary through the exact TLS
origin. Revocation then adds its hash through the canonical authority and must
make the running HTTP route reject it. Snapshot flags alone cannot complete
revocation. The canary contains no VPN access credentials; its revoked hash and
private encrypted intent remain available for reconciliation. The owned canary
document is removed with an exact-byte compare-and-swap after denial is proven;
its revocation tombstone remains. A retained publisher can be declared after
its cohort disables subscription hosting. Revocation updates its existing
authority without installing or starting a listener. It must still pass the
positive and negative TLS checks.

`complete` records the finished operation. Running or resuming it again repeats
runtime and native checks. `status` reports stored evidence only. Server-side
native checks do not prove delivery to a physical device or reachability from
its access network. Deliver the private artifact through the approved channel
and record any separately requested device acceptance.

## Rollback

Do not restore revoked credentials automatically. A failed or interrupted action
retains encrypted intent and completed per-node steps. The runtime barrier binds
the operation UUID and immutable intent digest, quiesces a failed candidate and
forbids compensation to credentials removed by an accepted revocation. Resume the same operation
after resolving the reported boundary. Do not delete its journal to regenerate
keys or tokens. An input conflict requires explicit reconciliation. A separate
new issuance is a new authorized action.

## Evidence to record

Record the operation UUID, action, source revision, categorical phase and check
outcomes. Keep manifest contents, subscription URLs, tokens, passwords, private
keys, payloads and raw command diagnostics out of public records. Never mark a
partial or unavailable-node result as complete.
