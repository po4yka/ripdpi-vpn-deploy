"""Complete isolated native acceptance; raw diagnostics remain private to the runner."""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import grp
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
SUITES = (
    (
        "completion",
        [
            "tests/native/transport_acceptance/test_completion.py",
            "tests/unit/test_xhttp_endpoint_contract_native.py",
            "tests/unit/test_awg_device_binding_native.py",
            "tests/unit/test_awg_dualstack_native.py",
            "tests/native/transport_acceptance/test_awg_udp_checksum.py",
        ],
    ),
    (
        "lifecycle",
        [
            "tests/unit/test_awg_activation_native.py",
            "tests/native/transport_acceptance/test_awg_lifecycle.py",
            "tests/unit/test_nginx_transaction_native.py",
        ],
    ),
    ("hopping", ["tests/native/transport_acceptance/test_hopping.py"]),
    (
        "compensation",
        [
            "tests/native/transport_acceptance/test_orchestrator.py",
            "tests/unit/test_transport_runtime_acceptance_native.py",
            "tests/native/transport_acceptance/test_rotation.py",
        ],
    ),
)


def suite_commands(plan):
    """Fixed complete CI plans; the local default executes their entire union."""
    if plan not in {"all", "core", "recovery-1", "recovery-2"}:
        raise RuntimeError("native-plan-refused")
    commands = []
    for name, paths in SUITES:
        if name != "compensation":
            if plan in {"all", "core"}:
                commands.append((name, paths, []))
            continue
        for group in (1, 2):
            if plan in {"all", "recovery-" + str(group)}:
                commands.append((name + "-" + str(group), paths, [
                    "--splits", "2", "--group", str(group),
                    "--splitting-algorithm", "least_duration",
                ]))
    return commands


def run(argv, **kwargs):
    return subprocess.run(
        argv, capture_output=True, timeout=30, check=True, **kwargs
    ).stdout


def resources():
    """Compare only identities, never configurations or peer keys."""
    tables = json.loads(run(["nft", "-j", "list", "tables"]))
    processes = []
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            executable = os.readlink(path / "exe")
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if Path(executable).name.split(" ")[0] in {
            "xray",
            "hysteria",
            "amneziawg-go",
            "nginx",
            "python",
            "python3",
            "python3.12",
        }:
            processes.append((path.name, executable))
    return {
        "authority": {
            raw: os.path.lexists(raw)
            for raw in (
                "/lab",
                "/usr/local/lib/awg-candidate",
                "/etc/xray",
                "/etc/hysteria",
                "/opt/xray",
                "/opt/hysteria",
                "/etc/ripdpi/transport-egress",
                "/var/lib/ripdpi/transport-runtime",
                "/var/lib/ripdpi/transport-egress",
                "/usr/local/libexec/ripdpi-transport-egress",
            )
        },
        "processes": sorted(processes),
        "users": sorted((entry.pw_name, entry.pw_uid) for entry in pwd.getpwall()),
        "groups": sorted((entry.gr_name, entry.gr_gid) for entry in grp.getgrall()),
        "namespaces": sorted(
            line.split()[0]
            for line in run(["ip", "netns", "list"]).decode().splitlines()
        ),
        "tables": sorted(
            (row["table"]["family"], row["table"]["name"])
            for row in tables["nftables"]
            if "table" in row
        ),
        "units": sorted(
            str(path.relative_to("/etc/systemd/system"))
            for path in Path("/etc/systemd/system").rglob("*.service")
        ),
        "links": sorted(
            row["ifname"] for row in json.loads(run(["ip", "-j", "link", "show"]))
        ),
    }


CLEANUP_CATEGORIES = frozenset({
    "authority", "processes", "users", "groups", "namespaces", "tables", "units", "links",
    "inventory", "engines", "source", "inspection",
})


def resource_differences(before, after):
    """Publish changed categories and counts, never private identities or paths."""
    result = {}
    for key in set(before) | set(after):
        if before.get(key) == after.get(key):
            continue
        label = key if key in CLEANUP_CATEGORIES else "inventory"
        values = (before.get(key), after.get(key))
        result[label] = dict(zip(("before", "after"), (
            len(value) if isinstance(value, (dict, list, tuple, set)) else int(value is not None)
            for value in values
        )))
    return result


def case_cleanup_differences(case):
    for node in case:
        message = node.get("message", "")
        prefix = "native-case-cleanup-unconfirmed:"
        if prefix not in message:
            continue
        try:
            value, _end = json.JSONDecoder().raw_decode(message.split(prefix, 1)[1])
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        return {
            key: {field: counts[field] for field in ("before", "after")}
            for key, counts in value.items()
            if key in CLEANUP_CATEGORIES and isinstance(counts, dict)
            and all(type(counts.get(field)) is int and counts[field] >= 0
                    for field in ("before", "after"))
        }
    return {}


AWG_PROBE_CASES = frozenset(
    "tests.unit.test_awg_dualstack_native."
    "test_owned_uplink_nat_mtu_dns_reconnect_revocation_and_no_native_bypass["
    + str(member) + "]" for member in (1, 2)
)
MAX_AWG_PROBE_SUMMARY_BYTES = 256


def awg_probe_summary(case, case_id, result):
    if case_id not in AWG_PROBE_CASES or result not in {"failure", "error"}:
        return None
    properties = [node for node in case.findall("./properties/property")
                  if node.get("name") == "awg-probe-summary"]
    if len(properties) != 1:
        return None
    raw = properties[0].get("value", "")
    if len(raw.encode("utf-8")) > MAX_AWG_PROBE_SUMMARY_BYTES:
        return None

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate-summary-key")
            value[key] = item
        return value

    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, TypeError, RecursionError):
        return None
    enums = {
        "family": {"ipv4", "ipv6"},
        "phase": {"tcp", "udp", "dns-1", "dns-28", "unknown"},
        "expected": {"accepted", "rejected"},
        "result": {"success", "nonzero-exit", "signal", "process-timeout"},
    }
    if not isinstance(value, dict) or set(value) != {*enums, "cycle"}:
        return None
    if any(type(value[key]) is not str or value[key] not in allowed
           for key, allowed in enums.items()):
        return None
    cycle = value["cycle"]
    if cycle is not None and (type(cycle) is not int or not 0 <= cycle <= 3):
        return None
    return value


SOCKS_READINESS_CASES = frozenset(
    "tests.native.transport_acceptance.test_hopping."
    "test_native_hopping_no_net_admin_outbound_preserved_and_repeated_removal["
    + str(family) + "]" for family in (4, 6)
)
MAX_SOCKS_READINESS_BYTES = 256


def socks_readiness_summary(case, case_id, result):
    if case_id not in SOCKS_READINESS_CASES or result not in {"failure", "error"}:
        return None
    properties = [node for node in case.findall("./properties/property")
                  if node.get("name") == "native-socks-readiness"]
    if len(properties) != 1:
        return None
    raw = properties[0].get("value", "")
    if len(raw.encode("utf-8")) > MAX_SOCKS_READINESS_BYTES:
        return None

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate-readiness-key")
            value[key] = item
        return value

    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, TypeError, RecursionError):
        return None
    enums = {
        "family": {"ipv4", "ipv6"}, "phase": {"hopping", "retirement"},
        "reason": {"connect-deadline", "reply-deadline", "eof", "wrong-version",
                   "wrong-method", "process-timeout", "probe-error"},
        "unit_state": {"active", "activating", "inactive", "deactivating", "failed", "unknown"},
    }
    if not isinstance(value, dict) or set(value) != {*enums, "cycle"}:
        return None
    if any(type(value[key]) is not str or value[key] not in allowed
           for key, allowed in enums.items()):
        return None
    if value["family"] != ("ipv4" if case_id.endswith("[4]") else "ipv6"):
        return None
    cycle = value["cycle"]
    if not ((value["phase"] == "hopping" and cycle is None)
            or (value["phase"] == "retirement" and type(cycle) is int and cycle in {0, 1})):
        return None
    return value


def case_results(path):
    root = ET.parse(path).getroot()
    rows = []
    for case in root.iter("testcase"):
        result = "passed"
        for tag in ("failure", "error", "skipped"):
            if case.find(tag) is not None:
                result = tag
        row = {
            "case": case.get("classname", "") + "." + case.get("name", ""),
            "result": result,
        }
        cleanup = case_cleanup_differences(case)
        if cleanup:
            row["cleanup_differences"] = cleanup
        probe = awg_probe_summary(case, row["case"], result)
        if probe is not None:
            row["probe"] = probe
        readiness = socks_readiness_summary(case, row["case"], result)
        if readiness is not None:
            row["readiness"] = readiness
        rows.append(row)
    return rows


def cases(path):
    rows = case_results(path)
    if not rows or any(row["result"] != "passed" for row in rows):
        raise RuntimeError("selected-case-incomplete")
    return rows


def engines():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "tests/unit"))
    from test_transport_semantics_native import exact_awg_sources

    import pytest

    try:
        go, tools = exact_awg_sources()
    except pytest.fail.Exception:
        raise RuntimeError("exact-AWG-build-prerequisite-refused") from None
    result = {}
    for name, path in [
        ("xray", shutil.which("xray")),
        ("hysteria", shutil.which("hysteria")),
        ("amneziawg-go", go),
        ("awg", tools),
    ]:
        if path is None or not Path(path).is_file():
            raise RuntimeError("engine-missing:" + name)
        data = Path(path).read_bytes()
        if data[:4] != b"\x7fELF":
            raise RuntimeError("engine-not-native")
        result[name] = hashlib.sha256(data).hexdigest()
    # Compare executable bytes against independently checksum-admitted archives.
    import importlib.util
    import zipfile

    spec = importlib.util.spec_from_file_location(
        "acceptance_pins",
        ROOT / "tests/integration/transport_runtime_acceptance/fixture.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache = module.artifacts(ROOT / ".cache/transport-runtime-acceptance")
    with zipfile.ZipFile(cache / "xray-v26.3.27.zip") as archive:
        if hashlib.sha256(archive.read("xray")).hexdigest() != result["xray"]:
            raise RuntimeError("xray-pin-mismatch")
    if (
        hashlib.sha256((cache / "hysteria-v2.13.0").read_bytes()).hexdigest()
        != result["hysteria"]
    ):
        raise RuntimeError("hysteria-pin-mismatch")
    pins = json.loads(
        (ROOT / "tests/integration/awg_source_candidate/sources.json").read_text()
    )
    sys.path.insert(0, str(ROOT / "tests/integration/awg_source_candidate"))
    from corrected_build import verify as verify_corrected_build

    for pair in ("baseline", "candidate"):
        for component, artifact in [("go", "amneziawg-go"), ("tools", "src/wg")]:
            source = ROOT / ".cache/four-transport-sources" / pair / component
            if (
                run(["git", "-C", str(source), "rev-parse", "HEAD"]).decode().strip()
                != pins[pair][component]["commit"]
            ):
                raise RuntimeError("AWG-pair-source-mismatch")
            if component == "go":
                receipt = verify_corrected_build(
                    source, pins[pair][component]["commit"],
                    ROOT / "ansible/roles/amneziawg/files",
                )
                result["awg-" + pair + "-go-correction"] = receipt["correction"]["digest"]
                result["awg-" + pair + "-go-commit"] = receipt["commit"]
            result["awg-" + pair + "-" + component] = hashlib.sha256(
                (source / artifact).read_bytes()
            ).hexdigest()
    return result


def main():
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or os.environ.get("TRANSPORT_NATIVE_ISOLATED") != "1"
    ):
        raise RuntimeError("isolated-Linux-root-required")
    os.umask(0o077)
    output = Path(
        os.environ.get(
            "TRANSPORT_NATIVE_EVIDENCE", "/var/tmp/transport-native-evidence.json"
        )
    )
    if output.exists() or output.is_symlink():
        raise RuntimeError("evidence-path-already-exists")
    evidence = {
        "source": None,
        "scope": "isolated-native-source",
        "engines": {},
        "suites": {},
        "cleanup": False,
        "success": False,
    }
    before = None
    plan = os.environ.get("TRANSPORT_NATIVE_PLAN", "all")
    commands = suite_commands(plan)
    evidence["plan"] = plan
    evidence["phase"] = "prerequisites"
    try:
        before = preflight(evidence)
        with tempfile.TemporaryDirectory(
            prefix="transport-native-", dir="/var/tmp"
        ) as private:
            for name, paths, selection in commands:
                evidence["phase"] = name
                report = Path(private) / (name + ".xml")
                with (Path(private) / (name + ".log")).open("wb") as log:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            *paths,
                            *selection,
                            "--fail-on-skip",
                            "--native-resource-checks",
                            "--basetemp=" + str(Path(private) / (name + "-scratch")),
                            "--tb=short",
                            "-q",
                            "--junitxml=" + str(report),
                        ],
                        cwd=ROOT,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=2400,
                    )
                if result.returncode:
                    # Keep diagnostics on this isolated machine only, with private modes.
                    if report.exists():
                        evidence["suites"][name] = case_results(report)
                        evidence["failure_locations"] = sorted(
                            set(
                                re.findall(
                                    r"tests/[A-Za-z0-9_/]+\.py:[0-9]+",
                                    report.read_text(),
                                )
                            )
                        )
                    diagnostic = output.with_suffix("." + name + ".log")
                    retain_diagnostic(Path(private) / (name + ".log"), diagnostic)
                    raise RuntimeError("native-suite-failed:" + name)
                evidence["suites"][name] = cases(report)
                difference = resource_differences(before, resources())
                if difference:
                    evidence["cleanup_differences"] = difference
                    raise RuntimeError("native-suite-cleanup-unconfirmed:" + name)
                print("native-suite-passed:" + name, flush=True)
        evidence["success"] = True
    except Exception as error:
        evidence["failure_type"] = type(error).__name__
        code = str(error)
        known = {
            "systemd-TUN-required",
            "pytest-selection-overrides-refused",
            "exact-source-clean-tree-required",
            "engine-not-native",
            "xray-pin-mismatch",
            "hysteria-pin-mismatch",
            "AWG-pair-source-mismatch",
            "exact-AWG-build-prerequisite-refused",
            "owned-runtime-fixture-command-refused",
            "owned-runtime-fixture-pin-mismatch",
            "selected-case-incomplete",
        }
        known.update(
            "engine-missing:" + name
            for name in ("xray", "hysteria", "amneziawg-go", "awg")
        )
        known.update("native-suite-failed:" + name for name, _paths, _selection in commands)
        known.update("native-suite-cleanup-unconfirmed:" + name for name, _paths, _selection in commands)
        evidence["failure_category"] = code if code in known else type(error).__name__
        raise
    finally:
        if before is None:
            publish(evidence, output)
        else:
            finish(evidence, before, output)


def preflight(evidence):
    evidence["phase"] = "source"
    evidence["source"] = run(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT).strip():
        raise RuntimeError("exact-source-clean-tree-required")
    evidence["phase"] = "capabilities"
    if not Path("/run/systemd/system").is_dir() or not Path("/dev/net/tun").exists():
        raise RuntimeError("systemd-TUN-required")
    if os.environ.get("PYTEST_ADDOPTS") or os.environ.get("PYTEST_PLUGINS"):
        raise RuntimeError("pytest-selection-overrides-refused")
    evidence["phase"] = "engines"
    evidence["engines"] = engines()
    evidence["phase"] = "resource-inventory"
    return resources()


def retain_diagnostic(source, destination):
    """Create only new private diagnostics; a foreign sibling is never adopted."""
    with destination.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        with source.open("rb") as original:
            shutil.copyfileobj(original, stream)


def publish(evidence, output):
    with output.open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(evidence, stream, sort_keys=True, indent=2)


def finish(evidence, before, output):
    """Persist categorical cleanup failure even when its inspection itself fails."""
    difference = {}
    try:
        difference = resource_differences(before, resources())
        if not difference:
            current_engines = engines()
            if current_engines != evidence["engines"]:
                difference["engines"] = {"before": len(evidence["engines"]), "after": len(current_engines)}
            if run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT).strip():
                difference["source"] = {"before": 0, "after": 1}
        evidence["cleanup"] = not difference
    except Exception as error:
        evidence["cleanup"] = False
        evidence["cleanup_error"] = type(error).__name__
        difference["inspection"] = {"before": 0, "after": 1}
    evidence["cleanup_differences"] = difference
    evidence["success"] = evidence["success"] and evidence["cleanup"]
    publish(evidence, output)
    if not evidence["cleanup"]:
        raise RuntimeError("owned-resource-cleanup-unconfirmed")


if __name__ == "__main__":
    main()
