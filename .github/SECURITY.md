# Security policy

## Reporting

This repo deploys **active VPN infrastructure**. Some classes of issue, if
disclosed publicly, hand attackers an immediate operational advantage.
Use the right channel.

### Critical — private channel only

Do **NOT** open a public issue for these:

- Suspected REALITY private key leak
- Active-probing pattern observed against a deployed listener
- IP / ASN appears burned (TCP/443 fails from many vantages)
- Subscription URL leaked publicly
- Operator workstation compromise
- Any issue where reporting it openly would help an active attacker

Channel:

- Preferred: open a **private security advisory** at
  <https://github.com/po4yka/ripdpi-vpn-deploy/security/advisories/new> —
  it lets the maintainer triage privately and publish a fix
  alongside a CVE if warranted.
- Fallback: encrypted DM to the maintainer (Signal / age-encrypted
  email). The maintainer's public age recipient lives in repo
  metadata; rotate via the same channel once contact is established.

Expected acknowledgement window: **24 hours**.

### Non-critical — public issues

These are fine to open as a normal issue with the `security` label:

- Template misconfigurations that the validators didn't catch.
- Role hardening suggestions (sysctl, systemd unit, capability drops).
- Documentation gaps in `docs/RUNBOOK-*.md`.
- CI gate gaps (a class of bug we should be testing for and aren't).
- Suggestions for stronger gitleaks rules.

## Disclosure

After we've shipped a fix:

1. Public release notes describe the issue class generically (no
   reproducer until the median operator can update).
2. After 30 days, full reproducer can be added to the relevant
   `docs/RUNBOOK-*.md` for future operators.

## What this repo treats as out-of-scope

Anything that is true in *every* network-attached system and not specific
to our deployment:

- The operator's age private key being weakly stored
- The operator running outdated Xray / Hysteria binaries because they
  ignored Dependabot PRs for 6 months
- Compromised CI runners (github-hosted; outside our control)
- BGP-level attacks on the upstream provider

## Operator-side runbooks for incident response

When you suspect any of the critical-class events:

1. `docs/RUNBOOK-incident.md` — decision matrix
2. `docs/RUNBOOK-rotate.md` — credential rotation procedures
3. `docs/RUNBOOK-restore.md` — disaster recovery from encrypted backup

These are the same runbooks we'd point a reporter at after triage.
