---
id: ANS-1794811064145966
title: Declare the operator-owned XHTTP site in the protected site write set
kind: bug
status: doing
area: ansible
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-16
updated: 2026-11-16
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

A site deploy publishes an operator-owned nginx-xhttp site whose files have any names. Today the protected ingress site journal declares only the bundled page paths for the nginx-xhttp owner, so an operator page outside that layout is refused on the host, and the deploy rolls back. A dry-run does not open the journal, so it passes. The self-steal owner already declares its operator tree file by file.

## Acceptance criteria

- The protected ingress declaration lists every regular file of `nginx_xhttp_public_site_dir` under `/var/www/public-site/`, beside the bundled page paths.
- A test that runs the real declaration tasks fails without the change for an operator page outside the bundled layout.
- A host without an operator-owned site keeps the same declaration.
