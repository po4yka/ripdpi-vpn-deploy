# SEC-1794156917837664: Block unsafe recipient destinations at the egress boundary

## Objective

Deny recipient connections to operator-selected unsafe names and address ranges on the shared transport egress boundary for P0, P1 and Hysteria2. The policy is off by default, uses only pinned deny data, and records no destination.

## Ownership

- `scripts/transport_destination_policy.py`, `scripts/transport_egress_normalizer.py`, `scripts/transport_egress_config.py`
- `ansible/group_vars/all.yml`
- `ansible/roles/transport-egress/` (defaults, tasks, `templates/normalizer.json.j2`, `templates/normalizer.service.j2`, `files/generation.py`, Molecule scenario)
- `secrets/schema.json`, `scripts/validate-secrets.py`, `secrets/prod.secrets.example.yaml`
- `tests/unit/test_transport_destination_boundary.py`, `tests/unit/test_transport_egress_role.py`, `tests/unit/test_transport_egress_secrets.py`, `tests/integration/transport_destination_boundary/`, `tests/snapshot/golden/transport-egress/`
- `docs/reference/transport-egress.md`

## Execution

- [x] SEC-1794157748624712 Select and pin the deny source, confirm its licence use and set the entry limit from a memory measurement on the smallest node class #feature @item:SEC-1794156917837664
- [x] SEC-1794158301568776 Add the name and address-range deny decision to the destination policy and normalizer, with parser limits and unit tests for REQ-EDF-ENFORCE, REQ-EDF-ALLOW and REQ-EDF-PRIVACY #feature @item:SEC-1794156917837664
- [x] SEC-1794158806186281 Add the default-off toggle, secrets schema and pinned candidate delivery in transport-egress with generation rollback, covered by Molecule and snapshot checks #feature @item:SEC-1794156917837664
- [x] SEC-1794159684079419 Refuse deny data that blocks the runtime canary or REALITY target at candidate admission, with tests #feature @item:SEC-1794156917837664
- [x] SEC-1794160231676642 Document inputs, coverage limits and the client-side block for direct traffic #feature @item:SEC-1794156917837664
- [x] SEC-1794160777177995 Enable on staging, verify name delivery and denial on P0, P1 and Hysteria2, and record soak results #feature @item:SEC-1794156917837664
- [x] SEC-1794161271796231 Accept on a client device and enable per production profile under separate deployment authorization #feature @item:SEC-1794156917837664

## Verification

- Local: `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py tests/unit/test_transport_egress_secrets.py`, `make molecule-test ROLE=transport-egress`, `make snapshot-check`, and `make check` once before handoff.
- CI: the checks that the changed paths select pass on the exact commit.
- Dry-run: `make dry-run` for one staging node shows the toggle and candidate delivery, and the disabled path shows no runtime change.
- Staging: a test name and a test range are denied on P0, P1 and Hysteria2, allowed names still connect, and the rollback restores the previous generation. Soak records memory and connection latency on the smallest node class.
- Live: each production profile is enabled under separate deployment authorization, and runtime acceptance passes after each change.
- Client: an issued test device reaches allowed destinations, cannot reach a denied test name, and shows the documented failure.
- Artifact: the deny data URL, SHA-256, entry count and licence decision are recorded without destination logs.
