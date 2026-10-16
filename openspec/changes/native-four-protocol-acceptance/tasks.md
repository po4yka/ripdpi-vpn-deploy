# TST-1791618356595983: Deliver isolated native acceptance for every baseline transport

## Objective

Deliver isolated native acceptance for every baseline transport.

## Ownership

- tests/native/transport_acceptance/ runner and native cases
- tests/integration/transport_runtime_acceptance/fixture.py orchestration ownership
- tests/conftest.py and tests/unit/test_four_transport_runner.py cleanup and honesty checks
- .github/workflows/ci.yml and scripts/select-ci-checks.py required native consumer
- tests/unit/test_ci_tooling_cache.py native consumer coverage
- Makefile, docs/TESTING.md, scripts/CLAUDE.md and tests/CLAUDE.md
- This task's portfolio, execution, specification and verification records

## Execution

- [x] TST-1791618369402905 Deliver exact-engine Linux four-protocol positive and rejection cases through existing adapters #feature !high @item:TST-1791618356595983
- [x] TST-1791618370981853 Exercise warm activation retirement rotation and failed authority compensation with real processes #feature !high @item:TST-1791618356595983
- [x] TST-1791618372464891 Prove both-family firewall-owned hopping and isolated unrelated-UDP preservation #feature !high @item:TST-1791618356595983
- [x] TST-1791618373730661 Wire complete no-skip native acceptance into source checks with exact redacted evidence and cleanup #feature !high @item:TST-1791618356595983

## Verification

- `make transport-native-acceptance` passed in the owned integrated Linux CI environment: all 34 cases, zero skips, confirmed resource and engine/source cleanup.
- `build-gate -- mise exec -- make check` passed at the recorded source revision; current focused integration checks and complete hosted source parity also passed. Exact revisions and outcomes are recorded in verification.md.

Requirement-to-step mapping and exact-source evidence live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Provider, physical-device and live-fleet acceptance require separate authorization and scope.
