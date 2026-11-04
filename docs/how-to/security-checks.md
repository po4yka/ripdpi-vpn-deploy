# Run repository security checks and host audits

> **Status:** Current · **Type:** how-to · **Tier:** — · **Reviewed:** 2026-11-04

## Purpose and scope

Use the daily repository workflow to find new dependency and pinned-image
advisories. Use the separate host audit to collect private reports from approved
VPN nodes. These checks have different inputs and evidence.

The [security policy](../../.github/SECURITY.md#daily-dependency-and-image-checks)
defines the daily schedule, scan scope, severity policy and notification rules.
Repository scans do not inspect installed packages or service configuration on
live hosts. The `security_audit` role runs through `security-audit.yml`, outside
`site.yml`; an ordinary deploy does not run it or install an audit timer.

## Preconditions

For repository checks, use the current default branch and an account that can
run the workflow and read its artifacts. Keep the owner issue subscription
enabled. GitHub account settings control email; the workflow needs no SMTP secret.

For a host audit, use the [pinned workstation](../../CONTRIBUTING.md#first-time-setup)
and a clean checkout of the reviewed source. Review any ignored `.fleet.mk`
configuration before use. Read the
[local operator kit](local-operator-kit.md). Prepare these private inputs:

- A frozen inventory whose `vpn` group contains exactly the approved hosts.
  Keep its source reference and checksum.
- A reviewed SSH configuration for those inventory addresses. Use the selected
  identity and host-key pins, strict host-key checking, batch authentication,
  and no ambient agent, proxy or multiplexed session. An approved host-key alias
  must bind to the same host in the recorded public and Tailnet contexts.
- Owned mode-0700 evidence directories and mode-0600 configuration files.
  Keep raw reports, preview diffs and diagnostics private.

The audit playbook does not load VPN secrets. It does not need `make decrypt`.
Lynis is enabled by default. The role can refresh APT metadata and install Lynis
and its package dependencies. AIDE, rkhunter and ClamAV remain deferred controls.

## Authorization

Workflow dispatch can use registry/advisory services and update the owner issue.
Host preview and audit use real SSH and `sudo`; the audit writes reports and can
install Lynis. Obtain approval for the exact hosts and these changes under the
[repository decision boundaries](../../AGENTS.md#decision-boundaries).
This procedure does not authorize changes to credentials, SSH, firewall rules
or transport configuration.

## Steps

### Run and review the repository workflow

1. Open the repository's `daily-security` workflow. Run it manually from the
   current default branch, or inspect its scheduled run.
2. Review the `dependencies`, `images` and `notify` results. Download the current
   attempt's dependency SARIF, image inventory and every image SARIF before
   their retention period ends. The Security tab also receives SARIF results.
3. Read the owner issue, **Daily security checks need attention**. It contains
   counts and run links. Use the retained reports for finding details.
4. After a failed or incomplete scan, use **Re-run all jobs**. A partial retry
   cannot reuse an earlier attempt's clean reports to close the issue.
5. If the default branch has advanced, start a new run from its current revision.
   A historical rerun keeps its old SHA and cannot update the shared issue.

New or changed problems create or update the issue. Identical results cause no
issue writes. Only a complete successful clean run closes it. Missing or invalid
reports are a failure, not recovery. A failed notification job is visible in
Actions even when it cannot write an issue. If an old artifact link has expired,
use the issue's **Latest daily runs** link.

### Run the host audit

Use one pinned Bash session at the repository root. Replace the example paths
with the reviewed private inputs and an existing owned evidence directory.

```bash
set -euo pipefail
umask 077
export AUDIT_INVENTORY=/private/operator/frozen-inventory.ini
export AUDIT_SSH_CONFIG=/private/operator/audit-ssh.conf
export AUDIT_EVIDENCE_DIR=/private/operator/audit-evidence
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
export ANSIBLE_INVENTORY="$AUDIT_INVENTORY"
export ANSIBLE_SSH_ARGS="-F \"$AUDIT_SSH_CONFIG\""
export ANSIBLE_HOST_KEY_CHECKING=True
export ANSIBLE_FORKS=3
unset ANSIBLE_SKIP_TAGS ANSIBLE_RUN_TAGS ANSIBLE_LOG_PATH
```

1. List the effective hosts. Confirm that the complete list matches approval.

   ```bash
   mise exec -- ansible-playbook ansible/playbooks/security-audit.yml --list-hosts
   ```

   `make security-audit` runs on the complete `vpn` group of `ANSIBLE_INVENTORY`.
   Its recipe does not use `ANSIBLE_LIMIT` or `ANSIBLE_EXTRA_VARS_FILE`.
   `ENV` and `HOSTS` do not narrow this audit. Do not use them as scope controls.

2. Preview the same playbook and inventory.

   ```bash
   mise exec -- ansible-playbook ansible/playbooks/security-audit.yml --check --diff \
     > "$AUDIT_EVIDENCE_DIR/preview.log" 2>&1
   ```

3. Review the private preview before mutation. Expect report files and, when
   absent, Lynis and its package dependencies. Stop on unrelated changes.
   Check mode skips Lynis collection and both execution and publication of the
   new systemd assessment. It produces no scan acceptance receipt.

4. Confirm that the frozen inventory and SSH configuration still match the
   reviewed inputs, then apply the audit.

   ```bash
   env -u MAKEFILES -u MAKEFLAGS -u GNUMAKEFLAGS -u MFLAGS \
     mise exec -- make security-audit ANSIBLE_INVENTORY="$AUDIT_INVENTORY" \
     ANSIBLE_SSH_ARGS="$ANSIBLE_SSH_ARGS" \
     > "$AUDIT_EVIDENCE_DIR/apply.log" 2>&1
   ```

5. Use each host's final output path to verify its new reports. Seal closed raw
   evidence and update the private catalog under the
   [operator kit protection and recovery rules](local-operator-kit.md#protection-and-recovery).

## Verification

Reports are under `/var/log/ripdpi-vpn-deploy/security-audit/<timestamp>/`.
The role retains listening ports, failed systemd units, nftables rules, effective
sshd configuration, selected sysctls and deferred-control notes.

For `systemd-security.txt`, verify a fresh file owned by `root:root` with mode
0640. Its command must be `systemd-analyze security --no-pager`. Read `rc`, stdout,
stderr and the module diagnostic. A completed assessment needs successful command
execution and a nonempty unit table. A nonzero or unavailable result is retained
as diagnostic evidence and must not be called a completed assessment.
Isolation scores describe unit configuration, not a vulnerability verdict.

Lynis uses a unique private `lynis-*` directory with `report.dat`, `lynis.log`
and a mode-0600 `collection.json` receipt. Read `collection_success` and warning
counts. The default audit is non-blocking: a successful playbook is not a clean
security verdict. With `fail_on_high_findings` enabled, the existing gate requires
fresh successful Lynis collection and zero warning records. It refuses that gate
when Lynis collection is disabled.

Check failed units and compare the relevant pre/post configuration, core manifest
and boot identity. These checks do not replace authenticated VPN traffic or
whole-fleet acceptance. The [deployment snapshot](../reference/deployment-status.md#security-reporting-update-2026-11-04)
records the dated three-node report acceptance and its limits.

## Rollback

The host audit does not activate service configuration. Retain failed reports as
diagnostic evidence. A reviewed source revert changes future audit collection;
reverting the repository workflow stops future scheduled checks. Installed audit
packages remain installed after a source revert. Existing reports and issue
history remain evidence.

## Evidence to record

- Exact source revision, audit-role identity and approved host set; keep private
  inventory, SSH context and pin references in the operator kit.
- Host list, preview, apply results and fresh report paths, ownership, modes,
  command results, Lynis collection status and warning counts.
- Pre/post host checks and their scope. Keep core deployment and client traffic
  claims separate from report collection.
- Workflow revision, run attempt, expected reports, job results and issue writes.
  Record unobserved delivery separately; a local notifier test is not a real
  GitHub notification.
- Encrypted raw evidence and a categorical catalog receipt. Do not publish
  endpoints, inventory, credentials or raw host diagnostics.
