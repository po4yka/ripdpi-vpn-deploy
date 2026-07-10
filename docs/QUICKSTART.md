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
cd ~/GitRep/vpn-deploy
cp terraform/providers/upcloud/environments/prod.tfvars.example \
   terraform/providers/upcloud/environments/prod.tfvars
$EDITOR terraform/providers/upcloud/environments/prod.tfvars
```

Required: `zone`, `plan`, `storage_template`, `admin_ssh_public_key`
(paste content of `~/.ssh/vpn_deploy.pub`), `allowed_ssh_cidrs` (your
operator IP, **never** `0.0.0.0/0`).

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

# Re-validate any candidate end-to-end (8 steps including ASN cross-check).
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
pins (`amneziawg_go_version`, `amneziawg_tools_version`), AmneziaWG H1–H4
obfuscation params, restic password.

Add your first device:

```bash
SOPS_FILE=~/.config/vpn-provision/prod.secrets.yaml \
./scripts/new-client.sh phone
```

## 5. Encrypt the secrets file

```bash
sops --encrypt --age "$RECIPIENT" \
  ~/.config/vpn-provision/prod.secrets.yaml \
  > ~/.config/vpn-provision/prod.secrets.sops.yaml

shred -u ~/.config/vpn-provision/prod.secrets.yaml
```

From now on edit only the encrypted file: `sops ~/.config/vpn-provision/prod.secrets.sops.yaml`.

## 6. Deploy

```bash
make init
make validate          # must pass before continuing
make decrypt           # writes /tmp/vpn-prod.secrets.yaml
make validate-target   # pre-deploy probe of REALITY target
make plan
make apply
make inventory
make wait              # 30–120 s, waits for cloud-init
make dry-run           # ansible --check --diff; review what will change
make deploy            # real run
make verify            # post-deploy gates
make smoke-test        # end-to-end real-traffic test through each profile
make clean             # shred /tmp/vpn-prod.secrets.yaml
```

If `dry-run` shows changes you didn't expect, stop and investigate. Don't
proceed to `deploy`.

## 7. Generate a client config

For a full sing-box JSON with selector + urltest covering every enabled
profile (recommended for sing-box / NekoBox / husi):

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
  "https://vpn.example.com:8443/health"
```

Then connect with the real client and run a real-life traffic test (curl
through the tunnel; speedtest if useful).

## 9. Recurring operator-side automation

Add to your operator's cron / launchd:

```bash
# Every 30 min — external IP reachability probe (catches IP burns early)
*/30 * * * *  cd ~/GitRep/vpn-deploy && make burn-check >> /tmp/vpn-burn.log 2>&1

# Every 2 min — authenticated protocol quorum (requires managed sentinels)
*/2 * * * *   cd ~/GitRep/vpn-deploy && LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml GREEN_ENV=spare make watch-spare >> /tmp/vpn-spare.log 2>&1

# Daily — encrypted backup of TF state to ~/.config/vpn-provision/state-backups/
@daily       cd ~/GitRep/vpn-deploy && make backup-state >> /tmp/vpn-tfstate-backup.log 2>&1
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
