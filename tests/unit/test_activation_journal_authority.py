"""Unknown or foreign retained activation authority is never auto-retired."""

import base64
import importlib.util
import os
from pathlib import Path
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(role, filename):
    spec = importlib.util.spec_from_file_location(
        role, ROOT / "ansible/roles" / role / "files" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", ["legacy", "foreign-bytes", "foreign-metadata"])
def test_nginx_unknown_or_foreign_pending_refuses_before_mutation(case, monkeypatch):
    module = load("nginx-xhttp", "nginx_transaction.py")
    with tempfile.TemporaryDirectory(
        dir=Path.home(), prefix=".nginx-authority-"
    ) as temporary:
        root = Path(temporary)

        def fixture_parent(path, *, missing=False):
            # Portable model of the owned tree; actual root ancestor authority
            # is exercised without mocks by the native publication test.
            assert Path(path).is_relative_to(root)
            info = Path(path).stat()
            assert info.st_uid == os.geteuid() and not info.st_mode & 0o022

        monkeypatch.setattr(module, "safe", fixture_parent)
        path = root / "nginx.conf"
        path.write_bytes(b"prior bytes")
        path.chmod(0o640)
        prior = module.capture(path)
        desired = dict(
            path=str(path),
            kind="file",
            mode=0o640,
            uid=os.geteuid(),
            gid=os.getegid(),
            content_b64=base64.b64encode(b"desired bytes").decode(),
        )
        request = dict(
            owner="authority-regression",
            roots=[str(root)],
            files=[desired],
            validate_argv=["/usr/sbin/nginx", "-t"],
            unit="p2-authority.service",
            activation="reload",
            check=False,
            credential_root="",
            runtime_directories=[],
            activate_inactive=False,
            desired_enabled=None,
        )
        pending = root / "pending.json"
        journal = dict(
            schema=1,
            candidate="candidate-" + "0" * 32,
            phase="publishing",
            request=request,
            files={str(path): prior},
            active=False,
            service=dict(active=False, unit_file_state="not-found", exists=False),
            owner=request["owner"],
        )
        if case == "legacy":
            journal.pop("schema")
        elif case == "foreign-bytes":
            path.write_bytes(b"foreign bytes")
        else:
            path.chmod(0o600)
        module.persist(pending, journal)
        before = {child.name: child.read_bytes() for child in root.iterdir()}
        monkeypatch.setattr(
            module,
            "command",
            lambda argv: pytest.fail("foreign recovery must not touch runtime"),
        )
        with pytest.raises(module.TransactionError):
            module.recover(pending, request["unit"])
        assert {child.name: child.read_bytes() for child in root.iterdir()} == before


def test_geodata_unknown_or_foreign_pending_preserves_pair_and_journal(monkeypatch):
    module = load("geodata", "geodata_publish.py")
    with tempfile.TemporaryDirectory(
        dir=Path.home(), prefix=".geodata-authority-"
    ) as temporary:
        directory = Path(temporary)
        pending = directory / ".geodata-pending"
        pending.mkdir(mode=0o700)
        for name in ("geosite.dat", "geoip.dat"):
            (directory / name).write_bytes(b"foreign pair")
            (directory / name).chmod(0o644)
        module.persist(pending / "snapshot.json", {"schema": 999})
        before = (pending / "snapshot.json").read_bytes()
        monkeypatch.setattr(
            module, "activate", lambda: pytest.fail("unknown state must not activate")
        )
        with pytest.raises(ValueError, match="manual-recovery-required"):
            module.recover(directory, pending)
        assert (pending / "snapshot.json").read_bytes() == before
        assert all(
            (directory / name).read_bytes() == b"foreign pair"
            for name in ("geosite.dat", "geoip.dat")
        )


def test_self_steal_prune_is_owned_bounded_and_logically_stable(monkeypatch):
    module = load("nginx-xhttp", "nginx_transaction.py")
    with tempfile.TemporaryDirectory(
        dir=Path.home(), prefix=".prune-authority-"
    ) as temporary:
        root = Path(temporary)
        releases = root / "releases"
        releases.mkdir(mode=0o700)

        def fixture_parent(path, *, missing=False):
            assert Path(path).is_relative_to(root)
            if Path(path).exists():
                info = Path(path).stat()
                assert info.st_uid == os.geteuid() and not info.st_mode & 0o022

        monkeypatch.setattr(module, "safe", fixture_parent)
        old = releases / ("a" * 64)
        old.mkdir(mode=0o700)
        empty = releases / ("b" * 64)
        empty.mkdir(mode=0o700)
        for name in ("fullchain.pem", "privkey.pem"):
            (old / name).write_bytes(b"synthetic owned TLS")
            (old / name).chmod(0o600)
        request = dict(
            owner="reality-self-steal",
            roots=[str(root)],
            files=[],
            validate_argv=["/usr/sbin/nginx", "-t"],
            unit="nginx.service",
            activation="reload",
            check=False,
            credential_root="",
            runtime_directories=[],
            activate_inactive=False,
            desired_enabled=None,
            prune_releases=dict(root=str(releases), keep=None),
        )
        module.request(request)
        fingerprint = module.fingerprint(request)
        expanded = module.expand_release_prune(request)
        assert len(expanded["files"]) == 2
        assert all(row["kind"] == "absent" for row in expanded["files"])
        assert request["files"] == [] and module.fingerprint(request) == fingerprint
        # A release published after logical disable construction is included.
        later = releases / ("c" * 64)
        later.mkdir(mode=0o700)
        (later / "privkey.pem").write_bytes(b"synthetic later key")
        (later / "privkey.pem").chmod(0o600)
        assert len(module.expand_release_prune(request)["files"]) == 3
        assert module.fingerprint(request) == fingerprint
        (later / "unknown").write_bytes(b"foreign owned input")
        with pytest.raises(module.TransactionError, match="foreign-release"):
            module.expand_release_prune(request)
        assert (later / "privkey.pem").exists()
        request["owner"] = "foreign-owner"
        with pytest.raises(module.TransactionError, match="release-prune"):
            module.request(request)


def test_self_steal_seventy_rotations_compact_only_owned_empty_hashdirs(monkeypatch):
    module = load("nginx-xhttp", "nginx_transaction.py")
    with tempfile.TemporaryDirectory(
        dir=Path.home(), prefix=".prune-rotation-"
    ) as temporary:
        root = Path(temporary)
        releases = root / "releases"
        releases.mkdir(mode=0o700)
        monkeypatch.setattr(module, "safe", lambda path, **kw: None)
        document = dict(
            owner="reality-self-steal",
            roots=[str(root)],
            files=[],
            prune_releases=dict(root=str(releases), keep=None),
        )
        for index in range(70):
            keep = f"{index:064x}"
            target = releases / keep
            target.mkdir(mode=0o700)
            (target / "privkey.pem").write_bytes(b"synthetic current key")
            (target / "privkey.pem").chmod(0o600)
            document["prune_releases"]["keep"] = keep
            rows = module.expand_release_prune(document)["files"]
            for row in rows:
                Path(row["path"]).unlink()
            module.compact_empty_releases(document)
            assert list(releases.iterdir()) == [target]
        # Pre-existing empty scaffolds from interrupted old pruning remain bounded
        # but do not consume the retained-pair quota, and are safely compacted.
        for index in range(100, 180):
            (releases / f"{index:064x}").mkdir(mode=0o700)
        module.expand_release_prune(document)
        module.compact_empty_releases(document)
        assert list(releases.iterdir()) == [target]
        empty = releases / ("e" * 64)
        empty.mkdir(mode=0o700)
        foreign = releases / "unknown"
        foreign.mkdir(mode=0o700)
        with pytest.raises(module.TransactionError, match="foreign-release"):
            module.compact_empty_releases(document)
        assert (
            empty.is_dir() and foreign.is_dir() and (target / "privkey.pem").is_file()
        )


def test_nginx_unsafe_prior_metadata_cannot_enter_an_unrecoverable_journal(monkeypatch):
    module = load("nginx-xhttp", "nginx_transaction.py")
    with tempfile.TemporaryDirectory(
        dir=Path.home(), prefix=".prior-mode-"
    ) as temporary:
        root = Path(temporary)
        monkeypatch.setattr(module, "safe", lambda path, **kw: None)
        target = root / "nginx.conf"
        target.write_bytes(b"known prior bytes")
        target.chmod(0o666)
        with pytest.raises(module.TransactionError, match="unsafe-file"):
            module.capture(target)
        assert target.read_bytes() == b"known prior bytes"
        assert target.stat().st_mode & 0o777 == 0o666
        assert not list(root.glob("pending*"))


def test_nginx_prior_links_are_recoverable_or_refused_before_publication(monkeypatch):
    module = load("nginx-xhttp", "nginx_transaction.py")
    with tempfile.TemporaryDirectory(
        dir=Path.home(), prefix=".prior-link-"
    ) as temporary:
        root = Path(temporary)
        monkeypatch.setattr(module, "safe", lambda path, **kw: None)
        (root / "enabled").mkdir(mode=0o700)
        (root / "available").mkdir(mode=0o700)
        target = root / "enabled/site"
        target.symlink_to("../available/site")
        document = dict(
            owner="authority",
            roots=[str(root)],
            files=[dict(path=str(target), kind="absent")],
            validate_argv=["/usr/sbin/nginx", "-t"],
            unit="nginx.service",
            activation="reload",
            check=False,
            credential_root="",
            runtime_directories=[],
            activate_inactive=False,
            desired_enabled=None,
        )
        module.request(document)
        prior = {str(target): module.capture(target)}
        module.validate_previous(document, prior)
        assert prior[str(target)]["target"] == "../available/site"
        # Recovery can restore the exact captured representation.
        target.unlink()
        module.apply(target, prior[str(target)], [])
        assert os.readlink(target) == "../available/site"
        target.unlink()
        target.symlink_to("/foreign/site")
        with pytest.raises(module.TransactionError, match="link"):
            module.validate_previous(document, {str(target): module.capture(target)})
        assert os.readlink(target) == "/foreign/site"
