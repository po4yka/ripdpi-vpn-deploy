"""Canonical bounded payloads and the operator payload probe implementation."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

MAX_BYTES = 1048576
PREFIX = b"vpn-deploy-payload-v1:"
NETWORK_ERRORS = {5, 6, 7, 16, 18, 28, 35, 52, 55, 56, 92, 97}


def payload(size: int) -> bytes:
    if not 1 <= size <= MAX_BYTES:
        raise ValueError("invalid-size")
    return b"".join(hashlib.sha256(PREFIX + counter.to_bytes(8, "big")).digest()
                    for counter in range((size + 31) // 32))[:size]


def sizes_value(value: str) -> list[int]:
    if len(value) > 128 or not re.fullmatch(r"[0-9]+(?:,[0-9]+)*", value):
        raise ValueError("invalid-sizes")
    sizes = [int(part) for part in value.split(",")]
    if not 1 <= len(sizes) <= 16 or sizes != sorted(set(sizes)) or not all(1 <= n <= MAX_BYTES for n in sizes):
        raise ValueError("invalid-sizes")
    return sizes


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid-arguments")


def arguments(argv):
    parser = Parser(description="Verify exact payload download and optional upload through an explicit path.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--sizes", default="1024,4096,8192,16384,24576,32768")
    parser.add_argument("--scheme", choices=("http", "https"), default="https")
    parser.add_argument("--echo-path", default="/__throttle_probe")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--asn")
    parser.add_argument("--no-state", action="store_true")
    parser.add_argument("--socks-port", type=int)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--ca-file", type=Path)
    args = parser.parse_args(argv)
    args.sizes = sizes_value(args.sizes)
    if not 1 <= args.port <= 65535 or not 1 <= args.timeout <= 30:
        raise ValueError("invalid-bounds")
    if args.socks_port is not None and not 1 <= args.socks_port <= 65535:
        raise ValueError("invalid-proxy")
    host = args.host
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part) for part in host.split(".")):
            raise ValueError("invalid-host") from None
    if not re.fullmatch(r"/[A-Za-z0-9/_-]*", args.echo_path) or len(args.echo_path) > 256:
        raise ValueError("invalid-path")
    if args.asn is not None:
        if not re.fullmatch(r"(?:AS)?[0-9]{1,10}", args.asn):
            raise ValueError("invalid-asn")
        number = int(args.asn.removeprefix("AS"))
        if not 1 <= number <= 4294967295:
            raise ValueError("invalid-asn")
        args.asn = f"AS{number}"
    if args.socks_port is not None and args.asn is None:
        # ASN discovery uses a separate direct whois/DNS path. Require explicit
        # metadata so selecting SOCKS never triggers that side channel.
        raise ValueError("proxy-requires-asn")
    if args.ca_file is not None and not args.ca_file.is_file():
        raise ValueError("invalid-ca-file")
    return args


def transfer(args, size: int, directory: Path, upload: bool = False) -> dict:
    host = f"[{args.host}]" if ":" in args.host else args.host
    url = f"{args.scheme}://{host}:{args.port}{args.echo_path}?bytes={size}"
    command = ["curl", "--disable", "--silent", "--globoff", "--max-time", str(args.timeout),
               "--connect-timeout", str(args.timeout), "--max-filesize", str(size),
               "--proto", "=http,https", "--header", "Accept-Encoding: identity",
               "--write-out", "\n%{http_code} %{time_total}"]
    if args.socks_port is None:
        command += ["--proxy", "", "--noproxy", "*"]
    else:
        command += ["--noproxy", "", "--socks5-hostname", f"127.0.0.1:{args.socks_port}"]
    if args.ca_file is not None:
        command += ["--cacert", str(args.ca_file)]
    if upload:
        source = directory / "upload"
        source.write_bytes(payload(size))
        command += ["--header", "Content-Type: application/octet-stream", "--data-binary", f"@{source}"]
    command += ["--url", url]
    # Curl's own deadline bounds a stalled read; the extra byte budget bounds
    # chunked/lying responses even on curl releases without streaming size caps.
    env = {key: value for key, value in os.environ.items()
           if not key.lower().endswith("_proxy") and key not in {"CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
    timed_out = False
    raw = bytearray()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env) as process:
        deadline = time.monotonic() + args.timeout + 2
        try:
            with selectors.DefaultSelector() as selected:
                selected.register(process.stdout, selectors.EVENT_READ)
                while len(raw) < size + 128:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selected.select(remaining):
                        timed_out = True
                        break
                    chunk = os.read(process.stdout.fileno(), size + 128 - len(raw))
                    if not chunk:
                        break
                    raw.extend(chunk)
            if timed_out or len(raw) == size + 128:
                process.kill()
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    raw = bytes(raw)
    result = {"bytes": size, "completed": False, "rtt_ms": None, "direction": "upload" if upload else "download"}
    if timed_out or process.returncode in NETWORK_ERRORS:
        result["error_kind"] = "network"
        return result
    try:
        body, metadata = raw.rsplit(b"\n", 1)
        status, elapsed = metadata.decode("ascii").split()
        ms = round(float(elapsed) * 1000)
    except (ValueError, UnicodeError, OverflowError):
        result["error_kind"] = "unexpected-response"
        return result
    if process.returncode != 0 or status != "200" or body != payload(size):
        result["error_kind"] = "payload-mismatch" if status == "200" else "unexpected-response"
        return result
    result.update(completed=True, rtt_ms=ms)
    return result


def classify_direction(rows: list[dict]) -> tuple[str, int | None]:
    baseline = [row for row in rows if row["bytes"] < 16384]
    suspect = [row for row in rows if row["bytes"] >= 16384]
    if not baseline or not suspect or not all(row["completed"] for row in baseline):
        return "unknown", None
    # Total time grows with body size even at a constant healthy rate.
    # Compare per-byte time; zero-duration samples have no timing resolution.
    rates = [row["rtt_ms"] / row["bytes"] for row in baseline if row["rtt_ms"] > 0]
    median = statistics.median(rates) if rates else 0
    thresholds = [row["bytes"] for row in suspect
                  if not row["completed"] or (median > 0 and row["rtt_ms"] / row["bytes"] >= 3 * median)]
    return ("throttled", min(thresholds)) if thresholds else ("ok", None)


def classify(rows: list[dict]) -> dict:
    completed = [row for row in rows if row["completed"]]
    rtt = int(statistics.median(row["rtt_ms"] for row in completed)) if completed else None
    result = {"verdict": "unknown", "rtt_ms": rtt, "threshold_bytes": None, "sizes": rows}
    errors = [row.get("error_kind") for row in rows if row.get("error_kind") not in {None, "network"}]
    if errors:
        result.update(verdict="error", error_kind=errors[0])
        return result
    if not completed:
        result["verdict"] = "blocked"
        return result
    directions = [classify_direction([row for row in rows if row["direction"] == direction])
                  for direction in sorted({row["direction"] for row in rows})]
    thresholds = [threshold for verdict, threshold in directions if verdict == "throttled"]
    if thresholds:
        result.update(verdict="throttled", threshold_bytes=min(thresholds))
    elif all(verdict == "ok" for verdict, _ in directions):
        result["verdict"] = "ok"
    return result


def probe(argv) -> dict:
    args = arguments(argv)
    if shutil.which("curl") is None:
        raise ValueError("missing-curl")
    prefix = None
    if args.asn is None:
        lookup = Path(__file__).with_name("probe-asn.sh")
        try:
            observed = subprocess.run([str(lookup), args.host], text=True, capture_output=True, timeout=10, check=True)
            columns = observed.stdout.strip().split("\t")
            args.asn = f"AS{int(columns[1])}"
            if not 1 <= int(columns[1]) <= 4294967295:
                raise ValueError
            prefix = str(ipaddress.ip_network(columns[2], strict=False))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            raise ValueError("asn-lookup-failed") from None
    with tempfile.TemporaryDirectory(prefix="payload-throttle-") as directory:
        rows = []
        for size in args.sizes:
            rows.append(transfer(args, size, Path(directory)))
            if args.upload:
                rows.append(transfer(args, size, Path(directory), upload=True))
        result = classify(rows)
    result["asn"] = args.asn
    if prefix is not None:
        result["prefix"] = prefix
    if not args.no_state:
        directory = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "vpn-deploy/payload-throttle"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
                name = stream.name
                json.dump(result, stream, sort_keys=True)
                stream.write("\n")
            os.replace(name, directory / f"{args.asn}.json")
        finally:
            if name is not None:
                Path(name).unlink(missing_ok=True)
    return result


def main():
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--hashes":
            result = [{"expected_bytes": size, "sha256": hashlib.sha256(payload(size)).hexdigest()}
                      for size in sizes_value(sys.argv[2])]
        else:
            result = probe(sys.argv[1:])
    except (ValueError, OSError, subprocess.SubprocessError):
        # Input/path/remote content never enters public diagnostics.
        result = {"verdict": "error", "rtt_ms": None, "error_kind": "probe-error"}
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
