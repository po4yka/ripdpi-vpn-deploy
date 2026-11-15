## Context

`proposal.md` gives the motivation. The watchdog role renders `provider: ntfy` and a public URL by default, and `group_vars/all.yml` enables the role. `scripts/burn-check.sh` has default third-party vantage points and `scripts/install-operator-crons.sh` schedules it every 30 minutes. The reputation and ASN scripts use plain DNS and plain whois. `scripts/probing-summary.sh` writes below `reports/` in the repository.

## Goals / Non-Goals

- Goal: no default sends a node address or hostname to a party outside the fleet.
- Goal: a tracked file cannot gain a public address without a failing test.
- Non-goal: a new private notification service. The existing private monitoring pipeline stays the recommended path.
- Non-goal: rewriting the public Git history. An address that is already public needs node recreation, which is an operator action.

## Decisions

- The watchdog default becomes `provider: none`. Rejected: keep the public service with a random topic, because the service still receives the address and hostname.
- The production refusal checks the destination host against the public service name. A self-hosted instance on another name passes.
- The alias is an operator-set value. The role reuses `observability_agent.node_id` when it is set, and refuses a configured destination that has no alias. Rejected: a hash of the hostname, because a hash of a guessable value is reversible.
- Scripts pass the token and URL to `curl --config -` on standard input, as `scripts/cascade-leg-probe.py` already does.
- The burn check keeps only the direct TCP probe by default. The third-party path and the UDP probe need a command-line option, so that an inherited environment variable cannot enable them. Rejected: delete the third-party path, because a manual run from a neutral network has value during an incident.
- Reputation lookups use DNS over HTTPS. The ASN lookup uses the DNS form of the same service over DNS over HTTPS, which removes the plain whois connection.
- Reports go below `${XDG_STATE_HOME:-$HOME/.local/state}/vpn-provision/`, which the operator cron logs already use. The file name uses the provider, environment and date.
- The address guard reads `git ls-files`, skips binary files, and uses `ipaddress` to select global addresses. The allowed list is a short committed file of public resolver and well-known service addresses, each with a reason.

## Contracts and ownership

- Ansible: `ansible/roles/watchdog/` defaults, templates and preflight; `ansible/group_vars/all.yml` comment.
- Scripts: the notification helper call sites, `burn-check.sh`, `install-operator-crons.sh`, `check-ip-reputation.sh`, `probe-asn.sh`, `asn-drift.sh`, `probing-summary.sh`.
- Secrets: no schema change. `watchdog_secrets.ntfy_topic` is needed only when the operator selects that provider.
- Tests: `tests/unit/test_repository_identifier_policy.py` owns the address guard and its allowed list.

## Risks / Trade-offs

- An operator who relied on the default loses alerts after the next deploy → the role prints one line that states that no destination is set, and the release note marks the break.
- The address guard can fail on an existing test fixture → the first run lists the present literals, and each one moves to a documentation range or to the allowed list with a reason.
- DNS over HTTPS can be blocked on the operator network → the check fails closed and reports it; it does not use cleartext.

## Migration Plan

Merge, then deploy the watchdog role through the ordinary dry-run and deploy transaction. Run `make install-operator-crons` again on the operator workstation. Rollback is a revert of the change and a second deploy. Gates: the focused unit tests, `make snapshot-check`, `make molecule-test ROLE=watchdog`, `make shellcheck`, and one `make check` before handoff.
