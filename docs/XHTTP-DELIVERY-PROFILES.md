# Direct XHTTP delivery profiles

The RIPDPI-format materializer emits the primary and, when
`nginx_xhttp.fallback_enabled` is true in the selected profile, a separate
`p1-xhttp-<host>-alternate` outbound. It uses `nginx_xhttp_fallback_port` and
`fallback_server_name` (or the primary name when intentionally shared).
Both endpoints remain independently selectable and independently probed.
Official sing-box export does not advertise unsupported XHTTP.

`xray.xhttp_mode` selects `auto`, `packet-up` or `stream-up`. The local Xray
adapter consumes the exact selected mode. Optional `xray.xhttp_xmux` admits only:

| Field | Inclusive bounds | Purpose |
|---|---|---|
| maxConnections | 1–16 | Client HTTP connection pool bound |
| hMaxRequestTimes | 1–1024 | Requests before connection retirement |
| hMaxReusableSecs | 1–600 | Maximum connection reuse lifetime |

Nondefault mode and XMUX inputs require `xray.version: v26.3.27`, the exact
engine covered by this local matrix. Other versions refuse these controls until
the allowlist and real native matrix are reviewed together. Values are integers; booleans, ranges, unknown fields and arbitrary extra JSON
refuse semantic admission before publication. XMUX controls the client pool;
the server uses the same typed mode and retains its own resource policy.
The allowlist follows the exact Xray 26.3.27 configuration structs and is
exercised by `make test-xhttp-delivery-matrix`. Existing defaults remain selected
unless an operator explicitly opts into these limits. Measurements establish
local traffic and fault behavior, not better performance on an external path.

Artifacts contain per-device credentials and must stay private. Local acceptance
uses synthetic authority and trusted test certificates with hostname validation.
External recipient adoption and production rollout are outside the local roadmap
completion scope. Classical P0, destination isolation, transport log suppression,
rollback and the PQE HOLD are retained.
