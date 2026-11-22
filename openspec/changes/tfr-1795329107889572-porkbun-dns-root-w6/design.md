## Context

See `proposal.md`. Research (2026-11-22): Porkbun's API base is `https://api.porkbun.com/api/json/v3`, with an IPv4-only host `api-ipv4.porkbun.com`; API access is opt-in per domain unless the account enables it for all domains; keys can be limited by source CIDR, domain and permission. Porkbun's own Terraform page lists two community providers: `marcfrederick/porkbun` (v1.3.3, MPL-2.0, `porkbun_dns_record`, retryablehttp with `ProxyFromEnvironment`) and `jianyuan/porkbun` (v0.3.4, MIT, DNS plus DNSSEC, nameservers, glue and forwards, active). `kyswtn/porkbun` is stale and `cullenmcdermott/porkbun` is archived.

## Goals / Non-Goals

- Goal: DNS record changes by pull request and CI, with no browser session.
- Non-goal: registration, transfers, nameserver or DNSSEC changes; reading node addresses from other roots' state.

## Decisions

- Provider: `marcfrederick/porkbun` at exactly 1.3.3 (or the latest 1.x at implementation, re-vetted), because it is on a stable major line, covers DNS records, and its client honours proxy environment variables. Rejected: `jianyuan/porkbun` (0.x API, more surface than the fleet needs); writing a provider (new code). The vetting step reads the pinned release source for credential handling and outbound hosts and confirms it is on `registry.opentofu.org`.
- Root layout: `terraform/dns/porkbun/{versions.tf,variables.tf,main.tf,outputs.tf,tests/*.tftest.hcl}`. Input `managed_domains` (list) and `records` (map keyed by a stable record ID with domain, name, type, content, ttl). `for_each` over `records`. Record content (including node addresses) comes from ops repository tfvars; no `terraform_remote_state`, so a DNS plan never needs another root's state key.
- Encryption and backend as in W3 from the first commit; key `porkbun/terraform.tfstate`.
- Credentials: `PORKBUN_API_KEY` and the provider's secret variable only from the environment; the provider configuration has no credential arguments.
- Policy: new `terraform/policy/porkbun_scope.rego` plus `_test.rego`: deny a record whose domain is not in `managed_domains`, deny TTL below 600.
- Adoption: generate `import` blocks from a read-only record list (`scripts/porkbun-import-blocks.py`, read key, stdout only, no secret output), commit them, plan to no-op, apply the import, then remove the `import` blocks.
- Egress: the Porkbun hosts are on the W5 allowlist; all calls go through the proxy, so the source restriction can name the egress address.

## Contracts and ownership

- New: `terraform/dns/porkbun/**`, `terraform/policy/porkbun_scope*.rego`, `scripts/porkbun-import-blocks.py`, `tests/unit/test_porkbun_import_blocks.py`, `docs/how-to/dns.md`.
- Changed: `Makefile` `tf-test`/`validate` loops and `tf-conftest` provider list (after W5 in the shared lane), `docs/reference/testing.md`, `terraform/CLAUDE.md`.
- Ops repository: `config/tfvars/porkbun/prod.tfvars`, `config/backend/porkbun.s3.tfbackend`.

## Risks / Trade-offs

- Small community provider is a supply-chain risk → exact pin, lock hashes, source review per version bump, minimal resource use.
- A wrong DNS apply can take the service off its domains → reviewer-gated `tofu-apply`, no-op adoption, policy scope.
- Porkbun API outage → records stay as they are; the web console remains the break-glass path.

## Migration Plan

1. Land root, policy, tests, import-block script and docs (offline: `make tf-test`, `make tf-policy-verify`, `python3 -m pytest tests/unit/test_porkbun_import_blocks.py`).
2. Authorized live steps: enable API access on managed domains only; create read and DNS keys limited to those domains and the egress address; store them in the W4 environments; generate import blocks; plan to no-op; apply the import.
3. Rollback: disable domain API access and revoke the keys; the state history stays in B2; the records are unchanged because adoption only imports.

## Open verification questions

1. Is the chosen provider version published on `registry.opentofu.org`, and do its lock hashes match the GitHub release checksums?
2. Does Porkbun's per-key source restriction accept a single IPv4 /32 and apply it to the DNS endpoints the provider calls?
3. Does the provider call `api.porkbun.com` or `api-ipv4.porkbun.com` by default, and does it need a configuration flag to stay on IPv4 through the proxy?
4. Which domains does the fleet use, and is any record managed by another system (for example a CDN or mail provider) that must stay out of `records`? The operator answers this from the catalog during the live step.
