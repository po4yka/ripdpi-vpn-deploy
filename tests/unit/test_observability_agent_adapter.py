"""Behavioural coverage for the bounded node-manifest adapter."""

from __future__ import annotations

import json
from collections.abc import Iterator
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
METRIC_MANIFEST = ROOT / "contract" / "observability-metric-manifest.example.json"
ADAPTER = (
    ROOT
    / "ansible"
    / "roles"
    / "observability_agent"
    / "files"
    / "observability-agent-adapter.py"
)


def _adapter_module():
    spec = importlib.util.spec_from_file_location(
        "observability_agent_adapter", ADAPTER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="ripdpi-observability-agent-", dir=Path.home()
    ) as value:
        root = Path(value)
        root.chmod(0o700)
        yield root


def _manifest(*, schema_version: int = 2, source_revision: str = "a" * 40) -> dict:
    return {
        "schema_version": schema_version,
        "source_revision": source_revision,
        "deployable_digest": "b" * 64,
        "environment": "prod",
        "provider": "test-provider",
    }


def _run(
    tmp_path: Path, document: dict, output: Path | None = None
) -> subprocess.CompletedProcess[str]:
    manifest = tmp_path / "manifest.json"
    output = output or tmp_path / "observability-agent.prom"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    manifest.chmod(0o644)
    return subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--node-id",
            "edge-prod",
            "--expected-source-revision",
            "a" * 40,
            "--expected-deployable-digest",
            "b" * 64,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _run_raw(tmp_path: Path, document: str) -> subprocess.CompletedProcess[str]:
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "observability-agent.prom"
    manifest.write_text(document, encoding="utf-8")
    manifest.chmod(0o644)
    return subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--node-id",
            "edge-prod",
            "--expected-source-revision",
            "a" * 40,
            "--expected-deployable-digest",
            "b" * 64,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_adapter_emits_only_schema2_manifest_identity(tmp_path: Path) -> None:
    result = _run(tmp_path, _manifest())

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "observability-agent.prom").read_text(encoding="utf-8")
    assert (
        'vpn_observability_node_manifest_identity{node="edge-prod",role="source-revision",state="match"} 1'
        in metrics
    )
    assert (
        'vpn_observability_node_manifest_identity{node="edge-prod",role="deployable-digest",state="match"} 1'
        in metrics
    )
    assert "source_revision" not in metrics
    assert "deployable_digest" not in metrics
    assert "provider" not in metrics
    assert "vpn_observability_adapter_collection_success 1" in metrics
    assert (tmp_path / "observability-agent.prom").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "document",
    [
        _manifest(schema_version=1),
        _manifest(source_revision="not-a-revision"),
        {"schema_version": 2},
    ],
)
def test_adapter_refuses_non_schema2_or_unbounded_manifest(
    tmp_path: Path, document: dict
) -> None:
    result = _run(tmp_path, document)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "observability-agent-adapter:" in result.stderr
    assert "vpn_observability_adapter_collection_success 0" in (
        tmp_path / "observability-agent.prom"
    ).read_text(encoding="utf-8")


def test_adapter_refuses_duplicate_keys_without_preserving_stale_success(
    tmp_path: Path,
) -> None:
    result = _run_raw(
        tmp_path,
        json.dumps(_manifest()).replace(
            '"schema_version": 2', '"schema_version": 2, "schema_version": 2'
        ),
    )

    assert result.returncode == 2
    assert "vpn_observability_adapter_collection_success 0" in (
        tmp_path / "observability-agent.prom"
    ).read_text(encoding="utf-8")


def test_adapter_refuses_symlinked_or_oversized_manifest(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_manifest()), encoding="utf-8")
    (tmp_path / "manifest.json").symlink_to(target)
    output = tmp_path / "observability-agent.prom"

    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output",
            str(output),
            "--node-id",
            "edge-prod",
            "--expected-source-revision",
            "a" * 40,
            "--expected-deployable-digest",
            "b" * 64,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2

    (tmp_path / "manifest.json").unlink()
    oversized = json.dumps(_manifest()) + (" " * (64 * 1024))
    result = _run_raw(tmp_path, oversized)
    assert result.returncode == 2


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_adapter_refuses_unsafe_existing_output_without_following_it(
    tmp_path: Path, kind: str
) -> None:
    target = tmp_path / "target.prom"
    target.write_text("do not replace\n", encoding="utf-8")
    output = tmp_path / "observability-agent.prom"
    if kind == "symlink":
        output.symlink_to(target)
    else:
        output.hardlink_to(target)

    result = _run(tmp_path, _manifest())

    assert result.returncode == 2
    assert target.read_text(encoding="utf-8") == "do not replace\n"
    assert not list(tmp_path.glob(".observability-agent.prom.*.tmp"))


def test_adapter_refuses_group_writable_or_replaced_output_parent(
    tmp_path: Path,
) -> None:
    output_parent = tmp_path / "textfile"
    output_parent.mkdir()
    output_parent.chmod(0o770)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    manifest.chmod(0o644)

    result = _run(tmp_path, _manifest(), output_parent / "observability-agent.prom")

    assert result.returncode == 2
    assert not list(output_parent.iterdir())

    output_parent.chmod(0o700)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    output_parent.rmdir()
    output_parent.symlink_to(replacement, target_is_directory=True)
    result = _run(tmp_path, _manifest(), output_parent / "observability-agent.prom")
    assert result.returncode == 2


def test_adapter_allows_only_a_setgid_sticky_shared_output_directory(
    tmp_path: Path,
) -> None:
    output_parent = tmp_path / "textfile"
    output_parent.mkdir()
    output_parent.chmod(0o3770)

    result = _run(tmp_path, _manifest(), output_parent / "observability-agent.prom")

    assert result.returncode == 0, result.stderr
    assert (output_parent / "observability-agent.prom").stat().st_mode & 0o777 == 0o600


def test_atomic_output_retries_short_writes_until_content_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter_module()
    output = tmp_path / "observability-agent.prom"
    original_write = adapter.os.write

    def one_byte_at_a_time(descriptor: int, data: bytes) -> int:
        return original_write(descriptor, data[:1])

    monkeypatch.setattr(adapter.os, "write", one_byte_at_a_time)
    adapter._atomic_write(output, "complete\n")

    assert output.read_text(encoding="utf-8") == "complete\n"
    assert output.stat().st_mode & 0o777 == 0o600


def test_atomic_output_cleans_dirfd_temporary_after_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter_module()
    output = tmp_path / "observability-agent.prom"

    def fail_write(_descriptor: int, _data: bytes) -> int:
        raise OSError("injected write failure")

    monkeypatch.setattr(adapter.os, "write", fail_write)
    with pytest.raises(OSError, match="injected write failure"):
        adapter._atomic_write(output, "incomplete\n")

    assert not output.exists()
    assert not list(tmp_path.glob(".observability-agent.prom.*.tmp"))


def test_atomic_output_refuses_parent_replacement_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter_module()
    output_parent = tmp_path / "textfile"
    moved_parent = tmp_path / "moved-textfile"
    output_parent.mkdir()
    output = output_parent / "observability-agent.prom"
    original_write_all = adapter._write_all

    def replace_parent(descriptor: int, content: bytes) -> None:
        original_write_all(descriptor, content)
        output_parent.rename(moved_parent)
        output_parent.mkdir()

    monkeypatch.setattr(adapter, "_write_all", replace_parent)
    with pytest.raises(adapter.AdapterError, match="unsafe output directory"):
        adapter._atomic_write(output, "never publish\n")

    assert not output.exists()
    assert not list(moved_parent.iterdir())


def test_adapter_emits_bounded_mismatch_state_without_raw_identity(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, _manifest(source_revision="c" * 40))

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "observability-agent.prom").read_text(encoding="utf-8")
    assert 'role="source-revision",state="mismatch"' in metrics
    assert "c" * 40 not in metrics


def test_adapter_metric_families_are_declared_in_canonical_manifest(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, _manifest())
    assert result.returncode == 0, result.stderr

    declared = {
        family["name"]
        for family in json.loads(METRIC_MANIFEST.read_text(encoding="utf-8"))[
            "families"
        ]
    }
    emitted = {
        line.split("{", 1)[0].split(" ", 1)[0]
        for line in (tmp_path / "observability-agent.prom")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith("#")
    }
    assert emitted <= declared
