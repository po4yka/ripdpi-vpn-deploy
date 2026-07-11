# Control assumptions audit

## Purpose and status

This document is a repository-local historical snapshot dated 2026-07-11. It records lessons about reviewing transport and defensive assumptions; it is neither a defect tracker nor a compliance report. Current behavior and status belong beside the owning code and documentation.

## Method

The review traced live repository contracts across roles, scripts, provider configuration, tests, and operator documentation, then adversarially cross-checked each conclusion against the implementation and its stated scope. Conclusions without direct repository evidence were treated as measurement questions rather than defects.

## Lessons

1. Log-token and schema contracts must fail loudly when upstream formats drift; silent empty matches create false confidence.
2. An on-host listener or firewall check does not prove delivery across the filtered path; external probes and packet capture answer different layers of the question.
3. A single vantage does not establish cohort behavior; results must identify the measured path and avoid generalizing beyond it.
4. Hardcoded ASN tiers and policy thresholds are dated operator judgments that require periodic repository-local measurement and an explicit owner.
5. Early post-deploy exposure is a measurement question; controls should record timing evidence before claiming preventive coverage.
6. Single-pass audits tend to overclaim unless every finding states its scope, evidence, confidence, and unresolved assumptions.

## Evidence map

- Log and schema contracts: `ansible/roles/policy-ratelimit/`, `scripts/run-rkn-block-checker.sh`, and `tests/unit/`.
- Host-versus-path reachability: `scripts/burn-check.sh`, `scripts/probe-sni-survival.sh`, `docs/PROVIDER-NOTES.md`, and `docs/TRANSPORT-REACHABILITY-MATRIX.md`.
- Vantage and cohort scope: `scripts/transport-reachability-matrix.sh`, `docs/MULTI-COHORT.md`, and `ansible/group_vars/all.yml`.
- ASN and provider judgments: `scripts/validate-reality-target.sh` and `docs/PROVIDER-NOTES.md`.
- Post-deploy observation: `ansible/roles/honeypot/`, `ansible/roles/monitoring/`, and `scripts/probing-summary.sh`.

## Maintenance

Keep current status beside the owning implementation. Future audits must cite checked-in repository paths and dated local measurements, identify scope and confidence, and move actionable work into the repository's normal issue and test surfaces.
