# Cascade: decide ASN-attestation re-verification cadence, ownership, and method-unavailable behavior

- [ ] #task Settle the recurring cadence, signer, and fallback behavior for the per-ASN attestation gate #repo/RIPDPI-VPN-DEPLOY #area/security #status/backlog 🔼

## Goal

Resolve the three unresolved operational parameters of the attestation gate so it can be enforced deterministically rather than assumed: the re-verification cadence, who is authorized to produce and re-sign the attestation, and what happens if the external verification method itself becomes unavailable.

## Why now

`docs/CASCADE-ASN-ATTESTATION.md` establishes the gate as recurring, expiring, and fail-closed, but deliberately leaves the cadence undecided because the source material describes allowlist membership as empirically variable without giving a volatility rate. A gate with no agreed cadence or owner degrades into a one-time check that silently goes stale — exactly the failure mode the design exists to prevent.

## Scope

- Decide the re-verification cadence (per-deploy / weekly / monthly / other) and record the rationale.
- Name the role authorized to produce and re-sign the attestation, and whether the record points to a script-output artifact, a dated report, or a manual sign-off note.
- Decide the method-unavailable behavior: if the verification method cannot run, the gate remains a permanent block (fail-closed) — name this explicitly as a residual risk, not an implicit bypass incentive.

## Out of scope

- No live measurement here (that is `cascade-first-asn-attestation.md`).
- No committed ASN/CIDR data or provider names.

## Ship definition

- [ ] `docs/CASCADE-ASN-ATTESTATION.md` records a concrete cadence with rationale.
- [ ] The attestation-owner role and evidence-artifact form are named.
- [ ] The method-unavailable = permanent-block behavior is stated as a named residual risk.
- [ ] The freshness-checker design honors the chosen cadence (stale past cadence → hard-block).

## Links

- `docs/CASCADE-ASN-ATTESTATION.md`
- `docs/RU-CASCADE-DECISION.md`
