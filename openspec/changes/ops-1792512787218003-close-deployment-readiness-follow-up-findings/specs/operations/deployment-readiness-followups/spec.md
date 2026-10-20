## Purpose

Keep every operator deploy path reviewable and bound to the intended
environment, keep decrypted secrets off disk after an operation stops, and keep
host builds, host images and nginx logs inside their documented boundaries.

## ADDED Requirements

### Requirement: REQ-DRF-REVIEW — Review before apply and convergence

Blue-green MUST require a typed `yes` after the green Terraform plan and before
apply, and after the green dry-run and before deploy. `vpnd deploy` MUST
require terminal confirmation after `make plan` and before `make apply`.
`vpnd reconverge` MUST require terminal confirmation after `make dry-run` and
before `make deploy`. The global `--yes` flag MUST NOT skip these reviews.

#### Scenario: The operator declines the green plan

- **WHEN** blue-green finishes `make plan` for the green environment
- **AND** the operator does not type `yes`
- **THEN** the script exits non-zero without `make apply`

#### Scenario: vpnd runs without a terminal

- **WHEN** `vpnd --yes deploy` or `vpnd --yes reconverge` reaches its review
  and no terminal is available
- **THEN** the command fails before `make apply` or `make deploy`
- **AND** it still runs `make clean`

### Requirement: REQ-DRF-BLUEENV — Honor the selected blue environment

`make blue-green`, `make promote-spare` and `make watch-spare` MUST pass
`BLUE_ENV` when it is set, else `ENV`. They MUST refuse when `BLUE_ENV` is set
and an explicit `ENV` from the command line or environment differs from it.

#### Scenario: The operator follows the rollback runbook

- **WHEN** the operator runs `BLUE_ENV=prod-b make blue-green GREEN_ENV=green`
- **THEN** `blue-green.sh` receives `BLUE_ENV=prod-b`

### Requirement: REQ-DRF-HOSTENV — Bind convergence to ENV

The deploy controller MUST refuse, before it reads the decrypted secrets file,
when `ENV` is empty or any selected inventory host has an `env` that differs
from `ENV`.

#### Scenario: A multi-environment inventory

- **WHEN** the generated inventory holds `prod` and `staging` hosts
- **AND** the operator runs `make dry-run ENV=prod` without a limit
- **THEN** the controller refuses before secrets, SSH or Ansible

### Requirement: REQ-DRF-DESTROY — Destroy gate and plan hygiene

`destroy.sh` MUST refuse, with a message and before Terraform, when the tfvars
file has no quoted nonempty `server_name`. It MUST remove the saved destroy
plan from the provider root on every exit.

#### Scenario: The operator declines the destroy plan

- **WHEN** the operator answers anything other than `yes` to the final prompt
- **THEN** the script exits non-zero and no `<env>.destroy.tfplan` remains

### Requirement: REQ-DRF-RUNBOOK — Clean secrets after the re-deploy recipe

The ordinary re-deploy recipe MUST run `make clean` when its preflight block
fails or is interrupted, and on every exit of its deploy block. The deploy
block MUST keep the failing step's status.

#### Scenario: The preflight dry-run fails

- **WHEN** `make dry-run` fails in the preflight block
- **THEN** `make clean` runs last and the block exits with the dry-run status

### Requirement: REQ-DRF-GOTOOL — Local Go toolchain for host builds

The AmneziaWG role and the real-VPS AWG sentinel MUST build Go sources with
`GOTOOLCHAIN=local`. The sentinel MUST NOT install `resolvconf`.

#### Scenario: A source requires a newer Go release

- **WHEN** the pinned source declares a Go version newer than the host toolchain
- **THEN** the build fails without downloading a toolchain

### Requirement: REQ-DRF-IMAGE — Supported host operating systems

Hetzner, Vultr and Scaleway image validation MUST admit only Debian 13 and
Ubuntu 24.04 images. The firewall role MUST refuse a host older than Debian 13
or Ubuntu 24.04 before it changes nftables.

#### Scenario: A Debian 12 tfvars file

- **WHEN** a Hetzner tfvars file selects `debian-12`
- **THEN** Terraform validation refuses the plan

### Requirement: REQ-DRF-BEARERLOG — No bearer paths in nginx-xhttp logs

The nginx-xhttp port-80 redirect servers and the Snell evaluation location MUST
disable access logging and send error logging to `/dev/null` at `crit`.

#### Scenario: A client sends a bearer path over plain HTTP

- **WHEN** a request for `http://<host>/<token>` reaches the redirect server
- **THEN** nginx redirects it and writes no log line that contains the path
