# Device migration during server replacement

`make device-migration` prepares device credentials on a separate replacement,
updates every discovered active subscription URL and resumes interrupted
publication. It keeps the source credentials and requires evidence from each
device before `ready` permits retirement. It does not destroy a server, move DNS
or automatically contact clients.

## Supported inputs

Read `LOCAL-OPERATOR-KIT.md` before selecting private authority. Use a clean,
reviewed checkout and two separate owner-only SOPS documents: the existing
source and a valid replacement with its own server keys and certificates.
The replacement may not yet be converged when `prepare` runs. Its inventory
identity, provider/environment selector and cohort must already be exact.
One provider/environment selector must identify one inventory alias.

The source publisher must expose `migration-publisher-v1`. Update the
subscription-host role through the normal deployment workflow first if needed.
Supported publications are atomic subscription documents with sing-box or RIPDPI
payloads. A legacy-only publication, active mirror generation, unavailable
delivery identity or changed authority refuses migration. Reissue legacy
deliveries through the ordinary issuer before preparing the replacement.
Static exports without an active subscription are explicitly excluded; arrange
their delivery separately and do not treat them as migrated by this workflow.

Device protocol credentials remain the same on the replacement. AWG retains the
device keypair and PSK, allocates addresses from the target instance, and keeps
the replacement server key. Enabled transport coverage cannot decrease.
Alternate nodes retain their selected sources. Every active URL for a device is
rendered from its current registry selection while retaining that URL's format
and expiry; the review explicitly reports this normalization.

The publisher can remain on a separate surviving host or move to a replacement
that serves the same TLS origin and namespace. When moving, all other active
subscription documents are copied unchanged. Active bootstrap grants block a
publisher move: consume or retire them through their own reviewed lifecycle.
Bootstrap consumption authority is never copied or reset by migration.

## Private plan

Store the JSON plan as an owner-only `0600` file in a private directory. All input
paths must be absolute, canonical, and contain only letters, digits, `_`, `-`,
`.` and `/`. Replace the illustrative path prefix below with your checkout.
The source and target files must be distinct regular files, including by inode.

```json
{
  "schema_version": 1,
  "id": "11111111-1111-4111-8111-111111111111",
  "inventory": "/ABSOLUTE_CHECKOUT/ansible/inventory/generated.ini",
  "known_hosts": "/ABSOLUTE_CHECKOUT/secrets/local/known_hosts",
  "source": {
    "host": "upcloud:prod",
    "alias": "vpn-blue",
    "cohort": "device-full-tailnet",
    "secrets_file": "/ABSOLUTE_CHECKOUT/secrets/local/blue.sops.yaml"
  },
  "target": {
    "host": "upcloud:green",
    "alias": "vpn-green",
    "cohort": "device-full-tailnet",
    "secrets_file": "/ABSOLUTE_CHECKOUT/secrets/local/green.sops.yaml",
    "awg_instances": {"awg0": "awg0"}
  },
  "publication": {
    "source_alias": "delivery",
    "target_alias": "delivery",
    "directory": "/var/lib/vpn-subscription",
    "origin": "https://delivery.example:8444"
  }
}
```

Generate a fresh migration UUID for each replacement. `awg_instances` maps source
instance names to existing target instance names; an omitted mapping retains the
same instance name. The target publisher cannot be the retiring source alias.
The selected known-hosts file and inventory transport parameters bind SSH to the
reviewed hosts. Changing them after preparation requires reconciliation, not
reuse of the prior approval.

## Review, prepare and publish

The following commands use the canonical Make entry point. These are authorized
operator actions: even `plan` reads encrypted authority and contacts the source
publisher. It does not change credentials or remote publication. The local
migration lock serializes runs against the same source.

```bash
export DEVICE_MIGRATION_PLAN="$PWD/secrets/local/migration.json"
make device-migration ACTION=plan
# Review devices, exclusions, all active grants and publisher movement.
make device-migration ACTION=prepare DEVICE_MIGRATION_APPROVAL=<reviewed-digest>
make device-migration ACTION=status
```

`prepare` commits an encrypted intent in the source SOPS document, then prepares
the target credentials. Resume with the same plan and approval after a lost
acknowledgement; it recognizes exact committed state without allocating new
peers or delivery challenges. The journal contains payloads and receipt keys
and stays encrypted. Do not copy decrypted journal contents into reports.

Converge the replacement through the canonical fresh-node ownership, dry-run
and deployment gates using its separate SOPS document. Then publish:

```bash
make device-migration ACTION=publish
```

Publication first runs exact-target `verify` and `smoke-test`, using a temporary
private plaintext projection that is removed on exit. It tests each publisher's
TLS origin and `/sub/` route with a random credential-free, five-minute canary.
Canary creation and cleanup use the same compare-and-swap protocol. No bearer
token enters command arguments or public diagnostics. Failed cleanup refuses
the phase; a process death leaves only an expiring canary.

Every update compares the current document to its recorded predecessor and
preserves the URL and expiry. Resume accepts an already committed identical
document; competing publication or revocation refuses. Source and target
registries advance only after all publications have been re-read successfully.
Repeated `publish` rechecks current authority and target health.

## Device evidence and retirement

RIPDPI imports the exact delivered bundle and records `received` only after its
relay and AWG imports commit. On the device, run the migration path check using
an explicitly selected target and HTTP(S) probe URL, then export the receipt.
Relay checks use the selected replacement transport. AWG checks require the
matching new profile to be active and verify the actual consumed configuration.
The receipt is an explicit file export; no mandatory telemetry endpoint exists.

```bash
make device-migration ACTION=receipt MIGRATION_RECEIPT=<absolute-private-receipt.json>
make device-migration ACTION=status
```

Receipt authentication binds the migration, delivery, exact raw payload digest,
timestamps and tested target. It proves possession of the delivered challenge,
not hardware attestation or protection against a compromised device. A received
receipt alone cannot permit retirement. A successful path test must be within
24 hours and from a current active delivery for that device.

Official sing-box clients retain their ordinary payload format. After manually
verifying the new path on that exact device, record explicit evidence:

```bash
make device-migration ACTION=attest MIGRATION_CLIENT=<device> \
  MIGRATION_REASON='Verified the replacement endpoint on this device'
```

This records `operator-confirmed`, separately from a client-authenticated test.
It is bound to the current migration generation and also expires after 24 hours.
RIPDPI deliveries require their authenticated receipt and cannot use this path.

When the publisher moves, change DNS separately through the reviewed workflow.
For both moved and unchanged publishers, the origin must resolve only to the
admitted target publisher address before retirement.

```bash
make device-migration ACTION=ready
```

`ready` rechecks inputs, target traffic, publication routes, exact documents,
current grants, public origin DNS, and per-device evidence. A new grant,
expired/revoked grant, changed private input or missing device proof refuses.
Success permits the separate reviewed drain/retirement operation; this command
does not perform it. Keep the target environment selector and tfvars path stable:
they are now part of delivered device bindings.

## Resume and rollback

Use `status` and repeat the failed phase with the same private plan. Do not edit
phase flags, delete the encrypted journal, or reissue affected URLs during an
unfinished transaction. A conflict must be reconciled against actual authority.

```bash
make device-migration ACTION=rollback
```

Rollback restores only journal-owned exact publication and registry changes.
It removes a copied target document only if it was absent before and still has
the expected bytes. Pre-existing unrelated documents remain. Target protocol
credentials remain available; removing them is a separate revocation action.
Rollback neither changes DNS nor destroys either node. If DNS moved, restore the
source route through its own reviewed operation before withdrawing the target.
When an affected grant expires or is revoked, automatic rollback refuses to
revive it.

## Blue-green and fleet rotation

`make blue-green` requires `GREEN_SOPS_FILE` and `DEVICE_MIGRATION_PLAN` in
addition to the exact source/target environments and cohorts. It reviews and
prepares migration after replacement ownership, converges the prepared target,
publishes after health checks, and requires `ready` before drain guidance.
`DEVICE_MIGRATION_APPROVAL` may contain the exact previously reviewed digest;
otherwise the operator enters it at the review boundary. Keep both nodes when
the device evidence is incomplete, and continue using the standalone commands.
The pair renderer retains admitted unrelated publisher and alternate rows,
including their SSH transport and cohort membership. Inventory-wide SSH
authority must remain unchanged. For a topology-wide observability generation,
render the complete topology through its owner and use standalone migration;
blue-green refuses pair-only rendering before provisioning in that case.

Fleet rotation plans supply `green_sops_file`, `migration_plan` and
`migration_approval` per entry. The fleet controller still retains an uncertain
in-flight operation for explicit reconciliation instead of replaying it.

Local encrypted-transaction and HTTP/TLS tests establish orchestration,
publication, receipt and recovery behavior. They do not establish a live fleet,
physical device or production DNS acceptance result.
