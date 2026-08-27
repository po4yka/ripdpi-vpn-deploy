# terraform/providers/upcloud — primary provider root

## Design decisions

**Per-provider root, identical outputs** — Terraform module sources cannot be
variable-driven, so each provider gets its own root. The output schema
(`server_ipv4`, `server_ipv6`, `admin_user`, `ssh_port`, `server_hostname`) is fixed
across providers so `scripts/render-inventory.sh` is provider-neutral.

**Local TF state by default** — we don't trust remote state with VPN secrets
even though we keep them out of TF. State is age-encrypted via
`make backup-state`. Loss → re-import (see `RUNBOOK-restore.md`).

**Secondary public IP is opt-in** — `additional_public_ip = true` allocates a
second public IPv4 for the honeypot role; there is no generic floating-IP
toggle. Blue-green moves follow the disposable-node path instead.

**Explicit address families** — every public interface declares IPv4 or IPv6.
The provider schema may otherwise leave the family unknown during planning,
which makes interface-count policy and IPv6-disable tests ambiguous.

**Enforcement and DNS replies are explicit** — `server.firewall = true` activates
the separate rules resource. DNS replies are not public listeners: approved
IPv4 resolvers, TCP/UDP source port 53, primary public IPv4 only, and configured
guest ephemeral destination ports. Secondary IPv4 never expands this scope.

## What's done well

- **Inputs are typed** — every variable has a `type` and `validation` block
  where the shape is constrained (CIDR, region, plan).
- **Outputs are minimal** — only what `render-inventory.sh` needs.
- **No `local-exec`** — TF stays declarative; cloud-init and Ansible own the
  imperative side.

## Pitfalls

- **Rules must precede live activation** — Terraform updates the server before
  its dependent rules resource. For an existing disabled firewall, preinstall
  and verify approved SSH and DNS rules before separately authorized activation;
  `-target` on the rules does not avoid its server dependency. Reject replacement
  or unrelated changes. Source integration is not live rollout permission.
- **DNS source ports vary** — 32768–60999 is a typical guest kernel range, not a
  guarantee for every DNS client. Verify resolver addresses and actual client
  source-port policy before activation; this rule does not allow IPv6 replies.
- **Provider filtering is stateless** — DNS reply rules do not establish return
  paths for HTTPS, NTP or other outbound traffic. Verify required traffic during
  the separate live rollout; do not infer it from ICMP or populated rules.
- **UpCloud plan names change** — the API accepts both legacy `1xCPU-1GB` and
  new tier strings. Pin via the validation block; don't accept arbitrary input.
- **Admin user is provisioned twice by design** — the server `login` block
  and cloud-init `users` both create `admin_user`. The login block delivers
  SSH access even when cloud-init fails; cloud-init owns sshd hardening.
  Do not drop either path without replacing its guarantee.
- **Storage size is in GiB** — if you pass `50` thinking GB, you get the
  smaller billing tier silently.
- **Region affects RU latency more than provider** — Helsinki / Frankfurt /
  Amsterdam are baseline; LON / NYC add jitter the cohort tuning won't fix.
- **UDP/443 edge rule ≠ UDP delivery** — `firewall.tf` opens UDP/443 under
  `enable_hysteria` (v4+v6), but a present rule does not guarantee the provider
  network delivers inbound UDP. After deploy, verify externally with
  `make burn-check` (QUIC probe); on-host `nft`/`ss` ACCEPT is not evidence.
  See `docs/PROVIDER-NOTES.md` → "UDP/443 edge reachability".
