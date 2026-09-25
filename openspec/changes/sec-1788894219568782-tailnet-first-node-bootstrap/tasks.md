# SEC-1788894219568782: Bootstrap restricted Tailnet access before dual-path deployment

## Objective

Deliver positive fresh-node enrollment and durable recovery, then exercise
ordinary deployment and guarded deletion on authorized disposable staging.

## Ownership

Primary owns the complete change serially. Controller/Make boundary, Tailnet
domain and role, firewall foundation, deploy callers, cleanup sequencing, and
their tests are the only implementation lanes. Shared task files and generated
board writes remain serialized. No parallel task is consulted or modified.

## Execution

- [ ] SEC-1788894502237285 Implement the literal one-node Make and controller boundary with pinned public SSH and tests proving invalid inputs cause zero writes #feature !high @item:SEC-1788894219568782
- [ ] SEC-1788894502776578 Extend the Tailnet domain and recovery units to external confirmation with bounded leases and tests for crash reboot expiry replay and fsync failure #feature !high @item:SEC-1788894219568782
- [ ] SEC-1788894503320732 Implement the minimal firewall foundation and atomic rollback in the firewall role with real nftables and systemd recovery tests #feature !high @item:SEC-1788894219568782
- [ ] SEC-1788894503869488 Wire bootstrap enrollment fresh public and Tailnet SSH SFTP proof and private handoff; migrate deploy to verification-only and test all callers #feature !high @item:SEC-1788894219568782
- [ ] SEC-1788894504408980 Enforce and document pre-bootstrap cleanup manifests and safe state-bound reissue after provider firewall changes with guard regressions #feature !high @item:SEC-1788894219568782
- [ ] SEC-1788894504951632 Pass local and exact-SHA hosted gates then exercise authorized positive staging recovery ordinary deployment protocol proof and guarded provider deletion #feature !high @item:SEC-1788894219568782

## Verification

Each implementation step includes regression and failure-path tests. The full
acceptance gates are `build-gate -- make ci-fast`,
`build-gate -- make validate`, affected Molecule/native Linux recovery tests,
exact-SHA hosted CI, positive staging bootstrap plus controller-loss/reboot
recovery, ordinary deploy protocol proof, and guarded exact-resource deletion.
The broader authorized serial live checks remain required for the parent
infrastructure objective; no local or bootstrap-only result substitutes.
