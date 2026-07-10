#!/usr/bin/env python3
"""Run a redacted Snell payload-size refinement evaluation from a client path."""
from __future__ import annotations

import argparse, hashlib, json, math, os, random, re, shutil, statistics, subprocess, sys, tempfile, time
from pathlib import Path
import yaml

DEFAULT_SIZES = [1024, 4096, 8192, 12288, 14336, 16384, 18432, 20480, 24576, 32768]
TECHNICAL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SCHEMA = Path(__file__).resolve().parent.parent / "contract" / "snell-refinement-result.schema.json"


def median(values: list[int]) -> int | None:
    return int(statistics.median(values)) if values else None


def classify_profile(profile: str, sizes: list[int], repetitions: int, observations: list[dict]) -> dict:
    result, verdict, first = [], "ok", None
    required = math.ceil(repetitions * 2 / 3)
    for size in sizes:
        rows = [r for r in observations if r["profile"] == profile and r["bytes"] == size]
        controls = [r for r in observations if r["profile"] == "direct" and r["bytes"] == size]
        healthy = len(controls) >= repetitions * 2 and all(r["completed"] for r in controls)
        completed = [r for r in rows if r["completed"]]
        elapsed, control_elapsed = median([r["duration_ms"] for r in completed]), median([r["duration_ms"] for r in controls if r["completed"]])
        current = "ok"
        if not healthy: current = "unknown"
        elif len(completed) < required: current = "blocked"
        elif elapsed is not None and control_elapsed and elapsed >= 3 * control_elapsed: current = "throttled"
        if current == "unknown": verdict = "unknown"
        elif current == "blocked" and verdict != "unknown": verdict = "blocked"
        elif current == "throttled" and verdict == "ok": verdict = "throttled"
        if current in {"blocked", "throttled"} and first is None: first = size
        result.append({"bytes": size, "control_healthy": healthy, "completed": len(completed), "attempts": repetitions, "median_ms": elapsed, "control_median_ms": control_elapsed})
    return {"profile": profile, "verdict": verdict, "first_failure_bytes": first, "sizes": result}


def classify(profiles: list[str], sizes: list[int], repetitions: int, observations: list[dict]) -> list[dict]:
    return [classify_profile(profile, sizes, repetitions, observations) for profile in profiles]


def curl_probe(url: str, expected: int, timeout: int, port: int | None = None) -> dict:
    cmd = ["curl", "-sS", "-o", "/dev/null", "--max-time", str(timeout), "-w", "%{http_code} %{size_download} %{time_total}"]
    if port is not None: cmd += ["--socks5-hostname", f"127.0.0.1:{port}"]
    cmd.append(url)
    try: proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2, check=False)
    except (OSError, subprocess.TimeoutExpired): return {"completed": False, "duration_ms": None}
    try: status, downloaded, duration = proc.stdout.strip().split(); duration_ms = round(float(duration) * 1000)
    except ValueError: return {"completed": False, "duration_ms": None}
    return {"completed": proc.returncode == 0 and int(status) == 200 and int(float(downloaded)) == expected, "duration_ms": duration_ms}


def build_config(bundle: dict, path: Path) -> dict[str, int]:
    outbounds = [o for o in bundle.get("outbounds", []) if str(o.get("tag", "")).startswith("p3-snell-")]
    if not outbounds: raise ValueError("bundle contains no p3-snell outbounds")
    ports = {o["tag"]: 19000 + i for i, o in enumerate(outbounds)}
    doc = {"log": {"level": "warn"}, "inbounds": [{"type": "mixed", "tag": f"probe-{i}", "listen": "127.0.0.1", "listen_port": p} for i, p in enumerate(ports.values())], "outbounds": outbounds, "route": {"rules": [{"inbound": [f"probe-{i}"], "outbound": tag} for i, tag in enumerate(ports)], "auto_detect_interface": True}}
    path.write_text(json.dumps(doc, separators=(",", ":")) + "\n"); os.chmod(path, 0o600)
    return ports


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700); fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f: json.dump(payload, f, sort_keys=True); f.write("\n")
        os.chmod(tmp, 0o600); os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--bundle", type=Path, required=True); ap.add_argument("--config", type=Path, required=True); ap.add_argument("--vantage", required=True); ap.add_argument("--state-dir", type=Path); args = ap.parse_args()
    if not TECHNICAL_ID.fullmatch(args.vantage): print("invalid technical vantage id", file=sys.stderr); return 2
    if not shutil.which("sing-box") or not shutil.which("curl"): print("sing-box and curl are required", file=sys.stderr); return 2
    try:
        bundle = json.loads(args.bundle.read_text()); config_bytes = args.config.read_bytes(); config = yaml.safe_load(config_bytes) or {}; base = str(config["probe_base_url"]).rstrip("/")
        if not base.startswith("https://"): raise ValueError("probe_base_url must use https")
        sizes = [int(v) for v in config.get("sizes", DEFAULT_SIZES)]; repetitions = int(config.get("repetitions", 3)); timeout = int(config.get("timeout_seconds", 15))
        if repetitions < 3 or any(v < 1 for v in sizes): raise ValueError("invalid repetitions or sizes")
    except (OSError, KeyError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc: print(f"invalid input: {exc}", file=sys.stderr); return 2
    observations, process = [], None
    with tempfile.TemporaryDirectory(prefix="snell-refinement-") as tmp:
        try:
            cfg = Path(tmp) / "sing-box.json"; ports = build_config(bundle, cfg)
            check = subprocess.run(["sing-box", "check", "-c", str(cfg)], capture_output=True, timeout=10, check=False)
            if check.returncode: raise RuntimeError("sing-box rejected probe config")
            process = subprocess.Popen(["sing-box", "run", "-c", str(cfg)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(.25)
            if process.poll() is not None: raise RuntimeError("sing-box stopped during startup")
            rng = random.Random(config.get("random_seed"))
            for size in sizes:
                url = f"{base}/{size}.bin"
                for _ in range(repetitions):
                    observations.append({"profile": "direct", "bytes": size, **curl_probe(url, size, timeout)})
                    order = list(ports.items()); rng.shuffle(order)
                    for profile, port in order: observations.append({"profile": profile, "bytes": size, **curl_probe(url, size, timeout, port)})
                    observations.append({"profile": "direct", "bytes": size, **curl_probe(url, size, timeout)})
            reports = classify(list(ports), sizes, repetitions, observations); overall = "ok"
            for candidate in ("unknown", "blocked", "throttled"):
                if any(r["verdict"] == candidate for r in reports): overall = candidate; break
            payload = {"schema_version": 1, "observed_at": int(time.time()), "vantage": args.vantage, "verdict": overall, "config_sha256": hashlib.sha256(config_bytes).hexdigest(), "profiles": reports}
            import jsonschema
            jsonschema.validate(payload, json.loads(SCHEMA.read_text()))
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc: print(f"snell-refinement: {exc}", file=sys.stderr); return 1
        finally:
            if process is not None and process.poll() is None: process.terminate(); process.wait(timeout=2)
        if args.state_dir:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(payload["observed_at"])); atomic_json(args.state_dir / args.vantage / f"{stamp}.json", payload)
        print(json.dumps(payload, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
