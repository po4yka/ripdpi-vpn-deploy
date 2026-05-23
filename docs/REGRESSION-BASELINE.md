# Deploy-side regression baseline

`scripts/run-rkn-block-checker.sh` runs the upstream
[`rkn-block-checker`](https://pypi.org/project/rkn-block-checker/)
Python tool against the canonical URL set
(`scripts/rkn-block-checker-url-set.yaml`) and diffs the per-layer
verdicts against the previous run for the same exit IP. Use it to
measure whether a server-side change shifted the four-layer verdict
in the intended direction.

The point of the baseline is **before/after measurement around a
deploy**, not continuous monitoring. Running it as part of a
debugging session, an Xray version bump, or a cohort flip-over gives
you the only data that actually answers the question "did this fix
the problem on the network?"

## Four-layer verdict taxonomy

Per-URL the tool emits a verdict per pipeline layer:

| Layer | OK | Filtered |
|-------|-----|----------|
| DNS   | resolver returned the origin's address | `DNS_BLOCK` — stub / loopback / NXDOMAIN |
| TCP   | TCP handshake reached the origin | `TCP_RESET` — handshake completed then RST mid-flow |
| TLS   | TLS ClientHello + ServerHello cleared | `TLS_BLOCK` — RST, FIN, or stall during handshake |
| HTTP  | server's actual body arrived | `HTTP_STUB` — TLS clean but body is a censorship stub page |

`OK` at every layer means the request reached the origin and the
origin's real response came back. Any non-OK verdict at any layer is
a filtering signal — the layer it fires at tells you where in the
pipeline the filter is acting.

## Installation

The tool issues real network probes. It is intentionally **not**
listed in the repo's hash-locked `requirements.txt` — adding it there
would make every CI lane pull the package and the lockfile would
have to be regenerated on every upstream bump. Install it ad-hoc:

```bash
# Operator workstation (recommended):
pipx install rkn-block-checker==0.1.0

# Or, per-user inside an existing venv:
pip install --user rkn-block-checker==0.1.0
```

The pinned version lives in **two** places, in sync:

- `scripts/run-rkn-block-checker.sh` → `RKN_BLOCK_CHECKER_VERSION="0.1.0"`
- `.github/workflows/rkn-block-checker-baseline.yml` → `rkn_block_checker_version` input default

Bumping the pin = edit both. The workflow accepts an override input
so an ad-hoc test of a newer version does not need a commit.

## Running locally

```bash
# Anchor the report by the VPS's public IP. The baseline is stored at
# ~/.local/state/vpn-deploy/rkn-baseline/<exit-ip>/.
scripts/run-rkn-block-checker.sh "$(terraform -chdir=terraform/providers/upcloud output -raw server_ipv4)"

# Run via a bypass channel (sing-box exposing a SOCKS5 listener at
# 127.0.0.1:10808 — adjust to whatever your local client exposes).
scripts/run-rkn-block-checker.sh "$EXIT_IP" --proxy socks5://127.0.0.1:10808
```

The wrapper exits 0 when no verdict has shifted since the previous
run, and non-zero when at least one URL's verdict changed. Plumb the
exit code into a deploy gate or just inspect the stdout summary.

## CI lane

`.github/workflows/rkn-block-checker-baseline.yml` runs the same
harness from a GitHub-hosted runner on `workflow_dispatch`. The runner
has no privileged path into the filtered network; the lane is for:

- Validating that the URL set itself produces sane results from a
  vantage with no filtering applied (every blacklist URL is expected
  to reach OK from a non-filtered runner — failures here indicate URL
  rot, not deploy regression).
- Cross-validating a `--proxy` bypass: route the runner through a
  bypass channel and confirm the blacklist URLs now reach OK.

Inputs:

| Input | Default | Notes |
|-------|---------|-------|
| `exit_ip` | `local` | Anchors the report key. Use the literal `local` when running from the runner itself. |
| `proxy`   | (empty) | Optional `socks5://…` URL. |
| `rkn_block_checker_version` | `0.1.0` | Override to test an upstream bump without committing. |

The lane uploads the full JSON report + diff as a workflow artifact
(`rkn-block-checker-baseline-<exit_ip>`, 90-day retention).

## URL set

`scripts/rkn-block-checker-url-set.yaml` carries two groups, sized to
upstream's recommendation:

- **21 whitelist controls** — endpoints expected to reach `OK` on any
  unfiltered network. A whitelist entry shifting to a non-OK verdict
  is a control-side false positive (URL rot, transient outage).
- **15 blacklist tests** — endpoints expected to land on the
  filtering pipeline. Each entry's `exercise:` comment names the
  technical behaviour the URL probes (TLS-layer block, DNS+TLS
  combo, locale-path block), not the entity behind the URL or the
  geography of the filter.

The set drifts as the filtering pipeline changes. Review quarterly
and rotate entries that have become uninformative. When rotating:

1. Run the existing wrapper to capture the current verdict.
2. Edit the YAML, keeping the 21+15 split.
3. Run again — the diff will flag every shifted URL, including the
   ones you intentionally removed/added.

## Interpreting the diff

The wrapper compares against `~/.local/state/vpn-deploy/rkn-baseline/
<exit-ip>/latest.json`. Verdict tuples are compared per-URL; a shift
is any non-empty difference between the two `{dns, tcp, tls, http}`
quads.

Common patterns:

- **Whitelist `OK → DNS_BLOCK`**: resolver path broken. Check the
  baseline role's `/etc/resolv.conf`.
- **Whitelist `OK → TLS_BLOCK`** on a single URL: that URL's CDN
  origin moved into a blocked ASN. Rotate the entry.
- **Blacklist `TLS_BLOCK → OK`** after a `--proxy` flag: the bypass
  channel works. Document the proxy in the linked deploy.
- **Blacklist `TLS_BLOCK → DNS_BLOCK`**: the filtering layer
  upstream of you tightened — TSPU moved from TLS-RST to DNS-stub
  on this entry. Not a deploy regression; record it.
- **Whitelist and blacklist both `OK`**: the path you're probing
  through has no filtering. Either you ran the harness from outside
  the threat-model network, or the bypass channel is intact.

## When to run

| Operation | Run baseline |
|-----------|--------------|
| `make deploy` against a fresh VPS | yes, before and after |
| Xray version bump | yes, before and after |
| `xray_flow_mode` cohort flip | yes, before and after |
| AmneziaWG cohort change | yes, before and after |
| Nginx-XHTTP path rotation | yes, before and after |
| `make rotate-credentials` | optional — credentials do not affect verdicts |
| Provider switch (UpCloud ↔ Hetzner) | yes — ASN reputation drives a lot of the verdicts |
| Cohort URL set quarterly review | yes — captures the rotation |

## Limitations

- The four-layer verdict is one observation from one vantage. A URL
  passing here does not mean the same URL passes from a different
  client IP, network, or carrier.
- The tool issues real network requests. Running it from a residential
  IP burns ~36 requests per invocation; from a runner the cost is the
  runner's outbound capacity.
- Stub responses can match the HTTP layer verdict shape on a clean
  network if the operator hits a captive portal or load-balancer
  health probe. Confirm the response body manually when in doubt.
