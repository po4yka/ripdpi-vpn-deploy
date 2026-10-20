# Change: Close deployment readiness follow-up findings

Task ID: `OPS-1792512787218003`

## Why

The pre-deployment audit that produced `ANS-1792499727513191` also found
operator-path and host-boundary defects that its runtime repair left out:

- `scripts/blue-green.sh` runs `make plan` and `make apply` back to back, and
  `make dry-run` and `make deploy` back to back. `make promote-spare` uses the
  same script. `vpnd deploy` applies its plan without review, and
  `vpnd reconverge` deploys after its dry-run without review.
- `make blue-green`, `make promote-spare` and `make watch-spare` set
  `BLUE_ENV` from `ENV`, which defaults to `prod`. The rollback runbook tells
  operators to set `BLUE_ENV`, and the Makefile silently discards it.
- The deploy controller converges every selected inventory host with one
  decrypted secrets file. It does not compare the host `env` with `ENV`, so an
  inventory with several environments can receive the wrong secrets.
- `scripts/destroy.sh` compares the typed hostname with the raw tfvars line
  when `server_name` is empty or not a quoted string, exits without a message
  when it is missing, and leaves the saved destroy plan in the provider root
  when the operator declines or a later step fails.
- The ordinary re-deploy recipe in `docs/RUNBOOK-deploy.md` leaves decrypted
  secrets on disk after a failed or interrupted preflight or deploy block.
- The AmneziaWG role and the real-VPS AWG sentinel build Go code with the
  distribution toolchain and no explicit `GOTOOLCHAIN`, so the go.env default
  can download a different toolchain during deployment. The sentinel also
  installs `resolvconf`, which removes `systemd-resolved` on Debian 13.
- Hetzner (`debian-12`), Vultr (Debian 12, Ubuntu 22.04) and Scaleway
  (`debian_bookworm`) still admit images whose nftables cannot run
  `destroy table`, so the firewall role fails after host changes start.
- The nginx-xhttp port-80 redirect servers and the Snell evaluation location
  can write a bearer path segment to an nginx log.

## What Changes

- Blue-green requires a typed `yes` after the green plan and after the green
  dry-run. `vpnd deploy` and `vpnd reconverge` require terminal confirmation
  after the plan or dry-run; `--yes` does not skip this review.
- The Makefile uses `BLUE_ENV` when it is set, else `ENV`, and refuses an
  explicit `ENV` that disagrees with `BLUE_ENV`.
- The deploy controller refuses, before it reads secrets, a selection that
  contains a host whose inventory `env` is not `ENV`.
- `destroy.sh` refuses, with a message, a tfvars file without a quoted
  `server_name`, and removes its saved plan on every exit.
- The re-deploy recipe cleans decrypted secrets after a failed preflight and
  after every deploy-block exit.
- AWG and sentinel Go builds run with `GOTOOLCHAIN=local`; the sentinel no
  longer installs `resolvconf`.
- Provider image allowlists admit only Debian 13 and Ubuntu 24.04 images, and
  the firewall role refuses an older host before it changes nftables.
- The port-80 redirect servers and the Snell location write no access or
  error log entries.

## Capabilities

### New Capabilities

- `operations/deployment-readiness-followups`: operator review pauses, source
  and target environment binding, destroy and runbook secret hygiene, AWG build
  toolchain, supported host images and bearer-path log privacy.

### Modified Capabilities

- None. Existing deployment, provider and transport contracts remain in force.

## Impact

- Scripts: `blue-green.sh`, `deploy-controller.py`, `destroy.sh`, Makefile
  blue-green, promote-spare and watch-spare recipes.
- vpnd: `deploy` and `reconverge` command handlers.
- Ansible roles: `amneziawg`, `real-vps-awg-nat`, `firewall`, `nginx-xhttp`.
- Terraform: Hetzner, Vultr and Scaleway image validation and examples.
- Docs: `RUNBOOK-deploy.md`, `RUNBOOK-rollback.md`, folder notes.
- A Hetzner root that omitted `image` now defaults to `debian-13`; its next
  plan shows a server replacement for review. A tfvars file with a removed
  image refuses validation. This change authorizes no deployment.
