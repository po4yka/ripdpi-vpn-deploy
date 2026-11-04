# Design

## DNS policy records

The zone is operator data in private tfvars. The root therefore only widens the accepted record contract; apex SPF `"v=spf1 -all"`, `_dmarc` reject policy, CAA restricted to Let's Encrypt and removal of the wildcard CNAME are applied as an ordinary reviewed plan after merge. TXT and CAA may repeat per name, so their uniqueness key includes the data. The wildcard is not refused by the contract, because it may be an imported legacy record; the Vultr note says to prefer explicit names.

## Recipient deny list

`198.18.0.0/15` is reserved for benchmarking. `64:ff9b::/96` (NAT64) and `2002::/16` (6to4) embed an IPv4 address that can name a private target where a translator exists. The Python policy remains the canonical table. The AWG forward drop set must stay equal to it, and the gateway DNS answer filter reads it through the policy CLI.

## Xray sandbox

The production unit adopts the baseline already proven by the probe Xray unit with the same binary: W^X memory, the `@system-service` allowlist minus `@privileged` and `@resources`, and restricted address families including `AF_NETLINK` for interface enumeration. The configuration directory is root-owned `0750`, so write access from the runtime user was never needed.

## Monitoring

The agent health adapter already exports certificate expiry for the observability client certificate. It gains the self-steal leaf certificate as `role="reality-self-steal"`, so the existing warning and critical expiry rules cover it. The collector Prometheus scrapes only the relay's drop counters on loopback and alerts when they increase. `scripts/release-inputs.py` emits the relay pin from the same verified vmutils release as the agent pin.
