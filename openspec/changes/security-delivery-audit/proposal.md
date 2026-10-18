# Change: Repair audited security and delivery contracts

Task ID: `SEC-1792306869763633`

## Why

Thirteen confirmed audit findings affect recovery, administrative encryption, authenticated HTTP, subscription delivery and alert operations. Repair these source contracts and record regression evidence before protected merge.

## What Changes

- Preserve recovery access during hardware-age enrollment; rotate SOPS data keys after compromise; preserve old restic generations until replacement recovery is verified.
- Publish complete encrypted state backups and subscription documents atomically.
- Refuse credential redirects, incoherent bundle inputs and unsupported RIPDPI port hopping; retain every selected Hysteria metadata entry.
- Align alert environment identity and Telegram flood-control handling.
- Admit supported hybrid SSH key exchange through the existing recovery transaction.
- BREAKING: previously accepted invalid bundles, non-HTTPS notification origins and unsupported recipient profiles are refused. Valid deployed profile structure remains compatible.

## Capabilities

### New Capabilities

- `security/audited-delivery-contracts`: bounded recovery, publication and compatibility invariants for the confirmed audit scope.

### Modified Capabilities

- None. Existing runtime transaction boundaries remain in force; this capability adds safety requirements.

## Impact

- Ansible baseline, subscription-host and observability control-plane roles; operator scripts; bundle semantic validation; recovery documentation and tests.
- No new production dependency, provider mutation, secret material, live rollout or changes to the peer client repository.
