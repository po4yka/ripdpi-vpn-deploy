# Design — client-config-registry

## Affected layers

| Layer | Owned paths | Change |
|---|---|---|
| Secrets (SOPS+age) | `secrets/schema.json`, `secrets/prod.secrets.example.yaml`, `scripts/check-secrets-coverage.py`, `scripts/validate-secrets.py` | New `clients[*].registry` block; new per-device AWG private-key field; coverage rules |
| Scripts | `scripts/new-client.sh`, `scripts/issue-sub-token.sh`, `scripts/emit-singbox.sh` / `scripts/emit-bundle.sh` (identity embedding), new `scripts/client-drift.py` | Registry reads/writes under the existing SOPS lock; refresh option resolution; drift check |
| Makefile | `client-drift` target, `clean` guidance | Operator surface |
| Docs | `docs/RIPDPI-BUNDLE.md` (private-key handoff contract), `docs/SECRETS.md` (what's in the file), `docs/SUBSCRIPTION-PLANE.md` (rotation item) | Contract reversal + registry description |
| Ansible | None | Delivery host unchanged: still stores hashed payloads + `.meta` sidecars only |

No Terraform, cloud-init, or role changes. vpnd is untouched (it shells out to
the same scripts).

## Key decisions

### 1. Registry lives in the SOPS document, not a separate file

The registry contains token hash prefixes, key fingerprints, and (decision 2)
device private keys — all secret-adjacent. A second SOPS file would add a
second key-custody problem for no isolation benefit: the main file already
holds the REALITY server private key. One document, one custody story,
existing lock (`*.new-client.lock`) and decrypt/shred cycle reused.

Schema shape (inside each existing `clients[*]` entry):

```yaml
clients:
  phone:
    registry:
      status: active          # issued|delivered|active|stale|revoked|burned
      issued_at: "2026-08-23T12:00:00Z"
      formats: [ripdpi]
      hosts: ["upcloud:prod", "scaleway:prod"]
      cohorts: ["p0-minimal", "edge-full"]   # may be empty
      token_hash_prefix: "9f86d081"          # first 8 hex of sha256(token)
      token_expires: "2026-12-31"
      awg_public_key_fingerprint: "sha256:…"
      last_payload_identity:
        source: "<deploy-source-identity hash>"
        outputs: "<sha256 of relevant terraform outputs>"
```

Full token hashes are NOT stored (the delivery host already holds them);
prefixes are enough for correlation with audit logs and `sub-reads`.

### 2. Private-key policy reversal (BREAKING)

Current contract (RIPDPI-BUNDLE.md): client AWG private key is never in SOPS;
out-of-band handoff only. The 2026-08-23 artifact deletion destroyed keys
permanently while SOPS kept orphaned public peers — unacceptable recovery
semantics for disposable-node infrastructure where regeneration churns peer
lists.

New contract: device-local storage stays primary; `new-client.sh` writes the
private key into `clients[<name>].awg_private_key` at generation time; local
plaintext artifacts are explicitly disposable caches shredded after delivery.
Distribution format does not change — bundles keep
`private_key_placeholder: true` and the out-of-band QR/Signal channel remains
the delivery path. The RIPDPI client contract states are unaffected.

Migration: existing devices with lost keys cannot be recovered (accepted —
that loss motivated this change); their stale public peer entries are removed
and peers re-provisioned on next onboarding.

Rollback: revert scripts + schema; registry fields in an already-extended
SOPS document are inert data for old scripts.

### 3. Refresh resolves options from the registry

`issue-sub-token.sh --refresh-token <token>`:

1. Look up the registry entry by re-hashing the token and matching the stored
   prefix; miss ⇒ fail closed (exit non-zero, no payload written).
2. Load options from the entry; explicit CLI/env overrides win and are echoed
   before any write.
3. After successful upload, update the entry (status, expiry, options if
   overridden) and append an audit note listing reused vs overridden options.

First issuance (`new-client.sh` path or bare issue) creates the entry, so
every refresh-capable token has a record by construction. Tokens issued
before this change have no entry: their first refresh fails closed with a
message directing the operator to re-issue (acceptable — all pre-recreation
tokens are dead anyway).

### 4. Drift check = identity comparison, not file diff

As implemented, the identity is computed at delivery time by
`scripts/client-drift.py --print-identity` and recorded by
`issue-sub-token.sh` in `registry.last_payload_identity`:

- `source`: `deploy-source-identity.sh --digest` (git blob IDs over
  `ansible/`, `scripts/`, `requirements.yml`);
- `outputs`: sha256 over the endpoint outputs (`server_ipv4`,
  `admin_user`, `server_hostname`) of every host pair in the entry.

The emitters are NOT modified. An earlier draft considered embedding an
identity line into emitted payloads, but standard sing-box payloads must pass
the pinned upstream parser, so foreign top-level keys are off-limits;
computing the identity outside the payload keeps both formats untouched.
`scripts/client-drift.py CLIENT=<name>`:

- reads the registry entry,
- recomputes both digests from current inputs,
- prints `current` / `stale (+changed component)` / `unknown`,
- exit codes: 0 current, 1 stale, 2 unknown/missing entry.

No delivered file is required locally — the identity recorded in the
encrypted registry is the reference point.

## External effects

- Audit log note format gains `options=reused|overridden:<fields>`; consumers
  parsing notes must tolerate the new field (append-only JSONL note string).
- `sub-reads` forensics can now correlate read-log hash prefixes with
  registry prefixes.

## Validation strategy

- Unit tests: schema/coverage checks (missing-field failure names device),
  refresh option-resolution matrix (registered/unregistered, override/no
  override), drift-check verdicts on synthetic identities.
- Snapshot tests: registry YAML rendering for a fixture client.
- Gates: `make ci-fast` plus targeted pytest; shellcheck on modified scripts.
- Live acceptance (deferred to apply phase): onboard one test device, shred
  local artifacts, run drift check (`current`), change an output, re-run
  (`stale`), refresh via registry-resolved options, revoke.
