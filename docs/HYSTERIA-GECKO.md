# Hysteria2 Gecko evidence and rollout

Gecko fragments QUIC long-header handshake packets into two to eight random-size, random-padded datagrams and then applies Salamander to every fragment. It is default-off because both endpoints must select Gecko and because the extra datagrams are useful only when Salamander's packet-size shape is being filtered.

## A-B-A measurement

Prepare external native Hysteria client configs for the currently deployed canary mode. Each config must listen on the same local SOCKS address and must stay outside this repository. Run ten fresh handshakes in each phase from one technical vantage against one canary: `salamander-a1`, `gecko-b`, then `salamander-a2`. Complete the sequence within 24 hours.

```bash
python3 scripts/hysteria-gecko-evidence.py probe --phase salamander-a1 --obfs-type salamander --client-config ~/.config/vpn-provision/hy2-a1.yaml --control-url https://control.example.invalid/healthz --target-url https://target.example.invalid/healthz --scope udp-443-salamander-1200 --vantage-id filtered-cgnat-a --canary-id canary-a --output ~/.cache/vpn-deploy/hysteria-gecko/a1.json
python3 scripts/hysteria-gecko-evidence.py evaluate ~/.cache/vpn-deploy/hysteria-gecko/a1.json ~/.cache/vpn-deploy/hysteria-gecko/b.json ~/.cache/vpn-deploy/hysteria-gecko/a2.json --output docs/measurements/hysteria-gecko-YYYY-MM-DD.json
```

The probe first copies each external client config into the private operator cache, verifies that the immutable copy selects the requested native obfuscator, and records only keyed HMAC-SHA-256 identities for the canary endpoint, control endpoint, target endpoint, complete client config, transport settings, and shared obfuscation password. The random HMAC key is created mode `0600` as `identity.key` in the raw-log directory, is reused by all three phases, and is never committed; `--identity-key-file` may select another cache-local key. The evaluator requires byte-identical A1/A2 client configs, the same password identity in every phase, and records the Gecko packet bounds for deployment validation. It confirms only when every phase has ten attempts and at least nine healthy control probes, both Salamander phases have at most two successes, Gecko has at least eight successes, every identity matches across A-B-A, and no auth, TLS, malformed-config, or local-process failure is counted as network evidence. Raw client configs, endpoints, identity key, per-attempt JSON, process logs, and errors remain under `~/.cache/vpn-deploy/hysteria-gecko/`; only the redacted evaluator output may be committed.

## Activation

Set `hysteria_obfs_type: gecko`, the packet bounds, evidence report path, report SHA256, and evidence scope in group vars. The technical scope must identify the Gecko bounds, server transport profile, and target network cohort without naming an operator, endpoint, provider, or geography. Set the canonical `hysteria.obfs_password` in SOPS and pin Hysteria to at least `v2.9.2`. `make pre-deploy-check`, direct Ansible role execution, and the client emitters all fail closed when the report is missing, altered, rejected, or scoped differently. Evidence does not expire solely with time, but the A-B-A sequence must be repeated when the scope, bounds, server transport profile, or target cohort changes.

Install the Gecko-capable RIPDPI build on every target device before switching the single production listener. Retain the previous Salamander server config and published bundle before the atomic cutover. After deployment run the normal smoke and verify gates, then repeat a filtered Gecko probe. Rollback restores the retained Salamander server config and republishes the retained Salamander bundle; parallel listeners and dual Gecko nodes are outside this procedure.
