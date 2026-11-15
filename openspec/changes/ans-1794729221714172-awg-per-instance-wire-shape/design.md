## Context

`proposal.md` gives the motivation. `bootstrap-secrets.sh` draws `h1` to `h4` from `/dev/urandom` and writes literal junk and padding values. `transport_semantics.py` holds `AWG_PARAMETERS` as the fallback and already refuses equal initiation and response sizes. `guard-wireguard-shape.yml` selects instances with `s1 == 0`, `s2 == 0` and headers 1 to 4. Each provider `listeners.tf` has a legacy list with a fixed AmneziaWG port and a `public_listeners` contract that overrides it.

## Goals / Non-Goals

- Goal: an observer cannot take the handshake pattern or the port of a production instance from this repository.
- Goal: no production instance sends WireGuard transport messages by accident.
- Non-goal: the transport-message padding values `s3` and `s4`. The arm64 version floor fixes them, and `TST-1792263206120096` owns that question.
- Non-goal: header ranges. `ANS-1792776076428131` owns range and signature profiles.

## Decisions

- One Python generator in `transport_semantics.py` returns a valid value set; `bootstrap-secrets.sh` calls it through `--generate-awg-shape`, and the operator uses the same flag for a later instance. Rejected: shell arithmetic in each script, because the relationships are already checked in Python. Rejected: a new cohort file for generated values, because a cohort file is public in this repository.
- Bounds: `jc` 3 to 8, `jmin` 20 to 80, `jmax` from `jmin + 20` to `jmin + 200`, `s1` and `s2` 15 to 150. They keep the handshake below the minimum MTU and inside the limits that validation, the secrets schema and the bundle contract already accept (`jc` 0 to 128, the others 0 to 1280). The generator draws again for equal initiation and response sizes and for the published value set.
- The fallback stays for staging, Molecule and callers that do not pass through the secrets schema, so that fixtures do not change. Production refuses the published value set on the effective values of an instance, which also covers an instance that takes every value from the fallback. The rule runs in `validate-secrets.py --strict --environment prod` and in the transport admission of a host whose `env` is `prod`. The secrets schema already requires the five values and the port in every document, production and staging, so no new omission rule is added. A value set from a selected cohort file passes: cohort profiles are deliberate measured configuration. Rejected: remove the fallback everywhere, because it rewrites every fixture for no production effect.
- The header guard keeps its measurement exception and widens its selection to any header value from 1 to 4. `real-vps-awg-nat` is a staging lane and keeps its defaults.
- The port is drawn from 20000 to 32767. The range is above every default listener and below the Linux ephemeral range, so an outbound socket cannot hold the port when the instance starts. The existing listener collision check before deployment covers ports that the operator chose. The legacy listener entry is removed from the four roots in one commit with their tests. `amneziawg_listen_port` stays in `group_vars/all.yml` as the staging and fixture fallback; production refuses its value.

## Contracts and ownership

- Scripts: `scripts/transport_semantics.py` (generator and production rules), `scripts/bootstrap-secrets.sh`, `scripts/validate-secrets.py`.
- Ansible: `ansible/roles/amneziawg/tasks/guard-wireguard-shape.yml`, evaluated by a unit test through real `ansible-playbook`; `ansible/playbooks/tasks/transport-input-preflight.yml` passes the inventory `env` to the admission.
- Terraform: `terraform/providers/*/listeners.tf` and `tests/`.
- Secrets: `secrets/prod.secrets.example.yaml` keeps integer example values, which the schema requires, with a comment that production refuses them.
- Client contract: `contract/ripdpi-bundle.schema.json` is unchanged; the bundle already carries the instance values.

## Risks / Trade-offs

- An existing production instance with the example values or port fails validation, and no production deploy passes while it is present. A second instance beside it cannot be deployed for the same reason → the operator replaces the values of the instance with generated ones, opens the new port in the listener contract, deploys, then redelivers every device configuration. Until a device has its new configuration it has no AmneziaWG tunnel and uses the other transports of its profile. The failure message names that path.
- A changed port needs a provider plan before the deploy → the listener contract check already fails a deploy whose port is not open.
- Random values can land on a shape that a network treats badly → the cohort measurement process stays the way to qualify a cohort; this change only removes the published default.

## Migration Plan

Merge. For each production instance with published values, generate a value set and port, replace them in the encrypted secrets, apply the provider plan for the new listener, deploy, then redeliver the device configurations. Rollback is a deploy of the previous release with the previous secrets generation. Gates: the transport semantics and secrets validation unit tests, `make molecule-test ROLE=amneziawg`, `make tf-test`, `make tf-policy-verify`, `make snapshot-check`, and one `make check` before handoff.
