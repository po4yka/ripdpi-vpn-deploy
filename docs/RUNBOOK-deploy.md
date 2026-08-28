# Runbook — deploy

Two flows: **first-time deploy** (handled by `QUICKSTART.md`) and
**re-deploy after editing configs** (this runbook).

For the currently deployed release, provider-to-role mapping, observed gate
results, and unresolved operator limitations, start with
[DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md).

## Re-deploy after a config or secrets edit

When you've edited a role template, group_vars, or the secrets file, and
want to push the change to an existing VPS:

```bash
export ANSIBLE_SSH_PRIVATE_KEY_FILE=~/.ssh/vpn_deploy
make decrypt           # writes the configured $(SECRETS_FILE), mode 0600
make validate          # gitleaks + lint must pass
make dry-run           # ansible --check --diff — read every changed line
make deploy
make verify
make source-drift      # normally repeated by deploy/verify; useful alone
make clean
```

If `dry-run` shows changes you didn't expect, **stop**. Investigate.
`deploy` refuses a dirty checkout so the live manifest can name an immutable
source revision. Documentation-only commits do not force convergence: the
parity gate compares a digest of deployable paths rather than the whole tree.
Don't push. The most common cause is a forgotten edit on a different
branch, or a role that's accidentally redownloading the binary because
the version pin moved.

Both commands freeze the canonical `ansible/inventory/generated.ini` once.
An empty `ANSIBLE_LIMIT` selects every `vpn` host; exact host aliases,
canonical cohort groups such as `vpn-p1-web`, and comma unions are accepted.
Globs, intersections, exclusions, external pattern files and unknown names
are rejected. `HOSTS`, `ENV` and `PROVIDER` do not independently narrow this
inventory selection. Approved `ANSIBLE_EXTRA_VARS_FILE` inputs still require
an explicit limit and apply before readiness.

All selected keys, known-host pins and private inputs are checked before any
SSH operation. The default pin file is `~/.ssh/known_hosts`; override it with
`INSPECT_KNOWN_HOSTS`. Deployment uses strict host-key checking, no ambient SSH
config, proxies, agent or multiplexed sessions. It does not enroll keys or
migrate SSH. The separate Terraform `make wait` command retains its first-boot
policy. Bootstrap errors and session/deadline failures stop the entire selected
deployment without printing raw cloud-init output.

Readiness, convergence and the automatic source-drift check use the same
private inventory and transport snapshots. Canonical all/vpn/cohort variables
are loaded per host before runtime metadata, secrets and approved overrides;
ambient host/group variable files, callbacks and plugin paths are excluded.
Ansible also discovers plugins beside playbooks and roles independently of
configured paths: custom discovery directories there, symlinked role paths,
and `ansible/playbooks/roles` shadow roles are unsupported and rejected before
SSH. Keep extensions in a separately reviewed source change rather than these
ambient locations. `ANSIBLE_DEBUG` is rejected; normal Ansible check/diff output
remains visible. A dirty or changed source after waiting prevents deployment.

`infra-v1.0.0` also has a known check-mode-only failure in firewall SSH-port
discovery. Do not weaken or skip the gate. Confirm the failure matches the
record in [DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md#current-operator-limitations)
and fix the source before treating `make dry-run` as green.

## Re-deploy after a Terraform change (instance type, zone, firewall)

```bash
make plan              # READ THE PLAN
# If it shows "destroy and recreate" on the server, STOP — that's
# infrastructure rollback, not config rollback. See RUNBOOK-rollback.md
# § "blue-green replacement".
make apply             # only if the plan was non-destructive
make inventory
# Restore and verify the local Tailscale SSH HostName override described in
# DEPLOYMENT-STATUS.md before the next Ansible command.
make wait
make deploy
make verify
```

`prevent_destroy = true` on `upcloud_server` blocks accidental destruction
in `terraform apply`. To deliberately destroy, run `make destroy`: the
wrapper lifts that lifecycle block through a temporary override file so
the tracked source stays clean.

## Add a new client device

```bash
SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml \
./scripts/new-client.sh --emit-uri laptop

make decrypt
make rotate-credentials      # re-renders xray/hysteria/awg configs
make verify
make clean
```

Hand the AmneziaWG private key (printed by the script) to the device
through a secure channel. Wipe it from your terminal scrollback.

## Selective deploy with tags

```bash
# Just push a config-only change to xray
make deploy ANSIBLE_TAGS=xray

# Just refresh nftables
make deploy ANSIBLE_TAGS=firewall

# Just re-render fallback transports
make deploy ANSIBLE_TAGS=transport
```

The `tags:` field on each role in `playbooks/site.yml` enumerates what's
selectable. `always` tags (`baseline`, `firewall`) run regardless.

## Staging first

```bash
ENV=staging make plan apply inventory wait dry-run deploy verify
# Test with a real client from a representative network
ENV=prod    make plan apply inventory wait dry-run deploy verify
```

Staging uses a different VPS, different REALITY keypair, different SNI
target, and ideally a different operator SSH key. Don't ever test new
Xray pre-release builds against prod users.

## What "verify" actually checks

`ansible/playbooks/verify.yml` asserts:

- cloud-init bootstrap marker present
- nftables config syntactically valid
- Xray config valid (`xray run -test -config`) and service active
- TCP/443 listening
- nginx -t passes (if P1 enabled)
- Hysteria service active and UDP/443 listening (if P2 UDP enabled)
- AmneziaWG interface up (if P2 AWG enabled)
- SSH refuses passwords and root login

If any of these fail, `make verify` exits non-zero. Don't sign off on a
deploy until verify is green.
