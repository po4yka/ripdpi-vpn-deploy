# Security policy

## Reporting

This repo deploys **active network infrastructure**. Some classes of issue, if
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

### Non-critical — public intake

Human-created public issues are intake-only and are closed automatically. A
maintainer may convert useful, non-sensitive details into a Git-native task.
Contributors can also submit a focused pull request for:

- Template misconfigurations that the validators didn't catch.
- Role hardening suggestions (sysctl, systemd unit, capability drops).
- Documentation gaps in the `docs/how-to/` runbooks.
- CI gate gaps (a class of bug we should be testing for and aren't).
- Suggestions for stronger gitleaks rules.

## Daily dependency and image checks

`daily-security.yml` is scheduled each day at 06:17 UTC and supports manual dispatch.
The vulnerability-only filesystem scan includes Python requirements, npm locks
with development dependencies, and Go modules. It reports all severities,
including unfixed dependency findings. The existing image inventory covers
Molecule and both observer architectures; its fixable HIGH/CRITICAL gate stays
unchanged. No image is rebuilt and no live host or fleet credential is used.

An automated issue is assigned to the repository owner for findings or scan
failures. A comment notifies subscribers when the result changes. Identical
results cause no issue writes. A complete successful clean run closes the issue;
missing or malformed reports cannot count as recovery. Reports remain attached
to the workflow run for 14 days; issues contain counts and run links only.

For email delivery, enable email for participating notifications in GitHub
account settings and keep the issue subscription enabled. The workflow needs
no SMTP credentials. A failed notification job remains visible as a failed run.
Only runs of the current default-branch revision update the shared issue.
Manual feature-branch and historical runs retain reports without changing it.
Reports belong to one run attempt. To retry a complete scan, use **Re-run all
jobs**; partial retries cannot use earlier clean reports to close the issue.

For manual runs, retries, report interpretation and the separate host audit,
follow [security checks](../docs/how-to/security-checks.md). Host audit output
stays private; do not attach raw server reports to the public notification issue.

## Disclosure

After we've shipped a fix:

1. Public release notes describe the issue class generically (no
   reproducer until the median operator can update).
2. After 30 days, full reproducer can be added to the relevant
   `docs/how-to/` runbook for future operators.

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

1. `docs/how-to/incident.md` — decision matrix
2. `docs/how-to/rotate.md` — credential rotation procedures
3. `docs/how-to/restore.md` — disaster recovery from encrypted backup

These are the same runbooks we'd point a reporter at after triage.
