# Cascade attestation artifact slot

The isolated cascade workflow looks for `cascade-asn-attestation.json` in this directory unless `CASCADE_ATTESTATION` points elsewhere. No record is checked in while the confirm-or-kill result is PENDING / UNVERIFIED; absence is the intentional fail-closed state.

A future record must validate against `contract/cascade-asn-attestation.schema.json` and pass `scripts/check-cascade-attestation.py`. It contains only a dated per-host/per-ASN claim, authorized signer role, opaque dated-report identifier and digest, and next-recheck date. Raw probe output, endpoint inventories, provider identity, commands, and ASN/CIDR feeds must not be committed here.

EXCEPTION registration also looks for `cascade-leg-health.json`. Its schema records only a fresh per-leg authenticated protocol-completion result and opaque report reference; it is not a probe implementation or raw observation feed. Missing, stale, degraded, far-leg-down, or locally unhealthy evidence blocks converge.
