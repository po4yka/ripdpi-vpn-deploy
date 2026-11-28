# Porkbun OpenTofu provider vetting — 2026-11-28

> **Status:** Research · **Type:** research · **Tier:** — · **Reviewed:** 2026-11-28

The review of the community provider that the Porkbun DNS root pins, as `REQ-PORKBUN-PROVIDER` of task `TFR-1795329107889572` requires. Repeat this review for every version bump of the pin in `terraform/ops/porkbun/versions.tf`.

## Release reviewed

| Field | Value |
|---|---|
| Provider | `marcfrederick/porkbun` on `registry.opentofu.org` |
| Version | `1.3.3`, tag `v1.3.3`, commit `4899ed92a29c666c56a5a563756e7afcd963c5fa`, released 2026-04-26 (latest; the OpenTofu registry lists 1.1.0 to 1.3.3) |
| License | MPL-2.0 |
| Maintainer activity | Releases from 2025-04 to 2026-04 on one stable major line; last commit 2026-07-03, last push 2026-09-01; not archived; 8 open issues |
| Lock | `terraform/ops/porkbun/.terraform.lock.hcl` holds the `1.3.3` hashes for `linux_amd64`, `linux_arm64`, `darwin_amd64` and `darwin_arm64` |

## Credentials and outbound hosts

- The provider reads `PORKBUN_API_KEY` and `PORKBUN_SECRET_API_KEY` from the environment (`internal/provider/provider.go`). The provider block can take them as sensitive attributes too; the root does not use those attributes.
- API calls go through the client library `github.com/tuzzmaniandevil/porkbun-go` `v1.0.2`. Its only base URLs are `https://api.porkbun.com/api/json/v3` and, with the provider's `ipv4_only` option, `https://api-ipv4.porkbun.com/api/json/v3`. The keys travel in the JSON request body to those hosts and nowhere else. Both hosts are on the egress proxy allowlist.
- Neither the provider nor the library logs request bodies. The library's only print statements are in its example command `cmd/main.go`, which the provider does not build.

## Proxy support

The provider builds its HTTP client with `retryablehttp.NewClient()` from `github.com/hashicorp/go-retryablehttp` `v0.7.8`. That client uses `cleanhttp.DefaultPooledClient()` from `github.com/hashicorp/go-cleanhttp` `v0.5.2`, whose transport sets `Proxy: http.ProxyFromEnvironment`. The provider therefore honours `HTTPS_PROXY` and `NO_PROXY`, so its calls can leave through the egress proxy.

## Surface

The release has resources for DNS records, DNSSEC records, URL forwards and nameservers, data sources for domains, nameservers and SSL bundles, and an SSL ephemeral resource. The root uses only `porkbun_dns_record`. Registration, transfers, nameserver and DNSSEC changes stay out of scope.

## Alternatives

- `jianyuan/porkbun` `0.3.4` (MIT): active, but on a `0.x` API and with more surface than the fleet needs.
- `kyswtn/porkbun` is stale and `cullenmcdermott/porkbun` is archived.
- Writing a provider would be new code on a credential path.
