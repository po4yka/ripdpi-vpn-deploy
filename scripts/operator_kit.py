"""Verify explicitly selected catalog authority and encrypted B2 recovery copies."""
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import tarfile

from operator_private import MAX_BYTES, checked, decode, environment, fields, read_owned, require, resolve_pointer, sha256
from operator_release import member_name
from private_client_artifact import new_output


def pointer(value, path):
    value = resolve_pointer(value, path)
    require(isinstance(value, str), "invalid-catalog-reference")
    return value


def selected(plan):
    fields(plan, ("schema_version", "catalog", "observed_at", "max_age_seconds", "entries"), ("backup",))
    observed = dt.datetime.fromisoformat(plan["observed_at"].replace("Z", "+00:00"))
    age = (dt.datetime.now(dt.timezone.utc) - observed).total_seconds()
    require(observed.tzinfo is not None and type(plan["max_age_seconds"]) is int
            and 0 < plan["max_age_seconds"] <= 604800 and 0 <= age <= plan["max_age_seconds"], "stale-kit-plan")
    catalog_path = Path(plan["catalog"])
    catalog_raw, catalog_identity = read_owned(catalog_path, limit=16 * 1024 * 1024, with_identity=True)
    catalog = decode(catalog_raw)
    authorities = {str(catalog_path): catalog_identity}
    entries = plan["entries"]
    require(isinstance(entries, list) and 1 <= len(entries) <= 10000, "kit-entry-limit")
    files, identities = {}, set()
    total = 0
    for entry in entries:
        fields(entry, ("name", "pointer", "sha256", "kind"))
        name = member_name(entry["name"])
        require(name != "manifest.json" and name not in files and
                entry["kind"] in ("configuration", "secrets", "state", "receipt", "source"), "invalid-kit-entry")
        raw_path = pointer(catalog, entry["pointer"])
        path = Path(raw_path)
        if not path.is_absolute():
            path = catalog_path.parent / path
        data, stamp = read_owned(path, with_identity=True)
        authorities[str(path)] = stamp
        total += len(data)
        require(total <= MAX_BYTES - 8 * 1024 * 1024, "kit-size-limit")
        require(sha256(data) == entry["sha256"], "kit-file-mismatch")
        info = path.stat()
        identity = (info.st_dev, info.st_ino)
        require(identity not in identities, "duplicate-kit-authority")
        identities.add(identity)
        files[name] = data
    if "backup" in plan:
        backup = plan["backup"]
        fields(backup, ("ciphertext", "recipient"),
               ("identity", "sha256", "bucket", "object", "rclone", "rclone_sha256"))
        # An alias or hard link must not include working credentials or output.
        for field in ("identity", "ciphertext"):
            if field in backup and os.path.lexists(backup[field]):
                info = Path(backup[field]).stat()
                require((info.st_dev, info.st_ino) not in identities, "excluded-kit-authority")
        require(all(not data.startswith(b"AGE-SECRET-KEY-") and b"-----BEGIN OPENSSH PRIVATE KEY-----" not in data
                    and b"AGE-SECRET-KEY-" not in data for data in files.values()), "plaintext-working-key-in-kit")
    return files, authorities


def manifest(files):
    return {name: {"sha256": sha256(data), "size": len(data)} for name, data in files.items()}


def check(plan):
    files, authorities = selected(plan)
    require(selected(plan) == (files, authorities), "kit-changed")
    return {"result": "selected-local-kit-verified", "files_verified": len(files),
            "live_host_health_verified": False}


def seal(plan):
    files, authorities = selected(plan)
    backup = plan["backup"]
    checked(["age", "-a", "-r", backup["recipient"]], data=b"recipient admission", limit=65536)
    with new_output(backup["ciphertext"]) as (write, validate):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as archive:
            for name, data in {**files, "manifest.json": json.dumps(manifest(files), sort_keys=True).encode()}.items():
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o600
                archive.addfile(info, io.BytesIO(data))
        require(len(payload.getbuffer()) <= MAX_BYTES, "kit-archive-limit")
        ciphertext = checked(["age", "-a", "-r", backup["recipient"]], data=payload.getvalue(),
                             timeout=120, limit=MAX_BYTES * 2)
        require(selected(plan) == (files, authorities), "kit-changed")
        validate()
        write(ciphertext.decode("ascii"))
    return {"result": "selected-kit-sealed", "files_sealed": len(files),
            "ciphertext_sha256": sha256(ciphertext), "offsite_verified": False}


def verify_payload(payload, files):
    require(len(payload) <= MAX_BYTES, "kit-archive-limit")
    contents = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for count, row in enumerate(archive, 1):
            require(count <= 10001, "kit-member-limit")
            member_name(row.name)
            require(row.isfile() and row.name not in contents and
                    row.name in {*files, "manifest.json"}, "invalid-kit-member")
            require(0 <= row.size <= MAX_BYTES, "kit-member-size")
            total += row.size
            require(total <= MAX_BYTES, "kit-archive-limit")
            stream = archive.extractfile(row)
            require(stream is not None, "missing-kit-member")
            data = stream.read(row.size + 1)
            require(len(data) == row.size, "truncated-kit-member")
            contents[row.name] = data
    require(set(contents) == {*files, "manifest.json"}, "kit-manifest-coverage")
    expected = manifest(files)
    require(decode(contents.pop("manifest.json")) == expected and
            manifest(contents) == expected, "kit-manifest-mismatch")


def verify_backup(plan):
    files, authorities = selected(plan)
    backup = plan["backup"]
    require({"identity", "sha256", "bucket", "object", "rclone", "rclone_sha256"} <= backup.keys(),
            "incomplete-backup-plan")
    require(re.fullmatch(r"[a-z0-9-]{6,63}", backup["bucket"]) and
            member_name(backup["object"]), "invalid-backup-object")
    executable = Path(backup["rclone"])
    require(executable.is_absolute(), "absolute-rclone-path-required")
    binary, binary_identity = read_owned(executable, private=False, limit=128 * 1024 * 1024, with_identity=True)
    executable = executable.resolve(strict=True)
    require(os.access(executable, os.X_OK), "rclone-not-executable")
    require(sha256(binary) == backup["rclone_sha256"], "rclone-checksum-mismatch")
    local = read_owned(backup["ciphertext"], limit=MAX_BYTES * 2)
    require(sha256(local) == backup["sha256"], "backup-ciphertext-mismatch")
    key = read_owned(backup["identity"], limit=65536)
    remote = ":b2:" + backup["bucket"] + "/" + backup["object"]
    require(read_owned(executable, private=False, limit=128 * 1024 * 1024, with_identity=True)
            == (binary, binary_identity), "rclone-changed")
    ciphertext = checked([str(executable), "cat", remote, "--config", "/dev/null",
                          "--retries", "1", "--low-level-retries", "1", "--timeout", "60s"],
                         timeout=360, limit=MAX_BYTES * 2,
                         env=environment(("RCLONE_B2_ACCOUNT", "RCLONE_B2_KEY")))
    require(sha256(ciphertext) == backup["sha256"], "downloaded-ciphertext-mismatch")
    require(read_owned(backup["identity"], limit=65536) == key, "identity-changed")
    payload = checked(["age", "--decrypt", "-i", backup["identity"]], data=ciphertext,
                      timeout=120, limit=MAX_BYTES)
    verify_payload(payload, files)
    require(selected(plan) == (files, authorities)
            and read_owned(backup["identity"], limit=65536) == key
            and read_owned(executable, private=False, limit=128 * 1024 * 1024, with_identity=True) == (binary, binary_identity)
            and read_owned(backup["ciphertext"], limit=MAX_BYTES * 2) == local,
            "kit-changed")
    return {"result": "downloaded-kit-manifest-verified", "files_verified": len(files),
            "ciphertext_sha256": sha256(ciphertext), "bucket_policy_verified": False,
            "live_host_health_verified": False}
