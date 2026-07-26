# Quickstart — zero to working VPN in ~30 minutes

This walks through deploying the full P0+P1+P2 stack to a single UpCloud VPS.
All commands run from your operator workstation; you should never SSH the
target VPS by hand for routine setup.

## 0. Prerequisites

```
terraform >= 1.15
ansible-core >= 2.19
sops, age, gitleaks, jq, openssl, python3 with PyYAML
ssh, terraform-cli, upctl (UpCloud CLI, optional but useful)
A domain you control with DNS (for nginx-xhttp + Hysteria TLS)
A public certificate for that domain (Let's Encrypt is fine; not bundled)
```

Verify in one shot:

```bash
make check-prereqs
make install-hooks      # one-time, installs pre-commit hooks for this repo
```

## 1. Provider credentials

UpCloud authenticates via env vars. Use a sub-account, not the master:

```bash
export UPCLOUD_USERNAME='vpn-deploy'
export UPCLOUD_PASSWORD='…'
```

Putting these in a shell login file (`.zshenv`) is fine; they must NEVER
appear in `*.tfvars`, in Terraform state, or in this repo.

## 2. Generate keys

```bash
mkdir -p ~/.config/vpn-provision

# 2a. age keypair (one-time)
age-keygen -o ~/.config/vpn-provision/age.key
RECIPIENT=$(grep '^# public key:' ~/.config/vpn-provision/age.key | awk '{print $4}')
echo "age recipient: $RECIPIENT"

# 2b. operator SSH key for the VPS (separate from your daily SSH key)
ssh-keygen -t ed25519 -f ~/.ssh/vpn_deploy -N '' -C 'vpn-deploy operator'
export ANSIBLE_SSH_PRIVATE_KEY_FILE=~/.ssh/vpn_deploy

# 2c. REALITY keypair (one-time per server)
docker run --rm ghcr.io/xtls/xray-core x25519
# or, if Xray is locally installed: xray x25519
```

Record the REALITY private key for the secrets file (next step) and the
public key for client URIs.

## 3. Fill out the Terraform vars

```bash
cd ~/GitRep/ripdpi-vpn-deploy
cp terraform/providers/upcloud/environments/prod.tfvars.example \
   terraform/providers/upcloud/environments/prod.tfvars
$EDITOR terraform/providers/upcloud/environments/prod.tfvars
```

Required: `zone`, `plan`, `storage_template`, `admin_ssh_public_key`
(paste content of `~/.ssh/vpn_deploy.pub`), `allowed_ssh_cidrs` (your
operator IP, **never** `0.0.0.0/0`). `ssh_port` defaults to `22`; changing it
updates cloud-init, the provider firewall, rendered `ansible_port`, wait logic,
and the on-host nftables allowlist together. It is a creation-time setting:
changing it on an existing node requests replacement and `prevent_destroy`
blocks an accidental in-place migration. Use blue-green recreation.

The default full-stack port layout is:

| Profile | Public listener |
|---|---|
| P0 REALITY | TCP/443 |
| P1 nginx-xhttp | TCP/8443 |
| P2 Hysteria2 | UDP/443 |

Keep `nginx_xhttp_public_port` at its default `8443` for single-host full-stack
deploys. Direct-only hosts with `vpn.enable_xray_reality: false` may override
both the Terraform variable and Ansible `nginx_xhttp_public_port` to `443`.

Find a current Debian 13 / Ubuntu 24.04 template UUID:

```bash
upctl storage list --public --template | grep -E 'Debian 13|Ubuntu 24.04'
```

## 4. Fill out the secrets file

```bash
cp secrets/prod.secrets.example.yaml ~/.config/vpn-provision/prod.secrets.yaml
$EDITOR ~/.config/vpn-provision/prod.secrets.yaml
```

### 4a. Pick a REALITY target

There is no safe default for `xray.target` — see the inline criteria in
the secrets schema and `docs/CDN-DECISION.md`. Two helpers narrow the
search:

```bash
# Discover candidates inside a CIDR or by crawling a public mirror list.
make scan-targets CIDR=107.172.103.0/24
make scan-targets CRAWL=https://launchpad.net/ubuntu/+archivemirrors

# Re-validate any candidate end-to-end (9 steps including ASN cross-check).
TARGET=mirror.example.com:443 SERVER_NAMES=mirror.example.com \
  ./scripts/validate-reality-target.sh
```

`scan-targets` is a wrapper around [XTLS/RealiTLScanner](https://github.com/XTLS/RealiTLScanner)
pinned at v0.2.1 with a sha256 check. It runs **on your workstation,
never on the VPS** (the upstream README is explicit that running the
scanner in the cloud may flag the VPS). The wrapper drops over-template
domains and demotes candidates in the "Avoid" ASN tier
(`docs/PROVIDER-NOTES.md`); export `VPS_ASN=<int>` to additionally
demote any candidate whose ASN does not match the VPS.

Fill: Xray version + sha256 (from the GitHub release page), REALITY keypair
from step 2c, target+server_names (validate with `make validate-target`),
nginx_xhttp cert/key (your public CA cert for `vpn.example.com`), Hysteria
version + sha256, geodata release URLs + sha256 values, AmneziaWG source
tag+commit pins (`amneziawg_go_version` + `amneziawg_go_commit`,
`amneziawg_tools_version` + `amneziawg_tools_commit`), AmneziaWG H1–H4
obfuscation params, restic password.

For a P0 host with an owned domain, the optional tactical self-steal mode replaces the external REALITY target with a loopback-only nginx TLS site. Assign the host to the `p0-self-steal` cohort, set `xray.target` to `127.0.0.1:8443`, set the only `xray.server_names` value and `reality_self_steal.server_name` to the same certificate hostname, and provide its public certificate chain and private key in `reality_self_steal.cert_pem` and `reality_self_steal.key_pem`. The role validates SAN, remaining lifetime, key match, listener collisions, and nginx syntax; disabling it removes its files and private listener. It never opens TCP/80 and does not change the public listener contract. DNS publication, production certificate issuance, and the live P0 switch remain explicit operator steps; use [the verified target research](REALITY-TARGET-RESEARCH-2026-07-12.md) as the promotion checklist.

## 5. Encrypt the secrets file

```bash
sops --encrypt --age "$RECIPIENT" \
  ~/.config/vpn-provision/prod.secrets.yaml \
  > ~/.config/vpn-provision/prod.secrets.sops.yaml

shred -u ~/.config/vpn-provision/prod.secrets.yaml
```

From now on edit only the encrypted file: `sops ~/.config/vpn-provision/prod.secrets.sops.yaml`.

Add the first device only after encryption; `new-client.sh` edits a SOPS file
and generates a distinct UUID, shortId, and peer key for that device:

```bash
SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml \
./scripts/new-client.sh phone
```

The external directory above is the default. Operators who deliberately keep
all deployment material next to the checkout may instead use the ignored
`secrets/local/config/`, `secrets/local/runtime/`, and
`secrets/local/clients/` directories and point `SOPS_FILE` and
`SECRETS_FILE` at them from the ignored `.fleet.mk`. Git must never track
anything below `secrets/local/`.

## 6. Deploy

```bash
make init
make validate          # must pass before continuing
make decrypt           # writes the configured SECRETS_FILE, mode 0600
make validate-target   # pre-deploy probe of REALITY target
make plan
make apply
make inventory
make wait              # 30–120 s, waits for cloud-init
make dry-run           # ansible --check --diff; review what will change
make deploy            # real run
make verify            # post-deploy gates
make smoke-test        # end-to-end real-traffic test through each profile
make clean             # shred the configured plaintext SECRETS_FILE
```

If `dry-run` shows changes you didn't expect, stop and investigate. Don't
proceed to `deploy`.

## 7. Generate a client config

For a full sing-box JSON with selector + urltest covering every enabled
profile (recommended for RIPDPI or a current sing-box-compatible client):

```bash
make emit-singbox CLIENT=laptop > laptop.singbox.json
```

For just URI strings (v2rayN and simpler clients):

```bash
SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml \
./scripts/new-client.sh --emit-uri laptop
```

For AmneziaWG, `new-client.sh` prints a private key — hand it to the
device through a secure channel and put it on the device, then forget it.
For P1 XHTTP client profiles, use the nginx public port
`nginx_xhttp_public_port` (`8443` by default), not the localhost Xray inbound
port `nginx_xhttp_port`.

## 8. External health check

```bash
SNI_TARGET=www.cloudflare.com ./scripts/healthcheck.sh

IP=$(PROVIDER=upcloud ENV=prod ./scripts/terraform-env.sh output -raw server_ipv4)
curl -fsS --resolve "vpn.example.com:8443:${IP}" \
  "https://vpn.example.com:8443/"
```

Then connect with the real client and run a real-life traffic test (curl
through the tunnel; speedtest if useful).

## 9. Recurring operator-side automation

Add to your operator's cron / launchd:

```bash
# Every 30 min — external IP reachability probe (catches IP burns early)
*/30 * * * *  cd ~/GitRep/ripdpi-vpn-deploy && make burn-check >> /tmp/vpn-burn.log 2>&1

# Every 2 min — authenticated protocol quorum (requires managed sentinels)
*/2 * * * *   cd ~/GitRep/ripdpi-vpn-deploy && LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml GREEN_ENV=spare make watch-spare >> /tmp/vpn-spare.log 2>&1

# Daily — encrypted backup of TF state to ~/.config/vpn-provision/state-backups/
@daily       cd ~/GitRep/ripdpi-vpn-deploy && make backup-state >> /tmp/vpn-tfstate-backup.log 2>&1
```

The VPS itself runs a local watchdog every 5 minutes (the `watchdog`
Ansible role) that pushes alerts to ntfy.sh / Pushover when probes fail.
Set `watchdog_secrets.ntfy_topic` in your secrets file before deploy.
The local watchdog covers process, listener, and configuration state only. Configure at least two client-path sentinels per `docs/PROTOCOL-LIVENESS.md` before treating liveness as an infrastructure-rotation signal.

On a filtered probe host, install daily active-target ASN/path monitoring with `make install-operator-crons REALITY_TARGET_VANTAGE=filtered-cohort-a`. The label must describe a technical cohort, not a carrier, operator, or geography. See `docs/REALITY-TARGET-MONITORING.md` for the two-strike alert and acknowledgement flow.

## 10. Optional — split the age key for k-of-n recovery

```bash
./scripts/age-recovery-split.sh 2 3
```

Distributes 2-of-3 Shamir shares; any 2 shares can reconstruct the age
private key. See `docs/AGE-RECOVERY.md` for storage discipline.

## What's next

- `docs/RUNBOOK-rotate.md` — rotate UUIDs / shortIds / peer keys
- `docs/RUNBOOK-rollback.md` — config rollback, binary rollback, blue-green
- `docs/RUNBOOK-incident.md` — IP burned / key leaked / panel exposed
- `docs/RUNBOOK-restore.md` — restore from restic backup after host loss
- `docs/RUNBOOK-add-fallback.md` — add a second VPS in a different ASN

Read `docs/CDN-DECISION.md` before you reach for Cloudflare.
