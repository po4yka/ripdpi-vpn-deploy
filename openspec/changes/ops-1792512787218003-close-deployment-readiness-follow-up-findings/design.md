## Context

See proposal.md. The canonical Make path is fail-closed: `plan`, review,
`apply`, host pinning and ownership, `dry-run`, review, `deploy`, `verify`.
The defects are in wrappers that chain these steps, in environment selection,
and in boundaries that the runtime repair `ANS-1792499727513191` left out.

## Goals / Non-Goals

- Goal: add the missing review, binding or cleanup at the owning wrapper with
  the smallest change, plus a regression that fails on the parent commit.
- Non-goal: change the geodata activation script. `site.yml` enables geodata
  only with REALITY or cascade ingress, and its stage-only predicate covers
  REALITY; no profile enables cascade ingress alone, so the direct restart is
  unreachable on every profile.
- Non-goal: the subscription native logging regression. It belongs to the open
  task `SEC-1792301529650686`.
- Non-goal: deploy, apply, destroy or touch any host or provider.

## Decisions

- Review: blue-green reuses its `confirm` helper. vpnd uses the existing
  terminal-bound `confirm(..., default=False)` inside the cleanup boundary, so
  a declined or failed review still runs `make clean`. Rejected: honoring
  `--yes`, because unattended use then applies an unreviewed plan again.
- Blue environment: resolve `$(or $(BLUE_ENV),$(ENV))` in the three recipes,
  and refuse when `$(origin ENV)` is command line or environment and differs.
  Rejected: always requiring `BLUE_ENV`, because it breaks the documented
  `make promote-spare OTP=...` path.
- Host environment: compare inventory metadata in the controller, which already
  owns host selection and runs before the secrets read. Rejected: a `site.yml`
  assert, because the controller passes no `ENV` to Ansible and the check would
  run after secrets were copied.
- Destroy: parse only a quoted `server_name` value and refuse when it is absent,
  in both modes, before Terraform. Remove `${TF_DIR}/${PLAN_PATH}` in the
  existing EXIT trap for the ordinary path; the staging path keeps its private
  directory cleanup.
- Runbook: the preflight block cleans only on a non-zero exit, so the reviewed
  plaintext remains for the deploy block; the deploy block uses the guarded
  subshell from the rotation runbook.
- Toolchain: reuse the repository Go pin (mise and the source-candidate lab,
  1.27.1, digests checked against go.dev), download it with `get_url`
  checksum verification, extract it under `/opt/ripdpi-go`, and put it first
  on the build step `PATH` with `GOTOOLCHAIN=local`. Rejected: distribution Go
  with `GOTOOLCHAIN=local`, because Ubuntu 24.04 Go 1.22.2 cannot build the
  pinned source; rejected: keeping `auto`, because it fetches an unpinned
  toolchain during deployment. The sentinel installer already builds with
  `GOTOOLCHAIN=local` and vendored modules.
- Images: Hetzner admits `debian-13` and `ubuntu-24.04` (default
  `debian-13`); Vultr keeps OS IDs 2284 and 2625; Scaleway keeps
  `ubuntu_noble`. No unverified Scaleway Debian 13 label is added. The OS
  assertion is a `site.yml` pre-task on gathered facts. Rejected: an assertion
  in the firewall role, because playbooks without fact gathering and the
  firewall task-order contracts also run that role.
- Logs: follow the subscription vhost pattern with `access_log off` and
  `error_log /dev/null crit`. Rejected: a categorical log format for port 80,
  because the role has no format to reuse and the redirect needs no audit.

## Risks / Trade-offs

- An unattended `vpnd --yes deploy` now stops at the plan review. This is the
  intended contract; the Make path remains for scripted use.
- A Hetzner node created from the old default plans a replacement. That node
  could not converge its firewall, and plan review shows the replacement.
