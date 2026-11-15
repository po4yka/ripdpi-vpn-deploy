"""Subscription mirror generations publish one coherent payload pointer."""

from __future__ import annotations

import importlib.util
import json
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from scripts.template_render import render_fragment, template_environment

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
FETCH_SCRIPT = (
    REPO_ROOT / "ansible/roles/subscription-host/templates/vpn-sub-mirror-fetch.sh.j2"
)
FETCH_UNIT = (
    REPO_ROOT / "ansible/roles/subscription-host/templates/vpn-sub-mirror-fetch.service.j2"
)
# The one place the fetch unit writes and the publisher reads; tests point it at tmp_path.
FETCHED = "/var/lib/vpn-sub-mirror/incoming"
MIRROR_UNIT = (
    REPO_ROOT / "ansible/roles/subscription-host/templates/vpn-sub-mirror.service.j2"
)
MOLECULE_VERIFY = (
    REPO_ROOT / "ansible/roles/subscription-host/molecule/default/verify.yml"
)


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


@pytest.fixture
def umask_022():
    """Exercise authority publication under the normal Linux process umask."""
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def _render_helper(tmp_path: Path, dest: Path, **mirror: str) -> Path:
    variables = renderer.merge_render_vars()
    variables["subscription"].update(
        {
            "subscription_dir": str(dest),
            "mirror": {"backend": "rsync", **mirror},
        }
    )
    # The publisher copies the tree that the fetch unit pulled; tests hand it a tree directly.
    incoming = mirror.get("source", str(tmp_path / "incoming")).rstrip("/")
    helper = tmp_path / "vpn-sub-mirror.py"
    helper.write_text(renderer.render_template(MIRROR_HELPER, variables).replace(FETCHED, incoming))
    helper.chmod(0o755)
    return helper


def _render_bootstrap(tmp_path: Path, dest: Path) -> dict[str, object]:
    """Load the delivery handler with all writable state below the fixture."""
    variables = renderer.merge_render_vars()
    variables["subscription"].update(
        {
            "subscription_dir": str(dest),
            "reads_log": str(tmp_path / "reads.log"),
            "revoked_file": str(tmp_path / "revoked"),
        }
    )
    for name, data in (
        (".vpn-bootstrap-state.lock", ""),
        (".vpn-bootstrap-retired-before", '{"schema":1,"retired_before":0}'),
    ):
        authority = dest / name
        authority.write_text(data)
        authority.chmod(0o600)
    (tmp_path / "revoked").write_text("", encoding="ascii")
    # Match the role's explicit vpn-bootstrap-owned 0600 publication.
    (tmp_path / "revoked").chmod(0o600)
    bootstrap = tmp_path / "vpn-bootstrap.py"
    bootstrap.write_text(renderer.render_template(BOOTSTRAP_HELPER, variables))
    return runpy.run_path(str(bootstrap))


def _run(
    helper: Path, *, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(helper)], capture_output=True, text=True, env=environment
    )


def _current_generation(dest: Path) -> Path:
    return dest / os.readlink(dest / ".vpn-sub-mirror-current")


def test_molecule_verifies_payload_through_the_active_generation_pointer() -> None:
    verify = MOLECULE_VERIFY.read_text()

    assert "/.vpn-sub-mirror-current/sub/" in verify
    assert "/vpn-subscription/sub/" not in verify


def _write_source(source: Path, label: str) -> None:
    for route in ("sub", "bootstrap"):
        route_path = source / route
        route_path.mkdir(parents=True, exist_ok=True)
        (route_path / "payload").write_text(f"{label}:{route}")


def test_mirror_unit_allows_only_rsyncs_setrlimit_resource_call() -> None:
    """Keep the resource deny-list while permitting the rsync startup syscall."""
    unit = MIRROR_UNIT.read_text()

    assert "SystemCallFilter=~@privileged @resources" in unit
    assert "SystemCallFilter=setrlimit" in unit
    assert unit.index("SystemCallFilter=~@privileged @resources") < unit.index(
        "SystemCallFilter=setrlimit"
    )


def test_unprivileged_mirror_never_requests_chown_for_its_own_payload(
    tmp_path: Path,
) -> None:
    """The service owns every created node and must keep @chown denied."""
    source = tmp_path / "source"
    _write_source(source, "next")
    dest = _private_directory(tmp_path / "destination")
    helper = _render_helper(tmp_path, dest, source=str(source) + "/")
    namespace = runpy.run_path(str(helper))
    module_os = namespace["os"]
    original_chown = module_os.chown

    def forbidden_chown(*_args, **_kwargs):
        raise AssertionError("mirror requested a privileged chown syscall")

    module_os.chown = forbidden_chown
    try:
        assert namespace["main"]() == 0
    finally:
        module_os.chown = original_chown

    namespace["_private_tree"](_current_generation(dest))


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


def test_molecule_revocation_authority_is_accepted_under_umask_022(tmp_path, umask_022):
    """The real parser must admit the same authority that Molecule converges."""
    converge = yaml.safe_load((MOLECULE_VERIFY.parent / "converge.yml").read_text())[0]
    values = {}
    for filename in converge.get("vars_files", []):
        values.update(yaml.safe_load((MOLECULE_VERIFY.parent / filename).read_text()))
    values.update(converge.get("vars", {}))
    entries = values["subscription"]["revoked_tokens"]
    dest = _private_directory(tmp_path / "destination")
    namespace = _render_bootstrap(tmp_path, dest)
    authority = tmp_path / "revoked"
    authority.write_text("\n".join(entries) + "\n", encoding="ascii")
    metadata = authority.stat()
    assert metadata.st_uid == os.geteuid()
    assert metadata.st_nlink == 1
    assert metadata.st_mode & 0o777 == 0o600
    assert namespace["_is_revoked"]("") is False
    assert all(namespace["_is_revoked"](entry) is True for entry in entries)


def test_bootstrap_consumption_tombstone_survives_later_mirror_generation(
    tmp_path: Path,
    umask_022,
) -> None:
    """A restored bootstrap payload must never resurrect a consumed token."""
    issued = int(time.time())
    token = f"b1_{issued:010d}_" + "a" * 43
    source = tmp_path / "source"
    _write_source(source, "first")
    dest = _private_directory(tmp_path / "destination")
    _private_directory(dest / ".vpn-bootstrap-consumed")
    helper = _render_helper(tmp_path, dest, source=str(source) + "/")
    assert _run(helper).returncode == 0

    namespace = _render_bootstrap(tmp_path, dest)
    token_hash = namespace["_hash"](token)
    assert namespace["_bootstrap_consumed"](token_hash) is False
    assert (
        namespace["_record_bootstrap_consumption"](token_hash, int(time.time())) is True
    )
    tombstone = dest / ".vpn-bootstrap-consumed" / token_hash
    assert tombstone.is_file()
    assert tombstone.stat().st_mode & 0o777 == 0o600

    _write_source(source, "second")
    assert _run(helper).returncode == 0
    current = _current_generation(dest)
    (current / "bootstrap" / token_hash).write_text("must-not-resurrect")
    (current / "bootstrap" / token_hash).chmod(0o600)

    handler = object.__new__(namespace["Handler"])
    handler.path = f"/bootstrap/{token}"
    handler.headers = {}
    handler.client_address = ("127.0.0.1", 0)
    status: list[int] = []
    handler.send_error = lambda code, *_args: status.append(code)
    handler.do_GET()

    assert status == [410]
    assert namespace["_bootstrap_consumed"](token_hash) is True
    assert (current / "bootstrap" / token_hash).exists()


def test_bootstrap_consumption_refuses_symlinked_tombstone_directory(
    tmp_path: Path,
) -> None:
    dest = _private_directory(tmp_path / "destination")
    external = tmp_path / "external"
    _private_directory(external)
    (dest / ".vpn-bootstrap-consumed").symlink_to(external, target_is_directory=True)
    namespace = _render_bootstrap(tmp_path, dest)

    assert namespace["_bootstrap_consumed"]("a" * 64) is None


def test_bootstrap_consumption_refuses_directory_swap_after_marker_create(
    tmp_path: Path,
) -> None:
    """A marker written into a detached tombstone directory cannot succeed."""
    dest = _private_directory(tmp_path / "destination")
    consumed = _private_directory(dest / ".vpn-bootstrap-consumed")
    namespace = _render_bootstrap(tmp_path, dest)
    token_hash = "a" * 64
    module_os = namespace["os"]
    original_open = module_os.open
    swapped = False

    def swap_before_marker(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == token_hash and dir_fd is not None and not swapped:
            swapped = True
            consumed.rename(dest / ".vpn-bootstrap-consumed.detached")
            _private_directory(dest / ".vpn-bootstrap-consumed")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    module_os.open = swap_before_marker
    try:
        assert (
            namespace["_record_bootstrap_consumption"](token_hash, int(time.time()))
            is None
        )
    finally:
        module_os.open = original_open

    assert swapped
    assert namespace["_bootstrap_consumed"](token_hash) is None


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
    assert "fetched payload contains" in result.stderr
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


def test_interrupted_pulled_stage_with_nonprivate_payload_modes_is_reclaimed(
    tmp_path: Path,
) -> None:
    """Only a private stage root is required for stale-stage cleanup."""
    source = tmp_path / "source"
    _write_source(source, "next")
    dest = _private_directory(tmp_path / "destination")
    generation_root = _private_directory(dest / ".vpn-sub-mirror-generations")
    stage = _private_directory(generation_root / ".stage-interrupted")
    pulled_route = stage / "sub"
    pulled_route.mkdir()
    pulled_route.chmod(0o755)
    pulled_payload = pulled_route / "payload"
    pulled_payload.write_text("pulled-before-hardening")
    pulled_payload.chmod(0o644)

    helper = _render_helper(tmp_path, dest, source=str(source) + "/")
    result = _run(helper)

    assert result.returncode == 0, result.stderr
    assert not stage.exists()
    assert (_current_generation(dest) / "sub" / "payload").read_text() == "next:sub"


def _render_fetch(tmp_path: Path, incoming: Path, **mirror: str) -> Path:
    variables = renderer.merge_render_vars()
    variables["subscription"].update({"mirror": mirror})
    script = tmp_path / "vpn-sub-mirror-fetch.sh"
    script.write_text(renderer.render_template(FETCH_SCRIPT, variables).replace(FETCHED, str(incoming)))
    script.chmod(0o755)
    return script


@pytest.mark.parametrize("valid_layout", [True, False])
def test_restic_layout_is_validated_before_generation_publish(
    tmp_path: Path, valid_layout: bool
) -> None:
    dest = _private_directory(tmp_path / "destination")
    incoming = tmp_path / "fetched" / "incoming"
    incoming.parent.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    restored = "sub/payload" if valid_layout else "unexpected/sub/payload"
    restic = fake_bin / "restic"
    restic.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ntarget=\n"
        '[ "$RESTIC_PASSWORD_FILE" = "$EXPECTED_PASSWORD_FILE" ]\n'
        'while [ "$#" -gt 0 ]; do if [ "$1" = --target ]; then target=$2; shift 2; else shift; fi; done\n'
        f'mkdir -p "$target/{Path(restored).parent}"\n'
        f'printf restored > "$target/{restored}"\n'
        f'chmod 0600 "$target/{restored}"\n'
    )
    restic.chmod(0o755)
    password = tmp_path / "password"
    fetch = _render_fetch(
        tmp_path, incoming, backend="restic", restic_repo="fixture-repository",
        restic_snapshot_path="", restic_password_file=str(password),
    )
    environment = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}", "EXPECTED_PASSWORD_FILE": str(password)}
    fetched = subprocess.run(["bash", str(fetch)], capture_output=True, text=True, env=environment)
    assert fetched.returncode == 0, fetched.stderr
    # The delivery user reads the fetched tree through directory permissions, whatever the snapshot modes were.
    assert (incoming / restored).stat().st_mode & 0o777 == 0o644

    result = _run(_render_helper(tmp_path, dest, source=str(incoming)))

    if valid_layout:
        assert result.returncode == 0, result.stderr
        assert (_current_generation(dest) / "sub/payload").read_text() == "restored"
    else:
        assert result.returncode != 0
        assert "unexpected root entry" in result.stderr
        assert not (dest / ".vpn-sub-mirror-current").exists()


def test_fetch_replaces_the_tree_and_a_failed_pull_keeps_the_previous_one(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_source(source, "first")
    incoming = tmp_path / "fetched" / "incoming"
    incoming.parent.mkdir()
    fetch = _render_fetch(tmp_path, incoming, source=str(source) + "/")
    assert subprocess.run(["bash", str(fetch)], capture_output=True, text=True).returncode == 0
    assert (incoming / "sub/payload").read_text() == "first:sub"
    (source / "sub/stale").write_text("removed upstream")
    assert subprocess.run(["bash", str(fetch)], capture_output=True, text=True).returncode == 0
    (source / "sub/stale").unlink()
    _write_source(source, "second")
    assert subprocess.run(["bash", str(fetch)], capture_output=True, text=True).returncode == 0
    assert (incoming / "sub/payload").read_text() == "second:sub" and not (incoming / "sub/stale").exists()
    assert {entry.name for entry in incoming.parent.iterdir()} == {"incoming"}

    failing = _render_fetch(tmp_path, incoming, source=str(tmp_path / "missing") + "/")
    assert subprocess.run(["bash", str(failing)], capture_output=True, text=True).returncode != 0
    assert (incoming / "sub/payload").read_text() == "second:sub"


def test_fetch_pins_the_worker_host_key_before_any_operator_option(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    rsync = fake_bin / "rsync"
    rsync.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$RSYNC_ARGV"\n')
    rsync.chmod(0o755)
    incoming = tmp_path / "fetched" / "incoming"
    incoming.parent.mkdir()
    fetch = _render_fetch(
        tmp_path, incoming, source="build@worker.example:/payload/", ssh_opts="-p 2222",
        ssh_key_path="/etc/vpn-subscription/mirror_ssh_key", ssh_known_hosts_path="/etc/vpn-subscription/mirror_known_hosts",
    )
    argv_file = tmp_path / "rsync-argv"
    environment = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}", "RSYNC_ARGV": str(argv_file)}
    assert subprocess.run(["bash", str(fetch)], capture_output=True, text=True, env=environment).returncode == 0
    argv = argv_file.read_text().splitlines()
    remote_shell = argv[argv.index("-e") + 1].split()
    assert remote_shell[:5] == ["ssh", "-F", "/dev/null", "-i", "/etc/vpn-subscription/mirror_ssh_key"]
    strict, extra = remote_shell.index("StrictHostKeyChecking=yes"), remote_shell.index("2222")
    pinned = remote_shell.index("UserKnownHostsFile=/etc/vpn-subscription/mirror_known_hosts")
    # ssh keeps the first value of an option, so the pinned ones precede the operator's.
    assert strict < extra and pinned < extra
    assert {"ForwardAgent=no", "KnownHostsCommand=none", "GlobalKnownHostsFile=/dev/null", "ConnectTimeout=10"} <= set(remote_shell)
    assert "accept-new" not in " ".join(remote_shell)
    assert argv[-2:] == ["build@worker.example:/payload/", f"{incoming}.fetch/"]


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
    gate = tmp_path / "gate"
    gate.mkdir()
    # The first publisher holds the lock inside its copy step until the gate is released.
    driver = tmp_path / "gated-publisher.py"
    driver.write_text(
        "import os, runpy, sys, time\n"
        "namespace = runpy.run_path(sys.argv[1])\n"
        "copy = namespace['_pull_into']\n"
        "def gated(stage):\n"
        "    gate = os.environ['MIRROR_GATE']\n"
        "    try:\n"
        "        os.mkdir(gate + '/first')\n"
        "    except FileExistsError:\n"
        "        return copy(stage)\n"
        "    open(gate + '/started', 'w').close()\n"
        "    while not os.path.exists(gate + '/release'):\n"
        "        time.sleep(0.02)\n"
        "    copy(stage)\n"
        "namespace['main'].__globals__['_pull_into'] = gated\n"
        "raise SystemExit(namespace['main']())\n"
    )
    environment = os.environ | {"MIRROR_GATE": str(gate)}

    first = subprocess.Popen(
        [sys.executable, str(driver), str(helper)],
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
        [sys.executable, str(driver), str(helper)],
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


def test_atomic_document_survives_complete_mirror_generation(tmp_path):
    import base64
    import json
    source = _private_directory(tmp_path / "source")
    for route in ("sub", "bootstrap"):
        _private_directory(source / route)
    digest = "a" * 64
    exact = b'{ "generation": "atomic-mirror" }\n'
    content = json.dumps(dict(schema_version=1, client="phone", expires="",
                             payload_b64=base64.b64encode(exact).decode()))
    (source / "sub" / (digest + ".document")).write_text(content)
    dest = _private_directory(tmp_path / "dest")
    helper = _render_helper(tmp_path, dest, source=str(source) + "/")
    result = _run(helper)
    assert result.returncode == 0, result.stderr
    namespace = _render_bootstrap(tmp_path, dest)
    root = namespace["_payload_root"]()
    assert namespace["_delivery"](root / "sub", digest) == (exact, False)


MIRROR_TASKS = REPO_ROOT / "ansible/roles/subscription-host/tasks/mirror.yml"


def _mirror_tasks() -> dict[str, dict]:
    import yaml

    return {task["name"]: task for task in yaml.safe_load(MIRROR_TASKS.read_text())}


def test_mirror_credentials_belong_to_the_mirror_user_only() -> None:
    tasks = _mirror_tasks()
    directory = tasks["Ensure mirror credential directory"]["ansible.builtin.file"]
    assert (directory["owner"], directory["group"], directory["mode"]) == ("vpn-sub-mirror", "vpn-sub-mirror", "0700")
    for name in ("Drop rsync ssh key", "Drop restic password file", "Pin the build worker host key"):
        task = tasks[name]
        credential = task["ansible.builtin.copy"]
        # Owner-only and not the delivery service user, which faces the internet.
        assert (credential["owner"], credential["group"], credential["mode"]) == ("vpn-sub-mirror", "vpn-sub-mirror", "0600")
        assert task["no_log"] is True and task["diff"] is False
    fetched = tasks["Ensure the fetched payload directory"]["ansible.builtin.file"]
    assert (fetched["owner"], fetched["group"], fetched["mode"]) == ("vpn-sub-mirror", "vpn-bootstrap", "0750")


def test_fetch_runs_as_the_mirror_user_and_publication_waits_for_it() -> None:
    variables = renderer.merge_render_vars()
    fetch = renderer.render_template(FETCH_UNIT, variables)
    publish = renderer.render_template(MIRROR_UNIT, variables)
    assert "User=vpn-sub-mirror\n" in fetch and "User=vpn-bootstrap" not in fetch
    assert "TimeoutStartSec=15min\n" in fetch
    assert "ReadWritePaths=/var/lib/vpn-sub-mirror\n" in fetch
    assert "User=vpn-bootstrap\n" in publish
    assert "Requires=vpn-sub-mirror-fetch.service\n" in publish
    assert "vpn-sub-mirror-fetch.service" in next(line for line in publish.splitlines() if line.startswith("After="))
    # The publisher holds no credential and starts no network client.
    helper = renderer.render_template(MIRROR_HELPER, variables)
    assert "import subprocess" not in helper and "mirror_ssh_key" not in helper and "PASSWORD" not in helper


@pytest.mark.parametrize(
    ("mirror", "admitted"),
    [
        ({"source": "/srv/payload/"}, True),
        ({"source": "build@worker.example:/payload/", "ssh_known_hosts": "worker.example ssh-ed25519 AAAA", "ssh_opts": "-p 2222"}, True),
        ({"source": "build@worker.example:/payload/"}, False),
        ({"source": "build@worker.example:/payload/", "ssh_known_hosts": "  "}, False),
        ({"source": "rsync://worker.example/payload/", "ssh_known_hosts": "worker.example ssh-ed25519 AAAA"}, False),
        ({"source": "/srv/payload/", "ssh_opts": "-o StrictHostKeyChecking=accept-new"}, False),
        ({"source": "/srv/payload/", "ssh_opts": "-o KnownHostsCommand=/bin/true"}, False),
        ({"source": "/srv/payload/", "ssh_opts": "-p 2222 -A"}, False),
        ({"source": "/srv/payload/", "rsync_opts": "-az $(id)"}, False),
        ({"source": "/srv/payload/", "rsync_opts": "-az --delete\n"}, False),
        ({"backend": "restic", "restic_repo": "repository"}, True),
    ],
    ids=["local", "remote-pinned", "remote-unpinned", "remote-blank-pin", "rsync-daemon", "host-key-option",
         "known-hosts-command", "agent-forwarding", "shell-syntax", "trailing-line-break", "restic"],
)
def test_mirror_inputs_need_a_pinned_host_key_and_plain_options(tmp_path, mirror, admitted) -> None:
    # Real Ansible evaluates the role's own task, so its typing of the conditions is what is tested.
    play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
             "vars": {"subscription": {"mirror": mirror}}, "tasks": [_mirror_tasks()["Validate mirror inputs"]]}]
    playbook = tmp_path / "play.json"
    playbook.write_text(json.dumps(play))
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)], capture_output=True, text=True, timeout=120, cwd=tmp_path,
        env={**os.environ, "ANSIBLE_CONFIG": str(REPO_ROOT / "ansible/ansible.cfg"), "ANSIBLE_NOCOLOR": "1"},
    )
    assert (result.returncode == 0) is admitted, result.stdout + result.stderr


def test_a_tree_replaced_during_the_copy_is_not_published(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_source(source, "first")
    dest = _private_directory(tmp_path / "destination")
    namespace = runpy.run_path(str(_render_helper(tmp_path, dest, source=str(source))))
    module_shutil = namespace["main"].__globals__["shutil"]
    original = module_shutil.copyfileobj

    def replace_then_copy(reader, writer):
        # What a second fetch does: a new directory takes the place of the one being copied.
        if source.exists() and not (tmp_path / "old").exists():
            source.rename(tmp_path / "old")
            _write_source(source, "second")
        original(reader, writer)

    module_shutil.copyfileobj = replace_then_copy
    try:
        assert namespace["main"]() == 1
    finally:
        module_shutil.copyfileobj = original
    assert not (dest / ".vpn-sub-mirror-current").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any directory")
def test_an_unreadable_fetched_directory_is_not_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_source(source, "next")
    (source / "sub" / "nested").mkdir()
    (source / "sub" / "nested").chmod(0o000)
    dest = _private_directory(tmp_path / "destination")
    try:
        result = _run(_render_helper(tmp_path, dest, source=str(source)))
    finally:
        (source / "sub" / "nested").chmod(0o700)
    assert result.returncode != 0 and "unreadable" in result.stderr
    assert not (dest / ".vpn-sub-mirror-current").exists()
