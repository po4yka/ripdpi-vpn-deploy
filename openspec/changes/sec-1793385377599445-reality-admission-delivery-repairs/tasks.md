# SEC-1793385377599445: Harden REALITY admission and repair client delivery defects

## Objective

Render a bounded REALITY replay window, refuse unreviewed production Xray pins, probe with the recipient uTLS fingerprint, emit complete read-only share URIs, emit truthful bundle topology, and keep XHTTP paths unguessable.

## Ownership

Single serialized lane. Ansible: `roles/xray`, `roles/xray-runtime`, `roles/watchdog`, `playbooks/tasks/smoke-reality.yml`, `roles/nginx-xhttp`, `roles/cdn-front` and the Molecule inputs. Scripts: `client_payload.py`, `emit-qr.sh`, `bootstrap-secrets.sh`, `transport_semantics.py`, `liveness_profiles.py`, `device_lifecycle_probe.py`, `check-xray-version-pin.py`. Contracts: secrets example and fixtures, snapshot goldens, the bundle, release-line and client-notes references.

## Execution

- [ ] SEC-1793385515086119 Bound REALITY maxTimeDiff in the xray template with preflight admission and goldens #feature !high @item:SEC-1793385377599445
- [ ] SEC-1793385515749582 Refuse unreviewed production Xray pins in xray-runtime and check allowlist parity #feature !high @item:SEC-1793385377599445
- [ ] SEC-1793385516458547 Use the configured recipient uTLS fingerprint in watchdog and smoke probes #feature !high @item:SEC-1793385377599445
- [ ] SEC-1793385517096983 Make emit-qr URI output read-only and complete via client_payload --share-uri #feature !high @item:SEC-1793385377599445
- [ ] SEC-1793385517743702 Stop claiming split-hop egress for family outbounds in RIPDPI bundles #feature !high @item:SEC-1793385377599445
- [ ] SEC-1793385518379176 Generate 128-bit XHTTP paths and refuse absent or published /app-sync paths #feature !high @item:SEC-1793385377599445
- [ ] SEC-1793385519027248 Update docs, role notes and run the full local gate #feature !high @item:SEC-1793385377599445

## Verification

- Local narrow checks: the matching `pytest` files, then `make snapshot-check`, `make shellcheck` and `make docs-check`.
- Local gate: `make check`.
- Remote: PR CI on the exact head SHA.
- Dry-run, staging, live and client: deferred to a separately authorized `make dry-run`/`make deploy`. This change does not run them.
