# terraform/providers/hetzner — secondary provider

## Design decisions

**Mirrors UpCloud's output schema** — `server_ipv4`, `server_ipv6`,
`admin_user`, `ssh_port`, `server_hostname`. So `render-inventory.sh` stays
provider-neutral.

**Cloud-init via `user_data`** — Hetzner accepts cloud-init natively. Same
shared template as UpCloud (`terraform/shared/cloud-init.yaml.tftpl`).

## What's done well

- **Server type validation** — only the curated set (`cx22`, `cx32`, `cpx21`,
  `cpx31`) is accepted. The unrestricted list is a footgun.
- **Region restriction** — datacenter is constrained to fsn1/nbg1/hel1.
  Hetzner US regions are off-limits for our threat model.

## Pitfalls

- **SSH key handling differs from UpCloud** — Hetzner creates a named
  `hcloud_ssh_key` resource referenced by ID; UpCloud has no key resource and
  inlines the public key through `login.keys`.
- **Volume attachment is async** — adding a separate volume needs a
  `depends_on` against the server resource; otherwise `cloud-init` boots
  without the volume mounted.
- **Floating IP is region-scoped** — moving a host across regions invalidates
  any attached FIP; plan blue-green carefully.
- **AS24940 is in the Avoid tier** — `docs/PROVIDER-NOTES.md` records the
  datacenter-ASN TCP freeze (~14-25 KB) on filtered mobile paths. Use this
  root for development and unaffected cohorts, and rotate IPs more often than
  on UpCloud.
- **UDP/443 edge rule ≠ UDP delivery** — UDP/443 is opened by the typed
  `public_listeners` contract (`enable_hysteria` only feeds the legacy
  fallback), but a present rule does not
  guarantee the provider network delivers inbound UDP. After deploy, verify
  externally with `make burn-check` (QUIC probe); on-host `nft`/`ss` ACCEPT is
  not evidence. See `docs/PROVIDER-NOTES.md` → "UDP/443 edge reachability".
