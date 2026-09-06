## Purpose

Security-relevant behavior matches the repo's written conventions: secret-bearing renders stay out of logs, root scheduled units run sandboxed, perimeter ICMP is shaped per the hardening floor, scheduled work is timer-driven, external repository trust anchors are pinned mandatorily, browser-facing vhosts carry the full header baseline, and rate limiting has exactly one enforcement layer.

## ADDED Requirements

### Requirement: REQ-SECRET-RENDER-SILENT — Secret-bearing renders MUST suppress logs and diffs

Template tasks rendering secret material MUST set no_log and disable diffs, matching the established repo pattern.

#### Scenario: verbose dry-run over a secret-bearing config

- **WHEN** a diff-enabled or debug deploy renders the dns-morph-bridge configuration
- **THEN** no secret value appears in play output or captured logs

### Requirement: REQ-ROOT-UNIT-FLOOR — Root scheduled units MUST carry the systemd sandbox floor

Units running root scripts that parse remote data MUST include the standard hardening directive floor plus minimal writable paths.

#### Scenario: parser compromise in a refresh script

- **WHEN** the backup or geodata refresh script misbehaves on hostile input
- **THEN** the unit's sandbox contains filesystem, privilege, and process-surface exposure

### Requirement: REQ-ICMP-SHAPED — Perimeter ICMP MUST follow the documented shaping floor

Echo traffic MUST be accepted only under a rate limit; required non-echo ICMPv6 types (neighbor discovery, PMTUD) MUST remain explicitly allowed.

#### Scenario: scanner flood

- **WHEN** echo-request volume exceeds the configured rate from any source
- **THEN** excess echo is dropped while neighbor discovery and PMTUD continue working

### Requirement: REQ-TIMER-ONLY-SCHEDULING — Scheduled work MUST use systemd timers

Recurring jobs MUST be scheduled via persistent, jittered timers; new root cron entries are prohibited.

#### Scenario: prefix refresh scheduling

- **WHEN** cdn-front prefix refresh is deployed
- **THEN** it appears in systemctl list-timers with catch-up behavior and no cron.daily file remains

### Requirement: REQ-MANDATORY-REPO-PIN — External repository keys MUST be pinned mandatorily

Artifacts fetched from external repositories MUST verify against a non-empty pin; verification MUST fail closed when the pin is absent.

#### Scenario: unset key digest

- **WHEN** warp-outbound converges without a repository key pin
- **THEN** the role fails before installing any package from that repository

### Requirement: REQ-VHOST-HEADER-PARITY — Browser-facing vhosts MUST share one response-header baseline

Vhosts delivering browser-rendered pages MUST send CSP, X-Content-Type-Options, and Permissions-Policy alongside the existing no-store/referrer/robots directives.

#### Scenario: recipient page fetch

- **WHEN** a client fetches a share-bundle page from the subscription vhost
- **THEN** response headers match the public-site vhost baseline

### Requirement: REQ-RATELIMIT-SINGLE-LAYER — Rate limiting MUST be enforced at exactly one documented layer

Request-rate enforcement for public endpoints MUST live either at nftables per the convention or at nginx per documented exceptions — never both, never undocumented.

#### Scenario: convention audit

- **WHEN** the fleet's rate-limit surfaces are inventoried
- **THEN** each endpoint maps to exactly one enforcement layer whose choice matches the synced documentation
