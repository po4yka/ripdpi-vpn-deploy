# Change: Rotate Xray logs without restarting Xray and tighten its runtime settings

Task ID: `ANS-1795163234714653`

## Why

The Xray log rotation policy ran a `postrotate` recovery that restarted Xray. On the live TCP nodes the journal shows Xray starting at exactly 00:00 UTC on four consecutive days, on both nodes in the same minute. Every client session dropped daily, and both TCP paths dropped together. Three specifications required that restart because the pinned Xray cannot reopen its logs. Xray appends through an `O_APPEND` descriptor, so in-place truncation rotates the files with no restart. The same audit found that sniffing replaced client destinations with sniffed names, that a 4 KB per-connection buffer had no recorded reason, and that the unit lacked several sandbox options and allowed as many open files as the whole host.

## What Changes

- Xray log rotation truncates the log files in place and runs no script. It no longer restarts or recovers Xray on any profile. BREAKING for the previous restart contract.
- Xray sniffing is used for routing only on the REALITY and XHTTP inbounds. The destination a client requested is sent to egress unchanged.
- The per-connection `bufferSize` override is removed; Xray uses its default.
- The Xray unit adds `ProtectProc=invisible`, `PrivateDevices`, `ProtectClock`, `ProtectKernelLogs`, `ProtectHostname` and `UMask=0077`, and its open-file limit is below the host `fs.file-max`.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `audit-boundary-correctness`: REQ-AUDIT-GENERATION no longer recovers a frontend on rotation.
- `ansible/deployment-readiness-runtime`: REQ-DRR-ROTATE forbids a rotation restart; new REQ-DRR-XRAY-RUNTIME covers sniffing, the unit sandbox and the file limit.
- `security/ansible-role-p1-safety`: REQ-P1-XRAY rotation scenario keeps the running process.

## Impact

- Ansible roles `monitoring` (logrotate policy) and `xray` (configuration and unit templates), their snapshots, unit tests and native rotation tests.
- No Terraform, secrets schema, `vpnd` or client contract changes. The next deploy restarts Xray once to load the new configuration and unit.
