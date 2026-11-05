# Change: Renew the REALITY self-steal certificate off-node on a schedule

Task ID: `SCR-1793858662430806`

## Why

P0 now presents an operator-owned self-steal certificate. The pair is supplied through SOPS and nothing renews it, so the P0 REALITY camouflage would break when the certificate expires. The node has no public HTTP listener, so HTTP-01 is impossible. Giving the node DNS API credentials would expose the whole DNS account from a disposable node.

## What Changes

- `make renew-self-steal-cert` reissues the pair off-node with ACME DNS-01 on the Vultr zone when 30 days or fewer remain. It writes the pair into a new SOPS document beside the source, never changes the source, and removes the issued key from disk.
- Later runs report `awaiting-deploy` while a renewed document exists, so the job does not issue repeatedly.
- `make install-operator-crons` gains an optional daily job, enabled only when both documents are named.
- Deployment of the renewed document stays a reviewed dry-run and deploy.

## Capabilities

### New Capabilities

- `operations/self-steal-certificate-renewal`: due-only off-node reissue into a new encrypted document, with a pinned client and pair validation.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/renew-self-steal-cert.py`, `scripts/install-operator-crons.sh`.
- Make: `renew-self-steal-cert`.
- Docs: `docs/how-to/certificates.md`, `ansible/roles/reality-self-steal/CLAUDE.md`.
- Tests: `tests/unit/test_renew_self_steal_cert.py`.
