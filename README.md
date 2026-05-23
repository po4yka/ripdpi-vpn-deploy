# vpn-deploy

[![ci](https://github.com/po4yka/vpn-deploy/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/po4yka/vpn-deploy/actions/workflows/ci.yml)
[![codeql](https://github.com/po4yka/vpn-deploy/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/po4yka/vpn-deploy/actions/workflows/codeql.yml)
[![scorecard](https://api.securityscorecards.dev/projects/github.com/po4yka/vpn-deploy/badge)](https://securityscorecards.dev/viewer/?uri=github.com/po4yka/vpn-deploy)
[![release](https://img.shields.io/github/v/release/po4yka/vpn-deploy?sort=semver)](https://github.com/po4yka/vpn-deploy/releases)

Reproducible VPN deployment automation for the multi-profile access stack
(`P0` VLESS+REALITY+Vision → `P1` nginx+XHTTP direct → `P2` Hysteria2 +
AmneziaWG). Layered architecture: Terraform owns cloud resources,
cloud-init does first-boot bootstrap, Ansible owns runtime state, and
secrets live outside the repo (SOPS + age).

## Layers

```mermaid
flowchart LR
    TF["Terraform<br/><sub>VPS · firewall · SSH key · DNS</sub>"]
    CI["cloud-init<br/><sub>admin user · SSH hardening · python3</sub>"]
    AN["Ansible<br/><sub>nftables · xray · nginx · hysteria · AWG · monitoring · backup</sub>"]
    SC[("SOPS + age<br/><sub>secrets at rest, outside the repo</sub>")]
    VD["vpnd CLI<br/><sub>Rust convenience over Make / TF / Ansible / SOPS</sub>"]

    TF --> CI --> AN
    SC -. VPN_SECRETS_FILE .-> AN
    VD -. wraps .-> TF
    VD -. wraps .-> AN
    VD -. wraps .-> SC
```

Every layer is dry-runnable. Every layer has a rollback path. Nodes are
disposable: when an IP burns, recreate from git + secrets, do not repair.

## Stack

P0 is the RU baseline. P1 and P2 run alongside it as alternate transports;
clients carry selector + urltest logic so they automatically fail over to
whichever profile is still reachable. P3 is the operator-level recovery —
a burned IP is replaced, not repaired.

```mermaid
flowchart LR
    subgraph CL[client]
        direction TB
        SB["sing-box / NekoBox<br/>selector + urltest"]
        AC["AmneziaWG client"]
    end
    subgraph TSPU["RU internet · TSPU"]
        DPI["DPI · SNI inspection · active probing"]
    end
    subgraph VPS["disposable VPS · nftables · geoblock"]
        direction TB
        P0X["<b>P0</b> · xray REALITY + Vision / mux<br/>TCP/443 · RU baseline"]
        P1X["<b>P1</b> · nginx XHTTP direct<br/>TCP/8443 or 443"]
        P2H["<b>P2</b> · Hysteria2<br/>UDP/443 · port-hop opt"]
        P2A["<b>P2</b> · AmneziaWG<br/>UDP/cohort · obfuscated"]
    end
    subgraph UP[upstream]
        WI["internet<br/>geosite-routed egress"]
    end

    SB -- VLESS --> DPI
    SB -- XHTTP --> DPI
    SB -- QUIC --> DPI
    AC -- WG --> DPI
    DPI --> P0X
    DPI --> P1X
    DPI --> P2H
    DPI --> P2A
    P0X --> WI
    P1X --> WI
    P2H --> WI
    P2A --> WI

    P3(("<b>P3</b><br/>manual fallback:<br/>alt IPs · alt ports<br/>WARP outbound<br/>recreate on burn"))
    P3 -. recovery .-> VPS
```

## Provider support

| Provider | Status |
|---|---|
| UpCloud | primary (v1) |
| Hetzner | implemented (v1.1) |
| Vultr | implemented (v1.1) |

Switch via `make PROVIDER=upcloud …`.

## Deploy profiles

Default is P0+P1+P2 on one node. Partial deploys come from cohort
`group_vars` files in `ansible/group_vars/`:

- `vpn-p0.yml` — REALITY only.
- `vpn-p1p2.yml` — XHTTP + Hysteria2 + AmneziaWG; REALITY off, nginx free
  to take 443.
- `vpn-fullstack.yml` — same as `all.yml` defaults, made explicit so a
  host in `[vpn-fullstack]` is unambiguous.

```mermaid
flowchart LR
    subgraph CH[cohort]
        direction TB
        P0[vpn-p0]
        PM[vpn-p1p2]
        FS[vpn-fullstack]
    end
    subgraph TR[transports on the VPS]
        direction TB
        XR["xray REALITY<br/><sub>P0 · TCP/443</sub>"]
        NG["nginx XHTTP<br/><sub>P1 · TCP/8443 or 443</sub>"]
        HY["Hysteria2<br/><sub>P2 · UDP/443</sub>"]
        AW["AmneziaWG<br/><sub>P2 · UDP/cohort</sub>"]
    end

    P0 --> XR
    PM --> NG
    PM --> HY
    PM --> AW
    FS --> XR
    FS --> NG
    FS --> HY
    FS --> AW
```

Assign a host to a cohort with `COHORTS=` on `render-inventory.sh`:

```bash
HOSTS="upcloud:p0" COHORTS="p0" ./scripts/render-inventory.sh
```

Or skip the inventory rebuild and tag-scope the play:
`ansible-playbook site.yml --tags p0` runs baseline + firewall + the P0
role only. Multi-VPS layouts: `docs/RUNBOOK-add-fallback.md`.

## Where to start

Agents and contributors: `AGENTS.md` and `CLAUDE.md` at the repo root carry
the working rules (per-folder variants apply when working inside a subtree).
Then:

1. `docs/QUICKSTART.md` — zero-to-working in ~30 minutes.
2. `docs/ARCHITECTURE.md` — how this repo maps to the P0–P3 stack.
3. `docs/CDN-DECISION.md` — explicit ADR: Cloudflare CDN is **not** the RU
   baseline; nginx-xhttp role is direct-only by default.
4. `docs/SECRETS.md` — SOPS+age model, age-key recovery, rotation.
5. `docs/AGE-RECOVERY.md` — Shamir-split the age key for k-of-n recovery.
6. `docs/TESTING.md` — coverage matrix and what's intentionally not tested.
7. `docs/BRANCH-PROTECTION.md` — apply required-status-check rules via GH API.
8. `docs/RUNBOOK-deploy.md` — full deploy procedure.
9. `docs/CLIENT-NOTES.md` — client-side bugs and version pins (AWG #2457,
   sing-box NaiveProxy padding leak, NaiveProxy v147 preamble).
10. `docs/SUBSCRIPTION-PLANE.md` — gap matrix against the wiki spec.
11. `docs/XRAY-RELEASE-LINE.md` — Xray-core 2026 release-line tracker
    (v26.2.6 → v26.5.3) with breaking-change notes for upgrades.
12. `docs/AWG-COHORTS.md` — AmneziaWG cohort obfuscation profiles by
    packet-shape signature (e.g. `narrow-junk-sequential`).
13. `docs/MULTI-COHORT.md` — multiple VLESS+REALITY inbounds per host,
    each with its own port/flow_mode/finalmask/clients.
14. `docs/MULTI-OPERATOR.md` — per-scope SOPS rules, role-scoped secrets
    files, audit-log boundaries.
15. `docs/SUBSCRIPTION-HOST-SEPARATION.md` — run the subscription
    delivery role on a dedicated VPS via `vpn_subscription_only`.
16. `docs/CI-REAL-DEPLOY.md` — workflow_dispatch ephemeral-UpCloud
    deploy gate for PRs labelled `ci-real-deploy`.
17. `docs/REGRESSION-BASELINE.md` — `rkn-block-checker` four-layer
    verdict harness for before/after deploy measurement.

Operational runbooks: `docs/RUNBOOK-{rotate,rollback,incident,restore,add-fallback}.md`.

## Contributing

PRs welcome — see `CONTRIBUTING.md`. Subjects follow Conventional Commits;
release-please picks them up automatically.

## Security

Critical issues (active probing, IP burn, key leak) → private channel per
`.github/SECURITY.md`. Don't open public issues for those.

## Make targets

```
# Core lifecycle
make init        # terraform init for the chosen PROVIDER
make validate    # fmt, validate, gitleaks, ansible-lint
make decrypt     # sops --decrypt → /tmp/vpn-<env>.secrets.yaml
make plan        # terraform plan -out=<env>.tfplan
make apply       # terraform apply <env>.tfplan
make inventory   # render Ansible inventory from terraform outputs
make wait        # wait for cloud-init to finish on the new VPS
make dry-run     # ansible-playbook --check --diff
make deploy      # ansible-playbook site.yml
make verify      # post-deploy verification playbook
make clean       # shred decrypted secrets

# Rollback / rotation
make rollback-xray ROLLBACK_XRAY_VERSION=vX.Y.Z
make rollback-config
make rotate-credentials

# Operations
make destroy                              # safe, double-confirmation destroy
make backup-state                         # age-encrypt local TF state
make burn-check                           # external IP reachability probe
make diff-secrets                         # drift detection
make emit-singbox CLIENT=<name>           # full sing-box client JSON
make install-hooks                        # one-time pre-commit setup
make molecule-test ROLE=<name>            # role-level idempotence test
make validate-target                      # pre-deploy REALITY target probe (8-step audit)
make scan-targets CIDR=<range>            # discover REALITY targets via RealiTLScanner
make smoke-test                           # end-to-end traffic test (real proxy dial)
make blue-green GREEN_ENV=<name>          # orchestrate blue-green replacement
```

## Hard rules

- No secrets in git, in Terraform state, in Terraform variables/outputs, in
  cloud-init `user_data`, in Ansible debug output, or in screenshots.
- No public admin panel. No remote installer piped into a root shell.
- One UUID / one shortId / one peer key **per device**, never shared.
- Pinned versions. Pre-release versions go through staging only.
- CI gate: gitleaks must pass with the `.gitleaks.toml` rules in this repo.

## License

BSD 3-Clause (see `LICENSE`).
