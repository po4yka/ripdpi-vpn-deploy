## Context

The current parser selects `(current Latest` and conflates availability with adoption.

## Goals / Non-Goals

- Goal: check one explicit reviewed pin while recording the security release accurately.
- Non-goal: change private pins, promote a release, or bypass the 48-hour staging gate.

## Decisions

Use the exact `(repository pin)` heading marker, require one match, and update all callers and tests. Do not retain the old marker as a fallback.

## Contracts and ownership

The primary writer owns scripts/check-xray-version-pin.py, its unit test, and docs/reference/xray-release-line.md. Other infrastructure layers are unaffected.

## Risks / Trade-offs

A stale local pin can still pass parity, so the reference must state the separate security qualification requirement. Parity is not a vulnerability scan or deployment acceptance.

## Migration Plan

Change the reference marker and parser together. Test new Latest with retained pin, mismatch, missing and duplicate markers; run the existing breaking-change guard and make check. Revert the source change together if needed; no deployed state changes.
