# operations/deployment-readiness-followups Specification

## Purpose
Keep every operator deploy path reviewable and bound to the intended
environment, keep decrypted secrets off disk after an operation stops, and keep
host builds, host images and nginx logs inside their documented boundaries.
Keep terminal deployment reviews responsive to stop signals without weakening
operator approval or secrets cleanup.

## Requirements

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

#### Scenario: A handled signal reaches a worker during review

- **WHEN** SIGINT, SIGQUIT, SIGTERM or SIGHUP reaches a worker while either vpnd review awaits terminal input
- **THEN** the review MUST stop without a terminal answer and the command MUST exit with 128 plus the first handled signal
- **AND** it MUST run secrets cleanup once before exit and MUST NOT perform the gated mutation

#### Scenario: Signal and approval become ready together

- **WHEN** a handled signal and an affirmative terminal answer are ready at the same review boundary
- **THEN** the signal MUST win and no gated mutation may start

#### Scenario: Terminal input remains the only authority

- **WHEN** the review reads empty, invalid, partial or queued terminal input, or standard input is a pipe
- **THEN** empty input MUST refuse, invalid input MUST prompt again, and partial input MUST remain interruptible
- **AND** each confirmation MUST consume only its own terminal line; piped input MUST NOT authorize mutation

#### Scenario: A signal was inherited as ignored

- **WHEN** a review starts with an ignored terminal signal, including SIGHUP under nohup
- **THEN** that signal MUST remain ignored throughout the review and subsequent Make steps

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

The AmneziaWG role MUST build amneziawg-go with one pinned Go release whose
archive digest it verifies before extraction, and with `GOTOOLCHAIN=local`. It
MUST refuse an architecture without a pinned digest before the download. The
real-VPS AWG sentinel MUST NOT install `resolvconf`.

#### Scenario: An Ubuntu 24.04 host

- **WHEN** the distribution Go is older than the pinned source requires
- **THEN** the build uses the verified pinned toolchain and downloads no other

### Requirement: REQ-DRF-IMAGE — Supported host operating systems

Hetzner, Vultr and Scaleway image validation MUST admit only Debian 13 and
Ubuntu 24.04 images. `site.yml` MUST refuse a host older than Debian 13 or
Ubuntu 24.04 before any host change.

#### Scenario: A Debian 12 tfvars file

- **WHEN** a Hetzner tfvars file selects `debian-12`
- **THEN** Terraform validation refuses the plan

### Requirement: REQ-DRF-BEARERLOG — No bearer paths in nginx-xhttp logs

The nginx-xhttp port-80 redirect servers and the Snell evaluation location MUST
disable access logging and send error logging to `/dev/null` at `crit`.

#### Scenario: A client sends a bearer path over plain HTTP

- **WHEN** a request for `http://<host>/<token>` reaches the redirect server
- **THEN** nginx redirects it and writes no log line that contains the path
