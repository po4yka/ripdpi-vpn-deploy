# Idle-cycle access-attempt unblock — <YYYY-MM-DD>

Fill this template after running `docs/RUNBOOK-idle-cycle-measurement.md`
end-to-end. Save the result as
`docs/measurements/access-attempt-unblock-<YYYY-MM-DD>.md`. Do not
publish carrier / ISP / operator / geographic identifiers — describe
the vantage by technical signature only.

## Measurement metadata

| Field | Value |
|-------|-------|
| Run timestamp (UTC, started_at) | <YYYY-MM-DDTHH:MM:SSZ> |
| Run timestamp (UTC, finished_at) | <YYYY-MM-DDTHH:MM:SSZ> |
| Server endpoint                  | `host:port` of the measurement rig |
| Server SNI                       | `<sni>` |
| Vantage descriptor               | one of: residential-CGNAT, residential-fixed-IP, datacenter, mobile-CGNAT (technical signature, no operator name) |
| Schedule                         | e.g. `5m,30m,60m,4h,24h` |
| Followups per cycle              | <int> |
| Driver version                   | git SHA of `scripts/idle-cycle-measure.sh` at run time |
| Correlation tool version         | git SHA of `scripts/idle-cycle-server-correlate.py` at run time |

## Raw data

Attach (or link to) the correlated JSON. Inline the per-cycle summary
table:

| Cycle idx | Idle duration | Cold ms | Cold verdict | Followup median ms | Other-source SYNs in cold envelope | Client SYN retransmits in cold envelope |
|-----------|---------------|---------|--------------|--------------------|------------------------------------|----------------------------------------|
| 0         | 5m            |         | ok           |                    | 0                                  | 1                                      |
| 1         | 30m           |         |              |                    |                                    |                                        |
| 2         | 1h            |         |              |                    |                                    |                                        |
| 3         | 4h            |         |              |                    |                                    |                                        |
| 4         | 24h           |         |              |                    |                                    |                                        |

JSON output: `<path or link>`

## Interpretation

Map the observed data to the working hypothesis space from the
runbook. Pick **one** primary classification and justify with two to
four data points from the table above. If the data are
inconclusive, say so — do not over-fit.

| Hypothesis | Match | Why |
|------------|-------|-----|
| `idle-lru` (filter state cached + evicted) | yes / no / partial | <data> |
| `nat-conntrack` (upstream NAT lost translation) | yes / no / partial | <data> |
| `probe-and-cache` (active upstream probe before admit) | yes / no / partial | <data> |
| Inconclusive | | |

**Primary classification:** `<one of the four>`

**Reasoning:** <one paragraph, with cycle indices cited>

## Vantage-side caveats

- <Did the vantage's network conditions change mid-run? (DHCP rebind,
  carrier hand-off, OS update)>
- <Was any other measurement traffic active on the same network
  during the run?>
- <What additional vantage / endpoint pairs would be useful to
  triangulate the result?>

## Follow-ups

- <Is the pattern stable enough to promote to a `vpnd probe-idle-cycle`
  subcommand? — list the threshold values that would inform the
  default schedule.>
- <Does this signal compose with any of the three already-known
  filtering classes (TLS-cap policing, TCP-freeze, four-layer
  baseline)? If yes, link to the relevant measurement or doc.>

## Hard-rules compliance checklist

Tick before publishing. Treat any unchecked item as a blocker.

- [ ] No carrier / ISP / regulator / geographic identifiers in any
      field, table cell, or comment.
- [ ] No external knowledge-store references or page slugs.
- [ ] Vantage descriptor uses a technical signature.
- [ ] Client public IP not committed in plaintext.
- [ ] Server endpoint name does not embed an operator label.
