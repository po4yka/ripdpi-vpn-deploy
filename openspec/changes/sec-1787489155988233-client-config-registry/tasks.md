# SEC-1787489155988233: Client configuration registry and issuance-option persistence

## Objective

Deliver the encrypted per-device configuration registry, registry-resolved
token refresh, AWG private-key recovery storage, and payload drift detection
described by the linked portfolio task and delta specification, so every
distributed client artifact is reproducible from git + SOPS + Terraform
outputs plus persisted issuance options.

## Ownership

- Own `secrets/schema.json`, `secrets/prod.secrets.example.yaml`,
  `scripts/check-secrets-coverage.py`, `scripts/validate-secrets.py` changes
  for the registry block; serialize edits to the secrets schema files.
- Own `scripts/new-client.sh`, `scripts/issue-sub-token.sh`, new
  `scripts/client-drift.py`, identity embedding in `scripts/emit-bundle.sh`
  and `scripts/emit-singbox.sh`, the Makefile `client-drift` target.
- Own contract updates in `docs/RIPDPI-BUNDLE.md`, `docs/SECRETS.md`,
  `docs/SUBSCRIPTION-PLANE.md`.
- No Terraform, cloud-init, or Ansible role edits; the delivery host keeps
  storing only hashed payloads and `.meta` sidecars.

## Execution

- [x] SCR-1787489427509997 Add registry schema block, coverage rules, and private-key field to the secrets contracts !high #feature @item:SEC-1787489155988233
  Extend `secrets/schema.json` and `secrets/prod.secrets.example.yaml` with
  `clients[*].registry` (status, issued_at, formats, hosts, cohorts,
  token_hash_prefix, token_expires, awg_public_key_fingerprint,
  last_payload_identity) and `clients[*].awg_private_key`; update
  `scripts/check-secrets-coverage.py` and `scripts/validate-secrets.py` so a
  missing registry field fails naming the device. Gate: `make ci-fast`.
- [x] SCT-1787489427528995 Persist issuance parameters in provisioning and make refresh resolve options from the registry !high #feature @item:SEC-1787489155988233 @blocked_by:SCR-1787489427509997
  `new-client.sh` writes the AWG private key and a complete registry entry at
  generation time under the existing SOPS lock; `issue-sub-token.sh
  --refresh-token` fails closed on unregistered tokens, reuses registry
  options (explicit overrides win and are echoed), updates status/expiry, and
  extends the audit note with reused vs overridden options. Gate:
  shellcheck + targeted pytest.
- [x] TST-1787489427553290 Implement payload identity embedding and the client-drift check !high #feature @item:SEC-1787489155988233 @blocked_by:SCR-1787489427509997
  Embed a source+outputs identity line in emitter payloads; add
  `scripts/client-drift.py` and `make client-drift CLIENT=<name>` reporting
  `current` (exit 0) / `stale +delta` (exit 1) / `unknown` (exit 2) without
  requiring local stored files; add unit tests for the verdict matrix and
  snapshot tests for registry rendering. Gate: `make ci-fast`.
- [x] DOC-1787489427574672 Reverse the private-key custody contract and document the registry workflow !high #docs @item:SEC-1787489155988233 @blocked_by:SCT-1787489427528995
  Update `docs/RIPDPI-BUNDLE.md` (device-local primary, SOPS recovery copy,
  plaintext artifacts disposable), `docs/SECRETS.md` contents inventory, and
  `docs/SUBSCRIPTION-PLANE.md` rotation item; document the lifecycle states
  and the drift/refresh operator flow. Gate: docs lint via `make ci-fast`.

## Verification

Live acceptance after implementation: onboard one test device, shred local
plaintext artifacts, confirm key recoverability from SOPS, run drift check
(`current`), change a Terraform output, re-run (`stale`), refresh the token
via registry-resolved options, then revoke and confirm the revoked response.
Completion of these checkboxes advances the portfolio record at most to
`review`.
