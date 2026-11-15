## Context

`proposal.md` gives the motivation. `bootstrap-secrets.sh` draws `h1` to `h4` from `/dev/urandom` and writes literal junk and padding values. `transport_semantics.py` holds `AWG_PARAMETERS` as the fallback and already refuses equal initiation and response sizes. `guard-wireguard-shape.yml` selects instances with `s1 == 0`, `s2 == 0` and headers 1 to 4. Each provider `listeners.tf` has a legacy list with a fixed AmneziaWG port and a `public_listeners` contract that overrides it.

## Goals / Non-Goals

- Goal: an observer cannot take the handshake pattern or the port of a production instance from this repository.
- Goal: no production instance sends WireGuard transport messages by accident.
- Non-goal: the transport-message padding values `s3` and `s4`. The arm64 version floor fixes them, and `TST-1792263206120096` owns that question.
- Non-goal: header ranges. `ANS-1792776076428131` owns range and signature profiles.

## Decisions

- One Python generator in `transport_semantics.py` returns a valid value set; `bootstrap-secrets.sh` calls it, and the cohort recipe in `ansible/roles/amneziawg/CLAUDE.md` names it for a new cohort. Rejected: shell arithmetic in each script, because the relationships are already checked in Python.
- Bounds: `jc` 3 to 8, `jmin` 20 to 80, `jmax` from `jmin + 20` to `jmin + 200`, `s1` and `s2` 15 to 150. They keep the handshake below the minimum MTU and inside the limits that validation already accepts.
- The fallback stays for staging documents and Molecule, so that fixtures do not change. Production refuses an omitted value and the example value set. Rejected: remove the fallback everywhere, because it rewrites every fixture for no production effect.
- The header guard keeps its measurement exception and widens its selection to any header value from 1 to 4. `real-vps-awg-nat` is a staging lane and keeps its defaults.
- The port is drawn from 20000 to 60999 and must not collide with another listener in the contract. The legacy listener entry is removed from the four roots in one commit with their tests.

## Contracts and ownership

- Scripts: `scripts/transport_semantics.py` (generator and production rules), `scripts/bootstrap-secrets.sh`, `scripts/validate-secrets.py`.
- Ansible: `ansible/roles/amneziawg/tasks/guard-wireguard-shape.yml` and its Molecule case; `ansible/group_vars/all.yml` loses the fixed port default.
- Terraform: `terraform/providers/*/listeners.tf` and `tests/`.
- Secrets: `secrets/schema.json` descriptions and `secrets/prod.secrets.example.yaml` placeholders for the generated values.
- Client contract: `contract/ripdpi-bundle.schema.json` is unchanged; the bundle already carries the instance values.

## Risks / Trade-offs

- An existing production instance with the example values fails validation → the operator adds a cohort with generated values, migrates the devices with the existing device migration path, then retires the old cohort. The failure message names that path.
- A changed port needs a provider plan before the deploy → the listener contract check already fails a deploy whose port is not open.
- Random values can land on a shape that a network treats badly → the cohort measurement process stays the way to qualify a cohort; this change only removes the published default.

## Migration Plan

Merge. For each production instance, create a cohort with generated values and port, apply the provider plan for the new listener, deploy, reissue the device configurations, then retire the old cohort and close its port. Rollback is the old cohort, which stays valid until it is retired. Gates: the transport semantics and secrets validation unit tests, `make molecule-test ROLE=amneziawg`, `make tf-test`, `make tf-policy-verify`, `make snapshot-check`, and one `make check` before handoff.
