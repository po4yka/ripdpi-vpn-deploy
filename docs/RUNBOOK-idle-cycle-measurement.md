# Runbook: idle-cycle access-attempt measurement spike

Operator-side procedure for measuring whether a filtering pipeline
applies a per-flow idle-LRU rule to bare-HTTPS endpoints: first
access after a long idle stalls for ~1 minute, subsequent accesses
inside a short window are immediate, the block re-applies after the
next idle gap.

The source observation came from a single forum reporter with one
endpoint. This spike measures the pattern from a stable filtered-
residential vantage against a controlled server we operate, with
both sides logging at sub-second precision so the cold-probe wait
window can be cross-referenced against server-side SYNs from
non-client source IPs (the active-probe hypothesis).

This spike does **not** produce a confirmed mechanism on its own.
The deliverable is a reproducible measurement and a structured
report that names which of the three working hypotheses the data
supports.

## The three hypotheses

| Tag | Prediction | What confirms it |
|-----|------------|------------------|
| `idle-lru` | Filter caches per-flow state with an LRU; eviction takes ~60 s; on re-entry the filter does a fresh check | Cold probe stalls ~60 s, no `other_source_syn` in the wait window |
| `nat-conntrack` | An upstream NAT loses the flow's translation; the first packet through has to re-establish | Cold probe stalls but a SYN-RETRANSMIT pattern appears on the server side (multi-SYN from the client IP within 60 s) |
| `probe-and-cache` | The filter actively probes the destination before admitting the first user; second access uses the cached verdict | At least one SYN from a source IP that is **not** the client's appears between the cold probe's `pre_ms` and `post_ms` |

## Pre-requisites

- A foreign VPS reachable on a public IP (any provider; not the same
  IP that fronts production transports — a clean endpoint with no
  other listeners avoids cross-talk in the SYN log).
- TLS material for an SNI of the operator's choice. The source
  observation used a third-party SNI; this spike works with any SNI
  the operator can present a valid cert for. The cert does not need
  to be public-CA — the driver passes `-verify_quiet`.
- A workstation on the filtered-residential vantage with `openssl`,
  `jq`, and `python3` installed.
- Patience: the default schedule runs through 5 m, 30 m, 60 m, 4 h,
  24 h idle gaps — total wall time ~30 h.

## Step 1 — stand the server

On the foreign VPS:

```bash
# Minimal nginx config — see the inline block below.
sudo apt-get install -y nginx tcpdump iptables-persistent
sudo tee /etc/nginx/sites-available/idle-cycle.conf <<'NGX'
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name _;

    # Self-signed or operator-supplied. Path is illustrative.
    ssl_certificate     /etc/nginx/idle-cycle.fullchain.pem;
    ssl_certificate_key /etc/nginx/idle-cycle.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache off;            # measurement: no session resumption
    ssl_session_tickets off;          # measurement: no session resumption

    # Sub-second TLS access log. The correlation tool parses this
    # exact format.
    log_format idlecycle '$time_iso8601 $remote_addr sni=$ssl_server_name '
                        'tls_complete_ms=$request_time';
    access_log /var/log/nginx/idle-cycle-tls.log idlecycle;

    location / {
        return 204;
    }
}
NGX
sudo ln -sf /etc/nginx/sites-available/idle-cycle.conf /etc/nginx/sites-enabled/
sudo systemctl reload nginx

# SYN logging via iptables LOG with the prefix the correlation tool
# greps for.
sudo iptables -I INPUT -p tcp --dport 443 --syn -j LOG \
    --log-prefix "idle-cycle-syn: " --log-level 6
sudo netfilter-persistent save

# Pipe kern.log to a stable path (most distros do this already; the
# correlation tool reads /var/log/syslog by default).
```

Note: the `ssl_session_cache off` + `ssl_session_tickets off` lines
are load-bearing — TLS session resumption would short-circuit the
ClientHello latency on followup probes and erase the very signal we
are trying to measure.

## Step 2 — run the driver from the filtered-residential vantage

```bash
scripts/idle-cycle-measure.sh \
  --target measurement.example.com:443 \
  --sni '*.stackoverflow.com' \
  --vantage 'residential-vantage-A' \
  --schedule 5m,30m,60m,4h,24h \
  --followup-count 3 \
  --output ~/idle-cycle-$(date -u +%Y%m%dT%H%M%SZ).json
```

The script rejects vantage labels that smuggle in carrier / ISP /
operator identifiers (per the hard rules in root CLAUDE.md). Use
"residential-vantage-A", "datacenter-vantage-B" or similar technical-
signature labels.

Progress prints to stderr; the final per-cycle summary prints to
stdout. The full result lands at the `--output` path as a single
JSON object.

## Step 3 — collect the server-side logs

After the driver completes, on the foreign VPS:

```bash
# Capture the SYN log around the measurement window. Adjust the
# --since time to bracket the driver's started_at / finished_at.
sudo journalctl --since "$START_TS" --until "$END_TS" --no-pager > /tmp/idle-cycle-syn.log
sudo cp /var/log/nginx/idle-cycle-tls.log /tmp/idle-cycle-tls.log
```

Scp the two log files back to the operator workstation alongside the
JSON output from Step 2.

## Step 4 — correlate

```bash
scripts/idle-cycle-server-correlate.py \
  --client-report ~/idle-cycle-<timestamp>.json \
  --syn-log       ~/idle-cycle-syn.log \
  --tls-access-log ~/idle-cycle-tls.log \
  --client-ip     "$VANTAGE_PUBLIC_IP" \
  > ~/idle-cycle-<timestamp>.correlated.json
```

The output JSON carries a `per_probe` array with one entry per probe
(cold + followups), each carrying:

- `client_syn_count` — SYNs the server observed from the client IP
  inside the probe envelope. Repeated SYNs from the client inside a
  cold probe support the `nat-conntrack` hypothesis (retransmit
  pattern).
- `other_source_syn_count` and `other_source_syn_sample` — SYNs
  inside the probe envelope from any non-client IP. A non-zero count
  on a cold probe is the direct measurement of an upstream active
  probe; that supports the `probe-and-cache` hypothesis.

## Step 5 — interpret + publish

Read the correlated JSON against the hypothesis table at the top of
this doc. Map the data to one of the three tags (or "inconclusive"
if the pattern does not reproduce).

Publish the writeup at
`docs/measurements/access-attempt-unblock-<YYYY-MM-DD>.md` using the
template at `docs/measurements/access-attempt-unblock-TEMPLATE.md`.

Per the repo hard rules, do not name the operator, carrier, or
geography in the writeup; describe the vantage by technical signature
("filtered residential vantage with TLS-cap policing"; not
"residential connection in city X on carrier Y").

## Tear-down

On the foreign VPS:

```bash
sudo iptables -D INPUT -p tcp --dport 443 --syn -j LOG --log-prefix "idle-cycle-syn: " --log-level 6
sudo netfilter-persistent save
sudo rm /etc/nginx/sites-enabled/idle-cycle.conf
sudo systemctl reload nginx
sudo rm -f /var/log/nginx/idle-cycle-tls.log
```

If the VPS was provisioned for this spike only, `make destroy`
through the appropriate Terraform root retires it cleanly.

## Cross-spike notes

The driver's `--schedule` parser accepts the same `NN{s,m,h,d}`
grammar as `vpnd probe-matrix`, so an operator can copy a probe-
matrix schedule into this driver and back without translation.

This spike does not overlap with `docs/REGRESSION-BASELINE.md`. The
regression baseline measures four-layer verdicts against many URLs
at one moment; this spike measures one URL's first-access latency
across many idle gaps. Different signals; different reports.
