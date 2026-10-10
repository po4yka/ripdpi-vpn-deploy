"""Durable bootstrap retirement remains authoritative after bounded compaction."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "retention_renderer", ROOT / "scripts/check-templates-render.py"
    )
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    root = tmp_path / "payload"
    for path in (
        root,
        root / "bootstrap",
        root / "sub",
        root / ".vpn-bootstrap-consumed",
        tmp_path / "logs",
    ):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
    for name, data in (
        (".vpn-bootstrap-state.lock", ""),
        (".vpn-bootstrap-retired-before", '{"schema":1,"retired_before":0}'),
        ("revoked", ""),
    ):
        path = root / name
        path.write_text(data)
        path.chmod(0o600)
    variables = renderer.merge_render_vars()
    variables["subscription"].update(
        {
            "subscription_dir": str(root),
            "revoked_file": str(root / "revoked"),
            "reads_log": str(tmp_path / "logs/reads.log"),
            "bootstrap_max_lifetime_seconds": 60,
            "bootstrap_max_consumed_markers": 2,
            "reads_log_max_bytes": 4096,
            "reads_log_backup_count": 2,
        }
    )
    path = tmp_path / "bootstrap.py"
    path.write_text(
        renderer.render_template(
            ROOT / "ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2",
            variables,
        )
    )
    spec = importlib.util.spec_from_file_location("retention_service", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def token(issued):
    return f"b1_{issued:010d}_" + "A" * 43


def test_consumed_grant_remains_retired_after_gc_mirror_restore_ttl_change_and_clock_rollback(
    service,
):
    issued = 1791590400
    grant = token(issued)
    digest = service._hash(grant)
    with service._state_authority() as root:
        assert service._bootstrap_issued(grant, root, issued + 1) == issued
        assert service._record_bootstrap_consumption(digest, issued)
        assert service._bootstrap_consumed(digest) is True
        assert (
            service._maintain_locked(
                root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 1
            )
            == 0
        )
        assert service._read_fence(root) >= issued
        assert not (service.CONSUMED_BOOTSTRAP_DIR / digest).exists()
    # A restored payload and arbitrarily extended mutable metadata are powerless.
    (service.SUBSCRIPTION_DIR / "bootstrap" / digest).write_text("{}")
    (service.SUBSCRIPTION_DIR / "bootstrap" / f"{digest}.meta").write_text(
        '{"expires":9999999999}'
    )
    service.BOOTSTRAP_MAX_LIFETIME = 2592000
    with service._state_authority() as root:
        assert service._bootstrap_issued(grant, root, issued + 1) is None
        assert (
            service._bootstrap_issued(token(issued + 2), root, issued + 3) == issued + 2
        )


def test_capacity_preserves_unexpired_consumption_records(service):
    issued = 1791590400
    with service._state_authority() as root:
        for epoch in (issued, issued + 1):
            assert service._record_bootstrap_consumption(
                service._hash(token(epoch)), epoch
            )
        assert (
            service._maintain_locked(root, issued + 2) == service.BOOTSTRAP_MAX_MARKERS
        )
        assert len(list(service.CONSUMED_BOOTSTRAP_DIR.iterdir())) == 2
        assert (
            service._maintain_locked(
                root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 2
            )
            == 0
        )


def test_gc_failure_before_durable_fence_never_deletes_marker(service, monkeypatch):
    issued = 1791590400
    digest = service._hash(token(issued))
    assert service._record_bootstrap_consumption(digest, issued)

    def fail(_):
        raise OSError("fixture fsync failure")

    monkeypatch.setattr(service, "_sync_directory", fail)
    with service._state_authority() as root, pytest.raises(OSError):
        service._maintain_locked(root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 1)
    assert (service.CONSUMED_BOOTSTRAP_DIR / digest).exists()


def test_unsafe_or_malformed_marker_blocks_collection_before_fence(service):
    marker = service.CONSUMED_BOOTSTRAP_DIR / ("a" * 64)
    marker.write_text('{"issued":"wrong"}')
    marker.chmod(0o600)
    with service._state_authority() as root, pytest.raises(ValueError):
        service._maintain_locked(root, 1791590461)
    assert marker.exists()
    with service._state_authority() as root:
        assert service._read_fence(root) == 0


@pytest.mark.parametrize(
    "grant",
    [
        "A" * 43,
        "b1_9999999999_" + "A" * 43,
        "b1_0000000000_" + "A" * 43,
        "b1_1791590400_short",
    ],
)
def test_legacy_invalid_future_and_zero_tokens_are_refused(service, grant):
    with service._state_authority() as root:
        assert service._bootstrap_issued(grant, root, 1791590401) is None


def test_audit_bytes_and_archive_count_are_bounded_and_private(service):
    for i in range(200):
        service._audit("bootstrap", "a" * 64, "consumed", "192.0.2.1", i)
    logs = list(service.READS_LOG.parent.glob("reads.log*"))
    assert len(logs) == 3
    for path in logs:
        assert path.stat().st_size <= 4096
        assert path.stat().st_mode & 0o777 == 0o600
        for line in path.read_text().splitlines():
            assert json.loads(line)["token_prefix"] == "aaaaaaaa"


def test_gc_interruption_after_committed_fence_is_safe_and_retryable(
    service, monkeypatch
):
    issued = 1791590400
    digest = service._hash(token(issued))
    assert service._record_bootstrap_consumption(digest, issued)
    original = service.os.unlink

    def interrupt(name, *args, **kwargs):
        if name == digest:
            raise OSError("fixture interrupted unlink")
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(service.os, "unlink", interrupt)
        with service._state_authority() as root, pytest.raises(OSError):
            service._maintain_locked(
                root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 1
            )
    with service._state_authority() as root:
        assert service._bootstrap_issued(token(issued), root, issued + 1) is None
        assert service._maintain_locked(root, issued + 1) == 0


@contextlib.contextmanager
def http_service(service):
    import threading
    from http.server import ThreadingHTTPServer
    import urllib.error
    import urllib.request

    server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(grant):
        try:
            return urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/bootstrap/{grant}", timeout=3
            )
        except urllib.error.HTTPError as error:
            return error

    try:
        yield get
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_actual_http_consumption_capacity_and_retired_restore(service):
    from types import SimpleNamespace

    issued = 1791590400
    service.time = SimpleNamespace(time=lambda: issued + 2)
    for epoch in (issued, issued + 1, issued + 2):
        (
            service.SUBSCRIPTION_DIR / "bootstrap" / service._hash(token(epoch))
        ).write_bytes(b"public fixture")
    with http_service(service) as get:
        assert get(token(issued)).read() == b"public fixture"
        assert get(token(issued + 1)).status == 200
        assert get(token(issued + 2)).status == 503
        assert (
            service.SUBSCRIPTION_DIR / "bootstrap" / service._hash(token(issued + 2))
        ).exists()
        with service._state_authority() as root:
            assert (
                service._maintain_locked(
                    root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 2
                )
                == 0
            )
        (
            service.SUBSCRIPTION_DIR / "bootstrap" / service._hash(token(issued))
        ).write_bytes(b"restored old mirror")
        service.BOOTSTRAP_MAX_LIFETIME = 2592000
        assert get(token(issued)).status == 410
        # A new grant still consumes after compaction; refusal is not the only result.
        service.time = SimpleNamespace(time=lambda: issued + 65)
        (
            service.SUBSCRIPTION_DIR / "bootstrap" / service._hash(token(issued + 64))
        ).write_bytes(b"new grant")
        assert get(token(issued + 64)).read() == b"new grant"


def test_maintenance_process_waits_for_shared_request_lock(service):
    import subprocess
    import time

    process = None
    with service._state_authority():
        process = subprocess.Popen(
            [sys.executable, service.__file__, "--maintain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.1)
        assert process.poll() is None
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0, (stdout, stderr)


@pytest.mark.parametrize(
    "missing", [".vpn-bootstrap-retired-before", ".vpn-bootstrap-state.lock"]
)
def test_retained_authority_loss_after_gc_cannot_be_reprovisioned(
    service, monkeypatch, missing
):
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "authority_provision",
        ROOT / "ansible/roles/subscription-host/files/retention_authority.py",
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setattr(
        helper.pwd,
        "getpwnam",
        lambda _: SimpleNamespace(
            pw_uid=service.os.geteuid(), pw_gid=service.os.getegid()
        ),
    )
    issued = 1791590400
    assert service._record_bootstrap_consumption(service._hash(token(issued)), issued)
    with service._state_authority() as root:
        service._maintain_locked(root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 1)
    authority = service.SUBSCRIPTION_DIR / missing
    authority.unlink()
    for check in (False, True):
        with pytest.raises(ValueError, match="retained replay authority"):
            helper.provision(
                {
                    "directory": str(service.SUBSCRIPTION_DIR),
                    "check": check,
                    "initializing": False,
                }
            )
        assert not authority.exists()
    service.time = SimpleNamespace(time=lambda: issued + 1)
    (service.SUBSCRIPTION_DIR / "bootstrap" / service._hash(token(issued))).write_bytes(
        b"restored old grant"
    )
    with http_service(service) as get:
        assert get(token(issued)).status == 503


def test_fresh_initialization_and_safe_existing_pair_preserve_fence(
    service, monkeypatch
):
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "fresh_authority_provision",
        ROOT / "ansible/roles/subscription-host/files/retention_authority.py",
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setattr(
        helper.pwd,
        "getpwnam",
        lambda _: SimpleNamespace(
            pw_uid=service.os.geteuid(), pw_gid=service.os.getegid()
        ),
    )
    for name in (service.FENCE_NAME, service.STATE_LOCK_NAME):
        (service.SUBSCRIPTION_DIR / name).unlink()
    value = {
        "directory": str(service.SUBSCRIPTION_DIR),
        "check": True,
        "initializing": True,
    }
    assert helper.provision(value) == {"changed": True}
    assert not (service.SUBSCRIPTION_DIR / service.FENCE_NAME).exists()
    assert helper.provision({**value, "check": False}) == {"changed": True}
    with service._state_authority() as root:
        service._commit_fence(root, 1791590400)
    assert helper.provision({**value, "check": False, "initializing": False}) == {
        "changed": False
    }
    with service._state_authority() as root:
        assert service._read_fence(root) == 1791590400


@pytest.mark.parametrize(
    "kind", ["fence-bool", "fence-duplicate", "marker-bool", "marker-duplicate"]
)
def test_malformed_replay_schema_preserves_all_records_before_gc(service, kind):
    issued = 1791590400
    digest = service._hash(token(issued))
    assert service._record_bootstrap_consumption(digest, issued)
    marker = service.CONSUMED_BOOTSTRAP_DIR / digest
    fence = service.SUBSCRIPTION_DIR / service.FENCE_NAME
    if kind == "fence-bool":
        fence.write_text('{"schema":true,"retired_before":0}')
    elif kind == "fence-duplicate":
        fence.write_text('{"schema":1,"retired_before":0,"retired_before":1791590400}')
    elif kind == "marker-bool":
        marker.write_text(
            json.dumps({"schema": True, "issued": issued, "expires": issued + 60})
        )
    else:
        marker.write_text(
            '{"schema":1,"issued":1791590400,"issued":1791590399,"expires":1791590460}'
        )
    before = {path: path.read_bytes() for path in (marker, fence)}
    with service._state_authority() as root, pytest.raises(ValueError):
        service._maintain_locked(root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 1)
    assert all(path.read_bytes() == data for path, data in before.items())


def test_short_policy_expiry_cannot_retire_older_unexpired_long_policy_marker(service):
    issued = 1791590400
    service.BOOTSTRAP_MAX_LIFETIME = service.BOOTSTRAP_REPLAY_HORIZON
    long_digest = service._hash(token(issued))
    assert service._record_bootstrap_consumption(long_digest, issued)
    service.BOOTSTRAP_MAX_LIFETIME = 60
    short_digest = service._hash(token(issued + 100))
    assert service._record_bootstrap_consumption(short_digest, issued + 100)
    before = {p: p.read_bytes() for p in service.CONSUMED_BOOTSTRAP_DIR.iterdir()}
    with service._state_authority() as root:
        assert service._maintain_locked(root, issued + 161) == 2
        assert service._read_fence(root) < issued
    assert all(path.read_bytes() == data for path, data in before.items())
    with service._state_authority() as root:
        assert (
            service._maintain_locked(
                root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 1
            )
            == 1
        )
        assert not (service.CONSUMED_BOOTSTRAP_DIR / long_digest).exists()
        assert (service.CONSUMED_BOOTSTRAP_DIR / short_digest).exists()


def test_expired_markers_still_occupy_capacity_until_safe_replay_horizon(service):
    issued = 1791590400
    for epoch in (issued, issued + 1):
        assert service._record_bootstrap_consumption(service._hash(token(epoch)), epoch)
    with service._state_authority() as root:
        assert service._maintain_locked(root, issued + 62) == 2
        assert service._read_fence(root) < issued


def test_invalid_unknown_and_consumed_requests_never_scan_full_history(
    service, monkeypatch
):
    from types import SimpleNamespace

    issued = 1791590400
    service.time = SimpleNamespace(time=lambda: issued + 2)
    known = token(issued)
    assert service._record_bootstrap_consumption(service._hash(known), issued)

    def forbidden(*_):
        raise AssertionError("cheap refusal scanned history")

    monkeypatch.setattr(service, "_maintain_locked", forbidden)
    with http_service(service) as get:
        assert get("A" * 43).status == 410
        assert get(token(9999999999)).status == 410
        assert get(token(issued + 1)).status == 410
        assert get(known).status == 410


def test_unsupported_marker_lifetime_refuses_gc_without_deleting_unexpired_record(
    service,
):
    issued = 1791590400
    marker = service.CONSUMED_BOOTSTRAP_DIR / ("a" * 64)
    marker.write_text(
        json.dumps(
            {
                "schema": 1,
                "issued": issued,
                "expires": issued + service.BOOTSTRAP_REPLAY_HORIZON + 100,
            }
        )
    )
    marker.chmod(0o600)
    before = marker.read_bytes()
    with service._state_authority() as root, pytest.raises(ValueError):
        service._maintain_locked(root, issued + service.BOOTSTRAP_REPLAY_HORIZON + 1)
    assert marker.read_bytes() == before
    with service._state_authority() as root:
        assert service._read_fence(root) == 0


def test_replay_horizon_covers_the_full_supported_secret_lifetime_contract(service):
    schema = json.loads((ROOT / "secrets/schema.json").read_text())
    maximum = schema["properties"]["subscription"]["properties"][
        "bootstrap_max_lifetime_seconds"
    ]["maximum"]
    assert service.BOOTSTRAP_REPLAY_HORIZON == maximum


def test_actual_http_rechecks_retirement_committed_during_gc_before_delivery(
    service, monkeypatch
):
    from types import SimpleNamespace

    issued = 1791590400
    service.time = SimpleNamespace(time=lambda: issued + 1)
    grant = token(issued)
    payload = service.SUBSCRIPTION_DIR / "bootstrap" / service._hash(grant)
    payload.write_bytes(b"no delivery after retirement")

    def committed(root, now):
        service._commit_fence(root, issued)
        return 0

    monkeypatch.setattr(service, "_maintain_locked", committed)
    with http_service(service) as get:
        assert get(grant).status == 410
    assert payload.exists()
    assert not list(service.CONSUMED_BOOTSTRAP_DIR.iterdir())


def test_audit_policy_contraction_reconciles_archive_count_and_byte_bounds(service):
    service.READS_LOG_BACKUP_COUNT = 4
    service.READS_LOG_MAX_BYTES = 8192
    for i in range(400):
        service._audit("bootstrap", "a" * 64, "consumed", "192.0.2.1", i)
    assert len(list(service.READS_LOG.parent.glob("reads.log*"))) == 5
    service.READS_LOG_BACKUP_COUNT = 1
    service.READS_LOG_MAX_BYTES = 4096
    service._audit_append()
    logs = list(service.READS_LOG.parent.glob("reads.log*"))
    assert len(logs) == 2
    assert all(
        path.stat().st_size <= 4096 and path.stat().st_mode & 0o777 == 0o600
        for path in logs
    )


def test_unsafe_excess_archive_refuses_before_existing_logs_are_trimmed_or_removed(
    service, tmp_path
):
    current = service.READS_LOG
    current.write_bytes(b"public retained bytes\n" * 1000)
    current.chmod(0o600)
    target = tmp_path / "foreign-audit"
    target.write_bytes(b"preserve foreign bytes")
    target.chmod(0o600)
    archive = service.READS_LOG.parent / "reads.log.4"
    archive.symlink_to(target)
    service.READS_LOG_BACKUP_COUNT = 1
    before = current.read_bytes()
    with pytest.raises(OSError):
        service._audit_append()
    assert current.read_bytes() == before
    assert archive.is_symlink()
    assert target.read_bytes() == b"preserve foreign bytes"
