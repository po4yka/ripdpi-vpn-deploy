## Purpose

Let the one-shot disposable liveness executor verify the TLS certificate of a self-signed disposable staging node through an explicit, validated trust anchor, without disabling TLS verification in the liveness profiles.

## ADDED Requirements

### Requirement: REQ-STAGING-TRUST-ANCHOR-INSTALL — Install an explicit staging trust anchor

The implementation MUST install a certificate named by `STAGING_TRUST_ANCHOR` into the disposable executor's system trust store during `make provision-disposable-liveness-runtime`, run `update-ca-certificates`, and report the anchor's SHA-256 fingerprint in the printed result. Without `STAGING_TRUST_ANCHOR` the command MUST NOT change the executor's trust store.

#### Scenario: Valid self-signed staging certificate

- **WHEN** the operator passes `STAGING_TRUST_ANCHOR` naming one self-signed, currently valid PEM certificate with exactly one non-wildcard DNS subject alternative name
- **THEN** the executor trusts the certificate for TLS verification and the result carries `trust_anchor_sha256`

#### Scenario: No anchor

- **WHEN** the operator omits `STAGING_TRUST_ANCHOR`
- **THEN** no certificate is added to the executor trust store and the result has no `trust_anchor_sha256`

### Requirement: REQ-STAGING-TRUST-ANCHOR-VALIDATION — Refuse an unsuitable anchor before executor changes

The implementation MUST refuse, before it runs any command in the executor, a trust anchor file that does not hold exactly one PEM certificate, whose certificate is not self-signed, is outside its validity period, or whose subject alternative names are not exactly one non-wildcard DNS name.

#### Scenario: Bundle or CA-issued certificate

- **WHEN** the anchor file holds two certificates, or one certificate issued by another authority
- **THEN** provisioning fails with a categorical `trust-anchor` error and the executor is not contacted

#### Scenario: Expired certificate

- **WHEN** the anchor certificate's validity period has ended
- **THEN** provisioning fails with a categorical `trust-anchor` error and the executor is not contacted
