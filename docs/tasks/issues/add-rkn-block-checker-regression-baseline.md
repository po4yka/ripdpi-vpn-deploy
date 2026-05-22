---
title: Add rkn-block-checker Python harness as deploy-side regression baseline
type: task
status: backlog
area: ci
priority: high
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[rkn-block-checker-methodology]]"
linked_task: null
---

- [ ] #task Add rkn-block-checker Python harness as deploy-side regression baseline #repo/RIPDPI-VPN-DEPLOY #area/ci #status/backlog ⏫

## Motivation

The `rkn-block-checker` tool (Python pip package, published 2026-05-07) provides a structured four-layer DNS/TCP/TLS/HTTP diagnostic with explicit per-layer verdicts (`DNS_BLOCK`, `TCP_RESET`, `TLS_BLOCK`, `HTTP_STUB`, `OK`). Mapped to TSPU pipeline stages, the taxonomy is directly applicable to validating server-side configuration changes — run before and after every Xray/Hysteria2/AmneziaWG config change to confirm the change actually shifts the verdict in the intended direction.

## Proposed change

Add a deploy-side regression baseline that runs `rkn-block-checker` against:

1. Every deployed VPS exit IP, before and after each `make deploy` invocation.
2. A standardized 21-whitelist-control + 15-blacklist-test URL set (per upstream recommendation).
3. Pass `--proxy socks5://...` to also validate that bypass configurations change verdict from blocked to OK.

Implementation:

- `scripts/run-rkn-block-checker.sh` — wrapper that loads the URL set, invokes the tool, parses JSON output, and emits a diff against the previous run.
- `scripts/rkn-block-checker-url-set.yaml` — canonical 21+15 URL set with rationale per entry.
- `.github/workflows/rkn-block-checker-baseline.yml` — optional CI job that runs the harness on a `workflow_dispatch` trigger.
- Documented in `docs/REGRESSION-BASELINE.md`.

## Canonical recipe

no-canonical-fit — operator-tooling addition that does not strictly match any of the 4 documented recipes (new role / new provider / new vpnd subcommand / new AWG cohort). Closest analogue: tooling under `scripts/` per CLAUDE.md §"Layered ownership". Priority kept at `high` because every fleet deploy benefits from before/after measurement; if architecture discussion downgrades the fit, drop to `medium`.

## Acceptance criteria

- [ ] `pip install rkn-block-checker` reproducible from the repo (pinned to a known version in `requirements.txt`).
- [ ] `scripts/run-rkn-block-checker.sh <exit-ip>` runs cleanly and produces JSON output.
- [ ] URL set documented with rationale per entry.
- [ ] Diff-against-previous-run logic produces a human-readable changelog when verdicts shift.
- [ ] `docs/REGRESSION-BASELINE.md` describes operator usage and interpretation.

## Risks / open questions

- URL set composition may drift over time as the RU blocklist changes — schedule periodic review (quarterly?).
- Tool depends on Python + a few transitive dependencies; pin via `requirements.txt` to avoid CI drift.

## References

- [[rkn-block-checker-methodology]] — wiki concept page with full 4-layer taxonomy + JSON schema + 21+15 URL set rationale
- [[dpi-detector]] — complementary tool with phase-split error classifier (potentially run in parallel for cross-validation)
- [[censorship-update-habr-2026-05-09]] — source digest where the tool was first ingested
