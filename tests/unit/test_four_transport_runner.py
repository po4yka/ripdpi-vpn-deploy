"""Portable honesty checks; these never establish native protocol acceptance."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "four_transport_runner", ROOT / "tests/native/transport_acceptance/runner.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


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
    import json

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
    import json

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
