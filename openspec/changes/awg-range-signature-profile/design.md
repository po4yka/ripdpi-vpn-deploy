## Context

The current producer uses integer headers and drops signature fields. The Android engine has an AWG envelope around its existing Noise implementation. The reviewed source candidate supports intervals and signature programs.

## Goals / Non-Goals

- Goal: deliver and execute the named range and signature profile with real peer traffic.
- Non-goal: header protection, custom timers, random trailers, content padding, cookie disable, production promotion, or a physical-device success claim.

## Decisions

- Use canonical decimal string headers: one value or `min-max`, with no leading zero, sign, whitespace, reversed bounds, or equal endpoints in range form.
- Use bounded canonical `<b 0x...>`, `<r N>`, `<rd N>`, `<rc N>`, and `<t>` programs. Compile once in the consumer and generate fresh random bytes for each handshake. Send I1-I5 before junk packets.
- Prefix the existing ordered fingerprint preimage with `wire_profile=awg-3.1-ranges-v1&`. Hash canonical text in UTF-8.
- Require the reviewed Go commit b5928efb6ca19f0153958460c3d141f04abc5c2e and tools commit ee0f0a9aa34ff0a0da4b3433b9512781cfe02843 for ranges or signatures. Existing singleton/no-signature wire remains possible with its exact original message-type restriction.

## Contracts and ownership

The primary writer owns server admission, secrets schema, generators, Ansible templates, exports, canonical bundle schema and fingerprint. The isolated client worker owns Rust, Kotlin, and byte-identical mirrors. Terraform and cloud-init are unaffected. No new production dependency is needed.

## Risks / Trade-offs

- Wire drift: require real source-pinned peer tests and paired fingerprint tests.
- Parser work amplification: bound program text, token count and generated packet size before allocation.
- Accidental promotion: retain candidate and production eligibility gates and all S3/S4 restrictions.
- Existing private documents require explicit migration; no private data is read or rewritten in this change.

## Migration Plan

Update all repository producers, fixtures and consumers together. Regenerate public contract fixtures through a reviewed generator. Reject the old format with a categorical error. A future operator rollout must convert private headers to canonical strings and re-export subscriptions before activation. Keep the matching prior source and encrypted configuration for rollback; the local source package does not execute that rollout. Run targeted Python tests, snapshots, full make check, client compile and real native interop, then exact-head hosted checks.
