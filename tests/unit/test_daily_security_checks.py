"""Daily scan wiring and executable GitHub notification state changes."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
NOTIFIER = ROOT / "scripts/notify-security-scan.cjs"
HARNESS = """
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
process.env.SECURITY_JOB_RESULTS = JSON.stringify(input.jobs);
process.env.SECURITY_DOWNLOAD_RESULT = input.download;
process.env.SECURITY_RUN_ATTEMPT = String(input.attempt);
const calls = [];
const issues = {listForRepo: () => {}};
for (const method of ['create', 'createComment', 'update']) {
  issues[method] = async args => {calls.push({method, ...args}); return {data: {number: 7}};};
}
const github = {rest: {issues, repos: {getBranch: async () => ({data: {commit: {sha: input.currentSha}}})}},
                paginate: async () => input.issues};
const context = {repo: {owner: 'maintainer', repo: 'example'}, serverUrl: 'https://github.com', runId: 42,
                 sha: 'a'.repeat(40), payload: {repository: {default_branch: 'main'}}};
const core = {info: () => {}, setFailed: message => calls.push({method: 'failed', message})};
require(process.argv[1])({github, context, core}).then(() => console.log(JSON.stringify(calls)))
  .catch(error => {console.error(error); process.exitCode = 1;});
"""


def sarif(*ids):
    return {
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "Trivy"}}, "results": [
            {"ruleId": value, "level": "error", "message": {"text": f"private report detail: {value}"}}
            for value in ids
        ]}],
    }


@pytest.fixture
def reports(tmp_path):
    root = tmp_path / "security-reports"
    inventory = root / "daily-security-1-inventory"
    inventory.mkdir(parents=True)
    (inventory / "image-matrix.json").write_text(json.dumps([
        {"image": "example.invalid/one@sha256:" + "a" * 64, "category": "one"},
        {"image": "example.invalid/two@sha256:" + "b" * 64, "category": "two"},
    ]))
    for name in ("dependencies", "image-0", "image-1"):
        path = root / f"daily-security-1-{name}"
        path.mkdir()
        (path / "trivy-results.sarif").write_text(json.dumps(sarif()))
    return root


def notify(reports, *, issue=None, dependency_result="success", image_result="success", download="success", attempt=1, current_sha="a" * 40):
    result = subprocess.run(
        ["node", "-e", HARNESS, str(NOTIFIER)],
        cwd=reports.parent,
        input=json.dumps({
            "jobs": {"dependencies": {"result": dependency_result}, "images": {"result": image_result}},
            "download": download,
            "attempt": attempt,
            "currentSha": current_sha,
            "issues": [] if issue is None else [issue],
        }),
        text=True, capture_output=True, check=True, timeout=15,
    )
    return json.loads(result.stdout)


def test_notify_creates_assigned_issue_and_changes_without_repeating_or_publishing_details(reports):
    report = reports / "daily-security-1-dependencies/trivy-results.sarif"
    report.write_text(json.dumps(sarif("CVE-2026-0001", "CVE-2026-0002")))
    created, = notify(reports, dependency_result="failure")
    assert created["method"] == "create" and created["assignees"] == ["maintainer"]
    assert "2 finding(s)" in created["body"] and "actions/runs/42" in created["body"]
    assert "private report detail" not in created["body"]
    issue = {"number": 7, "title": created["title"], "body": created["body"]}
    reordered = sarif("CVE-2026-0002", "CVE-2026-0001")
    reordered["runs"][0]["invocations"] = [{"startTimeUtc": "2026-11-04T01:00:00Z"}]
    report.write_text(json.dumps(reordered))
    assert notify(reports, issue=issue, dependency_result="failure") == []
    for directory in list(reports.iterdir()):
        shutil.copytree(directory, reports / directory.name.replace("daily-security-1-", "daily-security-2-"))
    assert notify(reports, issue=issue, dependency_result="failure", attempt=2) == []
    report.write_text(json.dumps(sarif("CVE-2026-0001", "CVE-2026-0003")))
    calls = notify(reports, issue=issue, dependency_result="failure")
    assert [call["method"] for call in calls] == ["createComment", "update"]
    assert "state" not in calls[1]
    report.write_text(json.dumps(sarif()))
    calls = notify(reports, issue=issue)
    assert [call["method"] for call in calls] == ["createComment", "update"]
    assert calls[1]["state"] == "closed" and calls[1]["state_reason"] == "completed"


def test_clean_first_run_is_quiet(reports):
    assert notify(reports) == []


@pytest.mark.parametrize("fault", ["missing", "invalid-json", "empty-runs", "failed-invocation", "invalid-result", "invalid-tool", "missing-inventory"])
def test_incomplete_evidence_cannot_close_an_existing_issue(reports, fault):
    issue = {"number": 7, "title": "Daily security checks need attention", "body": "<!-- daily-security-checks -->"}
    path = reports / "daily-security-1-image-1/trivy-results.sarif"
    if fault == "missing":
        path.unlink()
    elif fault == "invalid-json":
        path.write_text("not JSON")
    elif fault == "empty-runs":
        path.write_text(json.dumps({"version": "2.1.0", "runs": []}))
    elif fault == "failed-invocation":
        data = sarif()
        data["runs"][0]["invocations"] = [{"executionSuccessful": False}]
        path.write_text(json.dumps(data))
    elif fault == "invalid-result":
        data = sarif()
        data["runs"][0]["results"] = [{}]
        path.write_text(json.dumps(data))
    elif fault == "invalid-tool":
        data = sarif()
        data["runs"][0].pop("tool")
        path.write_text(json.dumps(data))
    else:
        (reports / "daily-security-1-inventory/image-matrix.json").unlink()
    calls = notify(reports, issue=issue)
    assert [call["method"] for call in calls] == ["createComment", "update", "failed"]
    assert all(call.get("state") != "closed" for call in calls)
    assert "incomplete" in calls[0]["body"]


@pytest.mark.parametrize("kwargs", [{"image_result": "failure"}, {"dependency_result": "cancelled"}, {"download": "failure"}])
def test_clean_reports_cannot_hide_a_failed_job_or_download(reports, kwargs):
    calls = notify(reports, **kwargs)
    assert calls[0]["method"] == "create"
    assert "incomplete checks" in calls[0]["body"]
    assert (calls[-1]["method"] == "failed") == (kwargs.get("download") == "failure")


@pytest.mark.parametrize("attempt", [2, "../outside"])
def test_earlier_attempt_reports_cannot_prove_recovery(reports, attempt):
    issue = {"number": 7, "title": "Daily security checks need attention", "body": "<!-- daily-security-checks -->"}
    calls = notify(reports, issue=issue, attempt=attempt)
    assert [call["method"] for call in calls] == ["createComment", "update", "failed"]
    assert all(call.get("state") != "closed" for call in calls)


def test_historical_revision_cannot_close_the_current_issue(reports):
    issue = {"number": 7, "title": "Daily security checks need attention", "body": "<!-- daily-security-checks -->"}
    assert notify(reports, issue=issue, current_sha="b" * 40) == []


def test_daily_workflow_scans_full_tree_and_preserves_image_policy():
    daily = yaml.safe_load((ROOT / ".github/workflows/daily-security.yml").read_text())
    events = daily.get("on", daily.get(True))
    assert events["schedule"] == [{"cron": "17 6 * * *"}]
    assert "workflow_dispatch" in events
    assert daily["permissions"] == {"contents": "read"}
    assert daily["concurrency"]["cancel-in-progress"] is False
    jobs = daily["jobs"]
    scan = next(step for step in jobs["dependencies"]["steps"] if step.get("name") == "Scan repository dependencies")
    assert scan["with"]["scan-type"] == "fs" and scan["with"]["scan-ref"] == "."
    assert scan["with"]["scanners"] == "vuln" and scan["with"]["exit-code"] == "1"
    assert scan["with"]["ignore-unfixed"] is False
    assert scan["with"]["severity"] == "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
    assert scan["env"]["TRIVY_INCLUDE_DEV_DEPS"] == "true"
    assert jobs["images"]["uses"] == "./.github/workflows/image-scan.yml"
    assert jobs["images"]["with"]["retain-reports"] is True
    assert jobs["notify"]["if"] == "always() && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)"
    assert set(jobs["notify"]["needs"]) == {"dependencies", "images"}
    assert [name for name, job in jobs.items() if job.get("permissions", {}).get("issues") == "write"] == ["notify"]
    images = yaml.safe_load((ROOT / ".github/workflows/image-scan.yml").read_text())
    for job in (jobs["dependencies"], images["jobs"]["scan"]):
        upload = next(step for step in job["steps"] if step.get("name", "").startswith("Retain the ") and "report" in step["name"])
        assert upload["if"].startswith("always()")
        assert upload["with"]["if-no-files-found"] == "error"
        assert "${{ github.run_attempt }}" in upload["with"]["name"]
    download = next(step for step in jobs["notify"]["steps"] if step.get("id") == "reports")
    assert download["with"]["pattern"] == "daily-security-${{ github.run_attempt }}-*"
    image_scan = next(step for step in images["jobs"]["scan"]["steps"] if step.get("name") == "Run Trivy vulnerability scanner")
    assert image_scan["with"]["severity"] == "HIGH,CRITICAL"
    assert image_scan["with"]["ignore-unfixed"] is True and image_scan["with"]["exit-code"] == "1"
    assert images.get("on", images.get(True))["workflow_call"]["inputs"]["retain-reports"]["default"] is False
