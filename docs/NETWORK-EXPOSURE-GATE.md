# Reviewed network exposure policy

The gate is disabled by default. It never downloads a feed, starts an updater,
or promotes a policy automatically. Terraform is unchanged; the existing
firewall role remains the only runtime renderer.

## Trust and artifact format

Keep the artifact and signing key outside Git. The controller needs Python with
the repository requirements and OpenSSL. The public key is configured separately
from the artifact and pinned by the SHA-256 digest of its DER SubjectPublicKeyInfo.
Only RSA/SHA-256 signatures with at least 2048-bit keys are accepted; a public key embedded in a feed is not trusted.

The schemas are `contract/network-exposure-artifact.schema.json` and
`contract/network-exposure-policy.schema.json`. Repository fixtures contain only
placeholders. Tests generate fresh addresses and keys in private temporary files.
`python3 scripts/network-exposure-gate.py --check-fixtures` rejects deployable
fixture data without printing its values.

The signed object contains `schema_version: 1`, a technical repository-local
`source_id`, timezone-qualified `created_at` and `expires_at`, an approved review
identity and review ID, `content_sha256`, and `policy`. The policy has exactly three
arrays, each containing at most 4096 canonical CIDRs:

| Direction | Kernel chain | Match |
|---|---|---|
| `ingress` | input | source address |
| `host_egress` | output | destination address |
| `forwarded` | forward | destination address |

An empty array means no decision in that direction. No direction inherits another.
Ingress preserves the local loopback accept; selected network rules precede
conntrack and other accepts. Host egress includes sockets opened by proxy services:
it is not a claim to distinguish their clients from other host-originated traffic.

Canonical JSON is UTF-8 with sorted keys, compact separators, and ASCII escaping (`json.dumps(value, sort_keys=True,
separators=(',', ':'), ensure_ascii=True).encode()`). `content_sha256` hashes
canonical `policy`. Sign canonical bytes of **all fields except `signature`**
with `openssl dgst -sha256 -sign`, then add
`signature: {algorithm: "rsa-sha256", value: "<base64 signature>"}`.
Duplicate JSON fields, unknown schema fields, bad digests, invalid signatures,
unapproved reviews, future creation times, expired artifacts, unsafe files,
and noncanonical CIDRs fail before a policy plan is emitted.

## Review without applying

Store a private operator JSON file outside Git. It has exactly the controller
fields below; no Ansible variable wrapper or YAML input is accepted. The file
must be owned by the invoking user, be a regular non-symlink file, and have mode
`0600`. The artifact must be an owner-controlled private regular file; the public
key must be owner-controlled and not writable by others.

```json
{
  "mode": "log_only",
  "artifact": "/absolute/path/reviewed-artifact.json",
  "trusted_key": "/absolute/path/trusted-public-key.pem",
  "trusted_key_sha256": "<64 lowercase hex characters>",
  "source_id": "<expected technical source ID>",
  "promotion": {
    "approved": false,
    "digest": "",
    "authorized_hosts": []
  }
}
```

```bash
make network-exposure-review NETWORK_EXPOSURE_CONFIG=/absolute/path/review.json ANSIBLE_LIMIT=vpn-p0
```

`ANSIBLE_LIMIT` must be a comma-separated list of exact inventory aliases; broad
groups and patterns are refused. This entry point runs only the controller gate.
It does not render, reload, or change the managed firewall. Summaries contain only
validation state, source ID, directional counts, and content/artifact digests. The
internal normalized plan is an Ansible-only interface protected by `no_log`; do
not use it for operator output.

A normal `make dry-run` uses Ansible check mode. A full site **deployment** still
converges the baseline firewall; `log_only` supplies an empty enforcement plan,
not a bypass of baseline drift repair. Disabled/log-only renders are byte-identical
to the pre-feature firewall. Reviewing an artifact does not remove already-applied
rules: rollback always requires an explicit canonical apply.

## Promotion, expiry, and rollback

Before promotion, record exact-SHA staging evidence, successful protocol and
management-path controls, the observation interval, false-positive thresholds,
and the rollback owner in the local review record. A log-only summary proves
validation, not traffic coverage or safety of a range. Review the proposed ranges
against management access, upstream services, DNS, monitoring, and forwarded client
traffic; collect existing liveness evidence without logging address data here.

For `canary` or `enforce`, explicitly set `promotion_approved: true`, bind
`promotion_digest` to the SHA-256 of the complete signed artifact file, and list
exact inventory aliases in `authorized_hosts`. Patterns are rejected. Canary
promotion must name only the approved isolated hosts; broadening to enforcement
is a new configuration/review decision. Neither mode is activated by this change.

Expiry is checked on every render, check, or apply. **Already-applied rules do not
auto-expire.** Schedule an operator rollback before the deadline: set `mode: disabled`,
apply the canonical firewall, and verify feature-owned `exposure-*` rules are absent
and baseline service controls remain healthy. Invalid or expired artifacts cannot
block this explicit disabled rollback. Refresh means creating and reviewing a new
signed local artifact and approving its new complete-file digest; there is no timer,
remote fetch, hidden refresh, or unattended apply path.
