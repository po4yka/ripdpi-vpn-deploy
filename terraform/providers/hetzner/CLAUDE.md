# terraform/providers/hetzner — secondary provider

## Design decisions

**Mirrors UpCloud's output schema** — `server_ipv4`, `server_ipv6`,
`admin_user`, `server_hostname`. So `render-inventory.sh` stays
provider-neutral.

**Cloud-init via `user_data`** — Hetzner accepts cloud-init natively. Same
shared template as UpCloud (`terraform/shared/cloud-init.yaml.tftpl`).

## What's done well

- **Server type validation** — only the curated set (`cx22`, `cx32`, `cpx21`,
  `cpx31`) is accepted. The unrestricted list is a footgun.
- **Region restriction** — datacenter is constrained to fsn1/nbg1/hel1.
  Hetzner US regions are off-limits for our threat model.

## Pitfalls

- **SSH key handling differs from UpCloud** — Hetzner uses key *names*, not
  fingerprints. The variable description spells this out.
- **Volume attachment is async** — adding a separate volume needs a
  `depends_on` against the server resource; otherwise `cloud-init` boots
  without the volume mounted.
- **Floating IP is region-scoped** — moving a host across regions invalidates
  any attached FIP; plan blue-green carefully.
- **Hetzner ASN (24940) is a known VPN exit ASN** — REALITY camouflage still
  helps, but cohort tuning should account for "Hetzner egress" appearing in
  recipient ASN logs as a known signal.
- **UDP/443 edge rule ≠ UDP delivery** — `firewall.tf` opens UDP/443 under
  `enable_hysteria` (public v4+v6 `source_ips`), but a present rule does not
  guarantee the provider network delivers inbound UDP. After deploy, verify
  externally with `make burn-check` (QUIC probe); on-host `nft`/`ss` ACCEPT is
  not evidence. See `docs/PROVIDER-NOTES.md` → "UDP/443 edge reachability".
