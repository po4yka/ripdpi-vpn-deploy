# role: node_manifest — machine-readable node capability summary

## Design decisions

**Late, non-secret manifest** — this role runs after transports, security roles, and recovery services so `/var/lib/ripdpi-vpn-deploy/manifest.json` describes the effective node. It records booleans, protocol/port surfaces, and known recovery paths only.

**Listener source is shared** — `site.yml` builds `public_listener_manifest` once for the pre-convergence collision guard, and this role consumes that same sanitized list. Do not rebuild listener logic here.

**Local JSON validation** — the template task uses `python3 -m json.tool` as a write-time validator and the verify playbooks assert the deployed file parses as JSON.

**Per-host fleet labels** — multi-provider inventories carry `provider` and `env` host variables. The role prefers those values and only falls back to the operator process environment for legacy single-host inventories.

## What's done well

- No UUIDs, private keys, client names, cert material, tokens, subscription URLs, or IP reputation data belong in the manifest.
- The manifest path is stable and world-readable: `/var/lib/ripdpi-vpn-deploy/manifest.json`, with the directory owned by root and mode `0755`.
- Role defaults keep schema and rollback path changes reviewable.

## Pitfalls

- Do not add `reason` fields from the listener preflight manifest; some roles may derive those from inventory labels.
- Do not add secrets-derived peer or client details for AmneziaWG, Xray, subscription-host, or watchdog providers.
- Keep the schema additive and deterministic so fleet tooling can consume it without brittle host-specific parsing.
- Never derive every host's labels from the controller's `PROVIDER` and `ENV` variables during a multi-provider play.
