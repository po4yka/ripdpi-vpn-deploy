#!/usr/bin/env python3
"""Local private intent assembly; no credential reads or external operations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys

from disposable_promotion import KIND, OUTPUTS, validate_intent

LIMIT = 32768
INPUT_ENV = {
    "sops_file": "PROMOTION_SOPS_FILE",
    "age_key_file": "PROMOTION_AGE_KEY_FILE",
    "awg_key_file": "PROMOTION_AWG_KEY_FILE",
    "executor_manifest": "PROMOTION_EXECUTOR_MANIFEST",
    "cleanup_manifest": "PROMOTION_CLEANUP_MANIFEST",
}


class PreparationError(ValueError):
    """Categorical diagnostics only."""


def _path(value):
    if not isinstance(value, str) or not value:
        raise PreparationError("intent-input-refused")
    path = Path(value)
    if (not path.is_absolute() or str(path) != value or ".." in path.parts
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise PreparationError("intent-input-refused")
    return path


def _directory(path):
    """Walk canonical ancestors by descriptor, preserving a private leaf."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (info.st_uid not in (0, os.getuid())
                    or (info.st_mode & 0o022 and not sticky_root)):
                raise PreparationError("intent-private-path-refused")
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise PreparationError("intent-private-path-refused")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PreparationError("intent-input-refused")
        value[key] = item
    return value


def _constant(_value):
    raise PreparationError("intent-input-refused")


def _bound_directory(path, expected):
    current = _directory(path)
    try:
        before, after = os.fstat(expected), os.fstat(current)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise PreparationError("intent-directory-changed")
    finally:
        os.close(current)


def _configuration(path):
    parent = _directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_size > LIMIT):
                raise PreparationError("intent-private-input-refused")
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise PreparationError("intent-input-refused")
        return json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
    finally:
        os.close(parent)


def _publish(directory, name, value):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write((json.dumps(value, sort_keys=True) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def prepare(environment):
    publishing = False
    try:
        def field(name):
            return environment[name + "_LITERAL"]

        config_path = _path(field("PROMOTION_LIVENESS_CONFIG"))
        output = _path(field("PROMOTION_OUTPUT_DIR"))
        inputs = {key: str(_path(field(name))) for key, name in INPUT_ENV.items()}
        if str(config_path) in inputs.values():
            raise PreparationError("intent-input-alias-refused")
        config = _configuration(config_path)
        target = config["sentinels"][0]["target"]
        awg = config["sentinels"][0]["awg_target"]
        outputs = {key: str(output / (key + ".json")) for key in OUTPUTS}
        intent_path = output / "intent.json"
        mapping_path = output / "deployment-inputs.json"
        reserved = {str(config_path), *inputs.values(), *outputs.values()}
        if str(intent_path) in reserved or str(mapping_path) in reserved:
            raise PreparationError("intent-path-alias-refused")
        intent = validate_intent({
            "schema_version": 1, "kind": KIND, "target_identity": target,
            "host": awg["provider"] + ":" + awg["environment"],
            "cohort": "device-full-staging", "client": field("PROMOTION_CLIENT"),
            "liveness": config, "inputs": inputs, "outputs": outputs,
        })
        directory = _directory(output)
        try:
            if os.listdir(directory):
                raise PreparationError("intent-output-not-empty")
            for name, value in (
                ("intent.json", intent),
                ("deployment-inputs.json", {target["inventory_alias"]: str(intent_path)}),
            ):
                _bound_directory(output, directory)
                publishing = True
                _publish(directory, name, value)
                _bound_directory(output, directory)
            os.fsync(directory)
            if set(os.listdir(directory)) != {"intent.json", "deployment-inputs.json"}:
                raise PreparationError("intent-output-changed")
            _bound_directory(output, directory)
        finally:
            os.close(directory)
        return {"status": "promotion-intent-prepared"}
    except PreparationError:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError, RecursionError):
        message = "intent-preparation-incomplete" if publishing else "intent-preparation-refused"
        raise PreparationError(message) from None


def main():
    if sys.argv[1:] == ["--help"]:
        print(__doc__ + "\nInvoke make prepare-disposable-promotion-intent with documented environment inputs.")
        return 0
    try:
        if sys.argv[1:]:
            raise PreparationError("intent-arguments-refused")
        print(json.dumps(prepare(os.environ), sort_keys=True))
        return 0
    except PreparationError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
