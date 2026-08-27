from pathlib import Path

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.tasks import taskctl


ROOT = Path(__file__).resolve().parents[2]


def test_task_contract_validates_the_local_portfolio_only() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "./taskctl validate \"${args[@]}\"" in workflow
    assert "federation validate" not in workflow
    assert "Check out federated RIPDPI portfolio" not in workflow


@pytest.fixture
def portfolio(monkeypatch):
    from scripts.tests.test_taskctl import TaskctlFixture

    fixture = TaskctlFixture()
    fixture.setUp()
    subprocess.run(["git", "init", "-q", str(fixture.root)], check=True)
    # Only the upstream planning validator is mocked; allocation, validation,
    # locking and file IO below use the production implementations.
    monkeypatch.setattr(taskctl, "tool_binary", lambda root, name: Path(name))
    monkeypatch.setattr(taskctl, "run_command", lambda command, **kwargs: subprocess.CompletedProcess(
        command, 0, json.dumps({"schemaName": "ripdpi-deploy-change", "artifacts": [
            {"id": name, "status": "done"} for name in ("proposal", "specs", "design")
        ]}),
    ))
    yield fixture
    fixture.tearDown()


def _required_planning(fixture):
    issue = fixture.add_active_spec_task(status="backlog")
    document = taskctl.read_document(issue)
    change = fixture.root / "openspec/changes" / document.values["openspec_change"]
    (change / "design.md").write_text("## Decisions\n\nPreserve access.\n")
    return document, change


def _add(fixture, task_id, *arguments):
    return taskctl.main(["--root", str(fixture.root), "steps", task_id, "add", *arguments])


def test_steps_add_allocates_backlink_defaults_and_preserves_content(portfolio, capsys):
    issue = portfolio.add_simple_task()
    document = taskctl.read_document(issue)
    path = taskctl.expected_execution_path(portfolio.root, document)
    path.chmod(0o640)
    previous = path.read_bytes()
    assert _add(portfolio, document.task_id, "Verify the failure path") == 0
    steps = taskctl.read_steps(path)
    assert path.read_bytes().startswith(previous)
    assert path.stat().st_mode & 0o777 == 0o640
    assert len(steps) == 2 and not steps[-1].done
    assert steps[-1].item_id == document.task_id
    assert steps[-1].text == f"Verify the failure path #chore !high @item:{document.task_id}"
    assert steps[-1].task_id in capsys.readouterr().out
    reservations = portfolio.root / ".git/taskctl-id-reservations"
    assert steps[-1].task_id.split("-")[1] in reservations.read_text().splitlines()
    taskctl.load_state(portfolio.root)


def test_steps_add_bootstraps_and_continues_only_selected_planning(portfolio, capsys):
    document, change = _required_planning(portfolio)
    (change / "tasks.md").unlink()
    (change / "verification.md").unlink()
    with pytest.raises(taskctl.ContractError, match="missing execution"):
        taskctl.load_state(portfolio.root)
    previous_umask = os.umask(0)
    try:
        assert _add(portfolio, document.task_id, "Implement guard") == 0
    finally:
        os.umask(previous_umask)
    assert (change / "tasks.md").stat().st_mode & 0o777 == 0o600
    first = (change / "tasks.md").read_bytes()
    assert _add(portfolio, document.task_id, "Test rejection", "--kind", "bug", "--priority", "critical") == 0
    assert (change / "tasks.md").read_bytes().startswith(first)
    steps = taskctl.read_steps(change / "tasks.md")
    assert len(steps) == 2 and steps[-1].text.endswith(f"#bug !crit @item:{document.task_id}")
    assert "pending" in capsys.readouterr().out.lower()
    assert not (change / "verification.md").exists()
    with pytest.raises(taskctl.ContractError, match="verification.md"):
        taskctl.load_state(portfolio.root)


def test_steps_add_bootstrap_does_not_interpolate_portfolio_title(portfolio):
    document, change = _required_planning(portfolio)
    values = dict(document.values, title="Heading\n- [ ] injected")
    document.path.write_text(taskctl.render_document(values, document.body))
    issue_before = document.path.read_bytes()
    (change / "tasks.md").unlink()
    (change / "verification.md").unlink()
    assert _add(portfolio, document.task_id, "Implement guard") == 0
    steps = taskctl.read_steps(change / "tasks.md")
    assert len(steps) == 1 and steps[0].item_id == document.task_id
    assert (change / "tasks.md").read_text().startswith(f"# {document.task_id}\n")
    assert document.path.read_bytes() == issue_before


def test_steps_add_accepts_incomplete_mapping_but_global_validation_stays_strict(portfolio):
    document, change = _required_planning(portfolio)
    verification = change / "verification.md"
    verification.write_text(verification.read_text().replace(
        "| REQ-ANS-1786234567890101-001 | ANS-1786234567890102 | Pending | required |", "",
    ))
    assert _add(portfolio, document.task_id, "Add evidence check") == 0
    with pytest.raises(taskctl.ContractError, match="requirement evidence mismatch"):
        taskctl.load_state(portfolio.root)


@pytest.mark.parametrize("corruption", ["missing-execution", "bad-backlink", "orphan", "duplicate-id"])
def test_steps_add_rejects_unrelated_invalid_state_without_writing(portfolio, corruption):
    document, change = _required_planning(portfolio)
    (change / "tasks.md").unlink()
    (change / "verification.md").unlink()
    other = portfolio.add_simple_task()
    path = taskctl.expected_execution_path(portfolio.root, taskctl.read_document(other))
    if corruption == "missing-execution":
        path.unlink()
    elif corruption == "bad-backlink":
        path.write_text(path.read_text().replace("@item:CIC-1786234567890001", "@item:ANS-1786234567890101"))
    elif corruption == "orphan":
        (path.parent / "orphan.md").write_text(path.read_text())
    else:
        path.write_text(path.read_text().replace("CIC-1786234567890002", "ANS-1786234567890101"))
    assert _add(portfolio, document.task_id, "Implement guard") == 2
    assert not (change / "tasks.md").exists()
    assert not (portfolio.root / ".git/taskctl-id-reservations").exists()


@pytest.mark.parametrize("corruption", ["design", "proposal", "metadata", "verification", "backlink", "tasks", "mapping"])
def test_steps_add_rejects_corrupt_selected_planning(portfolio, corruption):
    document, change = _required_planning(portfolio)
    if corruption in {"design", "metadata"}:
        (change / ("design.md" if corruption == "design" else ".openspec.yaml")).unlink()
    elif corruption == "proposal":
        (change / "proposal.md").write_text("No task backlink\n")
    elif corruption == "verification":
        (change / "verification.md").write_text("Not frontmatter\n")
    elif corruption == "backlink":
        path = change / "verification.md"
        path.write_text(path.read_text().replace("task_id: ANS-1786234567890101", "task_id: ANS-1786234567890999"))
    elif corruption == "mapping":
        path = change / "verification.md"
        path.write_text(path.read_text().replace("| ANS-1786234567890102 |", "| unallocated |"))
    else:
        (change / "tasks.md").write_text("- [ ] unallocated step\n")
    previous = (change / "tasks.md").read_bytes()
    assert _add(portfolio, document.task_id, "Implement guard") == 2
    assert (change / "tasks.md").read_bytes() == previous


@pytest.mark.parametrize("target", ["file", "parent", "dangling"])
def test_steps_add_rejects_symlink_execution_paths(portfolio, target):
    issue = portfolio.add_simple_task()
    document = taskctl.read_document(issue)
    path = taskctl.expected_execution_path(portfolio.root, document)
    previous = path.read_bytes()
    if target == "parent":
        original = path.parent
        destination = original.with_name("real-work")
        original.rename(destination)
        original.symlink_to(destination, target_is_directory=True)
    else:
        destination = path.with_suffix(".original")
        path.rename(destination)
        path.symlink_to(destination if target == "file" else path.with_suffix(".missing"))
    assert _add(portfolio, document.task_id, "New step") == 2
    if target != "parent":
        assert destination.read_bytes() == previous


def test_steps_add_never_bootstraps_missing_simple_execution(portfolio):
    issue = portfolio.add_simple_task()
    document = taskctl.read_document(issue)
    path = taskctl.expected_execution_path(portfolio.root, document)
    path.unlink()
    assert _add(portfolio, document.task_id, "New step") == 2
    assert not path.exists()


def test_steps_add_rejects_terminal_work_before_writing(portfolio, capsys):
    issue = portfolio.add_simple_task()
    document = taskctl.read_document(issue)
    values = dict(document.values, status="done", closed_at="2026-08-27", closed_reason="Done", evidence_summary="Observed")
    issue.write_text(taskctl.render_document(values, document.body))
    path = taskctl.expected_execution_path(portfolio.root, document)
    previous = path.read_bytes()
    assert _add(portfolio, document.task_id, "New step") == 2
    assert "terminal" in capsys.readouterr().err
    assert path.read_bytes() == previous


def test_steps_add_rejects_failed_upstream_spec_validation(portfolio, monkeypatch):
    document, change = _required_planning(portfolio)
    original = taskctl.run_command
    monkeypatch.setattr(taskctl, "run_command", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 1, "invalid delta")
                        if "validate" in command else original(command, **kwargs))
    previous = (change / "tasks.md").read_bytes()
    assert _add(portfolio, document.task_id, "New step") == 2
    assert (change / "tasks.md").read_bytes() == previous


@pytest.mark.parametrize("arguments", [
    [], [""], ["line\nbreak"], ["line\u0085break"], ["Injected @item:CIC-1786234567890001"],
    ["CIC-1786234567890999 Manual ID"], ["Title", "--id", "CIC-1786234567890999"],
    ["Title", "--path", "/tmp/elsewhere"], ["Title", "--kind", "invalid"],
])
def test_steps_add_rejects_malformed_arguments_without_writing(portfolio, arguments):
    issue = portfolio.add_simple_task()
    document = taskctl.read_document(issue)
    path = taskctl.expected_execution_path(portfolio.root, document)
    previous = path.read_bytes()
    try:
        result = _add(portfolio, document.task_id, *arguments)
    except SystemExit as error:
        result = error.code
    assert result == 2
    assert path.read_bytes() == previous


def test_steps_add_concurrent_calls_preserve_all_allocated_records(portfolio):
    issue = portfolio.add_simple_task()
    document = taskctl.read_document(issue)
    command = [sys.executable, str(ROOT / "scripts/tasks/taskctl.py"), "--root", str(portfolio.root),
               "steps", document.task_id, "add"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda n: subprocess.run(
            [*command, f"Concurrent step {n}"], text=True, capture_output=True,
        ), range(4)))
    assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
    _, steps = taskctl.load_state(portfolio.root)
    assert len(steps) == 5
    assert len({step.task_id for step in steps}) == 5
    assert all(re.fullmatch(r"CIC-\d{16}", step.task_id) for step in steps)
