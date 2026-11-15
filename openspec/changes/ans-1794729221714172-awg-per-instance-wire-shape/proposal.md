# Change: Randomise the AmneziaWG wire shape and listen port per instance

Task ID: `ANS-1794729221714172`

## Why

The 2026-11-15 audit found that the AmneziaWG handshake shape and port are the same on every node that keeps the generated values, and that this public repository states them:
- `scripts/bootstrap-secrets.sh` writes fixed junk and padding values (`jc`, `jmin`, `jmax`, `s1`, `s2`) for every new instance. Only the four header values are random. `scripts/transport_semantics.py` supplies the same numbers when an instance omits them. The resulting junk count, junk size range and handshake message sizes are a fixed pattern that an observer can read from the repository.
- The default listen port is the WireGuard default, in `group_vars/all.yml`, in the secrets example and in the legacy listener list of all four provider roots. A rule on the destination port alone matches it.
- The production guard for a WireGuard-shaped instance refuses only the case in which both padding values are zero and the four header values are 1 to 4. An instance with header values 1 to 4 and non-zero padding passes, and its data packets and keepalives are then identical to WireGuard transport messages. `ansible/roles/real-vps-awg-nat/defaults/main.yml` ships that shape.

## What Changes

- New instances get junk and padding values from a random source, inside validated bounds, at issue time.
- BREAKING: strict validation and transport admission refuse a production instance whose junk and padding values equal the published example values. The secrets schema already requires all five values in every document, so an instance cannot omit one.
- BREAKING: production refuses any header value from 1 to 4, unless a recorded measurement exists for that instance.
- BREAKING: production refuses the WireGuard default listen port. New instances get a random port. The provider legacy listener list has no AmneziaWG entry; the port comes from the listener contract. `amneziawg_listen_port` in `group_vars/all.yml` stays as the staging and fixture fallback.

## Capabilities

### New Capabilities

- `transports/awg-instance-wire-shape`: every production instance has its own junk, padding and port values, none of which this repository publishes, and no header value that is a WireGuard message type.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/bootstrap-secrets.sh`, `scripts/transport_semantics.py`, `scripts/validate-secrets.py`.
- Ansible: `ansible/roles/amneziawg/tasks/guard-wireguard-shape.yml`, `ansible/playbooks/tasks/transport-input-preflight.yml`, the notes in `ansible/roles/amneziawg/CLAUDE.md`, comments in `ansible/group_vars/all.yml`. The `real-vps-awg-nat` staging lane is unchanged.
- Terraform: `listeners.tf` in the four provider roots and their tests.
- Secrets: a comment in `secrets/prod.secrets.example.yaml`; the schema is unchanged.
- Clients: every device on an instance whose values change needs a new configuration. The operator replaces the values of the instance and redelivers the device configurations, as for a server-wide header rotation.
- Docs: `docs/reference/awg-cohorts.md`.
