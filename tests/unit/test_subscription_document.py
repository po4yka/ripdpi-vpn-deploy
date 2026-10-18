"""Atomic subscription documents cross the real publisher and HTTP reader."""
from __future__ import annotations

import base64
import concurrent.futures
import contextlib
import json
import os
import stat
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

import pytest
from test_subscription_retention import service as service  # noqa: PLC0414 - shared pytest fixture


def envelope(payload=b'{ "generation": "new" }\n', expires=''):
    return json.dumps({'schema_version': 1, 'client': 'phone', 'expires': expires,
                       'payload_b64': base64.b64encode(payload).decode()}).encode()


@contextlib.contextmanager
def delivery(service):
    token = 'synthetic-subscription-token'
    token_hash = service._hash(token)
    server = ThreadingHTTPServer(('127.0.0.1', 0), service.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def get():
        try:
            response = request.urlopen(f'http://127.0.0.1:{server.server_port}/sub/{token}', timeout=5)
        except error.HTTPError as failure:
            response = failure
        with response:
            return response.status, response.read()
    try:
        yield token_hash, get
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_document_http_preserves_exact_bytes_and_replaces_expiry_atomically(service):
    with delivery(service) as (digest, get):
        service._publish_subscription(digest, envelope(expires='2000-01-01T00:00:00Z'))
        assert get()[0] == 410
        exact = b'{\n  "generation": "refreshed", "unicode": "\\u0041"\n}\n'
        service._publish_subscription(digest, envelope(exact))
        assert get() == (200, exact)
        document = service.SUBSCRIPTION_DIR / 'sub' / (digest + '.document')
        assert stat.S_IMODE(document.stat().st_mode) == 0o600
        assert not list(document.parent.glob('.document-*'))


def test_readers_racing_refresh_only_observe_complete_generations(service):
    with delivery(service) as (digest, get):
        first, second = b'{"generation":"old"}', b'{ "generation": "new" }\n'
        service._publish_subscription(digest, envelope(first))
        barrier = threading.Barrier(3)
        def publish():
            barrier.wait()
            for index in range(30):
                service._publish_subscription(digest, envelope(first if index % 2 else second))
        def read():
            barrier.wait()
            return [get() for _ in range(30)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as workers:
            writer = workers.submit(publish)
            readers = [workers.submit(read) for _ in range(2)]
            writer.result(timeout=15)
            observations = [value for future in readers for value in future.result(timeout=15)]
        assert all(status == 200 and body in {first, second} for status, body in observations)


@pytest.mark.parametrize('checkpoint', ['write-sync', 'rename', 'directory-sync', 'interrupt'])
def test_publication_failure_retains_a_complete_document(service, monkeypatch, checkpoint):
    digest = service._hash('synthetic-subscription-token')
    old, new = envelope(b'{"generation":"old"}'), envelope()
    service._publish_subscription(digest, old)
    path = service.SUBSCRIPTION_DIR / 'sub' / (digest + '.document')
    original_sync, original_replace = service.os.fsync, service.os.replace
    def sync(descriptor):
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        if checkpoint == ('directory-sync' if directory else 'write-sync'):
            raise OSError('synthetic refusal')
        return original_sync(descriptor)
    def replace(*args, **kwargs):
        if checkpoint == 'rename':
            raise OSError('synthetic refusal')
        if checkpoint == 'interrupt':
            raise KeyboardInterrupt
        return original_replace(*args, **kwargs)
    monkeypatch.setattr(service.os, 'fsync', sync)
    monkeypatch.setattr(service.os, 'replace', replace)
    with pytest.raises((OSError, KeyboardInterrupt)):
        service._publish_subscription(digest, new)
    assert path.read_bytes() == (new if checkpoint == 'directory-sync' else old)
    assert not list(path.parent.glob('.document-*'))


def test_malformed_document_never_falls_back_to_legacy_authority(service):
    with delivery(service) as (digest, get):
        legacy = service.SUBSCRIPTION_DIR / 'sub' / digest
        legacy.write_bytes(b'{"generation":"legacy"}')
        assert get() == (200, legacy.read_bytes())
        document = legacy.with_name(digest + '.document')
        document.write_bytes(b'{"schema_version":1}')
        document.chmod(0o600)
        assert get()[0] == 503


@pytest.mark.parametrize('fault', ['symlink', 'hardlink', 'mode', 'duplicate', 'oversized', 'mirror'])
def test_publisher_refuses_unsafe_authority_and_inputs(service, fault, tmp_path):
    digest = service._hash('synthetic-subscription-token')
    directory = service.SUBSCRIPTION_DIR / 'sub'
    path = directory / (digest + '.document')
    content = envelope()
    if fault in {'symlink', 'hardlink'}:
        target = tmp_path / 'foreign'
        target.write_bytes(envelope())
        target.chmod(0o600)
        if fault == 'symlink':
            path.symlink_to(target)
        else:
            os.link(target, path)
    elif fault == 'mode':
        path.write_bytes(envelope())
        path.chmod(0o644)
    elif fault == 'duplicate':
        content = content.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
    elif fault == 'oversized':
        content = b' ' * (service.MAX_DOCUMENT_BYTES + 1)
    else:
        (service.SUBSCRIPTION_DIR / '.vpn-sub-mirror-generations').mkdir()
    with pytest.raises((ValueError, OSError)):
        service._publish_subscription(digest, content)
    assert not list(directory.glob('.document-*'))


def test_publisher_cli_requires_namespace_and_reports_categorical_failure(service):
    script = Path(service.__file__)
    root = str(service.SUBSCRIPTION_DIR)
    ready = subprocess.run([sys.executable, str(script), '--publication-ready', root], capture_output=True, check=False)
    assert ready.returncode == 0 and ready.stdout.strip() == b'subscription-publisher-v1'
    digest = service._hash('synthetic-subscription-token')
    result = subprocess.run([sys.executable, str(script), '--publish-sub', digest, root], input=envelope(), capture_output=True, check=False)
    assert result.returncode == 0 and result.stdout.strip() == b'subscription-published-v1'
    before = (service.SUBSCRIPTION_DIR / 'sub' / (digest + '.document')).read_bytes()
    rejected = subprocess.run([sys.executable, str(script), '--publish-sub', digest, root], input=b'synthetic-private-marker', capture_output=True, check=False)
    assert rejected.returncode == 2 and b'synthetic-private-marker' not in rejected.stderr
    assert (service.SUBSCRIPTION_DIR / 'sub' / (digest + '.document')).read_bytes() == before
    other = subprocess.run([sys.executable, str(script), '--publication-ready', root + '-other'], capture_output=True, check=False)
    assert other.returncode == 2


def test_process_death_before_atomic_rename_preserves_old_document(service, tmp_path):
    digest = service._hash('synthetic-subscription-token')
    old = envelope(b'{"generation":"old"}')
    service._publish_subscription(digest, old)
    ready = tmp_path / 'at-rename'
    script = tmp_path / 'interrupted-publisher.py'
    script.write_text("""import pathlib, runpy, sys, time
namespace = runpy.run_path(sys.argv[1])
replace = namespace['os'].replace
def blocked(*args, **kwargs):
    pathlib.Path(sys.argv[3]).write_text('ready')
    while True:
        time.sleep(0.05)
namespace['os'].replace = blocked
namespace['_publish_subscription'](sys.argv[2], sys.stdin.buffer.read())
""")
    process = subprocess.Popen([sys.executable, str(script), str(service.__file__), digest, str(ready)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.stdin.write(envelope())
        process.stdin.close()
        import time
        deadline = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), 'publisher did not reach atomic rename'
        process.kill()
        process.wait(timeout=3)
        path = service.SUBSCRIPTION_DIR / 'sub' / (digest + '.document')
        assert path.read_bytes() == old
        # A later real publication can proceed after kernel lock release.
        service._publish_subscription(digest, envelope())
        assert path.read_bytes() == envelope()
        assert not list(path.parent.glob(".document-*"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize('fault', ['symlink', 'hardlink', 'mode', 'oversized'])
def test_interrupted_stage_refusal_preserves_foreign_entries(service, tmp_path, fault):
    digest = service._hash('synthetic-subscription-token')
    directory = service.SUBSCRIPTION_DIR / 'sub'
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(b'preserved')
    foreign.chmod(0o600)
    stage = directory / ('.document-' + 'a' * 32)
    if fault == 'symlink':
        stage.symlink_to(foreign)
    elif fault == 'hardlink':
        os.link(foreign, stage)
    else:
        stage.write_bytes(b'preserved')
        stage.chmod(0o644 if fault == 'mode' else 0o600)
        if fault == 'oversized':
            with stage.open('ab') as stream:
                stream.truncate(service.MAX_DOCUMENT_BYTES + 1)
    with pytest.raises((ValueError, OSError)):
        service._publish_subscription(digest, envelope())
    assert stage.lstat() and foreign.read_bytes() == b'preserved'
    assert not (directory / (digest + '.document')).exists()


def test_revocation_covers_atomic_document_after_mirror_restore(service):
    import shutil
    with delivery(service) as (digest, get):
        exact = b'{ "generation": "preserved" }\n'
        service._publish_subscription(digest, envelope(exact))
        document = service.SUBSCRIPTION_DIR / 'sub' / (digest + '.document')
        service.MIRROR_GENERATIONS.mkdir(mode=0o700)
        def restore(name):
            generation = service.MIRROR_GENERATIONS / name
            generation.mkdir(mode=0o700)
            route = generation / 'sub'
            route.mkdir(mode=0o700)
            shutil.copyfile(document, route / document.name)
            (route / document.name).chmod(0o600)
            service.MIRROR_CURRENT.unlink(missing_ok=True)
            service.MIRROR_CURRENT.symlink_to(generation.relative_to(service.SUBSCRIPTION_DIR))
        restore('generation-first')
        assert get() == (200, exact)
        service.REVOKED_FILE.write_text(digest + '\n')
        assert get()[0] == 410
        restore('generation-restored')
        assert get()[0] == 410
        assert document.read_bytes() == envelope(exact)
