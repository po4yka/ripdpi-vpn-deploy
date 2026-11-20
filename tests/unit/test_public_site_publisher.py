"""Node-side publication of a public site bundle: scheduled generation, isolation and recovery."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import public_site
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests/fixtures/public-site-identity"
PUBLISHER = REPO_ROOT / "ansible/roles/public-site/files/public_site_publish.py"
PAST, FUTURE = 1_700_000_000, 4_000_000_000
# The fixture publishes two articles at once, then one for each later generation.
ARTICLES = ["freeing-a-stuck-carriage", "reading-a-drawband", "aligning-typebars", "platen-hardness", "cleaning-type-slugs"]


def run(bundles: Path, state: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(PUBLISHER), str(bundles), str(state)],
                          capture_output=True, text=True, timeout=60, check=False)


def install(tmp_path: Path, archive: Path, times: list[int]) -> tuple[Path, str]:
    """Lay an archive out as the role delivers it, with a schedule the test controls."""
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    target = tmp_path / "bundles" / digest
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(archive, target / "backlog.tar.gz")
    schedule(target, times)
    return tmp_path / "bundles", digest


def schedule(target: Path, times: list[int]) -> None:
    plan = {"version": 1, "generations": [{"n": n, "not_before": moment} for n, moment in enumerate(times)]}
    (target / "schedule.json").write_text(json.dumps(plan))


def served(state: Path, digest: str) -> dict[str, tuple[bytes, float]]:
    root = state / digest / "current"
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime)
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    public_site.build(FIXTURE, tmp_path / "bundle")
    return tmp_path / "bundle" / "backlog.tar.gz"


def test_publisher_serves_the_scheduled_generation_and_advances_with_the_clock(tmp_path: Path, archive: Path) -> None:
    bundles, digest = install(tmp_path, archive, [PAST, PAST + 1, FUTURE, FUTURE + 1])
    state = tmp_path / "state"
    first = run(bundles, state)
    assert first.returncode == 0, first.stderr
    pages = served(state, digest)
    assert {name for name in pages if name.startswith("bench/")} == {f"bench/{slug}.html" for slug in ARTICLES[:3]}
    assert pages["feed.xml"][0].count(b"<entry>") == 3
    assert os.readlink(state / digest / "current") == "generations/1"
    # An article of a later generation has no path below the served root or beside it.
    assert not list((state / digest).rglob("platen-hardness.html"))

    schedule(bundles / digest, [PAST, PAST + 1, PAST + 2, FUTURE])
    assert run(bundles, state).returncode == 0
    pages = served(state, digest)
    assert {name for name in pages if name.startswith("bench/")} == {f"bench/{slug}.html" for slug in ARTICLES[:4]}
    assert [path.name for path in (state / digest / "generations").iterdir()] == ["2"]


def test_file_times_follow_the_bundle_schedule_not_the_publication_run(tmp_path: Path, archive: Path) -> None:
    bundles, digest = install(tmp_path, archive, [PAST] * 4)
    assert run(bundles, tmp_path / "state").returncode == 0
    pages = served(tmp_path / "state", digest)
    built = json.loads((archive.parent / "schedule.json").read_text())["generations"]
    assert pages["bench/cleaning-type-slugs.html"][1] == built[3]["not_before"]
    assert pages["assets/main.css"][1] == built[0]["not_before"]
    assert pages["index.html"][1] == built[3]["not_before"]


def test_a_recreated_node_serves_the_same_bytes_and_times(tmp_path: Path, archive: Path) -> None:
    bundles, digest = install(tmp_path, archive, [PAST, PAST + 1, FUTURE, FUTURE + 1])
    assert run(bundles, tmp_path / "first").returncode == 0
    time.sleep(0.05)
    assert run(bundles, tmp_path / "second").returncode == 0
    assert served(tmp_path / "first", digest) == served(tmp_path / "second", digest)


def test_a_second_run_at_the_same_generation_changes_nothing(tmp_path: Path, archive: Path) -> None:
    bundles, digest = install(tmp_path, archive, [PAST, FUTURE, FUTURE, FUTURE])
    state = tmp_path / "state"
    assert run(bundles, state).returncode == 0
    before = (state / digest / "generations/0").stat().st_ino
    again = run(bundles, state)
    assert again.returncode == 0 and again.stdout == ""
    assert (state / digest / "generations/0").stat().st_ino == before


def test_generation_zero_is_served_before_its_scheduled_time(tmp_path: Path, archive: Path) -> None:
    bundles, digest = install(tmp_path, archive, [FUTURE] * 4)
    assert run(bundles, tmp_path / "state").returncode == 0
    assert os.readlink(tmp_path / "state" / digest / "current") == "generations/0"


def hostile(tmp_path: Path, kind: str, before: str) -> Path:
    """An archive with one unexpected member whose digest sorts before `before`, so it is processed first."""
    path = tmp_path / f"{kind}.tar"
    for nonce in range(10_000):
        with tarfile.open(path, "w") as archive:
            good = tarfile.TarInfo("generations/0/index.html")
            body = b"ok %d" % nonce
            good.size = len(body)
            archive.addfile(good, io.BytesIO(body))
            if kind == "link":
                member = tarfile.TarInfo("generations/0/passwd")
                member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
                archive.addfile(member)
            elif kind == "directory":
                member = tarfile.TarInfo("generations/0/assets")
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            else:
                name = {"parent": "generations/0/../../../escaped", "absolute": "/escaped",
                        "outside": "elsewhere/0/index.html", "dot": "generations/0/./index.html"}[kind]
                member = tarfile.TarInfo(name)
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
        if hashlib.sha256(path.read_bytes()).hexdigest() < before:
            return path
    raise AssertionError("no archive digest sorted first")


@pytest.mark.parametrize("kind", ["link", "directory", "parent", "absolute", "outside", "dot"])
def test_an_unexpected_archive_member_refuses_that_bundle_and_the_next_one_is_still_published(
        tmp_path: Path, archive: Path, kind: str) -> None:
    bundles, good = install(tmp_path, archive, [PAST] * 4)
    _, bad = install(tmp_path, hostile(tmp_path, kind, good), [PAST])
    assert sorted([bad, good]) == [bad, good]
    state = tmp_path / "state"
    result = run(bundles, state)
    assert result.returncode == 1 and "unexpected archive member" in result.stderr
    assert not (state / bad / "current").exists()
    assert not list(tmp_path.rglob("escaped")) and not list(tmp_path.rglob("passwd"))
    assert "bench/cleaning-type-slugs.html" in served(state, good)


@pytest.mark.parametrize(("plan", "message"), [
    ({"version": 2, "generations": [{"n": 0, "not_before": PAST}]}, "version 1"),
    ({"version": 1, "generations": []}, "version 1"),
    ({"version": 1, "generations": [{"n": 0, "not_before": PAST}, {"n": 99, "not_before": PAST}]}, "version 1"),
    ({"version": 1, "generations": [{"n": n, "not_before": "soon"} for n in range(4)]}, "integers"),
    ({"version": 1, "generations": [{"n": n, "not_before": PAST} for n in range(9)]}, "do not match the schedule"),
])
def test_a_schedule_that_does_not_describe_the_archive_is_refused(tmp_path: Path, archive: Path, plan: dict, message: str) -> None:
    bundles, digest = install(tmp_path, archive, [PAST] * 4)
    (bundles / digest / "schedule.json").write_text(json.dumps(plan))
    result = run(bundles, tmp_path / "state")
    assert result.returncode == 1 and message in result.stderr
    assert not (tmp_path / "state" / digest / "current").exists()


def test_leftovers_of_an_interrupted_run_do_not_stay_readable(tmp_path: Path, archive: Path) -> None:
    bundles, digest = install(tmp_path, archive, [PAST, FUTURE, FUTURE, FUTURE])
    state = tmp_path / "state"
    assert run(bundles, state).returncode == 0
    for leftover in ("3", ".3.building"):
        (state / digest / "generations" / leftover).mkdir()
        (state / digest / "generations" / leftover / "platen-hardness.html").write_text("unpublished")
    assert run(bundles, state).returncode == 0
    assert [path.name for path in (state / digest / "generations").iterdir()] == ["0"]


def test_an_archive_that_does_not_match_its_directory_name_is_refused(tmp_path: Path, archive: Path) -> None:
    bundles, digest = install(tmp_path, archive, [PAST] * 4)
    with open(bundles / digest / "backlog.tar.gz", "ab") as handle:
        handle.write(b"\0" * 512)
    result = run(bundles, tmp_path / "state")
    assert result.returncode == 1 and "digest does not match" in result.stderr
    assert not (tmp_path / "state" / digest / "current").exists()


def test_publisher_unit_has_no_network_or_privilege_and_writes_only_its_state() -> None:
    unit = (REPO_ROOT / "ansible/roles/public-site/templates/public-site-publish.service.j2").read_text().splitlines()
    for line in ("User=public-site", "CapabilityBoundingSet=", "NoNewPrivileges=true", "ProtectSystem=strict",
                 "PrivateNetwork=true", "RestrictAddressFamilies=none", "UMask=0027"):
        assert line in unit
    assert [line for line in unit if line.startswith("ReadWritePaths=")] == ["ReadWritePaths=/var/lib/public-site"]
    assert not [line for line in unit if line.startswith(("Environment", "LoadCredential", "After=network"))]
    timer = (REPO_ROOT / "ansible/roles/public-site/templates/public-site-publish.timer.j2").read_text().splitlines()
    assert "Persistent=true" in timer and any(line.startswith("RandomizedDelaySec=") for line in timer)


def test_live_refresh_unit_has_the_network_but_cannot_write_the_publisher_state() -> None:
    templates = REPO_ROOT / "ansible/roles/public-site/templates"
    unit = (templates / "public-site-live@.service.j2").read_text().splitlines()
    # One instance for each bundle, named by its digest; the declaration names the page.
    assert [line for line in unit if line.startswith("ExecStart=")] == [
        ("ExecStart=/usr/bin/python3 /usr/local/libexec/public-site-live-refresh /etc/public-site/%i/live.json "
         "/var/lib/public-site/%i/current /var/lib/public-site-live/%i")]
    for line in ("User=public-site", "CapabilityBoundingSet=", "NoNewPrivileges=true", "ProtectSystem=strict",
                 "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", "UMask=0027"):
        assert line in unit
    assert [line for line in unit if line.startswith("ReadWritePaths=")] == ["ReadWritePaths=/var/lib/public-site-live"]
    assert "PrivateNetwork=true" not in unit
    assert "Unit=public-site-live@%i.service" in (templates / "public-site-live@.timer.j2").read_text().splitlines()
    # No unit text comes from a bundle: a page name cannot add a directive.
    assert "{{" not in "\n".join(unit) and "{%" not in "\n".join(unit)
