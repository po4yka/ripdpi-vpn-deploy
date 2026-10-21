# Runbook — add a fallback VPS

v1 ships single-VPS. For a multi-VPS / multi-ASN posture, here's how to
extend.

## Two patterns

| Pattern | When | Effort |
|---|---|---|
| Same provider, same role | Need a hot spare for blue-green | Low |
| Different provider / ASN, same role | Want orthogonal failure domain | Medium |
| Different role (one P0, one P1+P2) | Want clean role separation | Medium |

## Pattern 1 — hot spare on UpCloud

Use a separate `ENV` value to keep two parallel root states without
fighting Terraform's `prevent_destroy`. The helper script
`scripts/new-cohort.sh` does the tfvars boilerplate:

```bash
# Generate a second tfvars in a different zone
PROVIDER=upcloud SOURCE_ENV=prod \
  ./scripts/new-cohort.sh spare de-fra1
$EDITOR terraform/providers/upcloud/environments/spare.tfvars   # review

# Provision and deploy the spare
ENV=spare make init plan apply inventory wait dry-run deploy verify
```

Both VPSes now share the same secrets and same Ansible roles. They have
different IPs, different REALITY private keys (REALITY private key is in
secrets — to truly differ you need a second secrets file or a per-host
override). For a hot spare in the same provider, sharing REALITY material
is acceptable for a short period.

To switch traffic: change DNS / subscription URLs to point at the spare, and decommission the original (`make ENV=prod destroy` after removing `prevent_destroy`).

## Pattern 2 — different provider / ASN

Create a provider-specific environment file, then provision the spare under a
different `PROVIDER`:

```bash
cp terraform/providers/hetzner/environments/prod.tfvars.example \
   terraform/providers/hetzner/environments/prod.tfvars
$EDITOR terraform/providers/hetzner/environments/prod.tfvars

HCLOUD_TOKEN=... PROVIDER=hetzner make init plan apply inventory wait dry-run deploy verify
```

Now you have two VPSes in different ASNs. To make them serve different
client cohorts:

- Use a per-cohort subscription URL on `subscription-host`.
- Send cohort A's traffic to the UpCloud VPS, cohort B's to the Hetzner
  one. If cohort A's path degrades, the operator switches that cohort's
  subscription URL to a different VPS.

This is the minimum useful cohort split. A full fleet model would also
introduce blast-radius caps (per-cohort credential isolation, no shared
SNI target), automated migration playbooks, and ASN burn detection —
all out of scope for v1.

## Pattern 3 — separate roles per VPS

Best for production. One VPS hosts only P0 (REALITY direct), another
hosts P1+P2 (XHTTP + Hysteria + AWG). They have no shared protocol
material; a compromise of one doesn't leak the other.

```bash
# VPS 1 — only REALITY
$EDITOR terraform/providers/upcloud/environments/p0.tfvars   # enable_hysteria=false
$EDITOR ~/.config/vpn-provision/p0.secrets.sops.yaml         # only xray.* fields

# Override role toggles per environment by editing playbooks/site.yml
# OR keep one site.yml and use:
ANSIBLE_TAGS="xray" ENV=p0 make decrypt deploy
```

For a separate-role split, use the cohort group_vars shipped with the
repo and the multi-host mode of `render-inventory.sh`:

```bash
# Provision both nodes (different ENVs or PROVIDERs)
ENV=p0    make init plan apply
ENV=p1p2  make init plan apply

# Render a multi-host inventory with cohort groups
HOSTS="upcloud:p0,upcloud:p1p2" \
COHORTS="p0,p1p2" \
ANSIBLE_SSH_PRIVATE_KEY_FILE=~/.ssh/vpn_deploy \
  ./scripts/render-inventory.sh

# Single deploy across both — each host gets the right toggles from
# group_vars/vpn-p0.yml or group_vars/vpn-p1p2.yml
ansible-playbook ansible/playbooks/site.yml
```

The pre-shipped cohort files are:

- `ansible/group_vars/vpn-p0-minimal.yml`      — REALITY only
- `ansible/group_vars/vpn-family-standard.yml` — REALITY + XHTTP + Hysteria, no AWG
- `ansible/group_vars/vpn-device-full.yml`     — family-standard + AWG
- `ansible/group_vars/vpn-lab.yml`             — lab/pilot surface; research roles still require `allow_research_roles`

Legacy aliases stay supported for existing inventories:

- `ansible/group_vars/vpn-p0.yml`        — alias for `vpn-p0-minimal`
- `ansible/group_vars/vpn-p1p2.yml`      — older XHTTP + Hysteria + AWG split host with REALITY disabled
- `ansible/group_vars/vpn-fullstack.yml` — alias for `vpn-device-full`

## Operational consequences of multi-VPS

- **Secrets get bigger**: separate REALITY keypairs per VPS, separate
  Hysteria server certs, separate AWG server keys. Decide whether you
  want one secrets file with all VPSes or one per VPS.
- **Restic gets bigger**: per-VPS local repos, or one remote bucket with
  per-VPS prefixes.
- **Subscription delivery starts mattering**: when there's one VPS, you
  hand-edit URIs. When there are two+, you need a real subscription
  endpoint that can hand each device the right cohort.
- **Health checks and failover** become explicit: clients need
  selector/urltest logic in RIPDPI or a current sing-box client to actually use the
  fallback VPS without a manual switch. `make emit-singbox CLIENT=<name>`
  produces a JSON with a selector + urltest group covering every
  configured host.

## What this repo intentionally does NOT automate

- Multi-VPS coordination (no shared state plane).
- Cohort assignment / per-device subscription rendering with revocation.
- Burned-ASN detection.

For v1 the answer is: pick a pattern above, run it twice, and treat the
second run as deliberate operator action.
