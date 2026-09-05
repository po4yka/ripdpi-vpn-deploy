"""Subscription mirror generations publish one coherent payload pointer."""

from __future__ import annotations

import importlib.util
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "mirror_renderer", REPO_ROOT / "scripts/check-templates-render.py"
)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
MIRROR_HELPER = (
    REPO_ROOT / "ansible/roles/subscription-host/templates/vpn-sub-mirror.py.j2"
)
BOOTSTRAP_HELPER = (
    REPO_ROOT / "ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2"
)


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _render_helper(tmp_path: Path, dest: Path, **mirror: str) -> Path:
    variables = renderer.merge_render_vars()
    variables["subscription"].update(
        {
            "subscription_dir": str(dest),
            "mirror": {"backend": "rsync", **mirror},
        }
    )
    helper = tmp_path / "vpn-sub-mirror.py"
    helper.write_text(renderer.render_template(MIRROR_HELPER, variables))
    helper.chmod(0o755)
    return helper


def _run(
    helper: Path, *, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(helper)], capture_output=True, text=True, env=environment
    )


def _current_generation(dest: Path) -> Path:
    return dest / os.readlink(dest / ".vpn-sub-mirror-current")


def _write_source(source: Path, label: str) -> None:
    for route in ("sub", "bootstrap"):
        route_path = source / route
        route_path.mkdir(parents=True, exist_ok=True)
        (route_path / "payload").write_text(f"{label}:{route}")


def test_mirror_publishes_one_private_generation_and_preserves_local_state(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    _write_source(source, "next")
    dest = _private_directory(tmp_path / "destination")
    for route in ("sub", "bootstrap"):
        (dest / route).mkdir()
        (dest / route / "legacy").write_text(f"legacy:{route}")
    (dest / ".ssh").mkdir()
    known_hosts = dest / ".ssh/known_hosts"
    known_hosts.write_text("pinned synthetic host key")
    revoked = dest / "revoked"
    revoked.write_text("synthetic revoked hash")

    helper = _render_helper(tmp_path, dest, source=str(source) + "/")
    result = _run(helper)

    assert result.returncode == 0, result.stderr
    generation = _current_generation(dest)
    assert (generation / "sub/payload").read_text() == "next:sub"
    assert (generation / "bootstrap/payload").read_text() == "next:bootstrap"
    assert (generation / "sub/payload").stat().st_mode & 0o777 == 0o600
    assert generation.stat().st_mode & 0o777 == 0o700
    assert (dest / "sub/legacy").read_text() == "legacy:sub"
    assert known_hosts.read_text() == "pinned synthetic host key"
    assert revoked.read_text() == "synthetic revoked hash"


def test_crash_after_pointer_switch_keeps_complete_generation_and_next_run_reconciles(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    _write_source(source, "first")
    dest = _private_directory(tmp_path / "destination")
    helper = _render_helper(tmp_path, dest, source=str(source) + "/")
    assert _run(helper).returncode == 0
    first = _current_generation(dest)

    _write_source(source, "second")
    crashed = _run(
        helper,
        environment=os.environ | {"VPN_SUB_MIRROR_TEST_CRASH_AFTER_POINTER": "1"},
    )
    assert crashed.returncode == 86
    second = _current_generation(dest)
    assert second != first
    assert (second / "sub/payload").read_text() == "second:sub"
    assert (second / "bootstrap/payload").read_text() == "second:bootstrap"
    assert first.is_dir()

    _write_source(source, "third")
    recovered = _run(helper)
    assert recovered.returncode == 0, recovered.stderr
    third = _current_generation(dest)
    assert (third / "sub/payload").read_text() == "third:sub"
    assert (third / "bootstrap/payload").read_text() == "third:bootstrap"
    assert second.is_dir()


@pytest.mark.parametrize("unsafe_kind", ["symlink", "fifo"])
def test_unsafe_nested_staged_payload_refuses_before_pointer_publish(
    tmp_path: Path, unsafe_kind: str
) -> None:
    source = tmp_path / "source"
    _write_source(source, "next")
    unsafe = source / "sub" / "unsafe"
    if unsafe_kind == "symlink":
        unsafe.symlink_to("payload")
    else:
        os.mkfifo(unsafe)
    dest = _private_directory(tmp_path / "destination")
    (dest / "sub").mkdir()
    (dest / "sub/current").write_text("direct payload")
    (dest / "bootstrap").mkdir()
    (dest / "bootstrap/current").write_text("direct bootstrap")
    helper = _render_helper(tmp_path, dest, source=str(source) + "/")

    result = _run(helper)

    assert result.returncode != 0
    assert "staged payload contains" in result.stderr
    assert not (dest / ".vpn-sub-mirror-current").exists()
    assert (dest / "sub/current").read_text() == "direct payload"
    assert (dest / "bootstrap/current").read_text() == "direct bootstrap"


def test_failed_pull_preserves_direct_payload_and_local_state(tmp_path: Path) -> None:
    dest = _private_directory(tmp_path / "destination")
    (dest / "sub").mkdir()
    (dest / "sub/current").write_text("direct payload")
    (dest / "bootstrap").mkdir()
    (dest / "bootstrap/current").write_text("direct bootstrap")
    (dest / ".ssh").mkdir()
    known_hosts = dest / ".ssh/known_hosts"
    known_hosts.write_text("pinned synthetic host key")
    revoked = dest / "revoked"
    revoked.write_text("synthetic revoked hash")
    helper = _render_helper(tmp_path, dest, source=str(tmp_path / "missing") + "/")

    result = _run(helper)

    assert result.returncode != 0
    assert not (dest / ".vpn-sub-mirror-current").exists()
    assert (dest / "sub/current").read_text() == "direct payload"
    assert (dest / "bootstrap/current").read_text() == "direct bootstrap"
    assert known_hosts.read_text() == "pinned synthetic host key"
    assert revoked.read_text() == "synthetic revoked hash"


@pytest.mark.parametrize("valid_layout", [True, False])
def test_restic_layout_is_validated_before_generation_publish(
    tmp_path: Path, valid_layout: bool
) -> None:
    dest = _private_directory(tmp_path / "destination")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    restored = "sub/payload" if valid_layout else "unexpected/sub/payload"
    restic = fake_bin / "restic"
    restic.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ntarget=\n"
        'while [ "$#" -gt 0 ]; do if [ "$1" = --target ]; then target=$2; shift 2; else shift; fi; done\n'
        f'mkdir -p "$target/{Path(restored).parent}"\n'
        f'printf restored > "$target/{restored}"\n'
    )
    restic.chmod(0o755)
    helper = _render_helper(
        tmp_path,
        dest,
        backend="restic",
        restic_repo="fixture-repository",
        restic_snapshot_path="",
        restic_password_file=str(tmp_path / "password"),
    )
    environment = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

    result = _run(helper, environment=environment)

    if valid_layout:
        assert result.returncode == 0, result.stderr
        assert (_current_generation(dest) / "sub/payload").read_text() == "restored"
    else:
        assert result.returncode != 0
        assert "unexpected root entry" in result.stderr
        assert not (dest / ".vpn-sub-mirror-current").exists()


def test_direct_bootstrap_mode_keeps_legacy_payload_root_when_pointer_is_absent(
    tmp_path: Path,
) -> None:
    dest = _private_directory(tmp_path / "destination")
    variables = renderer.merge_render_vars()
    variables["subscription"]["subscription_dir"] = str(dest)
    bootstrap = tmp_path / "vpn-bootstrap.py"
    bootstrap.write_text(renderer.render_template(BOOTSTRAP_HELPER, variables))

    namespace = runpy.run_path(str(bootstrap))

    assert namespace["_payload_root"]() == dest


def test_bootstrap_refuses_missing_pointer_after_mirror_mode_started(
    tmp_path: Path,
) -> None:
    dest = _private_directory(tmp_path / "destination")
    _private_directory(dest / ".vpn-sub-mirror-generations")
    variables = renderer.merge_render_vars()
    variables["subscription"]["subscription_dir"] = str(dest)
    bootstrap = tmp_path / "vpn-bootstrap.py"
    bootstrap.write_text(renderer.render_template(BOOTSTRAP_HELPER, variables))

    namespace = runpy.run_path(str(bootstrap))

    assert namespace["_payload_root"]() is None


def test_concurrent_publishers_are_serialized_and_keep_current_pointer_valid(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    _write_source(source, "payload")
    dest = _private_directory(tmp_path / "destination")
    helper = _render_helper(tmp_path, dest, source=str(source) + "/")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gate = tmp_path / "gate"
    gate.mkdir()
    rsync = fake_bin / "rsync"
    rsync.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if mkdir "$MIRROR_GATE/first" 2>/dev/null; then\n'
        '  touch "$MIRROR_GATE/started"\n'
        '  while [[ ! -e "$MIRROR_GATE/release" ]]; do sleep 0.02; done\n'
        "fi\n"
        'destination="${!#}"\n'
        'cp -R "$MIRROR_TEST_SOURCE"/. "$destination"\n'
    )
    rsync.chmod(0o755)
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MIRROR_GATE": str(gate),
        "MIRROR_TEST_SOURCE": str(source),
    }

    first = subprocess.Popen(
        [sys.executable, str(helper)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    deadline = time.monotonic() + 5
    while not (gate / "started").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert (gate / "started").exists()
    second = subprocess.Popen(
        [sys.executable, str(helper)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    time.sleep(0.15)
    assert second.poll() is None
    (gate / "release").touch()

    first_stdout, first_stderr = first.communicate(timeout=10)
    second_stdout, second_stderr = second.communicate(timeout=10)
    assert first.returncode == 0, (first_stdout, first_stderr)
    assert second.returncode == 0, (second_stdout, second_stderr)
    current = _current_generation(dest)
    assert (current / "sub/payload").read_text() == "payload:sub"
    assert (current / "bootstrap/payload").read_text() == "payload:bootstrap"
    generations = list((dest / ".vpn-sub-mirror-generations").glob("generation-*"))
    assert len(generations) == 2
    assert current in generations
