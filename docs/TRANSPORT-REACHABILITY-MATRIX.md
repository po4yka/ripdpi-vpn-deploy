# Transport reachability matrix

A two-vantage measurement of which transport-profile combinations
reach a freshly-provisioned VPS from (a) an unfiltered runner and
(b) an operator-supplied filtered-network vantage. The same VPS is
reconfigured between profiles so the exit IP and Reality identity
stay constant; only the active toggles change. The non-filtered
half is automated in CI; the filtered-vantage half is operator-driven
and the two halves are stitched together offline.

This complements `docs/REGRESSION-BASELINE.md`. Regression-baseline
measures a deploy diff *before vs after*; reachability-matrix measures
a profile diff *across the transport set, same deploy*.

## Why two vantages

A single-vantage report cannot distinguish "the profile is broken on
the server" from "the profile is filtered between the vantage and the
server". The non-filtered vantage isolates the server side: if the
runner cannot reach a profile, the server's configuration is wrong
regardless of any filtering pipeline. The filtered-network vantage
then attributes any *additional* failures to the network in between.

## Profile shorthands

Each shorthand expands to an `ansible-playbook --extra-vars` block. The
CI orchestrator (`scripts/transport-reachability-matrix.sh`) bakes the
mapping. The base set turns off every role that needs real hardware
(TUN devices, kernel modules, external networks) so an ephemeral CI
VPS can converge on every iteration without flake.

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

The workflow:

1. Provisions one ephemeral UpCloud VPS using the existing
   `make init plan apply inventory wait` chain.
2. For each profile in the input list, runs
   `ansible-playbook site.yml --extra-vars "<profile vars>"` against
   the VPS, then runs `scripts/run-rkn-block-checker.sh <exit-ip>`
   from the runner. Reports for each profile land at
   `.transport-reachability/<profile>/<exit-ip>/latest.json`.
3. Uploads `.transport-reachability/` as a 90-day artifact named
   `transport-reachability-matrix-<run-id>`.
4. Always destroys the VPS in the cleanup step, even on partial
   failure.

## Operator vantage half (manual)

The filtered-network vantage cannot be CI-automated — no commodity
runner sits behind the policy pipeline you want to characterise. The
manual procedure:

1. Pull the CI artifact for the run you care about. Note the
   `exit_ip` from `index.json`.
2. From a workstation on the filtered network (with `rkn-block-checker`
   installed — see `docs/REGRESSION-BASELINE.md`), run the harness
   once per profile against the same exit IP:
   ```bash
   scripts/run-rkn-block-checker.sh "$EXIT_IP" \
     --state-dir ~/.local/state/vpn-deploy/transport-reachability/<profile>/
   ```
3. Stitch the two halves: for each profile, diff the non-filtered
   report (from the CI artifact) against the filtered report (from
   your workstation). A URL that is `OK` from the runner and
   non-`OK` from the filtered vantage attributes the failure to the
   network in between.
4. Publish the consolidated table as
   `docs/TRANSPORT-REACHABILITY-MATRIX-<YYYY-MM-DD>.md` (one dated
   doc per coordinated measurement run). Use the template at the
   bottom of this file.

## Output schema

`.transport-reachability/index.json`:

```jsonc
{
  "schema_version": 1,
  "exit_ip": "203.0.113.1",
  "profiles": {
    "p0": {
      "extra_vars": "vpn.enable_xray_reality=true …",
      "report_path_relative": "p0/203.0.113.1/latest.json"
    },
    "p0p1": { … }
  }
}
```

The per-profile `latest.json` follows the `rkn-block-checker` report
schema (`schema_version: 1`, see `docs/REGRESSION-BASELINE.md`).

## Interpretation patterns

- **Runner OK, filtered non-OK, single profile** — that profile's
  wire signature is being matched. Compare the protocol family
  against other profiles to identify the discriminator.
- **Runner OK, filtered non-OK, every profile** — filtering applies
  at the IP/ASN layer, not the protocol. Rotate the exit IP; consider
  a different provider region.
- **Runner non-OK, single profile** — the server-side configuration
  failed to apply. Inspect the CI deploy log for that profile.
- **Runner non-OK, every profile** — the VPS is unreachable from any
  vantage. Provider firewall or routing issue; investigate before
  drawing transport-level conclusions.

## Cost and cadence

One workflow run lifecycles a single VPS for ~30 min plus per-profile
deploy time (~3–5 min each). Three profiles ~= 45 min, ~$0.40 of
UpCloud credit. Run when:

- A new transport role is added (sweep includes the new profile).
- A protocol fingerprint changes upstream and you want to confirm the
  server-side change still reaches an unfiltered vantage.
- Quarterly, to track drift across the existing profile set.

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
