## Purpose

Serve useful public model evaluation articles with accessible navigation, stable routes and readable layouts on common screen sizes.

## ADDED Requirements

### Requirement: REQ-PIS-READ — Responsive public reading

The implementation MUST retain the public article routes and useful content, provide clear navigation and a responsive reading layout, support keyboard focus and light and dark appearance, and avoid horizontal overflow on narrow screens.

#### Scenario: Narrow-screen reader

- **WHEN** a reader opens each public route at a narrow viewport
- **THEN** article text, navigation and cards remain readable and usable without clipped controls or horizontal scrolling.

### Requirement: REQ-PIS-BOUNDARY — Public content and verified HTTPS

The implementation MUST provide consistent canonical metadata and a real 404 response, redirect the alternate site hostname to the canonical HTTPS origin, and keep management and bearer access data out of the public content and request logs.

#### Scenario: Ordinary visitor and missing route

- **WHEN** an ordinary browser loads the public site or requests a missing route
- **THEN** valid HTTPS serves the expected public page or a styled 404 with correct HTTP status and without management or credential disclosure.

#### Scenario: Domain-facing web profile

- **WHEN** the public site uses the `vpn-p1-web` profile
- **THEN** its public listener contract contains only TCP/80 and TCP/443, and subscription delivery is disabled.

#### Scenario: Operator-owned site passes through the deployment controller

- **WHEN** an exact-host deployment supplies `nginx_xhttp_public_site_dir`
- **THEN** it MUST accept only a bounded owner-controlled static tree with a regular `404.html`, snapshot the validated content for publication, and refuse links, unsafe ancestry or a source change before host writes; unrelated role overrides remain forbidden.
