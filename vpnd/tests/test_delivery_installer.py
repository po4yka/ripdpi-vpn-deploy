"""Private-prefix release validation and transactional rollback regressions."""

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import zipfile

import pytest

from vpnd.commands.completions import render_page_set

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "delivery_installer", ROOT / "scripts/install-vpnd.py"
)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
VERSION = "1.4.2"


def wheel(name, version, requires=(), resources=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
        metadata += "".join(f"Requires-Dist: {value}\n" for value in requires)
        archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
        for path, content in (resources or {}).items():
            archive.writestr(path, content)
    return output.getvalue()


def bundle_files(**changes):
    pages = {f"vpnd/data/man/{name}.1": page for name, page in render_page_set()}
    resources = {
        "vpnd/data/recipient.html": "<p>Recipient</p>",
        "vpnd/data/docs/RUNBOOK.md": "# Packaged documentation\n",
        **pages,
    }
    resources.update(changes.get("resources", {}))
    for missing in changes.get("missing", []):
        resources.pop(missing)
    dependency = wheel("qrcode", "8.2")
    application = wheel(
        "vpnd",
        changes.get("wheel_version", VERSION),
        changes.get("requires", ["qrcode==8.2"]),
        resources,
    )
    locked_hash = changes.get("lock_hash", hashlib.sha256(dependency).hexdigest())
    return {
        f"vpnd-{VERSION}-py3-none-any.whl": application,
        "qrcode-8.2-py3-none-any.whl": dependency,
        "requirements.txt": f"qrcode=={changes.get('lock_version', '8.2')} --hash=sha256:{locked_hash}\n".encode(),
        "install.py": b"# Verified installer\n",
    }


def archive(path, files=None, target=None, entries=None, mutate_manifest=None):
    files = files if files is not None else bundle_files()
    manifest = {
        "version": VERSION,
        "target": target or installer.current_target(),
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    if mutate_manifest:
        mutate_manifest(manifest)
    members = [*files.items(), ("MANIFEST.json", json.dumps(manifest).encode())]
    members += entries or []
    with tarfile.open(path, "w:gz") as packed:
        for name, data in members:
            if isinstance(data, tarfile.TarInfo):
                packed.addfile(data)
            else:
                header = tarfile.TarInfo(name)
                header.size = len(data)
                packed.addfile(header, io.BytesIO(data))
    return path


def previous(prefix, kind="symlink"):
    binary = prefix / "bin/vpnd"
    binary.parent.mkdir(parents=True)
    old = prefix / "previous-vpnd"
    old.write_text("#!/bin/sh\nprintf 'previous usable command\\n'\n")
    old.chmod(0o755)
    if kind == "symlink":
        binary.symlink_to("../previous-vpnd")
    else:
        binary.write_bytes(old.read_bytes())
        binary.chmod(0o755)
    manuals = prefix / "share/man/man1"
    manuals.mkdir(parents=True)
    page = manuals / "vpnd.1"
    page.write_text("previous manual\n")
    page.chmod(0o640)
    return binary, page


def fake_install_processes(monkeypatch, events=None, packages=None, manual_pages=None):
    events = events if events is not None else []

    def create(_self, path):
        (path / "bin").mkdir()
        (path / "bin/python").touch()
        command = path / "bin/vpnd"
        command.write_text("#!/bin/sh\nprintf 'vpnd 1.4.2\\n'\n")
        command.chmod(0o755)

    def run(argv, **kwargs):
        events.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    def output(argv, **kwargs):
        if "-c" in argv:
            return json.dumps(
                {
                    "packages": packages or {"vpnd": VERSION, "qrcode": "8.2", "pip": "25.0.1"},
                    "pages": manual_pages
                    if manual_pages is not None
                    else {name + ".1": page for name, page in render_page_set()},
                }
            )
        return "vpnd 1.4.2\n"

    monkeypatch.setattr(installer.venv.EnvBuilder, "create", create)
    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer.subprocess, "check_output", output)
    return events


def assert_previous(binary, page, native=False):
    assert binary.is_file()
    if native:
        assert not binary.is_symlink() and stat.S_IMODE(binary.stat().st_mode) == 0o755
    else:
        assert binary.is_symlink() and os.readlink(binary) == "../previous-vpnd"
    assert "previous usable command" in binary.read_text()
    assert page.read_text() == "previous manual\n" and stat.S_IMODE(page.stat().st_mode) == 0o640


def test_valid_release_preflight_preserves_exact_inventory(tmp_path):
    artifact = archive(tmp_path / "bundle.tar.gz")
    version, files, app, locked, pages = installer.verified_bundle(artifact)
    assert version == VERSION and app == f"vpnd-{VERSION}-py3-none-any.whl"
    assert locked == {"qrcode": "8.2"}
    assert set(pages) == {name + ".1" for name, _ in render_page_set()}
    assert set(files) == set(bundle_files())


@pytest.mark.parametrize(
    "case", ["corrupt", "duplicate", "symlink", "traversal", "hash", "target", "oversized", "count"]
)
def test_bad_archives_fail_before_prefix_mutation(tmp_path, case, monkeypatch):
    prefix = tmp_path / "prefix"
    artifact = tmp_path / "bundle.tar.gz"
    if case == "corrupt":
        artifact.write_bytes(b"not gzip")
    elif case == "duplicate":
        archive(artifact, entries=[("install.py", b"duplicate")])
    elif case == "symlink":
        member = tarfile.TarInfo("link")
        member.type, member.linkname = tarfile.SYMTYPE, "/external"
        archive(artifact, entries=[("link", member)])
    elif case == "traversal":
        archive(artifact, entries=[("../escape", b"outside")])
    elif case == "hash":
        archive(
            artifact,
            mutate_manifest=lambda manifest: manifest["files"].update({"install.py": "0" * 64}),
        )
    elif case == "target":
        archive(artifact, target="wrong-platform")
    elif case == "oversized":
        archive(artifact)
        monkeypatch.setattr(installer, "MAX_MEMBER_BYTES", 10)
    else:
        archive(artifact)
        monkeypatch.setattr(installer, "MAX_MEMBERS", 1)
    with pytest.raises((ValueError, tarfile.TarError)):
        installer.install(artifact, prefix)
    assert not prefix.exists() and not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "case",
    [
        "stale-pin",
        "stale-hash",
        "app-version",
        "extra-wheel",
        "missing-template",
        "missing-docs",
        "missing-man",
    ],
)
def test_dependency_and_asset_mismatches_fail_before_mutation(tmp_path, case):
    options = {
        "stale-pin": {"lock_version": "8.1"},
        "stale-hash": {"lock_hash": "0" * 64},
        "app-version": {"wheel_version": "1.4.1"},
        "missing-template": {"missing": ["vpnd/data/recipient.html"]},
        "missing-docs": {"missing": ["vpnd/data/docs/RUNBOOK.md"]},
        "missing-man": {"missing": ["vpnd/data/man/vpnd.1"]},
    }
    files = bundle_files(**options.get(case, {}))
    if case == "extra-wheel":
        files["unexpected-1.0-py3-none-any.whl"] = wheel("unexpected", "1.0")
    prefix = tmp_path / "prefix"
    with pytest.raises(ValueError):
        installer.install(archive(tmp_path / "bundle.tar.gz", files), prefix)
    assert not prefix.exists()


@pytest.mark.parametrize("kind", ["symlink", "native"])
def test_postreplace_interrupt_restores_previous_command_and_all_manuals(
    tmp_path, monkeypatch, kind
):
    prefix = tmp_path / "prefix"
    binary, page = previous(prefix, kind)
    fake_install_processes(monkeypatch)
    original = installer.os.replace
    interrupted = False

    def replace(source, destination):
        nonlocal interrupted
        original(source, destination)
        if Path(destination) == binary and not interrupted:
            interrupted = True
            raise KeyboardInterrupt("signal delivered after completed rename")

    monkeypatch.setattr(installer.os, "replace", replace)
    with pytest.raises(KeyboardInterrupt):
        installer.install(archive(tmp_path / "bundle.tar.gz"), prefix)
    assert interrupted
    assert_previous(binary, page, kind == "native")
    assert set((prefix / "share/man/man1").iterdir()) == {page}
    assert list((prefix / "lib/vpnd/releases").iterdir()) == []
    assert not list(prefix.rglob(".vpnd-stage-*"))


def test_interrupt_during_manual_publication_restores_prior_outputs(tmp_path, monkeypatch):
    prefix = tmp_path / "prefix"
    binary, page = previous(prefix)
    fake_install_processes(monkeypatch)
    original = installer.os.replace
    interrupted = False

    def replace(source, destination):
        nonlocal interrupted
        original(source, destination)
        if Path(destination) == page and not interrupted:
            interrupted = True
            raise InterruptedError("manual publication interrupted")

    monkeypatch.setattr(installer.os, "replace", replace)
    with pytest.raises(InterruptedError):
        installer.install(archive(tmp_path / "bundle.tar.gz"), prefix)
    assert_previous(binary, page)
    assert set((prefix / "share/man/man1").iterdir()) == {page}
    assert list((prefix / "lib/vpnd/releases").iterdir()) == []


def test_failed_offline_install_and_pip_check_preserve_previous(tmp_path, monkeypatch):
    for phase in ["install", "check"]:
        prefix = tmp_path / phase
        binary, page = previous(prefix)
        fake_install_processes(monkeypatch)

        def failing(argv, **kwargs):
            if phase in argv:
                raise subprocess.CalledProcessError(7, argv)
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(installer.subprocess, "run", failing)
        with pytest.raises(subprocess.CalledProcessError):
            installer.install(archive(tmp_path / f"{phase}.tar.gz"), prefix)
        assert_previous(binary, page)
        assert not list((prefix / "lib/vpnd/releases").iterdir())


def test_installed_untracked_packages_and_stale_man_pages_refuse_promotion(tmp_path, monkeypatch):
    for phase in ["packages", "pages"]:
        prefix = tmp_path / phase
        binary, page = previous(prefix)
        packages = (
            {"vpnd": VERSION, "qrcode": "8.2", "pip": "25.0.1", "untracked": "1.0"}
            if phase == "packages"
            else None
        )
        pages = {"vpnd.1": "stale replica"} if phase == "pages" else None
        fake_install_processes(monkeypatch, packages=packages, manual_pages=pages)
        with pytest.raises(ValueError):
            installer.install(archive(tmp_path / f"{phase}.tar.gz"), prefix)
        assert_previous(binary, page)


def test_success_installs_every_parser_page_and_runs_dependency_check(tmp_path, monkeypatch):
    events = fake_install_processes(monkeypatch)
    prefix = tmp_path / "prefix"
    command = installer.install(archive(tmp_path / "bundle.tar.gz"), prefix)
    assert command.is_symlink() and command.exists()
    assert any(argv[-3:] == ["-m", "pip", "check"] for argv in events)
    for name, content in render_page_set():
        path = prefix / "share/man/man1" / (name + ".1")
        assert path.read_text() == content and stat.S_IMODE(path.stat().st_mode) == 0o644
    assert not list(prefix.rglob(".vpnd-stage-*"))


def test_root_guard_and_import_environment_are_not_bypassable(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.delenv("ALLOW_ROOT", raising=False)
    with pytest.raises(ValueError, match="refusing to run as root"):
        installer.install(tmp_path / "absent", tmp_path / "prefix")
    assert not (tmp_path / "prefix").exists()
    monkeypatch.setenv("PYTHONPATH", "/unrelated/modules")
    monkeypatch.setenv("PYTHONHOME", "/unrelated/runtime")
    monkeypatch.setenv("PIP_TARGET", "/unrelated/packages")
    environment = installer.installation_environment()
    assert (
        "PYTHONPATH" not in environment
        and "PYTHONHOME" not in environment
        and "PIP_TARGET" not in environment
    )
    assert environment["PIP_CONFIG_FILE"] == os.devnull


def test_installations_share_a_persistent_exclusive_private_lock(tmp_path):
    prefix = tmp_path / "prefix"
    with installer.installation_lock(prefix):
        path = prefix / "lib/vpnd/.install.lock"
        inode = path.stat().st_ino
        with pytest.raises(BlockingIOError):
            with installer.installation_lock(prefix):
                pytest.fail("overlapping publication lock")
    with installer.installation_lock(prefix):
        assert path.stat().st_ino == inode and stat.S_IMODE(path.stat().st_mode) == 0o600


def test_real_offline_install_uses_packaged_assets_outside_checkout(tmp_path):
    from artifact_helpers import SAMPLE, private, scaffold

    builder_spec = importlib.util.spec_from_file_location(
        "delivery_package_builder", ROOT / "scripts/build-vpnd-package.py"
    )
    builder = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(builder)
    distribution = tmp_path / "distribution"
    builder.build(distribution, installer.current_target())
    artifact = distribution / ("vpnd-" + installer.current_target() + ".tar.gz")
    prefix = tmp_path / "prefix"
    binary = installer.install(artifact, prefix)
    assert (
        subprocess.check_output(
            [str(binary), "--version"],
            text=True,
            cwd=tmp_path,
            env=installer.installation_environment(),
        ).strip()
        == "vpnd " + VERSION
    )
    for name, _ in render_page_set():
        assert (prefix / "share/man/man1" / (name + ".1")).is_file()
    runtime = scaffold(tmp_path / "isolated")
    (runtime / "Makefile").write_text("emit-singbox:\n\t@printf '%s\\n' '{\"outbounds\":[]}'\n")
    private(runtime / "runtime/vpn-test.secrets.yaml", SAMPLE)
    token = private(runtime / "token", "synthetic-Token_123")
    environment = installer.installation_environment()
    environment.update(
        XDG_RUNTIME_DIR=str(runtime / "runtime"),
        VPN_ENV="test",
        VPN_PROVIDER="upcloud",
        HOME=str(tmp_path / "isolated-home"),
    )
    output = runtime / "bundle"
    subprocess.run(
        [
            str(binary),
            "--root",
            str(runtime),
            "--env",
            "test",
            "share",
            "phone",
            "--qr",
            "--token-file",
            str(token),
            "--out",
            str(output),
        ],
        check=True,
        cwd=tmp_path,
        env=environment,
    )
    assert (output / "index.html").is_file() and "synthetic-Token_123" in (
        output / "index.html"
    ).read_text()
    for name in ["index.html", "config.singbox.json", "qr.svg", "qr-ripdpi.svg"]:
        assert stat.S_IMODE((output / name).stat().st_mode) == 0o600
    docs = tmp_path / "docs-output"
    subprocess.run(
        [str(binary), "--root", str(runtime), "ai-docs", "--out", str(docs)],
        check=True,
        cwd=tmp_path,
        env=environment,
    )
    assert (docs / "llms.txt").stat().st_size > 0 and (docs / "llms-full.txt").stat().st_size > 0
    with pytest.raises((ValueError, tarfile.TarError)):
        corrupt = tmp_path / "corrupt.tar.gz"
        corrupt.write_bytes(b"invalid")
        installer.install(corrupt, prefix)
    assert binary.exists()


def test_missing_subcommand_manual_is_rejected_before_promotion(tmp_path, monkeypatch):
    prefix = tmp_path / "prefix"
    binary, page = previous(prefix)
    fake_install_processes(monkeypatch)
    files = bundle_files(missing=["vpnd/data/man/vpnd-fleet-status.1"])
    with pytest.raises(ValueError, match="manual pages"):
        installer.install(archive(tmp_path / "bundle.tar.gz", files), prefix)
    assert_previous(binary, page)
    assert not list((prefix / "lib/vpnd/releases").iterdir())


def test_sigterm_after_actual_launcher_rename_restores_previous(tmp_path):
    prefix = tmp_path / "prefix"
    binary, page = previous(prefix)
    artifact = archive(tmp_path / "bundle.tar.gz")
    script = r"""
import importlib.util, json, os, pathlib, signal, subprocess, sys
from unittest.mock import patch
module = importlib.util.spec_from_file_location('installer', sys.argv[1])
m = importlib.util.module_from_spec(module)
module.loader.exec_module(m)
prefix = pathlib.Path(sys.argv[3])
from vpnd.commands.completions import render_page_set
signal.signal(signal.SIGTERM, m.terminate_installation)
def create(_self, candidate):
    (candidate / 'bin').mkdir()
    (candidate / 'bin/python').touch()
    (candidate / 'bin/vpnd').write_text('verified candidate')
def output(argv, **kwargs):
    if '-c' in argv:
        return json.dumps({'packages': {'vpnd': '1.4.2', 'qrcode': '8.2', 'pip': '25.0.1'}, 'pages': {name+'.1': page for name,page in render_page_set()}})
    return 'vpnd 1.4.2\n'
original = os.replace
interrupted = False
def replace(source, target):
    global interrupted
    original(source, target)
    if pathlib.Path(target) == prefix / 'bin/vpnd' and not interrupted:
        interrupted = True
        os.kill(os.getpid(), signal.SIGTERM)
with patch.object(m.venv.EnvBuilder, 'create', create), patch.object(m.subprocess, 'run', return_value=None), patch.object(m.subprocess, 'check_output', output), patch.object(m.os, 'replace', replace):
    try:
        m.install(sys.argv[2], prefix)
    except m.InstallationInterrupted:
        sys.exit(143)
raise AssertionError('expected an actual SIGTERM interruption')
"""
    output = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(ROOT / "scripts/install-vpnd.py"),
            str(artifact),
            str(prefix),
        ],
        env={**os.environ, "PYTHONPATH": str(ROOT / "vpnd/src")},
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert output.returncode == 143, output.stderr
    assert_previous(binary, page)
    assert set((prefix / "share/man/man1").iterdir()) == {page}
    assert not list((prefix / "lib/vpnd/releases").iterdir())
