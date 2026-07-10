# Cascade: produce the first per-ASN allowlist attestation (confirm-or-kill gate)

- [ ] #task Produce the first real dated per-ASN attestation before any cascade Phase 1+ work; gate is currently closed #repo/RIPDPI-VPN-DEPLOY #area/security #status/backlog ⏫

## Goal

Run the confirm-or-kill gate defined in `docs/CASCADE-ASN-ATTESTATION.md`: obtain a real, dated, per-ASN empirical attestation for at least one candidate RU-hosted entry ASN before any Terraform/Ansible cascade work begins. If no candidate ASN can produce a passing, non-stale, non-brand-inferred attestation, kill the cascade effort rather than build it.

## Why now

RU-jurisdiction hosting for a temporary whitelist-riding entry node is signed off, and the structure (EXCEPTION tier, fail-closed classifier, separate role pair) is approved — but the whitelist-ride economics are unverified. The attestation record ships PENDING/UNVERIFIED, so the gate is fail-closed and provisioning is blocked. The downside (RU legal/data-retention/seizure exposure, first hosting-jurisdiction exception) is paid the moment a node is placed; the upside is conditional on this attestation. This is the single decision that gates the whole investment.

## Scope

- Establish a genuine RU-side vantage measurement (operational step, owned by an operator — not in this repo's docs) proving the specific candidate ASN currently shows a real reachability advantage over the foreign-VPS baseline.
- Populate an attestation record conforming to the schema in `docs/CASCADE-ASN-ATTESTATION.md`, per-ASN and not brand-inferred, with an expiry/next-recheck date.
- Weigh the result against the documented latent tradeoff (escaping the foreign-DC freeze bucket trades into a different RKN TLS-fingerprint/rate path on a flagged RU AS).

## Out of scope

- No probe commands, tool invocations, CIDR/ASN inventories, or provider names committed to the repo — the record is a dated claim with a pointer to evidence, never the raw feed.
- No provisioning, roles, or Terraform until this attestation passes.
- No brand-based or assumed pass (Yandex.Cloud LLC vs YANDEX LLC are distinct ASNs).

## Ship definition

- [ ] A schema-valid attestation record exists for at least one candidate ASN, or a written decision to kill the cascade effort is recorded.
- [ ] The record is per-ASN, dated, `verified-not-brand-inferred: true`, and carries an expiry/next-recheck date.
- [ ] If no ASN passes, `docs/RU-CASCADE-DECISION.md` is updated to record the no-go and Phase 1+ is not started.
- [ ] The latent-risk tradeoff was explicitly weighed and recorded as part of the decision.

## Links

- `docs/CASCADE-ASN-ATTESTATION.md`
- `docs/RU-CASCADE-DECISION.md`
