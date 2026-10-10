"""Topology-aware probes with schema-3 durable checkpoints and owned jobs."""

import asyncio
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
from vpnd.text import trim_whitespace
from vpnd.yaml_loader import load_yaml
from vpnd.protected_file import open_private, write_private
from vpnd.runner import make
from vpnd.runner.process import CapturePolicy

CONFIG_SCHEMA_VERSION = 2
REPORT_SCHEMA_VERSION = 3
PROTOCOLS = ["mtproto", "xhttp-vless", "xhttp-trojan", "tcp-trojan", "tls-non-443"]
CLASSES = ["allowlist-pattern", "neutral-pattern", "non-allowlist-pattern"]
TOPOLOGIES = ["single-ip-dual-role", "split-hop-ingress"]
VERDICTS = ["ok", "throttled", "blocked", "unknown", "error"]


class Interrupted(Exception):
    def __init__(self, signum):
        self.signal = signum
        super().__init__(f"probe matrix interrupted by signal {signum}; partial report preserved")

    def exit_code(self):
        return 128 + self.signal


def technical_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value))


def parse_duration(value):
    match = re.fullmatch(r"([0-9]+)([smhd]?)", trim_whitespace(value))
    if not match:
        raise ValueError("duration must start with digits and use a known duration unit")
    result = int(match[1]) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match[2]]
    # Rust Instant uses signed nanosecond seconds; keep its representability bound.
    if not 0 < result < 2**63:
        raise ValueError("duration must be nonzero and fit the monotonic clock range")
    return result


def strict_keys(value, keys, required):
    if not isinstance(value, dict) or set(value) - set(keys) or set(required) - set(value):
        raise ValueError("invalid or unknown matrix configuration fields")


def validate_config(config):
    strict_keys(
        config,
        ["schema_version", "vantage", "poll_interval_seconds", "control", "protocols", "targets"],
        ["schema_version", "vantage", "control", "protocols", "targets"],
    )
    if type(config["schema_version"]) is not int or config["schema_version"] != 2:
        raise ValueError("schema_version must be 2")
    control = config["control"]
    strict_keys(
        control,
        ["url", "expected_status", "timeout_seconds", "degraded_after_ms"],
        ["url", "expected_status", "timeout_seconds", "degraded_after_ms"],
    )
    if (
        not technical_id(config["vantage"])
        or not isinstance(control["url"], str)
        or not control["url"].startswith("https://")
        or type(control["expected_status"]) is not int
        or not 100 <= control["expected_status"] <= 599
        or type(control["timeout_seconds"]) is not int
        or not 1 <= control["timeout_seconds"] <= 60
        or type(control["degraded_after_ms"]) is not int
        or not 0 < control["degraded_after_ms"] <= 2**64 - 1
    ):
        raise ValueError("invalid vantage or control configuration")
    interval = config.get("poll_interval_seconds")
    if interval is not None and (type(interval) is not int or not 0 <= interval <= 2**64 - 1):
        raise ValueError("invalid poll interval")
    protocols, targets = config["protocols"], config["targets"]
    if (
        not isinstance(protocols, list)
        or not isinstance(targets, list)
        or not protocols
        or not targets
    ):
        raise ValueError("protocols and targets are required")
    if any(p not in PROTOCOLS for p in protocols) or len(set(protocols)) != len(protocols):
        raise ValueError("protocols must be valid and unique")
    ids: set[str] = set()
    pairs: dict[str, list[dict]] = {}
    for target in targets:
        strict_keys(
            target,
            ["id", "comparison_set", "destination_class", "topology", "profile_file"],
            ["id", "comparison_set", "destination_class", "topology", "profile_file"],
        )
        if (
            not technical_id(target["id"])
            or not technical_id(target["comparison_set"])
            or target["id"] in ids
            or not isinstance(target["profile_file"], str)
            or not Path(target["profile_file"]).is_absolute()
            or target["destination_class"] not in CLASSES
            or target["topology"] not in TOPOLOGIES
        ):
            raise ValueError("invalid or duplicate target")
        ids.add(target["id"])
        pairs.setdefault(target["comparison_set"], []).append(target)
    for name, pair in pairs.items():
        if (
            len(pair) != 2
            or pair[0]["destination_class"] != pair[1]["destination_class"]
            or {t["topology"] for t in pair} != set(TOPOLOGIES)
        ):
            raise ValueError(f"comparison_set '{name}' must pair both topologies in one class")


def transport_fingerprint(profile):
    profile = copy.deepcopy(profile)
    profile.pop("target_id", None)
    profile.pop("endpoint", None)
    for settings in profile.get("protocols", {}).values():
        if isinstance(settings, dict):
            for field in ["secret", "uuid", "password"]:
                settings.pop(field, None)
    return profile


def validate_profiles(config):
    fingerprints: dict[str, dict] = {}
    for target in config["targets"]:
        try:
            with open_private(target["profile_file"]) as handle:
                if stat.S_IMODE(os.fstat(handle.fileno()).st_mode) != 0o600:
                    raise ValueError("mode must be exactly 0600")
                profile = json.load(handle)
        except (OSError, ValueError) as error:
            raise ValueError(
                f"target '{target['id']}' profile must be an owner-controlled 0600 regular file: {error}"
            ) from error
        if (
            not isinstance(profile, dict)
            or type(profile.get("schema_version")) is not int
            or profile.get("schema_version") != 1
            or profile.get("target_id") != target["id"]
        ):
            raise ValueError(f"target '{target['id']}' profile identity or schema is invalid")
        available = profile.get("protocols")
        if not isinstance(available, dict):
            raise ValueError(f"target '{target['id']}' profile has no protocols")
        for protocol in config["protocols"]:
            if protocol not in available:
                raise ValueError(
                    f"target '{target['id']}' profile is missing protocol '{protocol}'"
                )
        fingerprint = transport_fingerprint(profile)
        name = target["comparison_set"]
        if name in fingerprints and fingerprints[name] != fingerprint:
            raise ValueError(
                f"comparison_set '{name}' must use identical runtime and transport parameters"
            )
        fingerprints[name] = fingerprint


def scheduled_tick(start, interval, tick):
    offset = interval * tick
    return start + offset if offset < 2**63 else None


def load_config(path):
    config = load_yaml(Path(path).read_text())
    validate_config(config)
    validate_profiles(config)
    return config


def cell_error(tick, timestamp, protocol, target, verdict, kind):
    return dict(
        tick=tick,
        timestamp_unix_ms=timestamp,
        protocol=protocol,
        target_id=target["id"],
        comparison_set=target["comparison_set"],
        destination_class=target["destination_class"],
        topology=target["topology"],
        verdict=verdict,
        error_kind=kind,
    )


def capture(output):
    try:
        value = json.loads(trim_whitespace(output.stdout))
        if not isinstance(value, dict) or value.get("verdict") not in VERDICTS:
            raise ValueError("invalid verdict")
        rtt, kind = value.get("rtt_ms"), value.get("error_kind")
        if rtt is not None and (type(rtt) is not int or not 0 <= rtt <= 2**64 - 1):
            raise ValueError("invalid RTT")
        if kind is not None and not isinstance(kind, str):
            raise ValueError("invalid error kind")
        return {
            k: v
            for k, v in [("verdict", value["verdict"]), ("rtt_ms", rtt), ("error_kind", kind)]
            if v is not None
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"verdict": "error", "error_kind": "invalid-output"}


async def invoke(command, timeout, timeout_kind):
    try:
        output = await asyncio.wait_for(
            command.capture_policy(CapturePolicy.OWNED_PROCESS_GROUP).capture(False), timeout
        )
        return capture(output)
    except TimeoutError:
        return {"verdict": "unknown", "error_kind": timeout_kind}
    except Exception:
        return {"verdict": "error", "error_kind": "invoke"}


async def run_control(ctx, path, tick, timestamp, timeout):
    command = make.target_with(ctx, "probe-matrix-control", [("MATRIX_CONFIG", str(path))])
    probe = await invoke(command, timeout, "control_timeout")
    return dict(tick=tick, timestamp_unix_ms=timestamp, **probe, sweep_duration_ms=0, overrun_ms=0)


async def run_cell(ctx, path, tick, timestamp, protocol, target, control, timeout):
    try:
        command = make.target_with(
            ctx,
            "probe-matrix-cell",
            [
                ("MATRIX_CONFIG", str(path)),
                ("TARGET_ID", target["id"]),
                ("PROTOCOL", protocol),
                ("CONTROL_VERDICT", control),
            ],
        )
    except ValueError:
        return cell_error(tick, timestamp, protocol, target, "unknown", "make_validation_failed")
    probe = await invoke(command, timeout, "timeout")
    value = cell_error(
        tick, timestamp, protocol, target, probe["verdict"], probe.get("error_kind", "")
    )
    value.pop("error_kind")
    value.update(probe)
    return value


def windows(cells):
    series: dict[tuple[str, str], list[dict]] = {}
    for cell in cells:
        series.setdefault((cell["protocol"], cell["target_id"]), []).append(cell)
    out = []
    for key in sorted(series, key=lambda k: (PROTOCOLS.index(k[0]), k[1])):
        values = sorted(series[key], key=lambda cell: cell["tick"])
        onset = next(
            (i for i, cell in enumerate(values) if cell["verdict"] in ["blocked", "throttled"]),
            None,
        )
        if onset is None:
            continue
        recovery = None
        for cell in values[onset + 1 :]:
            if cell["verdict"] in ["unknown", "error"]:
                break
            if cell["verdict"] == "ok":
                recovery = cell["timestamp_unix_ms"]
                break
        first = values[0]
        out.append(
            {
                **{
                    k: first[k]
                    for k in [
                        "protocol",
                        "target_id",
                        "comparison_set",
                        "destination_class",
                        "topology",
                    ]
                },
                "onset_unix_ms": values[onset]["timestamp_unix_ms"],
                "recovery_unix_ms": recovery,
            }
        )
    return out


def observation(tick, kind, protocol, cls, affected, reason):
    value = dict(tick=tick, kind=kind)
    if protocol is not None:
        value["protocol"] = protocol
    if cls is not None:
        value["destination_class"] = cls
    value.update(
        comparison_sets=sorted({c["comparison_set"] for c in affected}),
        evidence_target_ids=sorted({c["target_id"] for c in affected}),
        reason=reason,
    )
    return value


def analyze(protocols, cells):
    ticks: dict[int, list[dict]] = {}
    for cell in cells:
        ticks.setdefault(cell["tick"], []).append(cell)
    output = []
    for tick in sorted(ticks):
        values = ticks[tick]
        if any(c["verdict"] in ["unknown", "error"] for c in values):
            output.append(
                observation(
                    tick, "indeterminate", None, None, [], "required evidence is unknown or error"
                )
            )
            continue
        classes = sorted({c["destination_class"] for c in values}, key=CLASSES.index)
        for protocol in protocols:
            affected, qualified = [], set()
            for cls in classes:
                candidates = [
                    c for c in values if c["protocol"] == protocol and c["destination_class"] == cls
                ]
                impaired = all(c["verdict"] in ["blocked", "throttled"] for c in candidates)
                alternatives = all(
                    any(
                        other["target_id"] == c["target_id"]
                        and other["protocol"] != protocol
                        and other["verdict"] == "ok"
                        for other in values
                    )
                    for c in candidates
                )
                if (
                    {c["topology"] for c in candidates} == set(TOPOLOGIES)
                    and impaired
                    and alternatives
                ):
                    qualified.add(cls)
                    affected.extend(candidates)
            if len(qualified) >= 2:
                output.append(
                    observation(
                        tick,
                        "protocol-specific",
                        protocol,
                        None,
                        affected,
                        "one protocol is impaired across both topologies in at least two destination classes while another remains healthy",
                    )
                )
        for cls in classes:
            affected = [c for c in values if c["destination_class"] == cls]
            blocked = len(affected) >= len(protocols) * 2 and all(
                c["verdict"] == "blocked" for c in affected
            )
            control_class = any(
                other != cls
                and all(
                    c["verdict"] in ["ok", "throttled"]
                    for c in values
                    if c["destination_class"] == other
                )
                for other in classes
            )
            if blocked and control_class:
                output.append(
                    observation(
                        tick,
                        "destination-class-wide-collateral",
                        None,
                        cls,
                        affected,
                        "all protocols are blocked across both topologies in one destination class",
                    )
                )
        matched, matched_classes = [], set()
        for name in sorted({c["comparison_set"] for c in values}):
            dual = [
                c for c in values if c["comparison_set"] == name and c["topology"] == TOPOLOGIES[0]
            ]
            split = [
                c for c in values if c["comparison_set"] == name and c["topology"] == TOPOLOGIES[1]
            ]
            if (
                len(dual) == len(protocols)
                and len(split) == len(protocols)
                and all(c["verdict"] == "blocked" for c in dual)
                and all(c["verdict"] in ["ok", "throttled"] for c in split)
            ):
                matched_classes.add(dual[0]["destination_class"])
                matched.extend(dual + split)
        if len(matched_classes) >= 2:
            output.append(
                observation(
                    tick,
                    "dual-role-targeting-candidate",
                    None,
                    None,
                    matched,
                    "single-IP targets are blocked while matched split-hop targets remain usable",
                )
            )
    return output


def validate_output_path(path):
    if path.name in {"", ".", ".."} or path.suffix.lower() in [".jsonl", ".lock"]:
        raise ValueError(
            "report output must name a file and must not use a reserved .jsonl or .lock suffix"
        )
    if not path.suffix.isascii():
        raise ValueError("report output extension must be ASCII")


def companion_path(path, suffix):
    return Path(str(path) + suffix)


def lock_output(path):
    validate_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        companion_path(path, ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
    )
    try:
        meta = os.fstat(descriptor)
        if (
            not stat.S_ISREG(meta.st_mode)
            or meta.st_uid != os.getuid()
            or stat.S_IMODE(meta.st_mode) != 0o600
            or meta.st_size != 0
        ):
            raise ValueError("unsafe probe session lock file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("probe report output is already in use or cannot be locked") from error
        return os.fdopen(descriptor, "r+b")
    except BaseException:
        os.close(descriptor)
        raise


def start_journal(path):
    journal_path = companion_path(path, ".jsonl")
    write_private(journal_path, b"")
    descriptor = os.open(journal_path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(descriptor)
        if (
            not stat.S_ISREG(meta.st_mode)
            or meta.st_uid != os.getuid()
            or stat.S_IMODE(meta.st_mode) != 0o600
        ):
            raise ValueError("unsafe probe journal file")
        return os.fdopen(descriptor, "ab")
    except BaseException:
        os.close(descriptor)
        raise


def report_to_json(report):
    return json.dumps(report, indent=2, ensure_ascii=False)


def checkpoint(report, protocols, path, journal, tick):
    report["finished_at_unix_ms"] = max(0, int(time.time() * 1000))
    report["windows"] = windows(report["cells"])
    report["observations"] = analyze(protocols, report["cells"])
    record = dict(
        schema_version=3,
        timestamp_unix_ms=report["finished_at_unix_ms"],
        completed=report["completed"],
        interrupted=report["interrupted"],
        control=next((c for c in report["controls"] if c["tick"] == tick), None),
        cells=[c for c in report["cells"] if c["tick"] == tick],
    )
    journal.write(
        (
            json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()
    )
    journal.flush()
    os.fsync(journal.fileno())
    write_private(path, report_to_json(report).encode())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def json_summary(report, output):
    value = {
        k: report[k]
        for k in [
            "schema_version",
            "completed",
            "interrupted",
            "started_at_unix_ms",
            "finished_at_unix_ms",
        ]
    }
    value.update(
        report_path=str(output),
        ticks=len(report["controls"]),
        cells=len(report["cells"]),
        observations=len(report["observations"]),
    )
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


async def race_signal(task, event):
    signal_task = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait([task, signal_task], return_when=asyncio.FIRST_COMPLETED)
        if signal_task in done:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return None
        return await task
    finally:
        signal_task.cancel()
        await asyncio.gather(signal_task, return_exceptions=True)


async def run(ctx, args):
    path = Path(args.config or ctx.root / "vpnd/config/probe-matrix.yaml").resolve(strict=True)
    config = load_config(path)
    for key, value in [
        ("ENV", ctx.env),
        ("PROVIDER", ctx.provider),
        ("SECRETS_FILE", str(ctx.secrets_file)),
        ("MATRIX_CONFIG", str(path)),
    ]:
        make.validate_kv(key, value)
    for target in config["targets"]:
        make.validate_kv("TARGET_ID", target["id"])
    interval = (
        args.poll_interval_seconds
        if args.poll_interval_seconds is not None
        else config.get("poll_interval_seconds")
    )
    interval = 300 if interval is None else interval
    if interval <= 0:
        raise ValueError("poll interval must be greater than zero")
    duration = parse_duration(args.duration)
    if ctx.explain:
        print(
            f"# vpnd probe-matrix would orchestrate:\n  vantage: {config['vantage']}\n  config: {path}\n  ticks: {(duration + interval - 1) // interval}\n  protocols: {len(config['protocols'])}\n  targets: {len(config['targets'])}\n  target ids: {', '.join(t['id'] for t in config['targets'])}"
        )
        print(
            "  "
            + make.target_with(
                ctx,
                "probe-matrix-cell",
                [
                    ("MATRIX_CONFIG", str(path)),
                    ("TARGET_ID", "target-id"),
                    ("PROTOCOL", "protocol"),
                    ("CONTROL_VERDICT", "verdict"),
                ],
            ).explain()
        )
        return 0
    started = int(time.time() * 1000)
    output = Path(args.output or ctx.root / f"vpnd/state/probe-matrix-{started}.json")
    report = dict(
        schema_version=3,
        completed=False,
        interrupted=False,
        vantage=config["vantage"],
        started_at_unix_ms=started,
        finished_at_unix_ms=started,
        poll_interval_seconds=interval,
        controls=[],
        cells=[],
        windows=[],
        observations=[],
    )
    event = asyncio.Event()
    caught: list[int] = []
    loop = asyncio.get_running_loop()
    previous = {sig: signal.getsignal(sig) for sig in [signal.SIGINT, signal.SIGTERM]}

    def interrupt(signum):
        if not caught:
            caught.append(signum)
        event.set()

    for sig in previous:
        loop.add_signal_handler(sig, interrupt, sig)
    try:
        with lock_output(output), start_journal(output) as journal:
            checkpoint(report, config["protocols"], output, journal, None)
            mono_start, tick = time.monotonic(), 0
            deadline = mono_start + duration
            while time.monotonic() < deadline:
                tick_start, timestamp = time.monotonic(), int(time.time() * 1000)
                control = await race_signal(
                    asyncio.create_task(
                        run_control(
                            ctx, path, tick, timestamp, config["control"]["timeout_seconds"]
                        )
                    ),
                    event,
                )
                if control is None:
                    control = dict(
                        tick=tick,
                        timestamp_unix_ms=timestamp,
                        verdict="unknown",
                        error_kind="interrupted",
                        sweep_duration_ms=0,
                        overrun_ms=0,
                    )
                defaults = [
                    cell_error(tick, timestamp, protocol, target, "unknown", "interrupted")
                    for protocol in config["protocols"]
                    for target in config["targets"]
                ]
                if not caught:
                    jobs = [
                        asyncio.create_task(
                            run_cell(
                                ctx,
                                path,
                                tick,
                                timestamp,
                                protocol,
                                target,
                                control["verdict"],
                                config["control"]["timeout_seconds"],
                            )
                        )
                        for protocol in config["protocols"]
                        for target in config["targets"]
                    ]

                    async def collect():
                        return await asyncio.gather(*jobs, return_exceptions=True)

                    result = await race_signal(asyncio.create_task(collect()), event)
                    for index, job in enumerate(jobs):
                        if job.done() and not job.cancelled():
                            if job.exception() is None:
                                defaults[index] = job.result()
                            else:
                                defaults[index]["verdict"], defaults[index]["error_kind"] = (
                                    "error",
                                    "task-failed",
                                )
                    if result is None:
                        for job in jobs:
                            job.cancel()
                        await asyncio.gather(*jobs, return_exceptions=True)
                sweep = int((time.monotonic() - tick_start) * 1000)
                control.update(sweep_duration_ms=sweep, overrun_ms=max(0, sweep - interval * 1000))
                report["controls"].append(control)
                report["cells"].extend(defaults)
                report["interrupted"] = bool(caught)
                checkpoint(report, config["protocols"], output, journal, tick)
                if caught:
                    break
                tick += 1
                next_tick = scheduled_tick(mono_start, interval, tick)
                if next_tick is None or next_tick >= deadline:
                    break
                if next_tick > time.monotonic():
                    await race_signal(
                        asyncio.create_task(asyncio.sleep(next_tick - time.monotonic())), event
                    )
                    if caught:
                        break
            report["completed"], report["interrupted"] = not caught, bool(caught)
            checkpoint(report, config["protocols"], output, journal, None)
        print(json_summary(report, output) if args.json else f"wrote {output}")
        if caught:
            raise Interrupted(caught[0])
        return 0
    finally:
        for sig, handler in previous.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)


def synthetic_report_for_snapshot():
    started, protocols = 1700000000000, ["mtproto", "xhttp-vless", "tcp-trojan"]
    targets = [
        dict(id=id, comparison_set=name, destination_class=cls, topology=topology)
        for id, name, cls, topology in [
            ("allow-dual", "allow-pair", "allowlist-pattern", TOPOLOGIES[0]),
            ("allow-split", "allow-pair", "allowlist-pattern", TOPOLOGIES[1]),
            ("nonallow-dual", "nonallow-pair", "non-allowlist-pattern", TOPOLOGIES[0]),
            ("nonallow-split", "nonallow-pair", "non-allowlist-pattern", TOPOLOGIES[1]),
        ]
    ]
    cells = []
    for tick in range(2):
        for protocol in protocols:
            for target in targets:
                blocked = tick == 1 and target["topology"] == TOPOLOGIES[0]
                cell = cell_error(
                    tick,
                    started + tick * 300000,
                    protocol,
                    target,
                    "blocked" if blocked else "ok",
                    "",
                )
                cell.pop("error_kind")
                if not blocked:
                    cell["rtt_ms"] = 42
                cells.append(cell)
    return dict(
        schema_version=3,
        completed=True,
        interrupted=False,
        vantage="synthetic",
        started_at_unix_ms=started,
        finished_at_unix_ms=started + 600000,
        poll_interval_seconds=300,
        controls=[
            dict(
                tick=tick,
                timestamp_unix_ms=started + tick * 300000,
                verdict="ok",
                rtt_ms=20,
                sweep_duration_ms=50,
                overrun_ms=0,
            )
            for tick in range(2)
        ],
        cells=cells,
        windows=windows(cells),
        observations=analyze(protocols, cells),
    )
