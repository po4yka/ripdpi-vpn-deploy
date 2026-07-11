# terraform/exception/cascade-ingress — inert candidate root

## Design decisions

This root owns a physically separate local state path and the fixed provider-neutral output contract. It contains only an inert `terraform_data` resource and an `external` data source that runs the attestation checker; it has no hosting provider or server resource. A future governance reversal must add a provider adapter explicitly rather than making the current scaffold live by variable alone.

## What's done well

- Literal confirmation, attestation verification, and `INERT_UNATTESTED` mode are plan-time preconditions.
- Outputs match the inventory contract while returning no routable address.

## Pitfalls

- Never add this root to `scripts/terraform-env.sh` or the normal Make deploy lifecycle.
- Never replace the empty address outputs with operator-supplied live data; addresses must eventually come from an owned provider resource in this isolated state.
