"""Portable honesty checks; these never establish native protocol acceptance."""

import importlib.util
import json
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


def _probe_report(tmp_path, values, *, case_id=AWG_CASE, result="failure"):
    root = runner.ET.Element("testsuite")
    classname, name = case_id.rsplit(".", 1)
    case = runner.ET.SubElement(root, "testcase", classname=classname, name=name)
    if result != "passed":
        failure = runner.ET.SubElement(case, result)
        failure.text = "private raw failure with address and credential"
    properties = runner.ET.SubElement(case, "properties")
    for value in values:
        runner.ET.SubElement(properties, "property", name="awg-probe-summary", value=value)
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
    observed = set()
    for plan in ("core", "recovery-1", "recovery-2"):
        selected = set()
        for _name, paths, options in runner.suite_commands(plan):
            cases = collect(paths, options)
            assert cases and not selected.intersection(cases)
            selected.update(cases)
        assert not observed.intersection(selected)
        observed.update(selected)
    assert observed == expected
    assert runner.suite_commands("all") == sum(
        (runner.suite_commands(plan) for plan in ("core", "recovery-1", "recovery-2")), []
    )
    import yaml
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    job = jobs["transport-native-acceptance"]
    assert job["strategy"]["matrix"]["plan"] == ["core", "recovery-1", "recovery-2"]
    assert job["strategy"]["fail-fast"] is False
    assert "transport-native-acceptance" in jobs["required"]["needs"]


def test_unknown_native_plan_cannot_silently_omit_cases():
    with pytest.raises(RuntimeError, match="native-plan-refused"):
        runner.suite_commands("recovery-3")


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
