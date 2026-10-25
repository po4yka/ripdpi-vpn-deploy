## Purpose

Keep terminal deployment reviews responsive to stop signals without weakening
operator approval or secrets cleanup.

## MODIFIED Requirements

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
