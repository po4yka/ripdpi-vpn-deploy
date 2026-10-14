"""Fixture-only real sink forwarding and historical rollback sample proof."""

import json
import math
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FIXTURE = Path("/var/lib/observability-fixture")
SINK = "http://127.0.0.1:19098"
METRIC = "vpn_observability_rollback_probe"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


ERROR_FIELDS = {
    "stage": {"length", "body", "peer", "forward", "receipt", "response", "unknown"},
    "detail": {
        "out_of_order",
        "too_old",
        "unsupported_format",
        "snappy_decode",
        "protobuf_decode",
        "other",
        "oversized_response",
        "unavailable",
        "not_http",
    },
    "encoding": {"snappy", "zstd", "absent", "other"},
    "write_version": {"v1", "v2", "absent", "other"},
    "content_type": {"protobuf", "absent", "other"},
    "category": {
        "forward_headers",
        "handler_input",
        "forward_contract",
        "sink_timeout",
        "sink_transport",
        "receipt_io",
        "response_io",
        "handler_other",
    },
}


def classify_handler_error(error, headers, stage):
    """Reduce fixture errors to fixed categories without returning raw content."""
    encoding = headers.get("Content-Encoding")
    version = headers.get("X-Prometheus-Remote-Write-Version")
    content_type = headers.get("Content-Type")
    result = {
        "stage": stage if stage in ERROR_FIELDS["stage"] else "unknown",
        "encoding": encoding
        if encoding in {"snappy", "zstd"}
        else "other"
        if encoding
        else "absent",
        "write_version": {"0.1.0": "v1", "2.0.0": "v2"}.get(
            version, "other" if version else "absent"
        ),
        "content_type": "protobuf"
        if content_type == "application/x-protobuf"
        else "other"
        if content_type
        else "absent",
        "detail": "not_http",
    }
    if isinstance(error, urllib.error.HTTPError):
        result["category"] = (
            "sink_http_" + str(error.code)
            if isinstance(error.code, int) and 400 <= error.code <= 599
            else "handler_other"
        )
        try:
            body = error.read(4097)
            if len(body) > 4096:
                result["detail"] = "oversized_response"
            else:
                text = body.decode("utf-8", errors="replace").lower()
                result["detail"] = "other"
                for category, needles in (
                    ("out_of_order", ("out of order", "out-of-order")),
                    ("too_old", ("too old", "out of bounds", "out-of-bounds")),
                    (
                        "unsupported_format",
                        ("unsupported", "content type", "content encoding"),
                    ),
                    ("snappy_decode", ("snappy",)),
                    ("protobuf_decode", ("protobuf", "proto:", "unmarshal")),
                ):
                    if any(needle in text for needle in needles):
                        result["detail"] = category
                        break
        except (OSError, ValueError, AttributeError, TypeError):
            result["detail"] = "unavailable"
    elif isinstance(error, (KeyError, TypeError)):
        result["category"] = (
            "forward_headers" if stage == "forward" else "handler_input"
        )
    elif isinstance(error, TimeoutError):
        result["category"] = "sink_timeout"
    elif isinstance(error, OSError):
        result["category"] = {"receipt": "receipt_io", "response": "response_io"}.get(
            stage, "sink_transport"
        )
    elif isinstance(error, ValueError):
        result["category"] = "forward_contract"
    else:
        result["category"] = "handler_other"
    return result


def forward_payload(body, headers):
    if not 0 < len(body) <= 8 * 1024 * 1024:
        raise ValueError("invalid_payload_bound")
    names = ("Content-Type", "Content-Encoding", "X-Prometheus-Remote-Write-Version")
    forwarded = {name: headers[name] for name in names}
    request = urllib.request.Request(
        SINK + "/api/v1/write", data=body, headers=forwarded
    )
    with OPENER.open(request, timeout=5) as response:
        if response.status not in (200, 204):
            raise ValueError("sink_did_not_accept")


def prepare_probe():
    with OPENER.open("http://127.0.0.1:19090/metrics", timeout=5) as response:
        text = response.read().decode()
    rows = re.findall(
        r"^vm_persistentqueue_blocks_written_total(?:[{][^}]*[}])? ([0-9.eE+-]+)$",
        text,
        re.MULTILINE,
    )
    if len(rows) != 1:
        raise ValueError("ambiguous_queue")
    nonce = time.time_ns() // 1_000_000
    descriptor, name = tempfile.mkstemp(
        prefix="rollback-probe-", suffix=".prom", dir=FIXTURE
    )
    outage_at = time.time()
    complete = False
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(f"{METRIC} {nonce}\n")
            handle.flush()
            os.fsync(handle.fileno())
            inode = os.fstat(handle.fileno()).st_ino
        complete = True
    finally:
        if not complete:
            Path(name).unlink()
    return {
        "nonce": nonce,
        "outage_at": outage_at,
        "probe": name,
        "inode": inode,
        "blocks_before": float(rows[0]),
    }


def remove_probe(proof):
    path = Path(proof["probe"])
    if (
        path.parent != FIXTURE
        or not path.name.startswith("rollback-probe-")
        or path.suffix != ".prom"
    ):
        raise ValueError("foreign_probe_path")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_ino != proof["inode"]:
        raise ValueError("foreign_probe_identity")
    path.unlink()


def _diagnostic_query(expression, proof, *, at_end):
    params = {"query": expression}
    if at_end:
        params["time"] = proof["outage_end"]
    try:
        with OPENER.open(
            SINK + "/api/v1/query?" + urllib.parse.urlencode(params), timeout=5
        ) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            return {"state": "oversized"}
        result = json.loads(raw)
        if (
            result.get("status") != "success"
            or result["data"].get("resultType") != "vector"
        ):
            return {"state": "invalid"}
        vector = result["data"]["result"]
        if not isinstance(vector, list):
            return {"state": "invalid"}
        samples = []
        for row in vector[:16]:
            metric = row["metric"]
            value = float(row["value"][1])
            samples.append(
                {
                    "expected_node": metric.get("node") == "node-fixture",
                    "job": metric.get("job")
                    if metric.get("job")
                    in {
                        "node-exporter",
                        "node-exporter-required-services",
                        "observability-agent",
                    }
                    else "other-or-absent",
                    "value_matches_nonce": math.isfinite(value)
                    and value == proof["nonce"],
                    "value_inside_outage": math.isfinite(value)
                    and proof["outage_at"] < value <= proof["outage_end"],
                }
            )
        return {
            "state": "success",
            "count": len(vector),
            "samples": samples,
            "truncated": len(vector) > 16,
        }
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        return {"state": "unavailable"}


def diagnose(proof):
    """Bounded fixture-only evidence; preserve the historical acceptance assertion."""
    expression = METRIC + '{node="node-fixture"}'
    result = {
        "historical_value": _diagnostic_query(expression, proof, at_end=True),
        "historical_timestamp": _diagnostic_query(
            "timestamp(" + expression + ")", proof, at_end=True
        ),
        "recent_any_node": _diagnostic_query(
            "max_over_time(" + METRIC + "[10m])", proof, at_end=False
        ),
    }
    names = {
        "vmagent_remotewrite_pending_data_bytes",
        "vmagent_remotewrite_pending_inmemory_blocks",
        "vmagent_remotewrite_errors_total",
        "vmagent_remotewrite_retries_count_total",
        "vmagent_remotewrite_packets_dropped_total",
        "vmagent_remotewrite_samples_dropped_total",
        "vmagent_remotewrite_bytes_sent_total",
        "vmagent_remotewrite_blocks_sent_total",
        "vm_persistentqueue_blocks_written_total",
        "vm_persistentqueue_blocks_read_total",
        "vm_persistentqueue_bytes_pending",
        "vm_persistentqueue_bytes_dropped_total",
        "vm_rows_ignored_total",
    }
    result["sender_counters"] = {}
    try:
        with OPENER.open("http://127.0.0.1:19090/metrics", timeout=5) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("oversized_metrics")
        for name, raw_value in re.findall(
            r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:[{][^}]*[}])? ([0-9.eE+-]+)$",
            raw.decode(),
            re.MULTILINE,
        ):
            if name in names:
                value = float(raw_value)
                if math.isfinite(value):
                    total = result["sender_counters"].get(name, 0) + value
                    if math.isfinite(total):
                        result["sender_counters"][name] = total
                    else:
                        result["sender_state"] = "invalid"
    except (OSError, ValueError):
        result["sender_state"] = "unavailable"
    phases = {
        "headers",
        "accepted",
        "handler_error",
        "length_rejected",
        "short_body",
        "tls_unknown_ca",
    }
    result["receiver_phases"] = {}
    result["handler_errors"] = {}
    try:
        with (FIXTURE / "receiver-events.log").open("rb") as source:
            size = os.fstat(source.fileno()).st_size
            source.seek(max(0, size - 65536))
            raw = source.read(65537)
        result["receiver_tail_truncated"] = size > 65536
        for line in raw.splitlines():
            try:
                event = json.loads(line)
                phase = event.get("phase")
                if isinstance(phase, str) and phase in phases:
                    result["receiver_phases"][phase] = (
                        result["receiver_phases"].get(phase, 0) + 1
                    )
                if phase == "handler_error":
                    for field, allowed in ERROR_FIELDS.items():
                        value = event.get(field)
                        if isinstance(value, str) and (
                            value in allowed
                            or (
                                field == "category"
                                and re.fullmatch(r"sink_http_[45][0-9]{2}", value)
                            )
                        ):
                            counts = result["handler_errors"].setdefault(field, {})
                            counts[value] = counts.get(value, 0) + 1
            except (ValueError, AttributeError):
                continue
    except OSError:
        result["receiver_state"] = "unavailable"
    return result


def require_historical(proof):
    expression = METRIC + '{node="node-fixture"}'
    rows = []
    for query in (expression, "timestamp(" + expression + ")"):
        params = urllib.parse.urlencode({"query": query, "time": proof["outage_end"]})
        with OPENER.open(SINK + "/api/v1/query?" + params, timeout=5) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("oversized_query_result")
        result = json.loads(raw)
        if result["status"] != "success" or result["data"]["resultType"] != "vector":
            raise ValueError("query_did_not_succeed")
        vector = result["data"]["result"]
        if len(vector) != 1 or vector[0]["metric"].get("node") != "node-fixture":
            raise ValueError("missing_or_ambiguous_historical_sample")
        rows.append(vector[0])
    labels = [
        {k: v for k, v in row["metric"].items() if k != "__name__"} for row in rows
    ]
    value, timestamp = (float(row["value"][1]) for row in rows)
    if (
        rows[0]["metric"].get("__name__") != METRIC
        or labels[0] != labels[1]
        or not math.isfinite(value)
        or value != proof["nonce"]
        or not proof["outage_at"] < timestamp <= proof["outage_end"]
    ):
        raise ValueError("exact_historical_sample_not_recovered")


def main():
    action = sys.argv[1]
    if action == "prepare":
        print(json.dumps(prepare_probe(), sort_keys=True))
        return
    proof = json.loads(sys.argv[2])
    if action == "freeze":
        proof["outage_end"] = time.time()
        remove_probe(proof)
        print(json.dumps(proof, sort_keys=True))
    elif action == "cleanup":
        remove_probe(proof)
    elif action == "diagnose":
        print(json.dumps(diagnose(proof), sort_keys=True, allow_nan=False))
    elif action == "verify":
        require_historical(proof)
        print("exact_historical_rollback_sample=pass")
    else:
        raise ValueError("unknown_fixture_action")


if __name__ == "__main__":
    main()
