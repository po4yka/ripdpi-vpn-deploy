## Purpose

Preserve the complete operator interface and its useful behavior when the
implementation of vpnd changes from Rust to Python.

## ADDED Requirements

### Requirement: REQ-PYCLI-SURFACE — Complete command and argument parity

Python vpnd MUST implement deploy, reconverge, share, doctor, probe,
probe-matrix, preflight, fleet, host, ai-docs, update and completions, including
every nested action, argument, short alias, default, environment override and
argument relationship enumerated in design.md. It MUST retain parser errors,
runtime failures and signal exit statuses, and scoped JSON support.

#### Scenario: Full interface exercised

- **WHEN** the baseline command/flag matrix runs through the repository launcher and installed wheel
- **THEN** each supported invocation reaches its real Python handler with the expected arguments
- **AND** invalid enums, conflicting token sources, unsupported JSON flags and doctor --clip without --ai fail before work starts

### Requirement: REQ-PYCLI-PIPELINES — Canonical orchestration and targeting

Each command MUST preserve the baseline ordered Make/script plan and flag
translation, validated environment/provider and explicit secrets path. Make
MUST remain canonical; Terraform calls MUST use scripts/terraform-env.sh.
Reconverge MUST use exact validated inventory aliases and MUST reject absent,
ambiguous or cross-environment registry matches before deployment.

#### Scenario: Scoped reconvergence

- **WHEN** a registered host resolves to exactly one matching vpn inventory key
- **THEN** dry-run, deploy and verify receive that exact limit
- **AND** an ambiguous match exits nonzero without invoking deployment

### Requirement: REQ-PYCLI-STATE — Existing state and version semantics

The replacement MUST read and write the existing hosts.toml and update-cache
formats and locations, preserve registry fields and name ordering, retain
version-skew warnings and the 24-hour cache policy, and recognize both current
release tag schemes. It MUST retain default root discovery, provider-directory
checks and runtime path resolution without rewriting operator-owned state.

#### Scenario: Existing installation state

- **WHEN** Python vpnd opens synthetic baseline registry and cache documents
- **THEN** records round-trip without losing optional fields, fresh cache hits avoid HTTP, future/corrupt cache data is rejected, and older/equal versions produce no upgrade notice

### Requirement: REQ-PYCLI-ARTIFACTS — Recipient and diagnostic output parity

The replacement MUST preserve sing-box JSON, recipient HTML, both QR SVGs,
deep links, platform app cards, documentation exports, diagnostic archive
members, clipboard prompts and structured output shapes. Templates MUST escape
untrusted text. Tokens MUST remain opaque, validated and absent from public
logs. SVGs MUST be valid and have numeric dimensions of at least 256 pixels.
Doctor MUST preserve partial diagnostics and exit nonzero if any step fails.

#### Scenario: Recipient bundle and failed diagnostics

- **WHEN** share renders an adversarial synthetic client and doctor encounters a failed middle diagnostic
- **THEN** the recipient artifacts contain usable escaped links/QR payloads and doctor exports all diagnostic sections with explicit failures and redacted sensitive content
