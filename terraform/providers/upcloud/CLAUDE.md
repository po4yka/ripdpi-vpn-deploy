# terraform/providers/upcloud — primary provider root

## Design decisions

**Per-provider root, identical outputs** — Terraform module sources cannot be
variable-driven, so each provider gets its own root. The output schema
(`server_ipv4`, `server_ipv6`, `admin_user`, `server_hostname`) is fixed
across providers so `scripts/render-inventory.sh` is provider-neutral.

**Local TF state by default** — we don't trust remote state with VPN secrets
even though we keep them out of TF. State is age-encrypted via
`make backup-state`. Loss → re-import (see `RUNBOOK-restore.md`).

**Floating IP optional** — `var.use_floating_ip` toggles allocation. Useful
for blue-green; pointless if the operator only runs one VPS.

## What's done well

- **Inputs are typed** — every variable has a `type` and `validation` block
  where the shape is constrained (CIDR, region, plan).
- **Outputs are minimal** — only what `render-inventory.sh` needs.
- **No `local-exec`** — TF stays declarative; cloud-init and Ansible own the
  imperative side.

## Pitfalls

- **UpCloud plan names change** — the API accepts both legacy `1xCPU-1GB` and
  new tier strings. Pin via the validation block; don't accept arbitrary input.
- **SSH key fingerprint format** — UpCloud expects MD5; some keypairs cache
  SHA256. The variable description says "MD5 fingerprint of the public key".
- **Storage size is in GiB** — if you pass `50` thinking GB, you get the
  smaller billing tier silently.
- **Region affects RU latency more than provider** — Helsinki / Frankfurt /
  Amsterdam are baseline; LON / NYC add jitter the cohort tuning won't fix.
- **UDP/443 edge rule ≠ UDP delivery** — `firewall.tf` opens UDP/443 under
  `enable_hysteria` (v4+v6), but a present rule does not guarantee the provider
  network delivers inbound UDP. After deploy, verify externally with
  `make burn-check` (QUIC probe); on-host `nft`/`ss` ACCEPT is not evidence.
  See `docs/PROVIDER-NOTES.md` → "UDP/443 edge reachability".
