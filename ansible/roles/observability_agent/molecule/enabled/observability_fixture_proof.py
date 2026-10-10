"""Fixture-only real sink forwarding and historical rollback sample proof."""

import json
import math
import os
import re
import stat
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

FIXTURE = Path("/var/lib/observability-fixture")
SINK = "http://127.0.0.1:19098"
METRIC = "vpn_observability_rollback_probe"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


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
    elif action == "verify":
        require_historical(proof)
        print("exact_historical_rollback_sample=pass")
    else:
        raise ValueError("unknown_fixture_action")


if __name__ == "__main__":
    main()
