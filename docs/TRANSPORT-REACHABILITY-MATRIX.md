# Transport reachability matrix

The harness deploys one tracked transport profile to a fresh disposable node,
then requires canonical server verification and smoke tests before collecting
SNI probes and a direct runner URL baseline. CI must provision a separate node
for each profile; toggling profiles on one guest leaves skipped services behind.

These artifacts do not establish end-to-end client transport acceptance. The
URL baseline does not use a VPN proxy, and the output explicitly records
`transport_client_acceptance: not_measured`. A filtered-vantage comparison
requires a separately verified client path through the selected transport.
Do not attribute direct runner failures to the deployed protocol.

## Profile shorthands

Each shorthand selects its complete, typed `ansible/group_vars/vpn-ci-*.yml`
cohort. Research profiles carry explicit reviewed role allowlists. The controller
retains normal private SSH identity, Tailnet handoff and ownership requirements;
profile selection never bypasses those gates.

| Shorthand | Active roles |
|-----------|--------------|
| `p0`     | `xray` (REALITY only) |
| `p0p1`   | `xray` + `nginx-xhttp` |
| `p0p1p2` | `xray` + `nginx-xhttp` + `hysteria` |
| `p0p4`   | `xray` + `dns-morph-bridge` |
| `p0p5`   | `xray` + `hysteria-realm` |

The CI default sweep is `p0,p0p1,p0p1p2`. Add `p0p4` or `p0p5` to a
manual run when the corresponding tier is under investigation.

## Workflow trigger

`.github/workflows/transport-reachability-matrix.yml` runs on:

- `workflow_dispatch` with inputs `profiles`, `zone`.
- `pull_request` labeled `ci-real-deploy` — same gating as
  `real-vps-deploy.yml`.

The workflow must provision each selected profile on a fresh node whose provider
listener contract matches that profile, establish trusted SSH and Tailnet
ownership, then invoke:

```bash
scripts/transport-reachability-matrix.sh --profile p0 \
  --secrets "$SECRETS_FILE" --output-dir "$RUN_OUTPUT"
```

`RUN_OUTPUT` must not already exist. The script runs scoped `make deploy verify
smoke-test`, then both probes. Missing tools, failed probes and absent/malformed
reports fail the run. The schema-2 index is written only after those checks.
The workflow retains artifacts and destroys its exact disposable resources even
when a deployment or probe fails. Both workflows use the protected reusable
`ci-disposable-deploy.yml` job and the configuration documented in
`docs/CI-REAL-DEPLOY.md`. Each run creates an SSH host key on an encrypted provider
seed disk, checks its import hash, and installs it before first SSH. The controller
uses that exact pin for bootstrap and recovery. Research profiles additionally
require their reviewed artifact hashes in `CI_DEPLOY_CONFIG`.

## Operator vantage half (manual)

A filtered operator run needs a verified client proxy for the exact transport.
Invoke the URL baseline with `--proxy socks5://127.0.0.1:<port>` and retain the
client configuration identity separately. Compare like-for-like paths and URLs;
the direct runner baseline is a control, not the unfiltered half of a measured
VPN path. Server-local smoke success and SNI success alone do not substitute for
client acceptance.

## SNI-variant survival (REALITY server_names selection)

The matrix also measures **which SNI variant of each REALITY `server_name`
survives**. Per the censorship-bypass concept
`sni-exact-match-vs-suffix-classification-2026`, TSPU on several non-CF paths
matches the SNI by **exact dot-component string, not by suffix**: the bare
`foo.com` and `www.foo.com` form of the *same* name can survive very
differently, in either direction. The topologically "canonical" form is not
privileged — you must pick `xray.server_names` by the variant that actually
survives the RU vantage.

**This decision cannot be made locally.** `scripts/validate-reality-target.sh`
runs from the operator/non-RU vantage and can only validate TLS/cert *hygiene*
of each variant (step 9). The asymmetry is observable only from inside an RU
TSPU path, so the survival verdict comes from `scripts/probe-sni-survival.sh`,
which probes both variants per name against the exit IP and records
`survived | blocked | error` per variant.

Like the rkn-block-checker, it runs in **both vantages**:

- **Unfiltered (CI):** `transport-reachability-matrix.sh` runs it once after
  resolving the exit IP and writes `sni-survival.json` (`vantage: unfiltered`)
  alongside the profile reports. Here every variant is expected to survive —
  this is the hygiene/baseline half. A `blocked`/`error` from this vantage
  means the server or cert is wrong, not the filter.
- **Filtered (operator, RU vantage):** run the same probe from the filtered
  network against the same exit IP:
  ```bash
  EXIT_IP="$EXIT_IP" VANTAGE=filtered make probe-sni-survival
  # or directly:
  scripts/probe-sni-survival.sh "$EXIT_IP" --secrets "$SECRETS_FILE" --vantage filtered \
    --out ~/.local/state/vpn-deploy/transport-reachability/sni-survival-filtered.json
  ```
  The variant marked `survived` in the **filtered** report is the one to put in
  `xray.server_names`. If bare and `www.` disagree, that disagreement is the
  whole point — do not assume the canonical form. If both survive, prefer the
  one already covered by the target certificate SAN (validate-reality-target.sh
  step 9).

Stitch the two `sni-survival.json` files the same way as the per-profile
reports: a variant that is `survived` unfiltered but `blocked` filtered
attributes the drop to the network in between — i.e. that SNI string is on the
exact-match drop table for this path.

## Output schema

Each fresh-node output directory contains this schema-2 `index.json`:

```json
{
  "schema_version": 2,
  "profile": "p0",
  "cohort": "ci-p0",
  "exit_ip": "203.0.113.1",
  "server_verify_and_smoke": "passed",
  "transport_client_acceptance": "not_measured",
  "reports": {
    "sni_survival": "sni-survival.json",
    "runner_direct_baseline": "runner-baseline/203.0.113.1/latest.json"
  }
}
```

The SNI report records its vantage. The URL report is a direct runner control;
client-path evidence must be captured and identified separately.

`.transport-reachability/sni-survival.json` (the unfiltered baseline; the
operator writes a `filtered` counterpart):

```jsonc
{
  "schema_version": 1,
  "vantage": "unfiltered",
  "exit_ip": "203.0.113.1",
  "port": 443,
  "captured_at": "2026-06-11T00:00:00+00:00",
  "results": [
    {
      "server_name": "candidate.example",
      "variants": {
        "candidate.example": "survived",
        "www.candidate.example": "survived"
      },
      "survived": ["candidate.example", "www.candidate.example"]
    }
  ]
}
```

The per-profile `latest.json` follows the `rkn-block-checker` report
schema (`schema_version: 1`, see `docs/REGRESSION-BASELINE.md`).

## Interpretation and cadence

A failed server verification indicates configuration or runtime failure before
probe collection. Direct runner URL failures describe that runner's path to the
URL; they do not identify a server protocol defect. SNI failures require separate
server, target TLS and network investigation. Only comparable verified client
paths can support a transport-level comparison.

Each selected profile consumes a separate disposable VPS. Cost depends on the
provider plan and actual runtime. Run after transport changes or when gathering
a fresh baseline, retaining server checks, direct controls and client acceptance
as separate evidence.

## Template for the dated publish doc

Save the consolidated two-vantage table at
`docs/TRANSPORT-REACHABILITY-MATRIX-<YYYY-MM-DD>.md` using:

```markdown
# Transport reachability matrix — <YYYY-MM-DD>

- **Exit IP:** <ip>
- **Provider / zone:** <provider> / <zone>
- **Vantage (filtered):** <one-line description — DC, residential, etc.; no operator-identifying labels>
- **CI run:** <workflow run URL>
- **Filtered run captured at:** <ISO timestamp>

| Profile | Runner verdict | Filtered verdict | Delta attribution |
|---------|----------------|------------------|-------------------|
| p0      | OK             | OK               | none              |
| p0p1    | OK             | TLS_BLOCK        | network-layer     |
| p0p1p2  | OK             | OK               | none              |

## Findings

- …

## Action items

- …
```

Do not include operator/carrier/ISP/geographic labels in the table or
findings — describe by technical signature (per the hard rules in root
`CLAUDE.md`). Acceptable: "filtered residential vantage with TLS-cap
policing on port 443". Not acceptable: anything naming a carrier or
oblast.
