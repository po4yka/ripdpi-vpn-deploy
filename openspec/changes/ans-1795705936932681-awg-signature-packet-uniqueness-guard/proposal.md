# Change: Refuse AmneziaWG signature packets that repeat across nodes or match a public default

Task ID: `ANS-1795705936932681`

## Why

A public write-up dated 2026-11-14 reported that many servers carry the same default I1 packet. The packet imitates a DNS response that no real resolver would return. A byte-identical packet across servers can become a one-rule signature. The write-up is a risk assessment. It reported no blocking. Treat it as single-source and unverified.

Two changes are in review and do not cover this. `ANS-1792776076428131` (`awg-range-signature-profile`) admits and delivers bounded signature programs. `ANS-1794729221714172` (`awg-per-instance-wire-shape`) randomizes headers, padding and port per instance. Neither compares packets across instances or against a public default. Both carry exact-SHA review evidence, so this follow-up is a separate change that builds on them.

## What Changes

- Generate signature packets per instance at instance creation.
- Add a production guard beside the existing wire-shape guard. It refuses a repeated static packet part and a digest match with a public default.
- Pin the digests of the public defaults in a repository data file. The packets themselves are not stored.
- Overlap: extends the admission rules of the two changes above. It depends on both reaching `main`.

## Capabilities

### New Capabilities

- `transports/awg-signature-packet-uniqueness`: per-instance signature packets and the production uniqueness guard.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/amneziawg/` guard and instance generator, and `docs/reference/awg-cohorts.md`.
- Scripts: the instance creation path and tests.
