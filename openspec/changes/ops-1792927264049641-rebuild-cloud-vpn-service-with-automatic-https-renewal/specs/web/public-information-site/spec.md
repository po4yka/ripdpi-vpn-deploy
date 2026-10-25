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
