# OPS-1792820562787120: Deliver native Hysteria port hopping to RIPDPI

## Objective

Export valid recipient hopping policies to the qualified native client without loss, downgrade, or partial publication.

## Ownership

Primary owns `scripts/client_payload.py`, `tests/unit/test_recipient_port_hopping.py`, related producer tests and guidance, and this task's artifacts. Native and Kotlin work belongs to `po4yka/RIPDPI#OUT-1792820412611017`; its owners serialize shared catalogue changes after the stored-policy migration fix. Only primary integrates and publishes PRs. No agent changes live infrastructure.

## Execution

- [ ] OPS-1792820856126759 Export the admitted hopping policy with exact interval validation and recipient regression tests #feature !high @item:OPS-1792820562787120
- [ ] OPS-1792820857234441 Verify paired native client traffic and import parity before producer release admission #feature !high @item:OPS-1792820562787120
- [ ] OPS-1792820858662402 Deliver qualified producer and client changes through passing PRs to main #feature !high @item:OPS-1792820562787120

## Verification

Run targeted producer tests, strict OpenSpec validation, task validation, federation with the paired client, and the full local gate. Client qualification requires positive traffic with the real pinned Hysteria server across three scheduled destination-port changes, including IPv6 and Salamander. Observe terminal PR and main CI before completion. No live deployment or physical-device acceptance is claimed.
