# Change: Client configuration registry and issuance-option persistence

Task ID: `SEC-1787489155988233`

## Why

The 2026-08-23 full-fleet recreation exposed three accounting failures in the
client-configuration workflow:

1. **No device roster.** After the fleet IPs changed, there was no record of
   which configuration (format, hosts, cohorts, token) had been issued to
   which device. Every distributed artifact went stale silently and the only
   recovery was a manual, per-device audit.
2. **AWG client private keys existed only as local plaintext files** under
   `secrets/local/clients/**`, outside SOPS, despite the SOPS file already
   holding strictly more sensitive material (server REALITY private key,
   provider credentials). Deleting the local artifacts permanently destroyed
   the keys while SOPS retained now-orphaned public peer entries.
3. **Token refresh drops issuance options.** `issue-sub-token.sh
   --refresh-token` reuses only the bearer token; `FORMAT`, `PROVIDER/ENV`,
   and the emitter environment (`HOSTS`/`COHORTS`/`SOPS_FILES`) reset to
   defaults, so a bare refresh silently overwrites a multi-host or ripdpi
   subscription with a wrong single-host payload. The audit log records only
   format/expiry — not enough to reconstruct the original invocation.

The invariant this change establishes: **distributed artifacts are never the
record — issuance parameters are.** Anything delivered to a device must be
reproducible from git + SOPS + Terraform outputs plus persisted issuance
options.

## What Changes

- Add an encrypted per-device registry (`clients` registry section in the
  SOPS secrets document) recording, for each device: formats issued, hosts,
  cohorts, token hash prefix, expiry, AWG public-key fingerprints, issuance
  date, and lifecycle status (`issued → delivered → active → stale | revoked
  | burned`).
- BREAKING: `scripts/new-client.sh` now writes AWG **private** client keys
  into the SOPS secrets document at generation time. The
  "never-in-SOPS" clause of the RIPDPI bundle private-key handoff contract is
  replaced by "device-local key remains primary; SOPS copy is the recovery
  path". Local plaintext artifacts become disposable caches that must be
  shredded after delivery.
- BREAKING: `scripts/issue-sub-token.sh --refresh-token` no longer accepts
  implicit defaults for refreshes of existing tokens; it reads the original
  issuance options from the registry and requires explicit confirmation when
  the operator overrides any of them.
- Add `make client-drift CLIENT=<name>`: re-renders the payload for a device
  from current git + SOPS + Terraform outputs and compares it with the last
  delivered payload identity (embedded source-identity hash + outputs hash),
  reporting stale devices instead of requiring stored file copies.
- Extend the secrets coverage check to require registry fields for every
  client entry.

## Capabilities

### New Capabilities

- `clients/config-registry`: encrypted per-device registry of issuance
  parameters and lifecycle state; refresh reads options from it; drift check
  detects devices whose delivered payload no longer matches a fresh render.

### Modified Capabilities

- None (no main specs exist yet for client provisioning; the bundle handoff
  contract change is documented under `docs/RIPDPI-BUNDLE.md` in tasks).

## Impact

- **Secrets layer**: schema addition (`clients[*].registry`) +
  `secrets/schema.json` + `scripts/check-secrets-coverage.py`; private-key
  storage policy reversal must be reflected in `docs/RIPDPI-BUNDLE.md`,
  `docs/SECRETS.md`.
- **Scripts**: `new-client.sh`, `issue-sub-token.sh` (option persistence),
  new `client-drift.sh`; audit-log note format extended.
- **Makefile**: new `client-drift` target wired into operator surface.
- **vpnd**: unaffected (reads tokens via existing scripts).
- No server-side changes: delivery host keeps storing hashed payloads +
  `.meta` sidecars only; the registry lives in the operator SOPS document.
