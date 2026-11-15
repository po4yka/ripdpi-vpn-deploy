# SEC-1794728936979277: Keep revoked devices revoked and bind secret delivery to pinned hosts

## Objective

A revoked device credential stays unusable across rollback and share bundles, device payloads go only to pinned hosts, and recipient removal rotates the SOPS data key.

## Ownership

- `ansible/roles/runtime-release/files/transport_runtime_rollback.py`, `ansible/roles/subscription-host/`, `scripts/issue_sub_token.py`, `scripts/issue-bootstrap.sh`, `scripts/rotate-secrets.sh`, `secrets/schema.json`, `secrets/prod.secrets.example.yaml`, their tests, snapshots and docs.

## Execution

- [x] SEC-1794728996747903 Refuse a config rollback that re-admits a removed client #bug !high @item:SEC-1794728936979277
- [x] SEC-1794729007676570 Remove a share bundle on revocation and prune undeclared bundles #bug !high @item:SEC-1794728936979277
- [x] SEC-1794729019627773 Send device payloads over pinned SSH and separate the mirror user #bug !high @item:SEC-1794728936979277
- [x] SEC-1794729031539704 Rotate the SOPS data key when recipients change #bug !high @item:SEC-1794728936979277

## Verification

- Transport runtime transaction unit tests, issuance and rotation script tests, `make molecule-test ROLE=subscription-host`, `make snapshot-check`, `make shellcheck`, one `make check`; remote CI. The subscription host and transport nodes receive the change through the reviewed dry-run and deploy transaction after merge.
