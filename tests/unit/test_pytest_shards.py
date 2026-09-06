"""Exercise real pytest grouping and the mandatory whole-suite coverage barrier."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def verifier():
    path = ROOT / "scripts/check-pytest-shards.py"
    spec = importlib.util.spec_from_file_location("check_pytest_shards", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_group(repo, group, mode="pass"):
    tests = repo / "tests"
    tests.mkdir(exist_ok=True, parents=True)
    (tests / "conftest.py").write_text((ROOT / "tests/conftest.py").read_text())
    cases = ["import pytest\n"]
    durations = {}
    for number in range(12):
        body = "pass"
        if number == 0 and mode in {"skip", "fail"}:
            body = "pytest.skip('fixture unavailable')" if mode == "skip" else "assert False"
        cases.append(f"def test_case_{number:02d}():\n    {body}\n")
        if number != 11:  # A newly added test must be covered without a cached duration.
            durations[f"tests/test_cases.py::test_case_{number:02d}"] = 12 - number
    cases.append("@pytest.mark.native_runtime\ndef test_native():\n    assert False\n")
    (tests / "test_cases.py").write_text("\n".join(cases))
    profile = repo / f"durations-{group}.json"
    profile.write_text(json.dumps(durations))
    report = repo / "reports" / f"group-{group}" / "report.json"
    args = [sys.executable, "-m", "pytest", "tests", "--rootdir", str(repo), "-m", "not native_runtime",
            "--fail-on-skip", "--splits", "4", "--group", str(group),
            "--splitting-algorithm", "least_duration", "--durations-path", str(profile),
            "--store-durations", "--clean-durations", "--shard-report", str(report), "-q"]
    if mode == "collect":
        args.append("--collect-only")
    if mode == "filter":
        args.extend(["-k", "not test_case_11"])
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(args, cwd=repo, env=env, capture_output=True, text=True, timeout=30)
    assert report.is_file(), result.stdout + result.stderr
    return result, json.loads(report.read_text())


@pytest.fixture(scope="module")
def complete_reports(tmp_path_factory):
    repo = tmp_path_factory.mktemp("pytest-grouping")
    reports = []
    for group in range(1, 5):
        result, report = run_group(repo, group)
        assert result.returncode == 0, result.stdout + result.stderr
        reports.append(report)
    return reports


def test_four_groups_execute_every_portable_test_once(complete_reports):
    durations = verifier().verify(complete_reports)
    assert len(durations) == 12
    assert all("test_native" not in node for node in durations)
    assert any("test_case_11" in node for node in durations)


@pytest.mark.parametrize("case", [
    "missing-group", "duplicate-group", "overlap", "missing-test", "different-collection",
    "different-profile", "failed-group", "unfinished-test", "missing-duration", "invalid-duration",
])
def test_barrier_rejects_incomplete_or_inconsistent_results(complete_reports, case):
    reports = deepcopy(complete_reports)
    first = reports[0]
    node = first["selected"][0]
    if case == "missing-group":
        reports.pop()
    elif case == "duplicate-group":
        reports[1]["group"] = first["group"]
    elif case == "overlap":
        reports[1]["selected"].append(node)
        reports[1]["finished"].append(node)
        reports[1]["durations"][node] = first["durations"][node]
    elif case == "missing-test":
        first["selected"].remove(node)
        first["finished"].remove(node)
        del first["durations"][node]
    elif case == "different-collection":
        first["expected"].append("tests/test_missing.py::test_missing")
    elif case == "different-profile":
        first["profile_sha256"] = "0" * 64
    elif case == "failed-group":
        first["exitstatus"] = 1
    elif case == "unfinished-test":
        first["finished"].remove(node)
    elif case == "missing-duration":
        del first["durations"][node]
    elif case == "invalid-duration":
        first["durations"][node] = float("nan")
    with pytest.raises(ValueError):
        verifier().verify(reports)


@pytest.mark.parametrize("mode", ["skip", "fail", "collect"])
def test_runtime_reports_cannot_hide_skips_failures_or_nonexecution(tmp_path, complete_reports, mode):
    result, report = run_group(tmp_path, 1, mode)
    if mode != "collect":
        assert result.returncode != 0
    reports = deepcopy(complete_reports)
    reports[0] = report
    with pytest.raises(ValueError):
        verifier().verify(reports)


def test_full_collection_survives_filtering(tmp_path):
    reports = [run_group(tmp_path, group, "filter")[1] for group in range(1, 5)]
    with pytest.raises(ValueError):
        verifier().verify(reports)


def test_required_status_waits_for_all_four_groups_and_coverage():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    split = jobs["unit-tests"]
    assert split["strategy"] == {"fail-fast": False, "max-parallel": 4, "matrix": {"group": [1, 2, 3, 4]}}
    assert "${{ matrix.group }}" in split["name"]
    assert any("make test-unit-shard" in step.get("run", "") for step in split["steps"])
    barrier = jobs["pytest-required"]
    assert barrier["name"] == "pytest unit tests"
    assert barrier["if"] == "always()"
    assert barrier["needs"] == ["unit-tests"]
    assert "pytest-required" in jobs["required"]["needs"]
    commands = "\n".join(step.get("run", "") for step in barrier["steps"])
    assert 'test "$SHARD_RESULT" = success' in commands
    assert "scripts/check-pytest-shards.py" in commands


def test_shard_make_target_rejects_an_invalid_group_without_execution(tmp_path):
    env = dict(os.environ, PYTEST_GROUP="5")
    result = subprocess.run(["make", "-f", str(ROOT / "Makefile"), "test-unit-shard"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "PYTEST_GROUP must be 1, 2, 3 or 4" in result.stderr
