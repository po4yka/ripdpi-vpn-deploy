# docs/measurements — operator-published field reports

This folder carries dated field-measurement reports. Each report
captures one measurement run end-to-end: methodology, raw data, and
the interpretation against working hypotheses. Reports are the
deliverable from spike tasks that ask "does the published pattern
reproduce against our infrastructure?"

## Design decisions

**Dated, not versioned** — every measurement is its own document
named `<topic>-<YYYY-MM-DD>.md`. A second run against the same topic
produces a second dated file; we do not edit prior reports to "add
new data" because the conditions of a measurement (vantage state,
filtering posture, upstream routing) drift fast enough that the old
data should not be retconned.

**Raw data, then interpretation** — every report carries the JSON
output from the measurement driver verbatim (or a link to it as an
artifact), then a separate "Interpretation" section that names which
hypothesis the data supports. The split is load-bearing: future
readers can re-run the interpretation against the same raw data
without having to repeat the field measurement.

**Templates live alongside the data** — when a spike adds a new
measurement methodology, the template lives at
`<topic>-TEMPLATE.md` in this folder. Operators copy and date it.

## What's done well

- **Hard-rules enforcement in the templates** — every template ships
  with an explicit reminder that vantage labels, source addresses,
  and other identifiers must describe the technical signature, not
  the operator/carrier/geography.

## Pitfalls

- **Do not commit raw secrets or client IPs** — vantage public IPs
  go in the report as a one-line "vantage IP class" descriptor
  (e.g. "residential dynamic-IP CGNAT") and the actual numeric IP
  stays in the driver's local JSON only. The correlation tool
  accepts the IP via `--client-ip` so the report does not need it
  to be interpreted.
- **Do not edit a prior report to "fix" methodology** — a re-run
  is a new dated file; the old report becomes "superseded by"
  with a link to the new one and stays in place as the audit
  trail.
