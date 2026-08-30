"""Behavioral contract for the shared source-build receipt helper."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    ROOT
    / "ansible"
    / "roles"
    / "runtime-release"
    / "files"
    / "runtime_build_receipt.py"
)


def _helper_module():
    spec = importlib.util.spec_from_file_location("runtime_build_receipt", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@contextmanager
def _trusted_temporary_path() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix=".ripdpi-build-receipt-", dir=Path.home()))
    original = root.lstat()
    try:
        root.chmod(0o700)
        yield root
    finally:
        if os.path.lexists(root):
            current = root.lstat()
            assert (current.st_dev, current.st_ino) == (
                original.st_dev,
                original.st_ino,
            )
            shutil.rmtree(root)
        assert not os.path.lexists(root)


@pytest.fixture
def trusted_root() -> Iterator[Path]:
    with _trusted_temporary_path() as root:
        yield root


def _staged_path(output: Path, name: str = "fixture-runtime") -> Path:
    return output.parent.parent / "runtime-build-staging" / name / "binary"


def _descriptor(
    output: Path,
    *,
    name: str = "fixture-runtime",
    revision: str = "a" * 40,
    expected_sha256: str | None = None,
    steps: list[dict] | None = None,
) -> dict:
    staged = _staged_path(output, name)
    output_descriptor = {
        "name": "binary",
        "staged_path": str(staged),
        "path": str(output),
    }
    if expected_sha256 is not None:
        output_descriptor["expected_sha256"] = expected_sha256
    return {
        "schema_version": 1,
        "name": name,
        "source": {
            "repository": "fixture://runtime",
            "revision": revision,
        },
        "steps": (
            steps
            if steps is not None
            else [
                {
                    "argv": ["/bin/cp", str(output), str(staged)],
                    "chdir": str(output.parent),
                    "environment": {},
                    "timeout_seconds": 30,
                }
            ]
        ),
        "outputs": [output_descriptor],
    }


def _prepare_layout(root: Path) -> tuple[Path, Path]:
    receipt_root = root / "receipts"
    output_root = root / "bin"
    receipt_root.mkdir(mode=0o755)
    output_root.mkdir(mode=0o755)
    output = output_root / "fixture-runtime"
    output.write_bytes(b"runtime-v1\n")
    output.chmod(0o755)
    return receipt_root, output


def test_missing_receipt_requires_rebuild_without_writing(trusted_root: Path) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)

    result = helper.inspect(receipt_root, _descriptor(output))

    assert result == {
        "schema_version": 1,
        "rebuild_required": True,
        "reason": "missing-receipt",
    }
    assert list(receipt_root.iterdir()) == []


def test_validate_cli_accepts_descriptor_without_receipt_root_or_writes(
    trusted_root: Path,
) -> None:
    output = trusted_root / "not-created"
    descriptor = _descriptor(output)

    result = subprocess.run(
        [sys.executable, str(HELPER), "validate"],
        input=json.dumps(descriptor),
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"schema_version": 1, "valid": True}
    assert not output.exists()


def test_validate_cli_rejects_unsafe_descriptor_before_filesystem_access(
    trusted_root: Path,
) -> None:
    descriptor = _descriptor(trusted_root / "output")
    descriptor["steps"][0]["timeout_seconds"] = 0

    result = subprocess.run(
        [sys.executable, str(HELPER), "validate"],
        input=json.dumps(descriptor),
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "runtime build receipt refused\n"


def test_build_executable_must_be_an_absolute_canonical_path(
    trusted_root: Path,
) -> None:
    helper = _helper_module()
    descriptor = _descriptor(trusted_root / "output")
    descriptor["steps"][0]["argv"][0] = "true"

    with pytest.raises(helper.UnsafeState, match="invalid-build-executable"):
        helper.validate(descriptor)


def test_record_binds_identity_paths_and_output_digests(trusted_root: Path) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
    }
    assert helper.inspect(receipt_root, descriptor) == {
        "schema_version": 1,
        "rebuild_required": False,
        "reason": "current",
    }

    receipt_path = receipt_root / "fixture-runtime.json"
    payload = json.loads(receipt_path.read_text())
    assert payload == {
        "schema_version": 1,
        "name": descriptor["name"],
        "source": descriptor["source"],
        "recipe_sha256": helper.recipe_sha256(descriptor["steps"]),
        "outputs": [
            {
                "name": "binary",
                "path": str(output),
                "sha256": helper.sha256_path(output),
            }
        ],
    }
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o644
    assert receipt_path.stat().st_uid == os.geteuid()
    assert receipt_path.stat().st_nlink == 1

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": False,
    }


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("revision", "inputs-changed"),
        ("missing", "missing-output"),
        ("drift", "output-drift"),
    ],
)
def test_inspect_classifies_actionable_rebuilds(
    trusted_root: Path, mutation: str, reason: str
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    helper.converge(receipt_root, descriptor)

    if mutation == "revision":
        descriptor = _descriptor(output, revision="c" * 40)
    elif mutation == "missing":
        output.unlink()
    else:
        output.write_bytes(b"runtime-drift\n")
        output.chmod(0o755)

    assert helper.inspect(receipt_root, descriptor) == {
        "schema_version": 1,
        "rebuild_required": True,
        "reason": reason,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda path: path.write_text("{not-json"),
        lambda path: path.chmod(0o666),
        lambda path: (path.unlink(), path.symlink_to("elsewhere")),
    ],
)
def test_existing_unsafe_receipt_fails_closed(trusted_root: Path, mutate) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    helper.converge(receipt_root, descriptor)
    receipt = receipt_root / "fixture-runtime.json"
    mutate(receipt)

    with pytest.raises(helper.UnsafeState):
        helper.inspect(receipt_root, descriptor)


def test_descriptor_rejects_ambiguous_or_unsafe_output_paths(
    trusted_root: Path,
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    duplicate = _descriptor(output)
    duplicate["outputs"].append(
        {
            "name": "binary",
            "staged_path": duplicate["outputs"][0]["staged_path"],
            "path": str(output),
        }
    )
    relative = _descriptor(output)
    relative["outputs"][0]["path"] = "relative/runtime"

    for descriptor in (duplicate, relative):
        with pytest.raises(helper.UnsafeState):
            helper.inspect(receipt_root, descriptor)


def test_symlinked_receipt_ancestor_is_rejected(trusted_root: Path) -> None:
    helper = _helper_module()
    real = trusted_root / "real"
    real.mkdir(mode=0o755)
    linked = trusted_root / "linked"
    linked.symlink_to(real, target_is_directory=True)
    output_root = trusted_root / "bin"
    output_root.mkdir(mode=0o755)
    output = output_root / "fixture-runtime"
    output.write_bytes(b"runtime\n")
    output.chmod(0o755)

    with pytest.raises(helper.UnsafeState):
        helper.inspect(linked, _descriptor(output))


def test_symlinked_output_is_rejected(trusted_root: Path) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    target = output.with_suffix(".real")
    output.rename(target)
    output.symlink_to(target)

    with pytest.raises(helper.UnsafeState):
        helper.converge(receipt_root, _descriptor(output))


def test_atomic_receipt_writer_completes_short_writes(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    real_write = helper.os.write

    def short_write(descriptor: int, payload) -> int:
        view = memoryview(payload)
        return real_write(descriptor, view[: max(1, len(view) // 3)])

    monkeypatch.setattr(helper.os, "write", short_write)
    helper.converge(receipt_root, _descriptor(output))

    assert helper.inspect(receipt_root, _descriptor(output))["reason"] == "current"


def test_atomic_receipt_writer_syncs_final_mode_before_publication(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    events: list[tuple[str, str | int]] = []
    real_fsync = helper.os.fsync
    real_fchmod = helper.os.fchmod
    real_replace = helper.os.replace

    def tracked_fsync(descriptor: int) -> None:
        kind = "directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file"
        events.append(("fsync", kind))
        real_fsync(descriptor)

    def tracked_fchmod(descriptor: int, mode: int) -> None:
        events.append(("fchmod", mode))
        real_fchmod(descriptor, mode)

    def tracked_replace(*args, **kwargs) -> None:
        events.append(("replace", 0))
        real_replace(*args, **kwargs)

    monkeypatch.setattr(helper.os, "fsync", tracked_fsync)
    monkeypatch.setattr(helper.os, "fchmod", tracked_fchmod)
    monkeypatch.setattr(helper.os, "replace", tracked_replace)
    helper.converge(receipt_root, _descriptor(output))

    receipt_sequence = [
        ("fsync", "file"),
        ("fchmod", 0o644),
        ("fsync", "file"),
        ("replace", 0),
        ("fsync", "directory"),
    ]
    assert any(
        events[index : index + len(receipt_sequence)] == receipt_sequence
        for index in range(len(events) - len(receipt_sequence) + 1)
    )


def test_cli_emits_only_categorical_json_and_redacts_refusals(
    trusted_root: Path,
) -> None:
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    success = subprocess.run(
        [sys.executable, str(HELPER), "inspect", "--receipt-root", str(receipt_root)],
        input=json.dumps(descriptor),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert success.returncode == 0
    assert json.loads(success.stdout) == {
        "schema_version": 1,
        "rebuild_required": True,
        "reason": "missing-receipt",
    }
    assert str(output) not in success.stdout + success.stderr

    refused = subprocess.run(
        [sys.executable, str(HELPER), "inspect", "--receipt-root", str(receipt_root)],
        input='{"source_revision":"private-value"}',
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused.returncode == 2
    assert refused.stdout == ""
    assert refused.stderr == "runtime build receipt refused\n"
    assert "private-value" not in refused.stderr


@pytest.mark.parametrize(
    "payload",
    [
        "{" + '"private":"' + ("x" * (64 * 1024)) + '"}',
        ("[" * 2000) + "0" + ("]" * 2000),
    ],
)
def test_cli_bounds_or_rejects_pathological_input_without_echo(
    trusted_root: Path, payload: str
) -> None:
    receipt_root, _output = _prepare_layout(trusted_root)
    result = subprocess.run(
        [sys.executable, str(HELPER), "inspect", "--receipt-root", str(receipt_root)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "runtime build receipt refused\n"
    assert "private" not in result.stderr


def test_converge_serializes_same_project_and_builds_once(trusted_root: Path) -> None:
    helper = _helper_module()
    receipt_root = trusted_root / "receipts"
    output_root = trusted_root / "bin"
    receipt_root.mkdir(mode=0o755)
    output_root.mkdir(mode=0o755)
    output = output_root / "fixture-runtime"
    counter = trusted_root / "build-count"
    builder = trusted_root / "builder.py"
    builder.write_text("""import os
import pathlib
import sys
import time

output = pathlib.Path(sys.argv[1])
counter = pathlib.Path(sys.argv[2])
time.sleep(0.1)
output.write_bytes(b'runtime-built\\n')
output.chmod(0o755)
with counter.open('a') as stream:
    stream.write('built\\n')
    stream.flush()
    os.fsync(stream.fileno())
""")
    descriptor = _descriptor(
        output,
        steps=[
            {
                "argv": [
                    sys.executable,
                    str(builder),
                    str(_staged_path(output)),
                    str(counter),
                ],
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 10,
            }
        ],
    )

    results: list[dict] = []
    failures: list[Exception] = []

    def run() -> None:
        try:
            results.append(helper.converge(receipt_root, descriptor))
        except Exception as error:  # test thread preserves the exact failure
            failures.append(error)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not failures
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(result["changed"] for result in results) == [False, True]
    assert counter.read_text().splitlines() == ["built"]
    assert helper.inspect(receipt_root, descriptor)["reason"] == "current"


def test_source_bump_rebuilds_only_the_affected_project(trusted_root: Path) -> None:
    helper = _helper_module()
    receipt_root = trusted_root / "receipts"
    output_root = trusted_root / "bin"
    receipt_root.mkdir(mode=0o755)
    output_root.mkdir(mode=0o755)
    builder = trusted_root / "builder.py"
    builder.write_text("""import pathlib
import sys

output = pathlib.Path(sys.argv[1])
counter = pathlib.Path(sys.argv[2])
output.write_text(sys.argv[3] + '\\n')
output.chmod(0o755)
with counter.open('a') as stream:
    stream.write(sys.argv[3] + '\\n')
""")

    descriptors: list[dict] = []
    counters: list[Path] = []
    for name in ("project-a", "project-b"):
        output = output_root / name
        counter = trusted_root / f"{name}.count"
        counters.append(counter)
        descriptors.append(
            _descriptor(
                output,
                name=name,
                steps=[
                    {
                        "argv": [
                            sys.executable,
                            str(builder),
                            str(_staged_path(output, name)),
                            str(counter),
                            name,
                        ],
                        "chdir": str(trusted_root),
                        "environment": {},
                        "timeout_seconds": 10,
                    }
                ],
            )
        )

    assert [helper.converge(receipt_root, item)["changed"] for item in descriptors] == [
        True,
        True,
    ]
    assert [helper.converge(receipt_root, item)["changed"] for item in descriptors] == [
        False,
        False,
    ]

    descriptors[0] = {
        **descriptors[0],
        "source": {**descriptors[0]["source"], "revision": "b" * 40},
    }
    assert [helper.converge(receipt_root, item)["changed"] for item in descriptors] == [
        True,
        False,
    ]
    assert counters[0].read_text().splitlines() == ["project-a", "project-a"]
    assert counters[1].read_text().splitlines() == ["project-b"]


def test_failed_build_does_not_publish_receipt(trusted_root: Path) -> None:
    helper = _helper_module()
    receipt_root = trusted_root / "receipts"
    output_root = trusted_root / "bin"
    receipt_root.mkdir(mode=0o755)
    output_root.mkdir(mode=0o755)
    output = output_root / "fixture-runtime"
    descriptor = _descriptor(
        output,
        steps=[
            {
                "argv": [sys.executable, "-c", "raise SystemExit(17)"],
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 10,
            }
        ],
    )

    with pytest.raises(helper.UnsafeState, match="build-step-failed"):
        helper.converge(receipt_root, descriptor)

    assert not (receipt_root / "fixture-runtime.json").exists()


def test_expected_output_digest_is_verified_before_receipt_publication(
    trusted_root: Path,
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    expected = helper.sha256_path(output)
    descriptor = _descriptor(output, expected_sha256=expected)

    assert helper.converge(receipt_root, descriptor)["changed"] is True
    receipt = json.loads((receipt_root / "fixture-runtime.json").read_text())
    assert receipt["outputs"] == [
        {
            "name": "binary",
            "path": str(output),
            "expected_sha256": expected,
            "sha256": expected,
        }
    ]

    output.write_bytes(b"substituted-runtime\n")
    output.chmod(0o755)
    with pytest.raises(helper.UnsafeState, match="output-checksum-mismatch"):
        helper.converge(receipt_root, descriptor)
    assert (
        json.loads((receipt_root / "fixture-runtime.json").read_text())["outputs"][0][
            "sha256"
        ]
        == expected
    )


def test_mismatched_staged_output_preserves_active_bytes_and_inode(
    trusted_root: Path,
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    expected = helper.sha256_path(output)
    before = output.stat()
    builder = trusted_root / "stage.py"
    builder.write_text(
        "import pathlib,sys\n"
        "path=pathlib.Path(sys.argv[1]); path.write_bytes(sys.argv[2].encode()); "
        "path.chmod(0o755)\n"
    )
    descriptor = _descriptor(
        output,
        expected_sha256=expected,
        steps=[
            {
                "argv": [
                    sys.executable,
                    str(builder),
                    str(_staged_path(output)),
                    "substituted",
                ],
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 10,
            }
        ],
    )

    with pytest.raises(helper.UnsafeState, match="output-checksum-mismatch"):
        helper.converge(receipt_root, descriptor)

    after = output.stat()
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert output.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()
    assert not _staged_path(output).exists()


def test_failed_build_after_staging_preserves_active_output_and_retries_cleanly(
    trusted_root: Path,
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    before = output.stat()
    staged = _staged_path(output)
    stage = [
        sys.executable,
        "-c",
        (
            "import pathlib,sys; p=pathlib.Path(sys.argv[1]); "
            "p.write_bytes(b'replacement\\n'); p.chmod(0o755)"
        ),
        str(staged),
    ]
    failed = _descriptor(
        output,
        steps=[
            {
                "argv": stage,
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 10,
            },
            {
                "argv": [sys.executable, "-c", "raise SystemExit(17)"],
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 10,
            },
        ],
    )

    with pytest.raises(helper.UnsafeState, match="build-step-failed"):
        helper.converge(receipt_root, failed)
    after = output.stat()
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert output.read_bytes() == b"runtime-v1\n"
    assert not staged.exists()

    successful = _descriptor(
        output,
        steps=[
            {
                "argv": stage,
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 10,
            }
        ],
    )
    assert helper.converge(receipt_root, successful)["changed"] is True
    assert output.read_bytes() == b"replacement\n"
    assert helper.inspect(receipt_root, successful)["reason"] == "current"


def test_second_output_publication_failure_rolls_back_every_live_output(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, first = _prepare_layout(trusted_root)
    second = first.with_name("fixture-companion")
    second.write_bytes(b"companion-v1\n")
    second.chmod(0o755)
    first_before = first.stat()
    second_before = second.stat()
    first_staged = _staged_path(first)
    second_staged = first_staged.with_name("companion")
    builder = trusted_root / "stage-pair.py"
    builder.write_text(
        "import pathlib,sys\n"
        "for path,payload in zip(sys.argv[1:],(b'first-v2\\n',b'second-v2\\n')):\n"
        " p=pathlib.Path(path); p.write_bytes(payload); p.chmod(0o755)\n"
    )
    descriptor = _descriptor(
        first,
        steps=[
            {
                "argv": [
                    sys.executable,
                    str(builder),
                    str(first_staged),
                    str(second_staged),
                ],
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 10,
            }
        ],
    )
    descriptor["outputs"].append(
        {
            "name": "companion",
            "staged_path": str(second_staged),
            "path": str(second),
        }
    )
    real_replace = helper.os.replace

    def fail_second_live_replace(source, destination, *args, **kwargs):
        if destination == second.name and ".runtime-build." in source:
            raise OSError("injected-second-publication-failure")
        return real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(helper.os, "replace", fail_second_live_replace)
    with pytest.raises(OSError, match="injected-second-publication-failure"):
        helper.converge(receipt_root, descriptor)

    assert first.read_bytes() == b"runtime-v1\n"
    assert second.read_bytes() == b"companion-v1\n"
    assert (first.stat().st_dev, first.stat().st_ino) == (
        first_before.st_dev,
        first_before.st_ino,
    )
    assert (second.stat().st_dev, second.stat().st_ino) == (
        second_before.st_dev,
        second_before.st_ino,
    )
    assert not (receipt_root / "fixture-runtime.json").exists()


def test_receipt_failure_rolls_back_live_output(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)

    def fail_receipt(*_args, **_kwargs):
        raise OSError("injected-receipt-failure")

    monkeypatch.setattr(helper, "_record_locked", fail_receipt)
    with pytest.raises(OSError, match="injected-receipt-failure"):
        helper.converge(receipt_root, descriptor)

    assert output.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()


@pytest.mark.parametrize("boundary", ["backup", "stage"])
def test_post_commit_cleanup_failure_reports_pending_success(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)

    if boundary == "backup":
        real_unlink = helper.os.unlink

        def fail_backup_cleanup(path, *args, **kwargs):
            if ".runtime-backup." in str(path):
                raise OSError("injected-post-commit-backup-cleanup-failure")
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(helper.os, "unlink", fail_backup_cleanup)
    else:
        real_remove = helper._remove_directory_contents
        calls = 0

        def fail_final_stage_cleanup(directory: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected-post-commit-stage-cleanup-failure")
            real_remove(directory)

        monkeypatch.setattr(helper, "_remove_directory_contents", fail_final_stage_cleanup)

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
        "cleanup_pending": True,
    }
    assert helper.inspect(receipt_root, descriptor)["reason"] == "current"


def test_existing_output_descriptor_is_closed_before_publication(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    opened: set[int] = set()
    real_open_output = helper._open_output_at
    real_close = helper.os.close
    real_publish = helper._publish_outputs

    def track_open(*args, **kwargs):
        file_descriptor = real_open_output(*args, **kwargs)
        opened.add(file_descriptor)
        return file_descriptor

    def track_close(file_descriptor: int) -> None:
        opened.discard(file_descriptor)
        real_close(file_descriptor)

    def require_closed(publications: list[dict]) -> None:
        assert not opened
        real_publish(publications)

    monkeypatch.setattr(helper, "_open_output_at", track_open)
    monkeypatch.setattr(helper.os, "close", track_close)
    monkeypatch.setattr(helper, "_publish_outputs", require_closed)

    assert helper.converge(receipt_root, descriptor)["changed"] is True
    assert not opened


def test_build_executes_from_retained_validated_directory_descriptor(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    source = trusted_root / "source"
    source.mkdir(mode=0o755)
    moved = trusted_root / "validated-source"
    attacker = trusted_root / "attacker"
    builder = trusted_root / "cwd-builder.py"
    builder.write_text(
        "import pathlib,sys\n"
        "pathlib.Path('cwd-marker').write_text('validated\\n')\n"
        "out=pathlib.Path(sys.argv[1]); out.write_text('built\\n'); out.chmod(0o755)\n"
    )
    descriptor = _descriptor(
        output,
        steps=[
            {
                "argv": [sys.executable, str(builder), str(_staged_path(output))],
                "chdir": str(source),
                "environment": {},
                "timeout_seconds": 10,
            }
        ],
    )
    real_popen = helper.subprocess.Popen
    replaced = False

    def replace_then_popen(*args, **kwargs):
        nonlocal replaced
        if not replaced:
            source.rename(moved)
            attacker.mkdir(mode=0o755)
            source.symlink_to(attacker, target_is_directory=True)
            replaced = True
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(helper.subprocess, "Popen", replace_then_popen)
    assert helper.converge(receipt_root, descriptor)["changed"] is True
    assert (moved / "cwd-marker").read_text() == "validated\n"
    assert not (attacker / "cwd-marker").exists()


def test_replaced_stage_directory_refuses_before_live_publication(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    before = output.stat()
    descriptor = _descriptor(output)
    project = _staged_path(output).parent
    moved = project.with_name("validated-stage")
    real_run = helper._run_build_steps

    def build_then_replace(build_descriptor: dict) -> None:
        real_run(build_descriptor)
        project.rename(moved)
        project.mkdir(mode=0o700)

    monkeypatch.setattr(helper, "_run_build_steps", build_then_replace)
    with pytest.raises(helper.UnsafeState, match="stage-directory-replaced"):
        helper.converge(receipt_root, descriptor)

    after = output.stat()
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert output.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()


def test_validated_stage_directory_descriptor_ignores_later_path_substitution(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    project = _staged_path(output).parent
    moved = project.with_name("retained-stage")
    real_require = helper._require_directory_identity
    replaced = False

    def validate_then_replace(path: Path, directory: int) -> None:
        nonlocal replaced
        real_require(path, directory)
        if not replaced and path == project:
            project.rename(moved)
            project.mkdir(mode=0o700)
            substituted = project / "binary"
            substituted.write_bytes(b"substituted\n")
            substituted.chmod(0o755)
            replaced = True

    monkeypatch.setattr(helper, "_require_directory_identity", validate_then_replace)

    assert helper.converge(receipt_root, descriptor)["changed"] is True
    assert output.read_bytes() == b"runtime-v1\n"
    assert (project / "binary").read_bytes() == b"substituted\n"
    assert not (moved / "binary").exists()


def test_live_output_inode_replacement_refuses_before_publication(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    original = output.with_name("original-runtime")
    real_open = helper._open_output_at
    replaced = False

    def replace_then_open(parent, name, uid, expected=None):
        nonlocal replaced
        if expected is not None and not replaced:
            output.rename(original)
            output.write_bytes(b"substituted\n")
            output.chmod(0o755)
            replaced = True
        return real_open(parent, name, uid, expected)

    monkeypatch.setattr(helper, "_open_output_at", replace_then_open)

    with pytest.raises(helper.UnsafeState, match="output-replaced"):
        helper.converge(receipt_root, descriptor)

    assert output.read_bytes() == b"substituted\n"
    assert original.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()


def test_project_lock_has_a_bounded_acquisition_deadline(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    directory = os.open(receipt_root, os.O_RDONLY)
    held = helper._open_project_lock(directory, "fixture-runtime")
    monkeypatch.setattr(helper, "LOCK_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(helper, "LOCK_POLL_SECONDS", 0.005)
    try:
        with pytest.raises(helper.UnsafeState, match="build-lock-timeout"):
            helper.converge(receipt_root, _descriptor(output))
    finally:
        helper.fcntl.flock(held, helper.fcntl.LOCK_UN)
        os.close(held)
        os.close(directory)


def test_build_timeout_terminates_the_whole_child_process_group(
    trusted_root: Path,
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    marker = trusted_root / "escaped-child"
    builder = trusted_root / "spawn-child.py"
    builder.write_text(
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'-c',"
        "'import pathlib,time;time.sleep(1.2);pathlib.Path(r\\\"'"
        '+sys.argv[1]+\'\\").write_text(\\"escaped\\")\'])\n'
        "time.sleep(30)\n"
    )
    descriptor = _descriptor(
        output,
        steps=[
            {
                "argv": [sys.executable, str(builder), str(marker)],
                "chdir": str(trusted_root),
                "environment": {},
                "timeout_seconds": 1,
            }
        ],
    )

    with pytest.raises(helper.UnsafeState, match="build-step-failed"):
        helper.converge(receipt_root, descriptor)
    time.sleep(0.4)

    assert not marker.exists()
    assert not (receipt_root / "fixture-runtime.json").exists()


@pytest.mark.parametrize("value", ["", "A" * 64, "0" * 63, "0" * 65])
def test_expected_output_digest_rejects_noncanonical_values(
    trusted_root: Path, value: str
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)

    with pytest.raises(helper.UnsafeState):
        helper.inspect(receipt_root, _descriptor(output, expected_sha256=value))
