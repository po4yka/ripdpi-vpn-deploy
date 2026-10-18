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
- Keep legacy expiry audit categories and private route fixtures consistent with the production role. Normalize CRLF encoder output before publishing a typed inventory host line.
- BREAKING: previously accepted invalid bundles, non-HTTPS notification origins and unsupported recipient profiles are refused. Valid deployed profile structure remains compatible.

## Capabilities

### New Capabilities

- `security/audited-delivery-contracts`: bounded recovery, publication and compatibility invariants for the confirmed audit scope.

### Modified Capabilities

- None. Existing runtime transaction boundaries remain in force; this capability adds safety requirements.

## Impact

- Ansible baseline, subscription-host and observability control-plane roles; operator scripts; bundle semantic validation; recovery documentation and tests.
- The paired client task `po4yka/RIPDPI#TST-1792309202117414` vendors only the two synthetic JSON examples. Schema, fingerprints and client production source do not change. Merge that copy before repeating this repository's contract byte comparison.
- No new production dependency, provider mutation, secret material or live rollout.
