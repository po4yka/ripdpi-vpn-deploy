"""Portable honesty checks; these never establish native protocol acceptance."""

import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "four_transport_runner", ROOT / "tests/native/transport_acceptance/runner.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
AWG_CASE = (
    "tests.unit.test_awg_dualstack_native."
    "test_owned_uplink_nat_mtu_dns_reconnect_revocation_and_no_native_bypass[1]"
)


def _probe_summary(**changes):
    return dict(family="ipv6", cycle=2, phase="udp", expected="accepted",
                result="nonzero-exit") | changes


def _probe_report(tmp_path, values, *, case_id=AWG_CASE, result="failure", property_name="awg-probe-summary"):
    root = runner.ET.Element("testsuite")
    classname, name = case_id.rsplit(".", 1)
    case = runner.ET.SubElement(root, "testcase", classname=classname, name=name)
    if result != "passed":
        failure = runner.ET.SubElement(case, result)
        failure.text = "private raw failure with address and credential"
    properties = runner.ET.SubElement(case, "properties")
    for value in values:
        runner.ET.SubElement(properties, "property", name=property_name, value=value)
    runner.ET.SubElement(properties, "property", name="credential", value="private-credential")
    runner.ET.SubElement(case, "system-out").text = "private stdout"
    runner.ET.SubElement(case, "system-err").text = "private stderr"
    path = tmp_path / "probe.xml"
    runner.ET.ElementTree(root).write(path)
    return path


@pytest.mark.parametrize("member", [1, 2])
@pytest.mark.parametrize("result", ["failure", "error"])
def test_awg_failure_admits_only_bounded_probe_summary(tmp_path, member, result):
    case_id = AWG_CASE[:-2] + str(member) + "]"
    summary = _probe_summary()
    rows = runner.case_results(_probe_report(
        tmp_path, [json.dumps(summary)], case_id=case_id, result=result,
    ))
    assert rows == [{"case": case_id, "result": result, "probe": summary}]
    assert "private" not in json.dumps(rows)


@pytest.mark.parametrize("changes", [
    {"family": "ipv4"}, {"expected": "rejected"},
    *({"phase": phase} for phase in ("tcp", "dns-1", "dns-28", "unknown")),
    *({"result": result} for result in ("success", "signal", "process-timeout")),
    *({"cycle": cycle} for cycle in (None, 0, 1, 3)),
])
def test_probe_summary_admits_closed_categories_and_optional_cycle(tmp_path, changes):
    summary = _probe_summary(**changes)
    row, = runner.case_results(_probe_report(tmp_path, [json.dumps(summary)]))
    assert row["probe"] == summary


@pytest.mark.parametrize("raw", [
    "not-json", "null", "[]", '"private"',
    json.dumps(_probe_summary()) + " " * 256,
    json.dumps(_probe_summary())[:-1] + ',"cycle":2}',
    json.dumps(_probe_summary())[:-1] + ',"cycle":3}',
    json.dumps(_probe_summary(private="private-authority")),
    json.dumps({key: value for key, value in _probe_summary().items() if key != "phase"}),
    *(json.dumps(_probe_summary(**{key: value})) for key, value in (
        ("family", "private-address"), ("family", 6), ("family", True),
        ("phase", "udp private-address"), ("phase", []),
        ("expected", "unknown"), ("expected", False),
        ("result", "private-error"), ("result", {}),
        ("cycle", -1), ("cycle", 4), ("cycle", True),
        ("cycle", 1.0), ("cycle", "1"), ("cycle", []),
    )),
])
def test_invalid_probe_property_is_dropped_without_publishing_private_data(tmp_path, raw):
    rows = runner.case_results(_probe_report(tmp_path, [raw]))
    assert rows == [{"case": AWG_CASE, "result": "failure"}]
    assert "private" not in json.dumps(rows)


def test_probe_summary_size_boundary_and_duplicate_properties(tmp_path):
    raw = json.dumps(_probe_summary())
    exact = raw.ljust(runner.MAX_AWG_PROBE_SUMMARY_BYTES)
    row, = runner.case_results(_probe_report(tmp_path, [exact]))
    assert row["probe"] == _probe_summary()
    for values in ([exact + " "], [raw, raw], [raw, "private-value"], []):
        assert runner.case_results(_probe_report(tmp_path, values)) == [
            {"case": AWG_CASE, "result": "failure"},
        ]


@pytest.mark.parametrize("case_id,result", [
    (AWG_CASE, "passed"), (AWG_CASE, "skipped"),
    (AWG_CASE.replace("[1]", "[3]"), "failure"),
    (AWG_CASE.replace("test_awg_dualstack_native", "foreign"), "error"),
    ("foreign.test_probe", "failure"),
])
def test_probe_property_never_admits_other_cases_or_nonfailures(tmp_path, case_id, result):
    rows = runner.case_results(_probe_report(
        tmp_path, [json.dumps(_probe_summary())], case_id=case_id, result=result,
    ))
    assert rows == [{"case": case_id, "result": result}]


READINESS_CASE = (
    "tests.native.transport_acceptance.test_hopping."
    "test_native_hopping_no_net_admin_outbound_preserved_and_repeated_removal[6]"
)


def _readiness_summary(**changes):
    return dict(family="ipv6", phase="retirement", cycle=1,
                reason="reply-deadline", unit_state="active") | changes


def _readiness_report(tmp_path, values, *, case_id=READINESS_CASE, result="failure"):
    return _probe_report(tmp_path, values, case_id=case_id, result=result,
                         property_name="native-socks-readiness")


@pytest.mark.parametrize("family", [4, 6])
@pytest.mark.parametrize("result", ["failure", "error"])
def test_hopping_readiness_admits_only_closed_failure_summary(tmp_path, family, result):
    case_id = READINESS_CASE[:-2] + str(family) + "]"
    summary = _readiness_summary(family="ipv" + str(family))
    rows = runner.case_results(_readiness_report(
        tmp_path, [json.dumps(summary)], case_id=case_id, result=result))
    assert rows == [{"case": case_id, "result": result, "readiness": summary}]
    assert "private" not in json.dumps(rows)


@pytest.mark.parametrize("changes", [
    {"phase": "hopping", "cycle": None}, {"cycle": 0},
    *({"reason": reason} for reason in (
        "connect-deadline", "eof", "wrong-version", "wrong-method", "process-timeout", "probe-error")),
    *({"unit_state": state} for state in ("activating", "inactive", "deactivating", "failed", "unknown")),
])
def test_readiness_summary_admits_finite_categories_and_context(tmp_path, changes):
    summary = _readiness_summary(**changes)
    row, = runner.case_results(_readiness_report(tmp_path, [json.dumps(summary)]))
    assert row["readiness"] == summary


@pytest.mark.parametrize("raw", [
    "not-json", "null", "[]", '"private"',
    json.dumps(_readiness_summary()) + " " * 256,
    json.dumps(_readiness_summary())[:-1] + ',"cycle":0}',
    json.dumps(_readiness_summary(private="private-authority")),
    json.dumps({key: value for key, value in _readiness_summary().items() if key != "reason"}),
    *(json.dumps(_readiness_summary(**{key: value})) for key, value in (
        ("family", "ipv4"), ("family", "private-address"), ("family", 6), ("family", True),
        ("phase", "unknown"), ("phase", []), ("phase", True),
        ("reason", "private-stderr"), ("reason", {}), ("reason", False),
        ("unit_state", "private-unit"), ("unit_state", []), ("unit_state", True),
        ("cycle", -1), ("cycle", 2), ("cycle", True), ("cycle", 1.0), ("cycle", "1"),
        ("cycle", []), ("cycle", None),
    )),
    json.dumps(_readiness_summary(phase="hopping", cycle=0)),
])
def test_invalid_readiness_property_never_publishes_private_data(tmp_path, raw):
    rows = runner.case_results(_readiness_report(tmp_path, [raw]))
    assert rows == [{"case": READINESS_CASE, "result": "failure"}]
    assert "private" not in json.dumps(rows)


def test_readiness_summary_size_and_duplicate_properties_refuse(tmp_path):
    raw = json.dumps(_readiness_summary())
    exact = raw.ljust(runner.MAX_SOCKS_READINESS_BYTES)
    row, = runner.case_results(_readiness_report(tmp_path, [exact]))
    assert row["readiness"] == _readiness_summary()
    for values in ([exact + " "], [raw, raw], [raw, "private-value"], []):
        assert runner.case_results(_readiness_report(tmp_path, values)) == [
            {"case": READINESS_CASE, "result": "failure"}]


@pytest.mark.parametrize("case_id,result", [
    (READINESS_CASE, "passed"), (READINESS_CASE, "skipped"),
    (READINESS_CASE.replace("[6]", "[5]"), "failure"),
    (READINESS_CASE.replace("test_hopping", "foreign"), "error"),
    (AWG_CASE, "failure"), ("foreign.test_probe", "failure"),
])
def test_readiness_property_never_admits_other_cases_or_nonfailures(tmp_path, case_id, result):
    assert runner.case_results(_readiness_report(
        tmp_path, [json.dumps(_readiness_summary())], case_id=case_id, result=result)) == [
            {"case": case_id, "result": result}]


def _awg_probe_producer():
    spec = importlib.util.spec_from_file_location(
        "awg_probe_producer", ROOT / "tests/unit/test_awg_dualstack_native.py"
    )
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    return producer


@pytest.mark.parametrize("returncode,accepted,category", [
    (0, False, "success"), (1, True, "nonzero-exit"), (-9, True, "signal"),
    (0, True, None), (1, False, None),
])
def test_probe_producer_records_only_unexpected_results(returncode, accepted, category):
    producer = _awg_probe_producer()
    properties = []
    result = subprocess.CompletedProcess(
        ["private-command"], returncode, stdout="private-stdout",
        stderr="private-address namespace credential nonce\nphase=tcp\nphase=dns-28\n",
    )
    producer.record_probe_summary(
        lambda *pair: properties.append(pair), "198.18.1.2", result,
        accepted=accepted, cycle=3,
    )
    if category is None:
        assert properties == []
        return
    name, raw = properties.pop()
    assert properties == [] and name == "awg-probe-summary"
    assert json.loads(raw) == _probe_summary(
        family="ipv4", cycle=3, phase="dns-28",
        expected="accepted" if accepted else "rejected", result=category,
    )
    assert "private" not in raw and "198.18" not in raw


@pytest.mark.parametrize("stderr,phase", [
    ("phase=tcp\nprivate\nphase=udp\n", "udp"),
    (b"private\xff\nphase=dns-1\n", "dns-1"),
    ("phase=udp private-address\n", "unknown"),
    ("private-prefix phase=tcp\n", "unknown"),
    ("phase=tcp\nphase=dns-28", "tcp"),
    ("phase=unknown\n", "unknown"), (None, "unknown"),
])
def test_probe_timeout_retains_only_last_complete_exact_phase(stderr, phase):
    producer = _awg_probe_producer()
    properties = []
    timeout = subprocess.TimeoutExpired(
        ["private-command"], 12, output=b"private-output", stderr=stderr,
    )
    producer.record_probe_summary(
        lambda *pair: properties.append(pair), "fd88::2", timeout,
    )
    assert len(properties) == 1
    assert json.loads(properties[0][1]) == _probe_summary(
        cycle=None, phase=phase, result="process-timeout",
    )
    assert "private" not in properties[0][1] and "fd88" not in properties[0][1]


def test_real_pytest_junit_serializes_producer_property_for_runner(tmp_path):
    directory = tmp_path / "tests/unit"
    directory.mkdir(parents=True)
    test_file = directory / "test_awg_dualstack_native.py"
    test_file.write_text(
        "import ast, importlib.util, pathlib, subprocess, types, pytest\n"
        f"spec = importlib.util.spec_from_file_location('probe_producer', {str(ROOT / 'tests/unit/test_awg_dualstack_native.py')!r})\n"
        "producer = importlib.util.module_from_spec(spec); spec.loader.exec_module(producer)\n"
        "tree = ast.parse(pathlib.Path(spec.origin).read_text())\n"
        "outer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_owned_uplink_'))\n"
        "probe = next(node for node in outer.body if isinstance(node, ast.FunctionDef) and node.name == 'probe')\n"
        "probe_code = compile(ast.Module(body=[probe], type_ignores=[]), spec.origin, 'exec')\n"
        "@pytest.mark.parametrize('members', [1, 2])\n"
        "def test_owned_uplink_nat_mtu_dns_reconnect_revocation_and_no_native_bypass(members, record_property):\n"
        "    def run(*args, **kwargs):\n"
        "        assert kwargs == dict(capture_output=True, text=True, timeout=12)\n"
        "        if members == 2: raise subprocess.TimeoutExpired(['private-command'], 12, stderr=b'private-address\\nphase=udp\\n')\n"
        "        return subprocess.CompletedProcess(['private-command'], 1, stdout='private-stdout', stderr='private-address\\nphase=udp\\n')\n"
        "    scope = dict(vars(producer))\n"
        "    scope.update(record_property=record_property, clients=['private-namespace'], token='private', server='private', uplink='private', interfaces=['private'], tools='private', path_evidence=lambda *args: {}, subprocess=types.SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired))\n"
        "    exec(probe_code, scope)\n"
        "    scope['probe'](0, 'fd88::2', cycle=members)\n"
    )
    report = tmp_path / "actual.xml"
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS"}}
    environment["PYTHONPATH"] = os.pathsep.join(
        map(str, (ROOT, ROOT / "scripts", ROOT / "tests/unit"))
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_file),
         "--rootdir=" + str(tmp_path), "--junitxml=" + str(report)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    rows = runner.case_results(report)
    assert len(rows) == 2
    for member, row in enumerate(rows, 1):
        assert row == {"case": AWG_CASE[:-2] + str(member) + "]", "result": "failure",
                       "probe": _probe_summary(cycle=member, result=(
                           "nonzero-exit" if member == 1 else "process-timeout"
                       ))}
    original = runner.ET.parse(report)
    failures = list(original.iter("failure"))
    assert "authenticated constrained-path result disagrees with policy" in failures[0].get("message")
    assert "subprocess.TimeoutExpired" in failures[1].get("message")
    assert "private" not in json.dumps(rows)


def test_native_ci_plans_cover_the_complete_real_collection_once():
    """Collect actual parameterized cases, including new recovery boundaries."""
    def collect(paths, options=()):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", *paths, *options],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True,
            env={key: value for key, value in os.environ.items()
                 if key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS"}},
        )
        return {line for line in result.stdout.splitlines() if line.startswith("tests/") and "::" in line}

    expected = collect([path for _name, paths in runner.SUITES for path in paths])
    assert expected
    weights = json.loads((ROOT / "tests/native/transport_acceptance/recovery-durations.json").read_text())
    assert weights and all(type(value) in (int, float) and math.isfinite(value) and value > 0
                           for value in weights.values())
    assert set(weights) == {case for case in expected
                            if case.startswith("tests/unit/test_transport_runtime_acceptance_native.py::")}
    mean = sum(weights.values()) / len(weights)
    largest = set(sorted(weights, key=weights.get, reverse=True)[:4])
    recovery_groups = []
    observed = set()
    for plan in ("core", "recovery-1", "recovery-2", "recovery-3", "recovery-4"):
        selected = set()
        for _name, paths, options in runner.suite_commands(plan):
            cases = collect(paths, options)
            assert cases and not selected.intersection(cases)
            selected.update(cases)
        assert not observed.intersection(selected)
        observed.update(selected)
        if plan.startswith("recovery-"):
            assert len(selected & largest) == 1
            recovery_groups.append(selected)
    assert observed == expected
    compensation_paths = next(paths for name, paths in runner.SUITES if name == "compensation")
    assert set.union(*recovery_groups) == {case for case in expected
                                          if case.split("::", 1)[0] in compensation_paths}
    # The pinned splitter assigns the relevant profile mean to unmeasured cases.
    # Bound estimated imbalance, not native acceptance or a fixed case allocation.
    loads = [sum(weights.get(case, mean) for case in group) for group in recovery_groups]
    assert max(loads) <= sum(loads) / len(loads) * 1.1
    assert runner.suite_commands("all") == sum(
        (runner.suite_commands(plan) for plan in ("core", "recovery-1", "recovery-2", "recovery-3", "recovery-4")), []
    )
    import yaml
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    job = jobs["transport-native-acceptance"]
    assert job["strategy"]["matrix"]["plan"] == ["core", "recovery-1", "recovery-2", "recovery-3", "recovery-4"]
    assert job["strategy"]["fail-fast"] is False
    assert "transport-native-acceptance" in jobs["required"]["needs"]


def test_missing_recovery_profile_refuses_instead_of_silent_count_balancing(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="native-duration-profile-required"):
        runner.suite_commands("recovery-1")


def test_unknown_native_plan_cannot_silently_omit_cases():
    with pytest.raises(RuntimeError, match="native-plan-refused"):
        runner.suite_commands("recovery-5")


@pytest.mark.parametrize(
    "body",
    [
        "",
        '<testcase name="missing"><skipped/></testcase>',
        '<testcase name="broken"><failure>private authority</failure></testcase>',
        '<testcase name="setup"><error>private authority</error></testcase>',
    ],
)
def test_missing_skipped_or_failed_native_case_cannot_be_credited(tmp_path, body):
    report = tmp_path / "report.xml"
    report.write_text("<testsuite>" + body + "</testsuite>")
    with pytest.raises(RuntimeError, match="selected-case-incomplete"):
        runner.cases(report)


def test_published_case_evidence_drops_raw_output_and_properties(tmp_path):
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuite><testcase classname="transport" name="positive"><system-out>private authority</system-out><properties><property name="credential" value="private authority"/></properties></testcase></testsuite>'
    )
    assert runner.cases(report) == [{"case": "transport.positive", "result": "passed"}]


def test_unsupported_host_is_failure_before_any_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(runner.sys, "platform", "darwin")
    monkeypatch.setenv("TRANSPORT_NATIVE_EVIDENCE", str(tmp_path / "evidence.json"))
    with pytest.raises(RuntimeError, match="isolated-Linux-root-required"):
        runner.main()
    assert not (tmp_path / "evidence.json").exists()


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_fake_engine_is_categorical_failure(tmp_path, monkeypatch, missing):
    import test_transport_semantics_native as native

    monkeypatch.setattr(runner.sys, "path", list(runner.sys.path))
    fake = tmp_path / "fake-engine"
    fake.write_text("#!/bin/sh\necho invented-version\n")
    fake.chmod(0o700)
    monkeypatch.setattr(native, "exact_awg_sources", lambda: (fake, fake))
    monkeypatch.setattr(
        runner.shutil, "which", lambda _: None if missing else str(fake)
    )
    with pytest.raises(
        RuntimeError, match="engine-missing:xray" if missing else "engine-not-native"
    ):
        runner.engines()


@pytest.mark.parametrize("unavailable", [False, True])
def test_cleanup_change_or_inspection_failure_persists_failure_without_private_diagnostics(
    tmp_path, monkeypatch, unavailable
):

    def inspect():
        if unavailable:
            raise OSError("private authority must never be published")
        return {"namespaces": ["remaining-owned-namespace"]}

    monkeypatch.setattr(runner, "resources", inspect)
    evidence = {"success": True, "engines": {}}
    output = tmp_path / "evidence.json"
    with pytest.raises(RuntimeError, match="owned-resource-cleanup-unconfirmed"):
        runner.finish(evidence, {"namespaces": []}, output)
    observed = json.loads(output.read_text())
    assert observed["success"] is False and observed["cleanup"] is False
    assert "private authority" not in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "category", ["systemd-TUN-required", "private-authority-must-not-be-published"]
)
def test_supported_host_preflight_failure_keeps_private_categorical_evidence(
    tmp_path, monkeypatch, category
):

    monkeypatch.setattr(runner.sys, "platform", "linux")
    monkeypatch.setattr(runner.os, "geteuid", lambda: 0)
    monkeypatch.setenv("TRANSPORT_NATIVE_ISOLATED", "1")
    output = tmp_path / "preflight.json"
    monkeypatch.setenv("TRANSPORT_NATIVE_EVIDENCE", str(output))

    def refused(_evidence):
        raise RuntimeError(category)

    monkeypatch.setattr(runner, "preflight", refused)
    previous_umask = runner.os.umask(0o077)
    try:
        with pytest.raises(RuntimeError):
            runner.main()
    finally:
        runner.os.umask(previous_umask)
    value = json.loads(output.read_text())
    assert (
        value["success"] is False
        and value["cleanup"] is False
        and value["suites"] == {}
    )
    assert value["failure_category"] == (
        category if category == "systemd-TUN-required" else "RuntimeError"
    )
    assert "private-authority" not in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("symlink", [False, True])
def test_failure_diagnostics_preserve_foreign_sibling_file_and_symlink(tmp_path, symlink):
    source = tmp_path / "private.log"
    source.write_bytes(b"generated-private-diagnostics")
    foreign = tmp_path / "foreign.log"
    foreign.write_bytes(b"foreign-authority")
    foreign.chmod(0o640)
    destination = tmp_path / "evidence.lifecycle.log" if symlink else foreign
    if symlink:
        destination.symlink_to(foreign)
    before = (foreign.stat().st_ino, foreign.stat().st_mode, foreign.read_bytes())
    with pytest.raises(FileExistsError):
        runner.retain_diagnostic(source, destination)
    assert (foreign.stat().st_ino, foreign.stat().st_mode, foreign.read_bytes()) == before
    assert destination.is_symlink() is symlink


def test_new_failure_diagnostic_is_private_and_byte_complete(tmp_path):
    source = tmp_path / "source.log"
    source.write_bytes(b"generated-private-diagnostics")
    destination = tmp_path / "evidence.lifecycle.log"
    runner.retain_diagnostic(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o600


def test_cleanup_inventory_reports_counts_without_private_identities():

    difference = runner.resource_differences(
        {"users": [], "private-field": ["private-before"]},
        {"users": [("private-user", 123)], "private-field": ["private-after"]},
    )
    assert difference == {
        "users": {"before": 0, "after": 1},
        "inventory": {"before": 1, "after": 1},
    }
    assert "private" not in json.dumps(difference)


def test_case_cleanup_evidence_filters_private_messages_and_unknown_fields(tmp_path):

    root = runner.ET.Element("testsuite")
    case = runner.ET.SubElement(root, "testcase", classname="native", name="cleanup")
    error = runner.ET.SubElement(case, "error")
    error.set("message", "native-case-cleanup-unconfirmed:" + json.dumps({
        "processes": {"before": 1, "after": 2, "identity": "private-process"},
        "private-field": {"before": 1, "after": 2},
    }))
    error.text = "private raw diagnostics"
    path = tmp_path / "cases.xml"
    runner.ET.ElementTree(root).write(path)
    rows = runner.case_results(path)
    assert rows == [{
        "case": "native.cleanup", "result": "error",
        "cleanup_differences": {"processes": {"before": 1, "after": 2}},
    }]
    assert "private" not in json.dumps(rows)


@pytest.mark.parametrize("changed", ["engines", "source"])
def test_final_cleanup_refuses_engine_or_source_drift_with_categorical_evidence(
    tmp_path, monkeypatch, changed
):

    before = {"namespaces": []}
    monkeypatch.setattr(runner, "resources", lambda: before)
    monkeypatch.setattr(runner, "engines", lambda: {"xray": "private-change" if changed == "engines" else "old"})
    monkeypatch.setattr(runner, "run", lambda *a, **k: b"M private-filename" if changed == "source" else b"")
    output = tmp_path / "evidence.json"
    with pytest.raises(RuntimeError, match="owned-resource-cleanup-unconfirmed"):
        runner.finish({"success": True, "engines": {"xray": "old"}}, before, output)
    observed = json.loads(output.read_text())
    assert observed["success"] is False and observed["cleanup"] is False
    assert set(observed["cleanup_differences"]) == {changed}
    assert "private" not in output.read_text()


DHCP_READINESS_CASE = (
    "tests.native.transport_acceptance.test_dhcpv6."
    "test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server"
)


def _dhcp_readiness_report(tmp_path, values, *, case_id=DHCP_READINESS_CASE, result="failure"):
    return _probe_report(tmp_path, values, case_id=case_id, result=result,
                         property_name="dhcpv6-readiness")


@pytest.mark.parametrize("stage,mask", [("bind-join", 0)])
@pytest.mark.parametrize("result", ["failure", "error"])
def test_dhcp_readiness_admits_only_closed_failure_summary(tmp_path, stage, mask, result):
    summary = {"stage": stage, "authority_mismatch": mask}
    assert runner.case_results(_dhcp_readiness_report(tmp_path, [json.dumps(summary)], result=result)) == [
        {"case": DHCP_READINESS_CASE, "result": result, "readiness": summary}]


@pytest.mark.parametrize("raw", [
    "not-json", "null", "[]", '"private"',
    '{"stage":"private","stage":"exit","authority_mismatch":0}',
    *(json.dumps(value) for value in [
        {"stage": "exit", "authority_mismatch": 0, "credential": "private"},
        {"stage": "exit"}, {"stage": "private", "authority_mismatch": 0},
        {"stage": [], "authority_mismatch": 0}, {"stage": True, "authority_mismatch": 0},
        {"stage": "authority", "authority_mismatch": 0},
        {"stage": "exit", "authority_mismatch": 1},
        *({"stage": "authority", "authority_mismatch": mask}
          for mask in (-1, 64, True, 1.0, "private", [], None)),
    ]),
])
def test_dhcp_readiness_invalid_property_keeps_private_data_out(tmp_path, raw):
    rows = runner.case_results(_dhcp_readiness_report(tmp_path, [raw]))
    assert rows == [{"case": DHCP_READINESS_CASE, "result": "failure"}]
    assert "private" not in json.dumps(rows)


def test_dhcp_readiness_property_byte_bound_and_duplicates(tmp_path):
    summary = {"stage": "bind-join", "authority_mismatch": 0}
    exact = json.dumps(summary).ljust(256)
    assert runner.case_results(_dhcp_readiness_report(tmp_path, [exact]))[0]["readiness"] == summary
    for values in ([exact + " "], [exact, exact], [exact, "private"], []):
        assert runner.case_results(_dhcp_readiness_report(tmp_path, values)) == [
            {"case": DHCP_READINESS_CASE, "result": "failure"}]


@pytest.mark.parametrize("case_id,result", [
    (DHCP_READINESS_CASE, "passed"), (DHCP_READINESS_CASE, "skipped"),
    (DHCP_READINESS_CASE.replace("bootstrap_rebind_and_legacy_server", "foreign"), "error"),
    (READINESS_CASE, "failure"), (AWG_CASE, "failure"), ("foreign.test_probe", "failure"),
])
def test_dhcp_readiness_never_admits_foreign_cases_or_nonfailures(tmp_path, case_id, result):
    assert runner.case_results(_dhcp_readiness_report(
        tmp_path, [json.dumps({"stage": "bind-join", "authority_mismatch": 0})], case_id=case_id, result=result)) == [
            {"case": case_id, "result": result}]


def test_socks_and_dhcp_readiness_cannot_cross_or_overwrite(tmp_path):
    dhcp = {"stage": "bind-join", "authority_mismatch": 0}
    for case_id, property_name, summary, foreign_name, foreign_summary in [
        (READINESS_CASE, "native-socks-readiness", _readiness_summary(), "dhcpv6-readiness", dhcp),
        (DHCP_READINESS_CASE, "dhcpv6-readiness", dhcp, "native-socks-readiness", _readiness_summary()),
    ]:
        report = _probe_report(tmp_path, [json.dumps(summary)], case_id=case_id, property_name=property_name)
        document = runner.ET.parse(report)
        runner.ET.SubElement(document.find(".//properties"), "property", name=foreign_name,
                             value=json.dumps(foreign_summary))
        document.write(report)
        assert runner.case_results(report) == [{"case": case_id, "result": "failure", "readiness": summary}]


@pytest.mark.parametrize("stage", ["bind-join"])
def test_real_pytest_junit_preserves_dhcp_receiver_refusal_for_runner(tmp_path, stage):
    """A real failing receiver child crosses pytest's actual property transport."""
    command = "producer.RECEIVER,'not-a-real-device','::','547','yes'"
    directory = tmp_path / "tests/native/transport_acceptance"
    directory.mkdir(parents=True)
    test_file = directory / "test_dhcpv6.py"
    test_file.write_text(
        "import importlib.util, os, subprocess, sys\n"
        f"spec=importlib.util.spec_from_file_location('dhcp_producer', {str(ROOT / 'tests/native/transport_acceptance/test_dhcpv6.py')!r})\n"
        "producer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=producer;spec.loader.exec_module(producer)\n"
        "def test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server(monkeypatch, record_property):\n"
        "    real_popen=subprocess.Popen;children=[]\n"
        "    def listener(*args, **kwargs):\n"
        f"        child=real_popen([sys.executable,'-c',{command}],env={{**os.environ,'PATH':{str(tmp_path)!r}}},stdin=kwargs['stdin'],stdout=kwargs['stdout'],stderr=kwargs['stderr'],text=kwargs['text'])\n"
        "        children.append(child);return child\n"
        "    def run(*args, **kwargs):\n"
        "        assert '-c' not in args, 'sender-launched-after-readiness-refusal'\n"
        "        return ''\n"
        "    monkeypatch.setattr(producer.subprocess,'Popen',listener)\n"
        "    monkeypatch.setattr(producer,'run',run)\n"
        "    try:\n"
        "        producer.packet('sender','receiver',source='fe80::10',target='ff02::1:2',sport=546,dport=547,send_interface='up0',receive_interface='peer0',observe_multicast=True,record_property=record_property)\n"
        "    finally:\n"
        "        assert children and all(child.poll() is not None for child in children)\n"
    )
    report = tmp_path / "actual-dhcp.xml"
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS"}}
    environment["PYTHONPATH"] = os.pathsep.join(map(str, (ROOT, ROOT / "scripts", ROOT / "tests/unit")))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_file), "--rootdir=" + str(tmp_path),
         "--confcutdir=" + str(tmp_path), "--junitxml=" + str(report)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 1
    original = runner.ET.parse(report)
    failure, = list(original.iter("failure"))
    assert "dhcpv6-receiver-not-ready" in failure.get("message")
    properties = [node for node in original.iter("property") if node.get("name") == "dhcpv6-readiness"]
    assert len(properties) == 1
    assert json.loads(properties[0].get("value")) == {"stage": stage, "authority_mismatch": 0}
    assert runner.case_results(report) == [{"case": DHCP_READINESS_CASE, "result": "failure",
                                           "readiness": {"stage": stage, "authority_mismatch": 0}}]


@pytest.mark.parametrize('early_pass,full_pass', [(True, True), (True, False), (False, True)])
def test_runner_early_regression_never_substitutes_full_suite_or_accepts_failure(
    tmp_path, monkeypatch, early_pass, full_pass
):
    """Real pytest children prove scheduling; no native traffic is claimed here."""
    area = tmp_path / 'tests/native/transport_acceptance'
    area.mkdir(parents=True)
    (area / 'runner.py').write_text(Path(runner.__file__).read_text())
    event_file = tmp_path / 'events'
    observation = {
        'probe_id': 'multicast-request', 'phase': 'packet', 'ready_ms': 1,
        'send_ms': 2, 'elapsed_ms': 703, 'receiver_member': True,
        'packet_received': False, 'output_before': 1, 'output_after': 1,
        'postrouting_after': 11, 'prerouting_before': 13,
        'prerouting_after': 17, 'ingress_expected': True,
        'ipv6_no_routes': 19, 'ipv6_multicast': 23, 'ipv6_discards': 29,
        'ipv6_address_errors': 31, 'ipv6_delivers': 37, 'local_multicast_routes': None,
        'input_before': 0, 'input_after': 0, 'udp_errors': 0,
        'udp_checksum_errors': 0, 'udp_no_ports': 0, 'udp_ignored_multicast': 0,
    }
    early = area / 'test_dhcpv6.py'
    early.write_text(
        'from pathlib import Path\n'
        f'events=Path({str(event_file)!r})\n'
        'def test_bootstrap():\n'
        "    with events.open('a') as stream:stream.write('bootstrap\\n')\n"
        "    print('private-preflight-canary')\n"
        f"    print({'dhcpv6-observation:' + json.dumps(observation)!r})\n"
        f'    assert {early_pass!r}\n'
        'def test_established():\n'
        "    with events.open('a') as stream:stream.write('established\\n')\n"
    )
    complete = area / 'test_complete.py'
    complete.write_text(
        'from pathlib import Path\n'
        'def test_full_suite():\n'
        f"    with Path({str(event_file)!r}).open('a') as stream:stream.write('full\\n')\n"
        f'    assert {full_pass!r}\n'
    )
    output = tmp_path / 'result.json'
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner.sys, 'platform', 'linux')
    monkeypatch.setattr(runner.os, 'geteuid', lambda: 0)
    monkeypatch.setenv('TRANSPORT_NATIVE_ISOLATED', '1')
    monkeypatch.setenv('TRANSPORT_NATIVE_PLAN', 'core')
    monkeypatch.setenv('TRANSPORT_NATIVE_EVIDENCE', str(output))
    monkeypatch.setattr(runner, 'preflight', lambda evidence: {})
    monkeypatch.setattr(runner, 'resources', dict)
    monkeypatch.setattr(runner, 'engines', dict)
    monkeypatch.setattr(runner, 'run', lambda *args, **kwargs: b'')
    monkeypatch.setattr(runner, 'suite_commands', lambda plan: [('hopping', [str(complete)], [])])
    actual_run = subprocess.run
    observed = []
    diagnostic_logs = []
    actual_projector = runner.dhcpv6_diagnostics

    def project(log):
        diagnostic_logs.append(log.name)
        return actual_projector(log)

    monkeypatch.setattr(runner, 'dhcpv6_diagnostics', project)
    def portable_pytest(argv, **kwargs):
        assert '--native-resource-checks' in argv and '--fail-on-skip' in argv
        observed.append(argv)
        assert 'env' not in kwargs, "runner-injected-obsolete-route-environment"
        # The owned portable child has no Linux inventory plugin. Keep actual
        # pytest collection, assertions, exit status, JUnit and every other arg.
        argv = [arg for arg in argv if arg not in {'--native-resource-checks', '--fail-on-skip'}]
        return actual_run(argv, **kwargs)

    monkeypatch.setattr(runner.subprocess, 'run', portable_pytest)
    if early_pass and full_pass:
        runner.main()
    else:
        with pytest.raises(RuntimeError, match='native-suite-failed:'):
            runner.main()
    evidence = json.loads(output.read_text())
    assert evidence['success'] is (early_pass and full_pass)
    assert evidence['cleanup'] is True
    assert 'dhcpv6-preflight' not in evidence['suites']
    assert 'route_diagnostic' not in evidence
    assert event_file.read_text().splitlines() == (
        ['bootstrap', 'established', 'full'] if early_pass else ['bootstrap', 'established'])
    assert len(observed) == (2 if early_pass else 1)
    if early_pass:
        assert set(evidence['suites']) == {'hopping'}
        assert diagnostic_logs == ['hopping.log']
        assert evidence['dhcpv6_diagnostics'] == []
    else:
        assert evidence['suites'] == {}
        assert diagnostic_logs == ['dhcpv6-preflight.log']
        assert evidence['failure_category'] == 'native-suite-failed:dhcpv6-preflight'
        assert evidence['phase'] == 'dhcpv6-preflight'
        assert evidence['dhcpv6_diagnostics'] == [observation]
        assert 'private-preflight-canary' not in output.read_text()


def test_ci_only_uploads_closed_evidence_and_keeps_mandatory_cleanup():
    import yaml

    workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
    steps = workflow['jobs']['transport-native-acceptance']['steps']
    assert not any(step.get('id') == 'native_route_diagnostic' for step in steps)
    assert not any('native-dhcpv6-route-diagnostic' in str(step) for step in steps)
    public, = [step for step in steps if step.get('with', {}).get('name') ==
               'native-four-transport-evidence-${{ matrix.plan }}']
    assert public['with']['path'] == 'native-evidence/result.json'
    assert public['with']['if-no-files-found'] == 'error'
    cleanup, = [step for step in steps if step.get('name') == 'Remove and confirm exact owned environment']
    assert cleanup['if'] == 'always()'
    assert 'test -z' in cleanup['run']
    assert steps.index(cleanup) > steps.index(public)


@pytest.mark.parametrize("clean", [True, False])
def test_actual_pytest_timeout_retains_private_progress_without_claiming_completion(tmp_path, monkeypatch, clean):
    """Exercise actual killed pytest, journal and runner publication; no native claim."""
    area = tmp_path / "tests/native/transport_acceptance"
    area.mkdir(parents=True)
    (area / "runner.py").write_text(Path(runner.__file__).read_text())
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    case = area / "test_timeout.py"
    case.write_text(
        "import os, time, pytest\n"
        "def test_completed(): pass\n"
        "@pytest.mark.parametrize('value', ['private-parameter-canary'])\n"
        "def test_blocked(value):\n"
        "    os.write(1, b'private-raw-log-canary\\n')\n"
        "    time.sleep(60)\n"
    )
    output = tmp_path / "result.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner.sys, "platform", "linux")
    monkeypatch.setattr(runner.os, "geteuid", lambda: 0)
    monkeypatch.setenv("TRANSPORT_NATIVE_ISOLATED", "1")
    monkeypatch.setenv("TRANSPORT_NATIVE_PLAN", "recovery-1")
    monkeypatch.setenv("TRANSPORT_NATIVE_EVIDENCE", str(output))
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    monkeypatch.delenv("PYTEST_PLUGINS", raising=False)
    monkeypatch.setattr(runner, "preflight", lambda evidence: {})
    monkeypatch.setattr(runner, "resources", lambda: {} if clean else {"links": ["private-link-canary"]})
    monkeypatch.setattr(runner, "engines", dict)
    monkeypatch.setattr(runner, "run", lambda *args, **kwargs: b"")
    monkeypatch.setattr(runner, "suite_commands", lambda plan: [("compensation-1", [str(case)], ["-s"])])
    actual_run = subprocess.run
    journals = []

    def portable_pytest(argv, **kwargs):
        assert kwargs["timeout"] == 2400
        kwargs["timeout"] = 3
        argv = [arg for arg in argv if arg not in {"--native-resource-checks", "--fail-on-skip"}]
        progress = Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--native-progress=")))
        try:
            return actual_run(argv, **kwargs)
        except subprocess.TimeoutExpired:
            assert progress.stat().st_mode & 0o777 == 0o600
            journals.append(progress)
            raise

    monkeypatch.setattr(runner.subprocess, "run", portable_pytest)
    error = "native-suite-timeout:compensation-1" if clean else "owned-resource-cleanup-unconfirmed"
    with pytest.raises(RuntimeError, match=error):
        runner.main()
    evidence = json.loads(output.read_text())
    assert evidence["success"] is False and evidence["cleanup"] is clean
    assert evidence["case_cleanup"] == "unconfirmed" and evidence["suites"] == {}
    assert evidence["phase"] == "compensation-1"
    assert evidence["failure_category"] == "native-suite-timeout:compensation-1"
    progress = evidence["timeout_progress"]
    assert progress["completed"] == {"passed": 1, "failed": 0, "skipped": 0}
    assert progress["current"]["phase"] == "call"
    assert progress["current"]["case"] == "tests/native/transport_acceptance/test_timeout.py::test_blocked"
    assert len(progress["current"]["case_sha256"]) == 64
    assert "private-" not in output.read_text()
    retained = output.with_suffix(".compensation-1.log")
    assert retained.stat().st_mode & 0o777 == 0o600
    assert "private-raw-log-canary" in retained.read_text()
    assert len(journals) == 1 and not journals[0].exists()


def test_timeout_progress_projection_rejects_private_or_damaged_fields(tmp_path):
    import copy

    path = tmp_path / "progress.json"
    case = "tests/native/transport_acceptance/test_timeout.py::test_blocked"
    valid = {"current": {"case": case, "case_sha256": "a" * 64, "phase": "call"},
             "completed": {"passed": 1, "failed": 0, "skipped": 0}}
    path.write_text(json.dumps(valid))
    assert runner.timeout_progress(path, {case}) == valid
    corrupt = ["{", " " * (runner.PROGRESS_LIMIT + 1), '{"current":null,"current":null,"completed":{}}', "[]"]
    for section, key, value in [
        ("current", "case", "/private/secret.py::test_blocked"),
        ("current", "case", case.replace("test_blocked", "test_unknown")),
        ("current", "case", case + "[private-parameter]"),
        ("current", "phase", "private-phase"), ("current", "case_sha256", "private-hash"),
        ("current", "extra", "private-extra"), ("completed", "passed", True),
        ("completed", "passed", -1), ("completed", "failed", 10000),
    ]:
        value_record = copy.deepcopy(valid)
        value_record[section][key] = value
        corrupt.append(json.dumps(value_record))
    for raw in corrupt:
        path.write_text(raw)
        assert runner.timeout_progress(path, {case}) is None
    path.unlink()
    assert runner.timeout_progress(path, {case}) is None


def test_progress_case_admission_uses_selected_repository_identifiers(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    case = tmp_path / "tests/native/test_progress.py"
    case.parent.mkdir(parents=True)
    case.write_text("def helper(): pass\ndef test_allowed(): pass\n")
    assert runner.progress_cases([str(case)]) == {"tests/native/test_progress.py::test_allowed"}
    with pytest.raises(ValueError):
        runner.progress_cases([str(tmp_path.parent / "test_foreign.py")])
    with pytest.raises(RuntimeError, match="native-progress-source-refused"):
        runner.progress_cases(["private/test_foreign.py"])
