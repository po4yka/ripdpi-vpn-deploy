# iOS split routing: Russian resources direct, everything else through VPN

**Research date:** 2026-07-14

**Scope:** Shadowrocket, Happ, and INCY on iOS; first-party application documentation, application-author repositories, Apple documentation, and source repositories that own the routing datasets. This document contains public validation addresses but no client credentials, private subscription URLs, or cryptographic secrets.

## Decision

Use a whitelist policy: unmatched traffic must go through the selected VPN profile, and only explicitly classified Russian resources and local networks may use `DIRECT`. The strict baseline should classify Russian resources by `geosite:category-ru`, not by `geoip:ru`: the domain category includes Russian TLDs and a curated set of Russian services, while an IP-country rule can also send a foreign service's Russian CDN edge directly and expose the device's real public IP to that service. Add `geoip:ru` only in a separately named compatibility profile after accepting that trade-off.

Happ is the safest first automation target because its author publishes the routing-profile schema, separate remote and domestic DNS paths, and unmatched-traffic behavior. INCY publishes a similar contract but currently needs additional DNS and profile-loading acceptance gates described below. Shadowrocket remains the preferred daily client for this fleet after a version-pinned physical acceptance test because it already carries every deployed transport, but its author does not publish an exact configuration grammar; the candidate syntax below is therefore empirical. [Shadowrocket's App Store description](https://apps.apple.com/us/app/shadowrocket/id932747118) confirms the capabilities but not the line grammar.

The existing repository-generated sing-box bundle is not an RU-direct profile. [`scripts/emit-singbox.sh`](../scripts/emit-singbox.sh) currently routes unmatched traffic to the selected VPN outbound and sends its single remote DNS server through that outbound, while its package-name exceptions are Android-only. iOS split-routing artifacts should therefore be introduced as a separate generator/output contract rather than inferred from the current sing-box JSON.

## Classification model

The source-grounded domain tag is `geosite:category-ru`. V2Fly's owned [`category-ru` source](https://github.com/v2fly/domain-list-community/blob/master/data/category-ru) includes `tld-ru` and curated Russian companies, public services, banks, media, retailers, and network operators. The owned [`tld-ru` source](https://github.com/v2fly/domain-list-community/blob/master/data/tld-ru) covers `.ru`, `.su`, `.рф` and the other Russian internationalized TLDs. The dataset has `category-ru`; it does not publish a top-level `ru` data file. Consequently, the `geosite:ru` shown in INCY's Russia example must not be assumed to work with the documented Loyalsoldier file without an on-device load test.

The Happ and INCY documentation points to Loyalsoldier's `geoip.dat` and `geosite.dat`. The [dataset owner's documentation](https://github.com/Loyalsoldier/v2ray-rules-dat) states that country categories use two-letter codes such as `geoip:ru`, and that its geosite file is built from V2Fly's domain-list-community. It is therefore appropriate to use `geosite:category-ru`; `geoip:ru` is available but intentionally omitted from the strict profile.

No static list makes the semantic promise “Russian site” perfectly. Domain ownership changes, multi-region CDNs move endpoints, apps may use hard-coded IPs or their own encrypted DNS, and geodata can lag. The safe failure direction for this requirement is VPN, not direct: a missing Russian entry reduces performance or local compatibility, whereas an overly broad direct entry exposes the real address to a foreign destination.

## DNS policy

Use two resolvers and bind them to the routing decision:

- Remote/proxy resources: Google Public DNS over HTTPS at `https://dns.google/dns-query`, bootstrapped with `8.8.8.8`, and sent through the selected VPN outbound. Google documents the RFC 8484 endpoint and addresses in its [DoH reference](https://developers.google.com/speed/public-dns/docs/doh/) and [address reference](https://developers.google.com/speed/public-dns/docs/using).
- Domestic/direct resources: Yandex DNS Basic over HTTPS at `https://common.dot.dns.yandex.net/dns-query`, bootstrapped with `77.88.8.8`, and sent directly. [Yandex's service page](https://dns.yandex.ru/) publishes the Basic resolver address and `common.dot.dns.yandex.net` DoH hostname.

This is the desired resolver policy, but the physical test showed that application/runtime behavior can differ from the imported fields: Happ exposed Cloudflare and Google resolvers, Shadowrocket exposed Cloudflare resolvers behind the P0 exit, and INCY exposed Google plus VPN-provider-side resolvers. None of the three captures identified the access-network resolver. A public resolver observed behind the VPN exit is not an access-network DNS leak, but the current Happ and Shadowrocket builds cannot be claimed to have a strict no-Cloudflare resolver path.

Use `IPIfNonMatch`: the client first checks the domain lists, then resolves and checks IP rules only when the domain did not match. The physical Happ rollout required `FakeDNS=true`; INCY remained on `FakeDNS=false`. Apps that perform their own DoH can prevent domain-based classification; in the strict profile such ambiguous traffic should fall through to VPN. Do not add a blanket direct IPv6 route: the final VPN rule must cover both address families.

## Happ

Happ's [official routing reference](https://www.happ.su/main/ru/dev-docs/routing) defines JSON routing profiles, `GlobalProxy`, direct/proxy/block lists, separate remote and domestic DNS, `IPIfNonMatch`, `RouteOrder`, and `UseChunkFiles`. It supports import from clipboard, QR, HTTP headers or subscription body, and `happ://routing/add/{base64}` or `happ://routing/onadd/{base64}`. The [official builder](https://routing.happ.su/en) exposes the same fields and current JSON types.

Recommended strict profile:

```json
{
  "Name": "RU-direct-strict",
  "GlobalProxy": true,
  "RouteOrder": "block-direct-proxy",
  "RemoteDNSType": "DoH",
  "RemoteDNSDomain": "https://dns.google/dns-query",
  "RemoteDNSIP": "8.8.8.8",
  "DomesticDNSType": "DoH",
  "DomesticDNSDomain": "https://common.dot.dns.yandex.net/dns-query",
  "DomesticDNSIP": "77.88.8.8",
  "Geoipurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
  "Geositeurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
  "LastUpdated": "",
  "DnsHosts": {
    "dns.google": "8.8.8.8",
    "common.dot.dns.yandex.net": "77.88.8.8"
  },
  "DirectSites": [
    "geosite:private",
    "geosite:category-ru"
  ],
  "DirectIp": [
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "255.255.255.255/32",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8"
  ],
  "ProxySites": [],
  "ProxyIp": [],
  "BlockSites": [],
  "BlockIp": [],
  "DomainStrategy": "IPIfNonMatch",
  "FakeDNS": true,
  "UseChunkFiles": true
}
```

`GlobalProxy: true` is the load-bearing default: if no direct rule matches, Happ uses the proxy outbound. `UseChunkFiles: true` is appropriate on iOS because Happ documents it as a way to reduce geodata memory use. `FakeDNS=true` is the physically accepted setting for the installed build. Keep `LastUpdated` empty during first import so the app can use its bundled/default geodata path instead of forcing a GitHub download before the VPN is established; update the files manually after connecting, then confirm the profile remains active and has no geodata error indicator.

For a compatibility variant, clone the profile, rename it `RU-direct-geoip-compat`, and append `"geoip:ru"` to `DirectIp`. Do not change the strict profile in place.

## INCY

INCY's [official routing reference](https://incy.gitbook.io/docs/dokumentaciya-dlya-razrabotchikov/routing) defines the same direct/proxy/block categories, split remote/domestic DNS, `DomainStrategy`, geodata URLs, and `incy://routing/add/{base64}` or `incy://routing/onadd/{base64}` imports. Its [official examples](https://incy.gitbook.io/docs/dokumentaciya-dlya-razrabotchikov/primery-marshrutizacii) explicitly implement a Russia-oriented `GlobalProxy=true` profile, but the example's `geosite:ru` tag conflicts with the named source dataset; substitute `geosite:category-ru` and validate it on the installed build. The [author-maintained repository](https://github.com/INCY-DEV/incy-platforms) independently confirms domain/IP direct, proxy, and block routing with separate remote and domestic DNS.

Recommended strict profile, limited to fields documented for INCY:

```json
{
  "Name": "RU-direct-strict",
  "GlobalProxy": "true",
  "RemoteDNSType": "DoH",
  "RemoteDNSDomain": "https://dns.google/dns-query",
  "RemoteDNSIP": "8.8.8.8",
  "DomesticDNSType": "DoH",
  "DomesticDNSDomain": "https://common.dot.dns.yandex.net/dns-query",
  "DomesticDNSIP": "77.88.8.8",
  "Geoipurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
  "Geositeurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
  "LastUpdated": "",
  "DnsHosts": {
    "dns.google": "8.8.8.8",
    "common.dot.dns.yandex.net": "77.88.8.8"
  },
  "DirectSites": [
    "geosite:private",
    "geosite:category-ru"
  ],
  "DirectIp": [
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "255.255.255.255/32",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8"
  ],
  "ProxySites": [],
  "ProxyIp": [],
  "BlockSites": [],
  "BlockIp": [],
  "DomainStrategy": "IPIfNonMatch",
  "FakeDNS": "false"
}
```

As with Happ, add `geoip:ru` only to a separately named compatibility profile. INCY supports URL-backed autorouting, but first rollout should use a local base64 deep link so a routing-source outage cannot silently change the current policy. Move to an authenticated, pinned, repository-owned update URL only after rollback and integrity behavior has been tested.

Treat INCY as the third rollout target rather than assuming parity with Happ: the [author-hosted feedback tracker](https://feedback.incy.cc/) currently lists open iOS reports for a system-DNS leak with `IPIfNonMatch` and failure to load a global routing profile from a server. These reports are upstream signals rather than reproduced findings in this repository, but they make physical DNS-path capture and local-profile import mandatory before INCY can be recommended for unattended use.

## Shadowrocket

The official public evidence establishes support for exact-domain, suffix, keyword, CIDR, and GeoIP matching, URL/iCloud rule import, local DNS mapping, and DoH/DoT/DoQ. It does not establish exact line syntax, `RULE-SET`, `FINAL`, rule precedence, geosite tags, or per-rule DNS routing. Do not present community configuration manuals as the app's specification.

On the physically tested build, the application emitted and matched rules in the following form; this is an empirical, version-pinned contract rather than a first-party published grammar:

```ini
[General]
bypass-system = true
dns-server = 8.8.8.8
fallback-dns-server = 8.8.8.8
ipv6 = true
prefer-ipv6 = false
dns-direct-system = false

[Rule]
DOMAIN-SUFFIX,ru,DIRECT
# ...the pinned category-ru dependency graph is compiled into exact and suffix rules...
IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
IP-CIDR,100.64.0.0/10,DIRECT,no-resolve
IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
IP-CIDR,169.254.0.0/16,DIRECT,no-resolve
IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
IP-CIDR6,::1/128,DIRECT,no-resolve
IP-CIDR6,fc00::/7,DIRECT,no-resolve
IP-CIDR6,fe80::/10,DIRECT,no-resolve
FINAL,PROXY
```

The locally generated physical-test artifact recursively compiled V2Fly revision `469b0339ac45fc3e8e594218c3ee69bacfd7ef55` into 1,563 suffix rules and 234 exact-domain rules, then embedded them in the Shadowrocket configuration. The V2Fly source file itself cannot be used as a Shadowrocket rule-set because it contains `include:`, `domain:`, attributes, and other source-format constructs. A durable repository generator should preserve include resolution, IDN normalization, deduplication, pinned source revision and hash, empty-output rejection, snapshots, and license attribution.

Do not enable `GEOIP,RU,DIRECT` in the strict profile. If the user chooses the compatibility trade-off, insert it immediately before `FINAL,PROXY`, name the configuration accordingly, and test a foreign service served from a Russian CDN to make the exposure visible.

Shadowrocket's public documentation does not prove route-bound split DNS. The physical request log proved `yandex.com` and `.ru` as `DIRECT` and foreign traffic as `PROXY`; BrowserLeaks saw Cloudflare resolvers while the page itself used the P0 exit. Treat this as a public resolver behind the VPN, not as proof of the intended Google/Yandex split-DNS path. INCY produced the cleanest resolver observation of the three installed builds.

## Optional filtering

Start with empty block lists. After routing is stable, an opt-in profile may add `geosite:category-ads-all` to `BlockSites` in Happ and INCY; the geodata owner documents how that category is assembled. Advertising and telemetry lists have false positives and can break authentication, payments, embedded video, and app startup, so the block profile should be separately named and tested, not silently folded into `RU-direct-strict`.

Yandex also publishes “Safe” and “Family” resolver modes, but those change DNS answers and apply content policy beyond routing. Keep the Basic resolver in the baseline. Resolver filtering and tunnel routing should remain independent controls so a failure can be diagnosed and rolled back without changing both at once.

## Platform limitations

These rules are enforced inside each client's packet-tunnel core, not by ordinary unmanaged iOS per-app VPN policy. Apple documents that programmatic iOS per-app VPN rules are created through MDM, while packet-tunnel providers control their own included and excluded routes in Network Extension. See [Apple's VPN routing documentation](https://developer.apple.com/documentation/networkextension/routing-your-vpn-network-traffic). A consumer app's routing UI must therefore be treated as its own implementation contract.

Only one policy should be active at a time. Local and carrier-grade NAT ranges are direct so LAN discovery, captive behavior, and private addresses do not enter the foreign tunnel. The `100.64.0.0/10` exception preserves the address class used by overlay/private networking, but it does not make two iOS packet-tunnel VPN applications concurrently usable; coexistence must be verified separately on the physical device.

## Physical acceptance matrix

The strict profile was imported and activated in all three applications on a physical iPhone 16 Pro Max running iOS 26.5.2 through WebDriverAgent over USB. The normal access-network IPv4 was `<redacted-address>`.

| Client | VPN transport used | Foreign IPv4 | Curated RU-domain IPv4 | Foreign IPv6 | DNS observation | Result |
|---|---|---|---|---|---|---|
| Shadowrocket | P0 REALITY | `<redacted-address>` via VPN | `<redacted-address>` direct | `<redacted-address>` via VPN | VPN exit plus Cloudflare resolvers; access-network resolver not observed | PASS |
| Happ | P0 REALITY | `<redacted-address>` via VPN | `<redacted-address>` direct | Explicit connection failure; no native IPv6 leak | Cloudflare and Google resolvers; access-network resolver not identified | PASS with DNS warning |
| INCY | P2 Hysteria2 | `<redacted-address>` via VPN | `<redacted-address>` direct | `<redacted-address>` via VPN | Google and VPN-provider-side resolvers; no Cloudflare or access-network resolver observed | PASS |

Shadowrocket additionally logged `yandex.com` as `DOMAIN-SUFFIX,yandex.com,DIRECT`, `.ru` as `DOMAIN-SUFFIX,ru,DIRECT`, and foreign test traffic as `FINAL,PROXY`. This is the strongest route-selection evidence because it confirms the matched rule rather than inferring the path only from the observed address.

Run this matrix on the physical iPhone for every client after importing the strict profile. Use one known-good VPN transport first; transport failover testing remains separate from routing-policy testing.

| Case | Expected path | Evidence |
|---|---|---|
| `.ru` public IP-check page | DIRECT | Page reports the phone's normal access-network public IP; client log shows direct rule hit |
| Curated Russian `.com` or `.net` entry from `category-ru` | DIRECT | Direct rule hit proves the compiled category, not only the TLD rule |
| Foreign IP-check page | VPN | Page reports the selected server's exit IP |
| Foreign service on a Russian CDN edge | VPN in strict mode | Confirms omission of `geoip:ru` prevents the expected leak class |
| Literal private/LAN address | DIRECT | Local service remains reachable and no packet is sent to the VPN server |
| Foreign IPv6 IP-check page | VPN or explicit failure | It must never report the access network's native IPv6 address |
| Russian domain DNS lookup | Domestic resolver/direct | App log or controlled DNS telemetry proves Yandex resolver selection |
| Foreign domain DNS lookup | Remote resolver/VPN | App log or controlled DNS telemetry proves Google DoH uses the selected outbound |
| Unknown domain absent from both geodata files | VPN | Confirms `GlobalProxy`/`FINAL` fail-closed behavior |
| Geodata refresh unavailable | Existing policy remains active | No empty direct list, silent global-direct fallback, or tunnel loss |

Repeat the essential direct-IP, VPN-IP, DNS-path, and IPv6 checks after each application or geodata update. A green connection indicator is not sufficient evidence: record the observed public IP, matched rule, resolver path, address family, client version, and geodata revision.

## Recommended repository work

1. Promote the local secret-free routing policy and renderer into a tracked repository interface with strict and optional compatibility variants; keep server credentials in the existing client-profile path.
2. Add schema and snapshot tests for the Happ/INCY JSON, deep-link encoding, Shadowrocket rule ordering, fail-closed final action, and IPv6 coverage.
3. Preserve the pinned V2Fly source revision, recursive include resolution, IDN normalization, source hashes, empty-output rejection, and license attribution in the tracked Shadowrocket compiler.
4. Add a repeatable physical-device acceptance runner that records only redacted route, DNS, and address-family evidence; never commit the secret-bearing PDF or raw device artifacts.
5. Re-run the matrix after every app or geodata update, with particular attention to Happ and Shadowrocket resolver behavior.

## Sources

- [Shadowrocket on the App Store](https://apps.apple.com/us/app/shadowrocket/id932747118)
- [Happ routing reference](https://www.happ.su/main/ru/dev-docs/routing)
- [Happ routing builder](https://routing.happ.su/en)
- [INCY routing reference](https://incy.gitbook.io/docs/dokumentaciya-dlya-razrabotchikov/routing)
- [INCY routing examples](https://incy.gitbook.io/docs/dokumentaciya-dlya-razrabotchikov/primery-marshrutizacii)
- [INCY author-maintained platform repository](https://github.com/INCY-DEV/incy-platforms)
- [V2Fly `category-ru` source](https://github.com/v2fly/domain-list-community/blob/master/data/category-ru)
- [V2Fly `tld-ru` source](https://github.com/v2fly/domain-list-community/blob/master/data/tld-ru)
- [Loyalsoldier geodata](https://github.com/Loyalsoldier/v2ray-rules-dat)
- [Google Public DNS DoH](https://developers.google.com/speed/public-dns/docs/doh/)
- [Yandex DNS](https://dns.yandex.ru/)
- [Apple VPN routing](https://developer.apple.com/documentation/networkextension/routing-your-vpn-network-traffic)
