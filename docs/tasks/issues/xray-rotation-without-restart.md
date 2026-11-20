---
id: ANS-1795163234714653
title: Stop the daily Xray restart from log rotation and tighten Xray runtime settings
kind: bug
status: review
area: ansible
priority: high
risk: high
owner: Ansible maintainer
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795163234714653-xray-rotation-without-restart
created: 2026-11-20
updated: 2026-11-20
related_tasks: []
---

## Goal

Daily log rotation no longer restarts Xray, so client sessions on the TCP nodes survive midnight and the nodes do not drop together. Xray sniffing is routing-only, the 4 KB per-connection buffer override is removed, and the Xray unit gains the missing sandbox options and a file limit below the host `fs.file-max`.

## Acceptance criteria

- The rendered Xray rotation policy uses `copytruncate` and contains no rotation script on any profile; a unit test fails if one returns.
- The native rotation lanes show an unchanged Xray `MainPID`, a rotated copy and working authenticated traffic after a forced rotation.
- Both sniffing blocks set `routeOnly: true`; `policy.levels.0` has no `bufferSize`.
- The Xray unit sets `ProtectProc=invisible`, `PrivateDevices`, `ProtectClock`, `ProtectKernelLogs`, `ProtectHostname`, `UMask=0077` and a `LimitNOFILE` below `fs.file-max`.
- After the next deploy, the Xray start time on each node does not move across a daily rotation.
