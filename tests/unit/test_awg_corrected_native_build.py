"""Native receipt admission over real Git; the synthetic profile proves no TUN."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORRECTION = ROOT / "ansible/roles/amneziawg/files"


@pytest.fixture
def native_source(tmp_path):
    fixture = tmp_path / "fixture"
    script = (ROOT / "ansible/roles/amneziawg/molecule/default/files/prepare-sources.sh").read_text()
    script = script.replace("fixture=/opt/molecule-awg-fixture", "fixture=" + shlex.quote(str(fixture)))
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_DEFAULT_HASH"] = "sha1"
    subprocess.run(["sh", "-c", script], check=True, capture_output=True, env=environment, timeout=30)
    source = fixture / "amneziawg-go"
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    assert commit == "c477e2aa7b49a02381861e8ce41170e9c1f615eb"
    spec = importlib.util.spec_from_file_location(
        "native_corrected_build", ROOT / "tests/integration/awg_source_candidate/corrected_build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, source, commit


def executable(source):
    # Real executable bytes exercise content identity only. They are never run
    # as AWG, and the explicit synthetic-no-tun profile cannot qualify native TUN.
    output = source / "amneziawg-go"
    shutil.copyfile(sys.executable, output)
    output.chmod(0o755)
    return output


def publish(native_source):
    module, source, commit = native_source
    module.prepare(source, commit, CORRECTION)
    executable(source)
    receipt = module.publish(source, commit, CORRECTION)
    return module, source, commit, receipt


def test_native_receipt_binds_correction_and_actual_executable_bytes(native_source):
    module, source, commit, receipt = publish(native_source)
    assert receipt["correction"]["profile"] == "synthetic-no-tun"
    assert receipt["commit"] == commit
    assert receipt["binary_sha256"] == hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    assert os.readlink(source / "amneziawg-go") == ".ripdpi-build/" + receipt["correction"]["digest"] + "/amneziawg-go"
    assert module.verify(source, commit, CORRECTION) == receipt


def test_warm_build_requires_verified_alias_and_fresh_output(native_source):
    module, source, commit, receipt = publish(native_source)
    artifact = (source / "amneziawg-go").resolve()
    module.prepare(source, commit, CORRECTION)
    assert not os.path.lexists(source / "amneziawg-go") and artifact.is_file()
    executable(source)
    assert module.publish(source, commit, CORRECTION) == receipt


@pytest.mark.parametrize("tamper", ["commit", "correction", "binary", "alias", "assume-unchanged-source"])
def test_stale_native_build_identity_refuses(native_source, tmp_path, tamper):
    module, source, commit, receipt = publish(native_source)
    artifact = (source / "amneziawg-go").resolve()
    record = artifact.parent / "receipt.json"
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"unrelated fixture bytes")
    if tamper == "commit":
        receipt["commit"] = "0" * 40
        record.write_text(json.dumps(receipt))
    elif tamper == "correction":
        receipt["correction"]["digest"] = "0" * 64
        record.write_text(json.dumps(receipt))
    elif tamper == "binary":
        artifact.write_bytes(artifact.read_bytes() + b"changed")
    elif tamper == "alias":
        (source / "amneziawg-go").unlink()
        (source / "amneziawg-go").symlink_to(foreign)
    else:
        subprocess.run(["git", "-C", str(source), "update-index", "--assume-unchanged", "fixture-go"], check=True)
        (source / "fixture-go").write_text("changed source\n")
    with pytest.raises((ValueError, OSError)):
        module.verify(source, commit, CORRECTION)
    assert foreign.read_bytes() == b"unrelated fixture bytes"


def test_prepare_preserves_foreign_output_alias(native_source, tmp_path):
    module, source, commit = native_source
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"unrelated fixture bytes")
    (source / "amneziawg-go").symlink_to(foreign)
    with pytest.raises(ValueError):
        module.prepare(source, commit, CORRECTION)
    assert (source / "amneziawg-go").is_symlink()
    assert foreign.read_bytes() == b"unrelated fixture bytes"


def test_old_unqualified_output_is_never_reused(native_source):
    module, source, commit = native_source
    output = executable(source)
    module.prepare(source, commit, CORRECTION)
    assert not os.path.lexists(output)
    assert not (source / ".ripdpi-build").exists()


def test_immutable_native_artifact_cannot_be_overwritten(native_source):
    module, source, commit, _receipt = publish(native_source)
    artifact = (source / "amneziawg-go").resolve()
    (source / "amneziawg-go").unlink()
    artifact.write_bytes(b"retained mismatched artifact")
    executable(source)
    with pytest.raises(ValueError, match="immutable-build-output-mismatch"):
        module.publish(source, commit, CORRECTION)
    assert artifact.read_bytes() == b"retained mismatched artifact"
