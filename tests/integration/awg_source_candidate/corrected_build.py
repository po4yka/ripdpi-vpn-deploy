"""Bind native AWG build outputs to the production source correction."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def correction(directory):
    spec = importlib.util.spec_from_file_location(
        "native_awg_source_correction", Path(directory) / "awg_source_correction.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity(value):
    return {key: item for key, item in value.items() if key != "changed"}


def owned_regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or info.st_mode & 0o022):
        raise ValueError("native-AWG-build-output-authority-refused")
    return path.read_bytes()


def location(source, selected):
    return Path(source) / ".ripdpi-build" / selected["digest"]


def verify(source, commit, correction_directory):
    source = Path(source)
    selected = identity(correction(correction_directory).verify(source, commit))
    target = location(source, selected)
    for directory in (target.parent, target):
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise ValueError("native-AWG-build-directory-authority-refused")
    binary = owned_regular(target / "amneziawg-go")
    expected = {"schema": 1, "commit": commit, "correction": selected,
                "binary_sha256": hashlib.sha256(binary).hexdigest()}
    receipt = json.loads(owned_regular(target / "receipt.json"))
    alias = source / "amneziawg-go"
    if receipt != expected or not alias.is_symlink() or os.readlink(alias) != str(target.relative_to(source) / "amneziawg-go"):
        raise ValueError("native-AWG-build-receipt-mismatch")
    return receipt


def prepare(source, commit, correction_directory):
    source = Path(source)
    selected = identity(correction(correction_directory).apply(source, commit))
    output = source / "amneziawg-go"
    if output.is_symlink():
        verify(source, commit, correction_directory)
        output.unlink()
    elif os.path.lexists(output):
        owned_regular(output)
        output.unlink()
    return selected


def test_checksums(source, commit, correction_directory, *, env=None):
    source = Path(source).resolve(strict=True)
    helper = correction(correction_directory)
    selected = identity(helper.verify(source, commit))
    if selected["profile"] != "upstream":
        raise ValueError("native-AWG-checksum-test-requires-upstream-source")
    regression = Path(correction_directory).resolve(strict=True) / "awg_checksum_regression_test.go"
    owned_regular(regression)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="awg-checksum-overlay-", suffix=".json") as overlay:
        json.dump({"Replace": {str(source / "tun/awg_checksum_regression_test.go"): str(regression)}}, overlay)
        overlay.flush()
        subprocess.run(
            ["go", "test", "-overlay", overlay.name, "-run", "^TestChecksumZeroReview(None|Split)$",
             "-count=1", "-p=2", "-timeout=120s", "./tun"],
            cwd=source, env=env, check=True, timeout=150,
        )
    helper.verify(source, commit)
    return {"correction": selected, "checksums": "passed"}


def publish(source, commit, correction_directory):
    source = Path(source)
    selected = identity(correction(correction_directory).verify(source, commit))
    output = source / "amneziawg-go"
    binary = owned_regular(output)
    target = location(source, selected)
    for directory in (target.parent, target):
        directory.mkdir(mode=0o755, exist_ok=True)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise ValueError("native-AWG-build-directory-authority-refused")
    artifact = target / "amneziawg-go"
    receipt = {"schema": 1, "commit": commit, "correction": selected,
               "binary_sha256": hashlib.sha256(binary).hexdigest()}
    if os.path.lexists(artifact):
        if owned_regular(artifact) != binary:
            raise ValueError("native-AWG-immutable-build-output-mismatch")
    else:
        with artifact.open("xb") as handle:
            handle.write(binary)
        artifact.chmod(0o755)
    record = target / "receipt.json"
    if os.path.lexists(record):
        if json.loads(owned_regular(record)) != receipt:
            raise ValueError("native-AWG-build-receipt-mismatch")
    else:
        with record.open("x") as handle:
            json.dump(receipt, handle, sort_keys=True)
            handle.write("\n")
        record.chmod(0o644)
    output.unlink()
    output.symlink_to(artifact.relative_to(source))
    return verify(source, commit, correction_directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = {"prepare": prepare, "publish": publish, "verify": verify, "test-checksums": test_checksums}
    parser.add_argument("action", choices=tuple(actions))
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--correction-directory", required=True, type=Path)
    args = parser.parse_args()
    result = actions[args.action](args.source, args.commit, args.correction_directory)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
