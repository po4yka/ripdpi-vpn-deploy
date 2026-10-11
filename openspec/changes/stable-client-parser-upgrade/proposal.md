# Change: Upgrade verified recipient parsers to the current stable client line

Task ID: `TST-1791618376497512`

## Why

The repository parser baseline is sing-box 1.13.16 while the fresh public release snapshot on 2026-10-10 identifies stable 1.14.3. Changing a parser pin must demonstrate exact consumer compatibility, not infer protocol support from a newer tag.

Audit coverage: Upgrade or feature roadmap; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Refresh exact verified stable parser artifacts and migration guards on supported architectures.
- Validate complete supported delivered payloads and preserve explicit unsupported XHTTP format routing.
- Keep client engine capability and server release identity independently recorded.

## Capabilities

### New Capabilities

- `clients/stable-parser-adoption`: upgrade verified recipient parsers to the current stable client line.

### Modified Capabilities

- None.

## Impact

- scripts/check-singbox-client-compatibility.py
- tests/unit/test_emit_singbox_roundtrip.py
- tests/unit/test_liveness_profiles.py
- docs/TESTING.md
- tools/tasking or unrelated vpnd migration are OUT OF SCOPE
- .github/workflows/ci.yml
- .github/actions/setup-disposable-ci/action.yml
- scripts/ci-real-deploy.py
- Makefile
- All exact-version expected-value tests discovered from the existing sing-box pin; runtime/source code unrelated to parser consumers is out of scope
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
