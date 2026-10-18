"""Exercise source admission in synthetic Git trees, without claiming AWG traffic."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "ansible/roles/amneziawg/files/awg_source_correction.py"
RECEIPTS = ROOT / "ansible/roles/runtime-release/files/runtime_build_receipt.py"
PREIMAGE = b"package tun\n\n// Synthetic source-admission fixture; no runtime implementation.\nnoneChecksum = ^noneSum\nsplitChecksum = ^splitSum\n"
REPLACEMENTS = [
    {"before": "noneChecksum = ^noneSum\n", "after": "noneChecksum = ^noneSum\nif noneChecksum == 0 { noneChecksum = 0xffff }\n"},
    {"before": "splitChecksum = ^splitSum\n", "after": "splitChecksum = ^splitSum\nif splitChecksum == 0 { splitChecksum = 0xffff }\n"},
]
POSTIMAGE = PREIMAGE
for _replacement in REPLACEMENTS:
    POSTIMAGE = POSTIMAGE.replace(_replacement["before"].encode(), _replacement["after"].encode())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module_at(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(source, *arguments):
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_DATE="2000-01-01T00:00:00Z", GIT_COMMITTER_DATE="2000-01-01T00:00:00Z")
    return subprocess.run(["git", "-C", str(source), *arguments], env=environment,
                          capture_output=True, check=True, timeout=10).stdout.decode().strip()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    path.chmod(0o600)


@pytest.fixture
def correction(tmp_path):
    temporary = tmp_path.resolve()
    source, assets = temporary / "source", temporary / "assets"
    (source / "tun").mkdir(parents=True)
    assets.mkdir()
    shutil.copyfile(HELPER, assets / HELPER.name)
    (assets / HELPER.name).chmod(0o600)
    (source / "tun/offload_linux.go").write_bytes(PREIMAGE)
    (source / "README").write_text("Synthetic source admission only.\n")
    (source / "version.go").write_text("package main\n// original fixture version\n")
    (source / ".gitignore").write_text("ignored.go\n")
    (source / ".gitattributes").write_text("* filter=fixture\n")
    git(source, "init", "--object-format=sha1", "-b", "fixture")
    git(source, "config", "user.name", "Source admission fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    git(source, "config", "commit.gpgsign", "false")
    git(source, "config", "core.hooksPath", os.devnull)
    git(source, "add", ".")
    git(source, "commit", "-m", "Synthetic source admission fixture")
    commit, tree = git(source, "rev-parse", "HEAD"), git(source, "rev-parse", "HEAD^{tree}")
    patch = {"schema": 1, "path": "tun/offload_linux.go", "replacements": REPLACEMENTS}
    write_json(assets / "awg-udp-checksum-zero.patch.json", patch)
    manifest = {"schema": 1, "name": "udp-zero-fixture", "patch_sha256": sha((assets / "awg-udp-checksum-zero.patch.json").read_bytes()),
                "commits": {commit: {"profile": "upstream", "tree": tree,
                                      "preimage_sha256": sha(PREIMAGE), "postimage_sha256": sha(POSTIMAGE),
                                      "generated_version_sha256": []}}}
    write_json(assets / "awg-source-correction.json", manifest)
    helper = module_at(assets / HELPER.name, "synthetic_awg_source_correction")
    helper.ASSETS = assets
    return helper, source, commit, assets, manifest


def snapshot(source):
    result = {}
    for directory, dirs, files in os.walk(source, followlinks=False):
        relative = Path(directory).relative_to(source)
        if relative == Path("."):
            dirs[:] = [name for name in dirs if name != ".git"]
        for name in files:
            path = Path(directory) / name
            result[str(path.relative_to(source))] = ("link", os.readlink(path)) if path.is_symlink() else ("file", path.read_bytes(), path.stat().st_mode)
    result[".git/index"] = (source / ".git/index").read_bytes()
    result["HEAD"] = git(source, "rev-parse", "HEAD")
    return result


def refused_without_mutation(helper, source, commit):
    before = snapshot(source)
    with pytest.raises((ValueError, OSError)):
        helper.apply(source, commit)
    assert snapshot(source) == before
    assert not list((source / "tun").glob(".awg-correction-*"))


def test_exact_preimage_applies_once_then_verifies_without_index_or_head_change(correction):
    helper, source, commit, _assets, _manifest = correction
    index = (source / ".git/index").read_bytes()
    identity = helper.describe(commit)
    assert helper.apply(source, commit) == {**identity, "changed": True}
    assert (source / helper.TARGET).read_bytes() == POSTIMAGE
    assert helper.verify(source, commit) == {**identity, "changed": False}
    assert helper.apply(source, commit) == {**identity, "changed": False}
    assert (source / ".git/index").read_bytes() == index
    assert git(source, "rev-parse", "HEAD") == commit
    assert not list((source / "tun").glob(".awg-correction-*"))


def test_verify_requires_correction_without_writing(correction):
    helper, source, commit, _assets, _manifest = correction
    before = snapshot(source)
    with pytest.raises(ValueError, match="correction-required"):
        helper.verify(source, commit)
    assert snapshot(source) == before


@pytest.mark.parametrize("failure", ["head", "tree", "index", "tracked", "target", "missing", "untracked", "ignored", "directory", "mode"])
def test_unadmitted_source_refuses_without_mutation(correction, failure):
    helper, source, commit, assets, manifest = correction
    if failure == "head":
        git(source, "commit", "--allow-empty", "-m", "different fixture commit")
    elif failure == "tree":
        manifest["commits"][commit]["tree"] = "0" * 40
        write_json(assets / helper.MANIFEST, manifest)
    elif failure == "index":
        (source / "README").write_text("staged fixture change\n")
        git(source, "add", "README")
    elif failure == "tracked":
        (source / "README").write_text("unstaged fixture change\n")
    elif failure == "target":
        (source / helper.TARGET).write_bytes(PREIMAGE + b"unreviewed bytes\n")
    elif failure == "missing":
        (source / "README").unlink()
    elif failure in ("untracked", "ignored"):
        (source / ("ignored.go" if failure == "ignored" else "untracked.go")).write_text("package main\n")
    elif failure == "directory":
        (source / "unexpected-directory").mkdir()
    else:
        (source / "README").chmod(0o755)
    refused_without_mutation(helper, source, commit)


@pytest.mark.parametrize("entry", ["target", "other-source", "manifest", "patch", "helper"])
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "writable"])
def test_untrusted_file_authority_refuses_without_source_mutation(correction, tmp_path, entry, kind):
    helper, source, commit, assets, _manifest = correction
    path = {"target": source / helper.TARGET, "other-source": source / "README",
            "manifest": assets / helper.MANIFEST, "patch": assets / helper.PATCH,
            "helper": assets / HELPER.name}[entry]
    if kind == "writable":
        path.chmod(0o666)
    else:
        outside = tmp_path / "outside"
        path.rename(outside)
        if kind == "symlink":
            path.symlink_to(outside)
        else:
            os.link(outside, path)
    refused_without_mutation(helper, source, commit)


@pytest.mark.parametrize("location", ["source", "assets", "tracked-parent", "git-metadata"])
def test_writable_directory_authority_refuses(correction, location):
    helper, source, commit, assets, _manifest = correction
    directory = {"source": source, "assets": assets, "tracked-parent": source / "tun", "git-metadata": source / ".git"}[location]
    directory.chmod(0o777)
    refused_without_mutation(helper, source, commit)


@pytest.mark.parametrize("location", ["source", "assets"])
def test_symlink_ancestor_is_not_hidden_by_resolution(correction, tmp_path, location):
    helper, source, commit, assets, _manifest = correction
    alias = tmp_path / "alias"
    alias.symlink_to(source.parent, target_is_directory=True)
    if location == "source":
        source = alias / source.name
    else:
        helper.ASSETS = alias / assets.name
    refused_without_mutation(helper, source, commit)


def test_unknown_commit_and_changed_patch_digest_refuse(correction):
    helper, source, commit, assets, _manifest = correction
    refused_without_mutation(helper, source, "f" * 40)
    patch = assets / helper.PATCH
    patch.write_bytes(patch.read_bytes() + b" ")
    refused_without_mutation(helper, source, commit)


@pytest.mark.parametrize("asset", ["helper", "manifest", "patch"])
def test_every_reviewed_asset_contributes_to_qualification_identity(correction, asset):
    helper, _source, commit, assets, manifest = correction
    before = helper.describe(commit)
    if asset == "helper":
        path = assets / HELPER.name
        path.write_bytes(path.read_bytes() + b"\n# fixture qualification change\n")
    elif asset == "manifest":
        manifest["name"] = "udp-zero-fixture-next"
        write_json(assets / helper.MANIFEST, manifest)
    else:
        path = assets / helper.PATCH
        path.write_bytes(path.read_bytes() + b"\n")
        manifest["patch_sha256"] = sha(path.read_bytes())
        write_json(assets / helper.MANIFEST, manifest)
    after = helper.describe(commit)
    assert after["digest"] != before["digest"]
    assert after["profile"] == before["profile"]


@pytest.mark.parametrize("driver", ["clean", "process"])
def test_filters_and_inherited_git_redirection_cannot_execute_or_change_authority(correction, tmp_path, monkeypatch, driver):
    helper, source, commit, _assets, _manifest = correction
    marker = tmp_path / "filter-executed"
    program = tmp_path / "filter.py"
    program.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n")
    git(source, "config", "filter.fixture." + driver, "python3 " + str(program))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing-git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "missing-tree"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "missing-index"))
    result = helper.apply(source, commit)
    assert result["changed"] is True
    assert helper.verify(source, commit)["changed"] is False
    assert not marker.exists()
    assert not (tmp_path / "missing-index").exists()


def test_atomic_publication_failure_leaves_preimage_and_cleans_only_owned_temporary(correction, monkeypatch):
    helper, source, commit, _assets, _manifest = correction
    before = snapshot(source)
    def refuse_replace(*_args, **_kwargs):
        raise OSError("owned fixture publication failure")
    monkeypatch.setattr(helper.os, "replace", refuse_replace)
    with pytest.raises(OSError, match="owned fixture publication failure"):
        helper.apply(source, commit)
    assert snapshot(source) == before
    assert not list((source / "tun").glob(".awg-correction-*"))


def test_git_admission_has_bounded_deadline_and_clean_environment(correction, monkeypatch):
    helper, source, commit, _assets, _manifest = correction
    original = subprocess.run
    observed = []
    def bounded(argv, **kwargs):
        assert kwargs["timeout"] == 20
        assert kwargs["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert "GIT_INDEX_FILE" not in kwargs["env"]
        observed.append(argv)
        return original(argv, **kwargs)
    monkeypatch.setattr(helper.subprocess, "run", bounded)
    helper.apply(source, commit)
    assert observed


def test_runtime_receipt_rebuilds_when_correction_identity_changes(correction):
    cache = ROOT / ".cache/awg-source-candidate"
    cache.mkdir(parents=True, mode=0o700, exist_ok=True)
    # The real receipt helper refuses writable system temp ancestry.
    with tempfile.TemporaryDirectory(prefix="receipt-regression-", dir=cache) as temporary:
        tmp_path = Path(temporary)
        helper, _source, commit, assets, manifest = correction
        receipt = module_at(RECEIPTS, "awg_correction_build_receipt")
        root = tmp_path.resolve() / "runtime-build-receipts"
        stage = tmp_path.resolve() / "runtime-build-staging"
        root.mkdir(mode=0o700)
        stage.mkdir(mode=0o700)
        output = tmp_path.resolve() / "release" / "amneziawg-go"
        output.parent.mkdir(mode=0o700)
        output.write_bytes(b"synthetic executable; no runtime claim\n")
        output.chmod(0o755)
        document = {"schema_version": 1, "name": "amneziawg-go", "source": {"commit": commit},
                    "steps": [{"argv": ["/usr/bin/true"], "chdir": str(output.parent), "environment": {}, "timeout_seconds": 1}],
                    "outputs": [{"name": "installed", "staged_path": str(stage / "amneziawg-go" / "amneziawg-go"), "path": str(output)}]}
        descriptor = receipt._normalize_descriptor(document, stage_root=stage)
        (root / "amneziawg-go.json").write_text(json.dumps(receipt._receipt_payload(descriptor)))
        assert receipt.inspect(root, document)["rebuild_required"] is False
        document["source"]["patches"] = helper.describe(commit)
        assert receipt.inspect(root, document)["reason"] == "inputs-changed"
        descriptor = receipt._normalize_descriptor(document, stage_root=stage)
        (root / "amneziawg-go.json").write_text(json.dumps(receipt._receipt_payload(descriptor)))
        assert receipt.inspect(root, document)["rebuild_required"] is False
        manifest["name"] += "-next"
        write_json(assets / helper.MANIFEST, manifest)
        document["source"]["patches"] = helper.describe(commit)
        assert receipt.inspect(root, document)["reason"] == "inputs-changed"


@pytest.mark.parametrize("matches", [False, True])
def test_cli_identity_pin_is_checked_before_mutation(correction, matches):
    helper, source, commit, assets, _manifest = correction
    before = snapshot(source)
    digest = helper.describe(commit)["digest"] if matches else "0" * 64
    result = subprocess.run([sys.executable, str(assets / HELPER.name), "apply", "--commit", commit,
                             "--source", str(source), "--identity-digest", digest],
                            capture_output=True, text=True, timeout=10)
    if matches:
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["changed"] is True
        assert (source / helper.TARGET).read_bytes() == POSTIMAGE
    else:
        assert result.returncode == 1
        assert result.stdout == ""
        assert "awg-source-correction:identity-digest" in result.stderr
        assert snapshot(source) == before


def test_blocked_git_metadata_cannot_escape_its_deadline(correction, monkeypatch):
    helper, source, commit, _assets, _manifest = correction
    index = source / ".git/index"
    index.unlink()
    os.mkfifo(index, 0o600)
    original = subprocess.run
    def bounded(argv, **kwargs):
        assert kwargs["timeout"] == 20
        kwargs["timeout"] = 0.2
        return original(argv, **kwargs)
    monkeypatch.setattr(helper.subprocess, "run", bounded)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        helper.apply(source, commit)
    assert time.monotonic() - started < 3
    assert (source / helper.TARGET).read_bytes() == PREIMAGE
    assert not list((source / "tun").glob(".awg-correction-*"))


@pytest.mark.parametrize("admitted", [False, True])
def test_only_manifest_admitted_generated_version_bytes_are_allowed(correction, admitted):
    helper, source, commit, assets, manifest = correction
    generated = b"package main\n// exact synthetic generated version\n"
    (source / "version.go").write_bytes(generated)
    if admitted:
        manifest["commits"][commit]["generated_version_sha256"] = [sha(generated)]
        write_json(assets / helper.MANIFEST, manifest)
        assert helper.apply(source, commit)["changed"] is True
        assert helper.verify(source, commit)["changed"] is False
    else:
        refused_without_mutation(helper, source, commit)
