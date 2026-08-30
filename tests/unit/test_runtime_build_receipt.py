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


def _two_output_layout(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    receipt_root = root / "receipts"
    output_root = root / "bin"
    input_root = root / "inputs"
    receipt_root.mkdir(mode=0o755)
    output_root.mkdir(mode=0o755)
    input_root.mkdir(mode=0o755)
    first = output_root / "fixture-runtime"
    second = output_root / "fixture-helper"
    first_seed = input_root / "next-runtime"
    second_seed = input_root / "next-helper"
    first.write_bytes(b"previous-runtime\n")
    first.chmod(0o755)
    first_seed.write_bytes(b"next-runtime\n")
    first_seed.chmod(0o755)
    second_seed.write_bytes(b"next-helper\n")
    second_seed.chmod(0o755)
    return receipt_root, first, second, first_seed, second_seed


def _two_output_descriptor(
    receipt_root: Path,
    first: Path,
    second: Path,
    first_seed: Path,
    second_seed: Path,
) -> dict:
    stage = receipt_root.parent / "runtime-build-staging" / "fixture-runtime"
    return {
        "schema_version": 1,
        "name": "fixture-runtime",
        "source": {
            "repository": "fixture://runtime",
            "revision": "b" * 40,
        },
        "steps": [
            {
                "argv": ["/bin/cp", str(first_seed), str(stage / "binary")],
                "chdir": str(first_seed.parent),
                "environment": {},
                "timeout_seconds": 30,
            },
            {
                "argv": ["/bin/cp", str(second_seed), str(stage / "helper")],
                "chdir": str(second_seed.parent),
                "environment": {},
                "timeout_seconds": 30,
            },
        ],
        "outputs": [
            {
                "name": "binary",
                "staged_path": str(stage / "binary"),
                "path": str(first),
            },
            {
                "name": "helper",
                "staged_path": str(stage / "helper"),
                "path": str(second),
            },
        ],
    }


def _crash_converge(
    receipt_root: Path, descriptor: dict, boundary: str
) -> subprocess.CompletedProcess[str]:
    program = r"""
import importlib.util
import json
import os
import pathlib
import sys

helper_path = pathlib.Path(sys.argv[1])
receipt_root = pathlib.Path(sys.argv[2])
descriptor = json.loads(sys.argv[3])
boundary = sys.argv[4]
spec = importlib.util.spec_from_file_location("runtime_build_receipt_crash", helper_path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

if boundary == "journal-link":
    real_link = helper.os.link
    journal_name = f".{descriptor['name']}.transaction.json"
    def crash_after_journal_link(src, dst, *args, **kwargs):
        result = real_link(src, dst, *args, **kwargs)
        if dst == journal_name:
            os._exit(91)
        return result
    helper.os.link = crash_after_journal_link
elif boundary == "journal":
    real = helper._write_transaction_journal
    def crash_after_journal(directory, journal):
        result = real(directory, journal)
        os._exit(91)
    helper._write_transaction_journal = crash_after_journal
else:
    live_names = [pathlib.Path(item["path"]).name for item in descriptor["outputs"]]
    receipt_name = f"{descriptor['name']}.json"
    real = helper.os.replace
    replaced = 0
    def crash_after_replace(src, dst, *args, **kwargs):
        global replaced
        result = real(src, dst, *args, **kwargs)
        if dst in live_names:
            replaced += 1
            if boundary == "rollback-live-1" and replaced == 1:
                raise OSError("force-precommit-reconcile")
            if boundary == f"live-{replaced}":
                os._exit(91)
        elif dst == receipt_name and boundary == "receipt":
            os._exit(91)
        return result
    helper.os.replace = crash_after_replace
    if boundary == "rollback-live-1":
        real_rename = helper.os.rename
        def crash_after_rollback_rename(src, dst, *args, **kwargs):
            result = real_rename(src, dst, *args, **kwargs)
            if src == live_names[0] and str(dst).endswith(".rollback"):
                os._exit(91)
            return result
        helper.os.rename = crash_after_rollback_rename

helper.converge(receipt_root, descriptor)
raise SystemExit(90)
"""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(HELPER),
            str(receipt_root),
            json.dumps(descriptor, sort_keys=True),
            boundary,
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )


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

    monkeypatch.setattr(helper, "_write_receipt_document", fail_receipt)
    with pytest.raises(OSError, match="injected-receipt-failure"):
        helper.converge(receipt_root, descriptor)

    assert output.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_preexisting_transaction_journal_is_preserved_without_live_mutation(
    trusted_root: Path, kind: str
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    before = output.stat()
    journal = receipt_root / ".fixture-runtime.transaction.json"
    foreign = trusted_root / "foreign-journal"
    foreign.write_bytes(b"foreign\n")
    foreign.chmod(0o600)
    if kind == "regular":
        journal.write_bytes(b'{"foreign":"journal"}\n')
        journal.chmod(0o600)
    else:
        journal.symlink_to(foreign)
    journal_before = journal.lstat()

    with pytest.raises(helper.UnsafeState):
        helper.converge(receipt_root, _descriptor(output))

    after = output.stat()
    assert output.read_bytes() == b"runtime-v1\n"
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert (journal.lstat().st_dev, journal.lstat().st_ino) == (
        journal_before.st_dev,
        journal_before.st_ino,
    )
    assert not (receipt_root / "fixture-runtime.json").exists()


def test_transaction_journal_link_race_preserves_foreign_entry(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    before = output.stat()
    journal = receipt_root / ".fixture-runtime.transaction.json"
    foreign = b'{"foreign":"race-winner"}\n'
    real_link = helper.os.link
    inserted = False

    def insert_before_link(source, destination, *args, **kwargs):
        nonlocal inserted
        if destination == journal.name and not inserted:
            inserted = True
            journal.write_bytes(foreign)
            journal.chmod(0o600)
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(helper.os, "link", insert_before_link)
    with pytest.raises(helper.UnsafeState, match="transaction-journal-exists"):
        helper.converge(receipt_root, _descriptor(output))

    after = output.stat()
    assert output.read_bytes() == b"runtime-v1\n"
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert journal.read_bytes() == foreign
    assert not (receipt_root / "fixture-runtime.json").exists()
    assert not list(output.parent.glob(".fixture-runtime.runtime-*"))


def test_receipt_replace_before_directory_sync_is_committed_not_rolled_back(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    original_descriptor = _descriptor(output)
    assert helper.converge(receipt_root, original_descriptor)["changed"] is True
    original = output.stat()
    updated = _descriptor(output, revision="b" * 40)
    receipt = receipt_root / "fixture-runtime.json"
    journal = receipt_root / ".fixture-runtime.transaction.json"
    root_inode = (receipt_root.stat().st_dev, receipt_root.stat().st_ino)
    real_fsync = helper.os.fsync
    failed = False

    def fail_after_receipt_replace(file_descriptor: int) -> None:
        nonlocal failed
        metadata = helper.os.fstat(file_descriptor)
        if (
            not failed
            and stat.S_ISDIR(metadata.st_mode)
            and (metadata.st_dev, metadata.st_ino) == root_inode
            and journal.exists()
            and json.loads(receipt.read_bytes())["source"]["revision"] == "b" * 40
        ):
            failed = True
            raise OSError("injected-receipt-directory-sync-failure")
        real_fsync(file_descriptor)

    monkeypatch.setattr(helper.os, "fsync", fail_after_receipt_replace)
    assert helper.converge(receipt_root, updated) == {
        "schema_version": 1,
        "changed": True,
    }

    committed = output.stat()
    assert (committed.st_dev, committed.st_ino) != (original.st_dev, original.st_ino)
    assert helper.inspect(receipt_root, updated)["reason"] == "current"
    assert not journal.exists()
    assert not list(output.parent.glob(".fixture-runtime.runtime-*"))


def test_receipt_failure_before_replace_classifies_previous_and_rolls_back(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    original = _descriptor(output)
    assert helper.converge(receipt_root, original)["changed"] is True
    previous_receipt = (receipt_root / "fixture-runtime.json").read_bytes()
    previous_output = output.stat()
    updated = _descriptor(output, revision="b" * 40)

    def fail_before_receipt_replace(*_args, **_kwargs) -> None:
        raise OSError("injected-receipt-file-sync-failure")

    monkeypatch.setattr(helper, "_write_receipt_document", fail_before_receipt_replace)

    with pytest.raises(OSError, match="injected-receipt-file-sync-failure"):
        helper.converge(receipt_root, updated)

    restored = output.stat()
    assert (restored.st_dev, restored.st_ino) == (
        previous_output.st_dev,
        previous_output.st_ino,
    )
    assert (receipt_root / "fixture-runtime.json").read_bytes() == previous_receipt
    assert not (receipt_root / ".fixture-runtime.transaction.json").exists()


def test_foreign_receipt_after_journal_refuses_without_rollback(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    before = output.stat()
    receipt = receipt_root / "fixture-runtime.json"
    journal = receipt_root / ".fixture-runtime.transaction.json"

    def publish_foreign_receipt(
        directory: int, receipt_name: str, _receipt: dict
    ) -> None:
        foreign = {
            "schema_version": 1,
            "name": "fixture-runtime",
            "source": {"repository": "fixture://foreign", "revision": "c" * 40},
            "recipe_sha256": "d" * 64,
            "outputs": [
                {
                    "name": "binary",
                    "path": str(output),
                    "sha256": "e" * 64,
                }
            ],
        }
        helper._atomic_write(
            directory,
            receipt_name,
            json.dumps(foreign, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        )
        raise OSError("injected-foreign-receipt")

    monkeypatch.setattr(helper, "_write_receipt_document", publish_foreign_receipt)
    with pytest.raises(helper.UnsafeState, match="cleanup-journal-receipt-ambiguous"):
        helper.converge(receipt_root, _descriptor(output))

    published = output.stat()
    assert (published.st_dev, published.st_ino) != (before.st_dev, before.st_ino)
    assert receipt.is_file()
    assert journal.is_file()


@pytest.mark.parametrize(
    "boundary",
    [
        "journal-link",
        "journal",
        "live-1",
        "live-2",
        "receipt",
        "rollback-live-1",
    ],
)
def test_fresh_process_recovers_two_output_transaction_after_real_crash(
    trusted_root: Path, boundary: str
) -> None:
    helper = _helper_module()
    receipt_root, first, second, first_seed, second_seed = _two_output_layout(
        trusted_root
    )
    descriptor = _two_output_descriptor(
        receipt_root, first, second, first_seed, second_seed
    )

    crashed = _crash_converge(receipt_root, descriptor, boundary)

    assert crashed.returncode == 91
    assert crashed.stdout == ""
    assert crashed.stderr == ""
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "converge",
            "--receipt-root",
            str(receipt_root),
        ],
        input=json.dumps(descriptor),
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["changed"] is True
    assert first.read_bytes() == b"next-runtime\n"
    assert second.read_bytes() == b"next-helper\n"
    assert helper.inspect(receipt_root, descriptor) == {
        "schema_version": 1,
        "rebuild_required": False,
        "reason": "current",
    }
    assert not (receipt_root / ".fixture-runtime.transaction.json").exists()
    assert not (receipt_root / "..fixture-runtime.transaction.json.quarantine").exists()
    assert not list(first.parent.glob(".*.runtime-*"))
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": False,
    }


def test_post_commit_cleanup_failure_reports_pending_success(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)

    real_unlink = helper.os.unlink
    failed = False

    def fail_backup_cleanup(path, *args, **kwargs):
        nonlocal failed
        if ".runtime-backup." in str(path) and not failed:
            failed = True
            raise OSError("injected-post-commit-backup-cleanup-failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(helper.os, "unlink", fail_backup_cleanup)

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
        "cleanup_pending": True,
    }
    assert helper.inspect(receipt_root, descriptor)["reason"] == "current"
    marker = receipt_root / ".fixture-runtime.transaction.json"
    assert marker.is_file()
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
    }
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": False,
    }
    assert not marker.exists()
    assert not list(output.parent.glob(f".{output.name}.runtime-backup.*"))
    stage = receipt_root.parent / "runtime-build-staging" / "fixture-runtime"
    assert stage.is_dir()
    assert list(stage.iterdir()) == []


def test_committed_recovery_notifies_before_any_fallible_stage_work(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    real_unlink = helper.os.unlink
    failed = False

    def fail_backup_cleanup(path, *args, **kwargs):
        nonlocal failed
        if ".runtime-backup." in str(path) and not failed:
            failed = True
            raise OSError("injected-post-commit-backup-cleanup-failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(helper.os, "unlink", fail_backup_cleanup)
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
        "cleanup_pending": True,
    }
    monkeypatch.undo()

    real_prepare_stage = helper._prepare_stage
    prepare_called = False

    def fail_after_real_recovered_stage_close(*args, **kwargs):
        nonlocal prepare_called
        prepare_called = True
        stage_path, stage_fd = real_prepare_stage(*args, **kwargs)
        helper.os.close(stage_fd)
        raise OSError("injected-recovered-stage-close-failure")

    monkeypatch.setattr(helper, "_prepare_stage", fail_after_real_recovered_stage_close)
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
    }
    assert prepare_called is False

    monkeypatch.undo()
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": False,
    }


def test_committed_recovery_for_prior_descriptor_converges_requested_revision(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    original = _descriptor(output)
    real_unlink = helper.os.unlink
    failed = False

    def fail_backup_cleanup(path, *args, **kwargs):
        nonlocal failed
        if ".runtime-backup." in str(path) and not failed:
            failed = True
            raise OSError("injected-post-commit-backup-cleanup-failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(helper.os, "unlink", fail_backup_cleanup)
    assert helper.converge(receipt_root, original) == {
        "schema_version": 1,
        "changed": True,
        "cleanup_pending": True,
    }
    monkeypatch.undo()

    seed = trusted_root / "runtime-v2"
    seed.write_bytes(b"runtime-v2\n")
    seed.chmod(0o755)
    staged = _staged_path(output)
    updated = _descriptor(
        output,
        revision="b" * 40,
        steps=[
            {
                "argv": ["/bin/cp", str(seed), str(staged)],
                "chdir": str(seed.parent),
                "environment": {},
                "timeout_seconds": 30,
            }
        ],
    )

    assert helper.converge(receipt_root, updated) == {
        "schema_version": 1,
        "changed": True,
    }
    assert output.read_bytes() == b"runtime-v2\n"
    assert helper.inspect(receipt_root, updated) == {
        "schema_version": 1,
        "rebuild_required": False,
        "reason": "current",
    }
    assert helper.converge(receipt_root, updated) == {
        "schema_version": 1,
        "changed": False,
    }


def test_cleanup_pending_is_not_reported_without_a_readable_durable_journal(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    journal = receipt_root / ".fixture-runtime.transaction.json"
    real_unlink = helper.os.unlink
    failed = False

    def corrupt_journal_then_fail_cleanup(path, *args, **kwargs):
        nonlocal failed
        if ".runtime-backup." in str(path) and not failed:
            failed = True
            journal.write_bytes(b"not-json\n")
            journal.chmod(0o600)
            raise OSError("injected-cleanup-failure-with-lost-journal")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(helper.os, "unlink", corrupt_journal_then_fail_cleanup)

    with pytest.raises(helper.UnsafeState, match="transaction-journal"):
        helper.converge(receipt_root, _descriptor(output))

    assert journal.read_bytes() == b"not-json\n"
    assert helper.inspect(receipt_root, _descriptor(output))["reason"] == "current"


def test_committed_cleanup_reports_pending_when_only_wal_quarantine_is_readable(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    canonical = receipt_root / ".fixture-runtime.transaction.json"
    quarantine = receipt_root / "..fixture-runtime.transaction.json.quarantine"
    root_inode = (receipt_root.stat().st_dev, receipt_root.stat().st_ino)
    real_fsync = helper.os.fsync
    failed = False

    def fail_after_wal_canonical_unlink(file_descriptor: int) -> None:
        nonlocal failed
        metadata = helper.os.fstat(file_descriptor)
        if (
            not failed
            and stat.S_ISDIR(metadata.st_mode)
            and (metadata.st_dev, metadata.st_ino) == root_inode
            and not canonical.exists()
            and quarantine.exists()
            and (receipt_root / "fixture-runtime.json").exists()
        ):
            failed = True
            raise OSError("injected-wal-quarantine-directory-sync-failure")
        real_fsync(file_descriptor)

    monkeypatch.setattr(helper.os, "fsync", fail_after_wal_canonical_unlink)

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
        "cleanup_pending": True,
    }
    assert quarantine.is_file()
    assert not canonical.exists()

    monkeypatch.undo()
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
    }
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": False,
    }
    assert not quarantine.exists()


def test_final_wal_unlink_sync_error_still_reports_committed_changed(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    canonical = receipt_root / ".fixture-runtime.transaction.json"
    quarantine = receipt_root / "..fixture-runtime.transaction.json.quarantine"
    root_inode = (receipt_root.stat().st_dev, receipt_root.stat().st_ino)
    real_fsync = helper.os.fsync
    failed = False

    def fail_after_final_wal_unlink(file_descriptor: int) -> None:
        nonlocal failed
        metadata = helper.os.fstat(file_descriptor)
        if (
            not failed
            and stat.S_ISDIR(metadata.st_mode)
            and (metadata.st_dev, metadata.st_ino) == root_inode
            and not canonical.exists()
            and not quarantine.exists()
            and (receipt_root / "fixture-runtime.json").exists()
        ):
            failed = True
            raise OSError("injected-final-wal-directory-sync-failure")
        real_fsync(file_descriptor)

    monkeypatch.setattr(helper.os, "fsync", fail_after_final_wal_unlink)

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
    }
    assert helper.inspect(receipt_root, descriptor)["reason"] == "current"

    monkeypatch.undo()
    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": False,
    }


@pytest.mark.parametrize(
    "fault",
    ["write", "file-fsync", "chmod", "fstat", "close", "link", "dir-fsync", "unlink"],
)
def test_wal_publication_syscall_failure_recovers_without_live_mutation(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    before = output.stat()
    active = False
    failed = False
    real_writer = helper._write_transaction_journal

    def tracked_writer(directory: int, journal: dict) -> dict:
        nonlocal active
        active = True
        try:
            return real_writer(directory, journal)
        finally:
            active = False

    monkeypatch.setattr(helper, "_write_transaction_journal", tracked_writer)

    def install(name: str) -> None:
        real = getattr(helper.os, name)

        def injected(*args, **kwargs):
            nonlocal failed
            if active and not failed:
                if fault == "dir-fsync" and name == "fsync":
                    if not stat.S_ISDIR(helper.os.fstat(args[0]).st_mode):
                        return real(*args, **kwargs)
                elif fault == "file-fsync" and name == "fsync":
                    if stat.S_ISDIR(helper.os.fstat(args[0]).st_mode):
                        return real(*args, **kwargs)
                failed = True
                if name == "close":
                    real(*args, **kwargs)
                raise OSError(f"injected-wal-{fault}-failure")
            return real(*args, **kwargs)

        monkeypatch.setattr(helper.os, name, injected)

    install(
        {
            "write": "write",
            "file-fsync": "fsync",
            "chmod": "fchmod",
            "fstat": "fstat",
            "close": "close",
            "link": "link",
            "dir-fsync": "fsync",
            "unlink": "unlink",
        }[fault]
    )

    with pytest.raises((OSError, helper.UnsafeState)):
        helper.converge(receipt_root, descriptor)

    after = output.stat()
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert output.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()

    monkeypatch.undo()
    assert helper.converge(receipt_root, descriptor)["changed"] is True
    assert helper.inspect(receipt_root, descriptor)["reason"] == "current"


def test_committed_cleanup_detects_backup_replacement_before_quarantine(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    foreign = b"foreign-backup\n"
    retained = output.parent / "retained-owned-backup"
    real_cleanup = helper._cleanup_committed_output
    replaced = False

    def replace_before_cleanup(item: dict) -> None:
        nonlocal replaced
        if not replaced and item["backup_name"] is not None:
            backup = output.parent / item["backup_name"]
            backup.rename(retained)
            backup.write_bytes(foreign)
            backup.chmod(0o755)
            replaced = True
        real_cleanup(item)

    monkeypatch.setattr(helper, "_cleanup_committed_output", replace_before_cleanup)

    with pytest.raises(helper.UnsafeState, match="transaction-backup-replaced"):
        helper.converge(receipt_root, _descriptor(output))

    backup_names = list(output.parent.glob(".*.runtime-backup.*"))
    assert len(backup_names) == 1
    assert backup_names[0].read_bytes() == foreign
    assert retained.read_bytes() == b"runtime-v1\n"
    assert (receipt_root / ".fixture-runtime.transaction.json").is_file()
    assert helper.inspect(receipt_root, _descriptor(output))["reason"] == "current"


def test_journal_cleanup_detects_replacement_at_validation_boundary(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    canonical = receipt_root / ".fixture-runtime.transaction.json"
    retained = receipt_root / "retained-owned-journal"
    foreign = b"foreign-journal\n"
    real_remove = helper._remove_transaction_journal
    replaced = False

    def replace_before_remove(
        directory: int, project: str, source_name: str, identity: dict
    ) -> None:
        nonlocal replaced
        if not replaced:
            canonical.rename(retained)
            canonical.write_bytes(foreign)
            canonical.chmod(0o600)
            replaced = True
        real_remove(directory, project, source_name, identity)

    monkeypatch.setattr(helper, "_remove_transaction_journal", replace_before_remove)

    with pytest.raises(helper.UnsafeState, match="transaction-journal"):
        helper.converge(receipt_root, _descriptor(output))

    assert canonical.read_bytes() == foreign
    assert retained.is_file()
    assert helper.inspect(receipt_root, _descriptor(output))["reason"] == "current"


def test_backup_quarantine_exclusive_claim_refuses_foreign_tombstone(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    foreign = b"foreign-quarantine\n"
    real_link = helper.os.link
    inserted: Path | None = None

    def insert_foreign_before_claim(source, destination, *args, **kwargs):
        nonlocal inserted
        if ".runtime-backup." in str(destination) and str(destination).endswith(
            ".quarantine"
        ):
            inserted = output.parent / str(destination)
            inserted.write_bytes(foreign)
            inserted.chmod(0o600)
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(helper.os, "link", insert_foreign_before_claim)

    with pytest.raises(helper.UnsafeState, match="transaction-backup-manual-recovery"):
        helper.converge(receipt_root, _descriptor(output))

    assert inserted is not None
    assert inserted.read_bytes() == foreign
    assert (receipt_root / ".fixture-runtime.transaction.json").is_file()
    assert helper.inspect(receipt_root, _descriptor(output))["reason"] == "current"


def test_backup_quarantine_detects_replacement_at_final_recheck(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    foreign = b"foreign-before-unlink\n"
    real_read = helper._read_identity_at
    real_unlink = helper.os.unlink
    tombstone_reads = 0
    replaced: Path | None = None

    def replace_on_final_recheck(directory: int, name: str):
        nonlocal tombstone_reads, replaced
        if ".runtime-backup." in name and name.endswith(".quarantine"):
            tombstone_reads += 1
            if tombstone_reads == 3:
                replaced = output.parent / name
                real_unlink(name, dir_fd=directory)
                replaced.write_bytes(foreign)
                replaced.chmod(0o600)
        return real_read(directory, name)

    monkeypatch.setattr(helper, "_read_identity_at", replace_on_final_recheck)

    with pytest.raises(helper.UnsafeState, match="transaction-backup-replaced"):
        helper.converge(receipt_root, _descriptor(output))

    assert replaced is not None
    assert replaced.read_bytes() == foreign
    assert (receipt_root / ".fixture-runtime.transaction.json").is_file()


def test_stage_cleanup_failure_rolls_back_before_receipt_commit(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    real_remove = helper._remove_directory_contents
    calls = 0

    def fail_precommit_stage_cleanup(directory: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected-precommit-stage-cleanup-failure")
        real_remove(directory)

    monkeypatch.setattr(
        helper, "_remove_directory_contents", fail_precommit_stage_cleanup
    )

    with pytest.raises(OSError, match="injected-precommit-stage-cleanup-failure"):
        helper.converge(receipt_root, descriptor)

    assert output.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()


def test_transaction_journal_replacement_after_publish_refuses_before_live_write(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    before = output.stat()
    canonical = receipt_root / ".fixture-runtime.transaction.json"
    retained = receipt_root / "retained-owned-journal"
    foreign = b'{"foreign":true}\n'
    real_write = helper._write_transaction_journal

    def replace_after_write(directory: int, journal: dict) -> dict:
        identity = real_write(directory, journal)
        canonical.rename(retained)
        canonical.write_bytes(foreign)
        canonical.chmod(0o600)
        return identity

    monkeypatch.setattr(helper, "_write_transaction_journal", replace_after_write)

    with pytest.raises(helper.UnsafeState, match="transaction-journal"):
        helper.converge(receipt_root, _descriptor(output))

    after = output.stat()
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert output.read_bytes() == b"runtime-v1\n"
    assert canonical.read_bytes() == foreign
    assert retained.is_file()
    assert not (receipt_root / "fixture-runtime.json").exists()


def test_two_output_second_preflight_failure_closes_first_descriptor_without_writes(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, first, second, first_seed, second_seed = _two_output_layout(
        trusted_root
    )
    descriptor = _two_output_descriptor(
        receipt_root, first, second, first_seed, second_seed
    )
    crashed = _crash_converge(receipt_root, descriptor, "journal")
    assert crashed.returncode == 91
    before = {
        path.name: (path.lstat().st_dev, path.lstat().st_ino)
        for path in first.parent.iterdir()
    }
    real_preflight = helper._preflight_precommit_output
    calls = 0
    first_parent: int | None = None

    def fail_second(output: dict) -> dict:
        nonlocal calls, first_parent
        calls += 1
        if calls == 2:
            raise helper.UnsafeState("injected-second-preflight-failure")
        result = real_preflight(output)
        first_parent = result["parent"]
        return result

    monkeypatch.setattr(helper, "_preflight_precommit_output", fail_second)
    directory = os.open(receipt_root, os.O_RDONLY)
    try:
        with pytest.raises(
            helper.UnsafeState, match="injected-second-preflight-failure"
        ):
            helper._reconcile_transaction_locked(
                directory, "fixture-runtime.json", "fixture-runtime"
            )
    finally:
        os.close(directory)

    assert first_parent is not None
    with pytest.raises(OSError):
        os.fstat(first_parent)
    assert {
        path.name: (path.lstat().st_dev, path.lstat().st_ino)
        for path in first.parent.iterdir()
    } == before
    assert not (receipt_root / ".fixture-runtime.cleanup.json").exists()


@pytest.mark.parametrize("boundary", ["unlock", "directory-close"])
def test_post_commit_finalization_error_does_not_reverse_success(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    failed = False

    if boundary == "unlock":
        real_flock = helper.fcntl.flock

        def fail_unlock(fd: int, operation: int) -> None:
            nonlocal failed
            if operation == helper.fcntl.LOCK_UN and not failed:
                failed = True
                raise OSError("injected-unlock-failure")
            real_flock(fd, operation)

        monkeypatch.setattr(helper.fcntl, "flock", fail_unlock)
    else:
        real_close = helper.os.close
        receipt_inode = (receipt_root.stat().st_dev, receipt_root.stat().st_ino)

        def fail_directory_close(fd: int) -> None:
            nonlocal failed
            metadata = helper.os.fstat(fd)
            real_close(fd)
            if (
                stat.S_ISDIR(metadata.st_mode)
                and (metadata.st_dev, metadata.st_ino) == receipt_inode
                and (receipt_root / "fixture-runtime.json").exists()
                and not failed
            ):
                failed = True
                raise OSError("injected-directory-close-failure")

        monkeypatch.setattr(helper.os, "close", fail_directory_close)

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
    }
    assert helper.inspect(receipt_root, descriptor)["reason"] == "current"


def test_output_parent_close_after_real_close_preserves_committed_changed(
    trusted_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _helper_module()
    receipt_root, output = _prepare_layout(trusted_root)
    descriptor = _descriptor(output)
    parent_inode = (output.parent.stat().st_dev, output.parent.stat().st_ino)
    real_close = helper.os.close
    failed = False

    def fail_output_parent_close_after_close(file_descriptor: int) -> None:
        nonlocal failed
        metadata = helper.os.fstat(file_descriptor)
        real_close(file_descriptor)
        if (
            not failed
            and stat.S_ISDIR(metadata.st_mode)
            and (metadata.st_dev, metadata.st_ino) == parent_inode
            and (receipt_root / "fixture-runtime.json").exists()
        ):
            failed = True
            raise OSError("injected-output-parent-close-failure")

    monkeypatch.setattr(helper.os, "close", fail_output_parent_close_after_close)

    assert helper.converge(receipt_root, descriptor) == {
        "schema_version": 1,
        "changed": True,
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
    real_write_journal = helper._write_transaction_journal

    def journal_then_replace(directory: int, journal: dict) -> dict:
        identity = real_write_journal(directory, journal)
        output.rename(original)
        output.write_bytes(b"substituted\n")
        output.chmod(0o755)
        return identity

    monkeypatch.setattr(helper, "_write_transaction_journal", journal_then_replace)

    with pytest.raises(helper.UnsafeState, match="transaction-live-ambiguous"):
        helper.converge(receipt_root, descriptor)

    assert output.read_bytes() == b"substituted\n"
    assert original.read_bytes() == b"runtime-v1\n"
    assert not (receipt_root / "fixture-runtime.json").exists()
    assert (receipt_root / ".fixture-runtime.transaction.json").is_file()


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
