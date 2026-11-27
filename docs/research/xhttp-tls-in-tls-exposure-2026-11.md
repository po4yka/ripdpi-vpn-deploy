# XHTTP TLS-in-TLS classifier exposure — 2026-11-27

> **Status:** Research · **Type:** research · **Tier:** — · **Reviewed:** 2026-11-27

This page assesses whether the P1 transport (VLESS over XHTTP behind nginx) as deployed is exposed to a TLS-in-TLS flow classifier, which server-side mitigations the deployment can choose, and whether a follow-up feature task is justified. It is not normative and changes no default. It is the server half of one study; the client half is `po4yka/RIPDPI#TRN-1795705033979683`. The conclusions here do not depend on that task.

## Evidence labels and confidence

Every claim carries a source class and a confidence.

| Source class | Meaning |
|---|---|
| Measured here | The loopback lab in [the fleet-wide transport signatures study](fleet-transport-signatures-2026-11.md#1-xhttp-inbound-without-a-vision-flow). No packet left the workstation. It shows a wire shape, not how a filter treats it. |
| Read from configuration | A template or golden render in this repository. |
| Upstream | The Xray project documentation for VLESS. Not checked against the pinned build here. |
| Abstract only | A preprint dated 2026-11-23. Only its abstract was read. Its data came from an access network outside the filtered path. Single source, unverified. |

Confidence is `high`, `medium` or `low`, and describes the claim, not the threat.

## What a TLS-in-TLS classifier looks for

A classifier of this kind looks at the outer encrypted stream and searches for the shape of a second TLS handshake inside it (Abstract only and general literature, medium). The features are:

1. **Inner handshake record sizes.** The inner ClientHello and the server flight appear as outer records whose length is the inner length plus a constant.
2. **Inner handshake order and direction.** Small upload, large download, small upload, then application data, in the first round trips of a flow.
3. **Round-trip timing.** The inner handshake adds round trips that a direct TLS session to the same server does not have.
4. **Flow-level divergence from one server.** The traffic of the flow does not look like the traffic of the TLS server that the outer handshake names.

The preprint reports that shaping a proxy to mimic one TLS server cut a classifier detection rate from over 85 percent to about 3 percent at a 1 percent false-positive rate (Abstract only, low). This page uses that result only as a reason to treat feature 4 as a candidate. It does not use the numbers to rank options.

## Exposure by feature

| Feature | P1 XHTTP as deployed | P0 REALITY with Vision |
|---|---|---|
| 1. Inner handshake record sizes | **Exposed.** Each inner handshake record appears as one outer record of inner size plus 26 bytes; ClientHello matched in 6 of 6 runs, the server flight in 6 of 6 (Measured here, high). | **Covered.** Vision pads the inner handshake; outer records changed on every run and matched no inner size plus a constant (Measured here, high). |
| 2. Inner handshake order and direction | **Exposed.** The outer record order follows the inner handshake one to one (Measured here, high). | **Partly covered.** Padding hides sizes; the direction pattern of the first round trips stays (Upstream, medium). |
| 3. Round-trip timing | **Exposed** to the same degree as any proxy; no timing shaping is configured (Read from configuration, high). | **Not covered.** Vision adds no delay (Upstream, medium). |
| 4. Divergence from one server | **Exposed.** The outer flow names the node's own nginx site, and its traffic does not look like that site (Read from configuration, medium). | **Not covered.** The flow names the borrowed or self-steal site; its traffic after the handshake does not look like that site (Read from configuration, medium). |

Where the exposure comes from (Read from configuration, high):

- The XHTTP inbound clients have no `flow` key, the inbound uses `"security": "none"` and `"decryption": "none"`, and nginx terminates the outer TLS (`ansible/roles/xray/templates/config.json.j2`, golden render `tests/snapshot/golden/xray/templates/config.json.j2`).
- nginx forwards the XHTTP path with request and response buffering off (`tests/snapshot/golden/nginx-xhttp/templates/site.conf.j2`), so each inner write leaves as its own HTTP/2 DATA frame.
- The XHTTP header padding is active, but it pads HEADERS frames only, not DATA frames (Measured here, high).
- The XHTTP mode does not change feature 1: in `stream-up` mode the first upload record also matched the inner ClientHello in 6 of 6 runs (Measured here, high; later records in that mode not measured).

What is not known: whether the filter on the target path uses any of these features against P1 today (no filtered-path evidence, unknown). The threat model row for TLS-in-TLS describes P1 as browser-shaped; that is true for the HTTP layer and false for the inner handshake shape.

## Server-side options

Design-level notes only. No option has concrete parameters here, and no option is chosen by this page.

| Option | Covers | Cost and risk | Evidence |
|---|---|---|---|
| A. VLESS Encryption with the Vision flow on the XHTTP inbound | Features 1 and partly 2, the same as P0 | Needs client support for VLESS Encryption; adds one inbound-wide server parameter beside the per-device UUIDs (it identifies the server, not a device); changes the client bundle contract | Upstream, medium: the Vision flow is available on any transport when VLESS Encryption is on, and then pads inside the encryption layer. Not measured with the pinned Xray build. |
| B. VLESS Encryption without Vision | The start of the flow only: the encryption handshake can send padding and use a randomised appearance | Same client cost as A; later inner records keep their size | Upstream, medium |
| C. XHTTP multiplexing so that one outer connection carries many inner flows | Feature 2 after the first inner handshake on a connection | The first inner handshake on each new outer connection stays clean; more concurrent streams on one connection | Read from configuration, medium (the client bundle can carry multiplexing settings); not measured |
| D. Front P1 with a CDN (`cdn-front` role) | Unknown: the CDN re-frames the stream, which can change record sizes | The CDN is not the filtered-path baseline ([decision 0001](../decisions/0001-cdn-not-filtered-path-baseline.md)) | None |
| E. Shape the flow to mimic the outer server | Feature 4, and the result that the preprint reports | No implementation in the pinned stack; research only | Abstract only, low |
| F. Keep P1 as a fallback behind P0 in the client order | Reduces how often the exposed shape is on the wire | Client decision, outside this repository; P1 then carries traffic mostly when P0 fails, which is when exposure matters | None here; owned by the client task |

Options A and B are the only ones that the deployment can set on the server with the pinned stack. Option A is the only one that removes feature 1, the feature that the lab measured.

## Conclusion for P1

- **Exposure:** P1 as deployed carries a detectable inner TLS handshake on every new outer connection. The size and order of the inner handshake are visible to a passive observer of the outer stream (Measured here, high). Whether the filter uses this is unknown.
- **Comparison:** P0 with Vision covers the size feature and leaves direction, timing and server divergence. P1 covers none of the four.
- **Go or no-go:** **go** for a follow-up feature task for option A, with two gates before any default changes:
  1. A loopback lab measurement with the pinned Xray build that repeats the record-size table of the fleet signatures study with option A on, and shows that no record matches an inner size plus a constant.
  2. A confirmed client capability for VLESS Encryption with Vision over XHTTP, owned by `po4yka/RIPDPI#TRN-1795705033979683`.

  The task is spec-required, because it changes the secrets schema, the Xray inbound and the client bundle contract. Filing it is a separate decision. No-go for options D and E as follow-ups now: D conflicts with decision 0001, and E has only abstract-level evidence.
