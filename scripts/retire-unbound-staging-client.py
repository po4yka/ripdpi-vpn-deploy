#!/usr/bin/env python3
"""Retire one unbound issued staging client after exact provider absence.

This recovery-only command never contacts a provider or host.  It consumes an
already verified cleanup result and mutates only the exact SOPS ciphertext.
Diagnostics are categorical so client names, paths and secret values never
reach stdout or stderr.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
from typing import Any, Callable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import disposable_liveness_executor as executor  # noqa: E402
import disposable_promotion as promotion  # noqa: E402

MAX_INPUT = 256 * 1024
MAX_STATE = 64 * 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
Failpoint = Callable[[str], None]
Runner = Callable[..., bytes]


class RetirementError(ValueError):
    """Categorical refusal safe for operator output."""


class _UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguity at every mapping depth."""


def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    value = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in value
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                None, None, "invalid mapping key", key_node.start_mark
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                None, None, "duplicate mapping key", key_node.start_mark
            )
        value[key] = loader.construct_object(value_node, deep=deep)
    return value


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _guard():
    spec = importlib.util.spec_from_file_location(
        "retirement_staging_cleanup_guard", ROOT / "scripts/staging-cleanup-guard.py"
    )
    if spec is None or spec.loader is None:
        raise RetirementError("retirement-component")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RetirementError("retirement-component") from exc
    return module


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_bytes(path: Path, label: str, limit: int) -> tuple[bytes, tuple[int, int]]:
    try:
        return _guard()._private_snapshot(
            path.absolute(), label, max_bytes=limit, exact_parent_mode=True
        )
    except Exception as exc:
        raise RetirementError("retirement-input") from exc


def _read_json(
    path: Path, label: str, limit: int = MAX_INPUT
) -> tuple[dict[str, Any], bytes]:
    payload, _ = _read_bytes(path, label, limit)
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RetirementError("retirement-input") from exc
    if not isinstance(value, dict) or _canonical(value) != payload:
        raise RetirementError("retirement-input")
    return value, payload


def _parent_fd(path: Path, label: str) -> tuple[int, str]:
    try:
        return _guard()._open_private_parent(path.absolute(), label)
    except Exception as exc:
        raise RetirementError("retirement-input") from exc


def _absent(path: Path) -> bool:
    parent, name = _parent_fd(path, "retirement artifact")
    try:
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return True
        except OSError as exc:
            raise RetirementError("retirement-bound") from exc
        return False
    finally:
        os.close(parent)


def _exact_write(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise RetirementError("retirement-write")
        view = view[written:]


def _unlink_exact(
    parent: int, name: str, identity: tuple[int, int], category: str
) -> None:
    try:
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RetirementError(category) from exc
    try:
        if (current.st_dev, current.st_ino) != identity:
            raise RetirementError(category)
        _guard()._unlink_matching_entry(parent, name, current, category)
    except RetirementError:
        raise
    except Exception as exc:
        raise RetirementError(category) from exc


def _write_new(path: Path, payload: bytes, category: str) -> tuple[int, int]:
    parent, name = _parent_fd(path, category)
    fd = -1
    identity: tuple[int, int] | None = None
    try:
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
        except OSError as exc:
            raise RetirementError(category) from exc
        try:
            opened = os.fstat(fd)
            identity = (opened.st_dev, opened.st_ino)
            os.fchmod(fd, 0o600)
            _exact_write(fd, payload)
            os.fsync(fd)
        except BaseException as exc:
            try:
                if identity is not None:
                    _unlink_exact(parent, name, identity, category)
            except RetirementError as cleanup:
                raise RetirementError(category) from cleanup
            if isinstance(exc, RetirementError):
                raise
            if isinstance(exc, OSError):
                raise RetirementError(category) from exc
            raise
        os.fsync(parent)
        return identity
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent)


def _atomic_replace(path: Path, expected: bytes, payload: bytes, category: str) -> None:
    parent, name = _parent_fd(path, category)
    temporary = f".{name}.replace-{secrets.token_hex(16)}"
    temp_fd = -1
    temp_identity: tuple[int, int] | None = None
    current_fd = -1
    try:
        try:
            current_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            opened = os.fstat(current_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
            ):
                raise RetirementError(category)
            actual = os.read(current_fd, len(expected) + 1)
            if actual != expected:
                raise RetirementError(category)
            temp_fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            temp_info = os.fstat(temp_fd)
            temp_identity = (temp_info.st_dev, temp_info.st_ino)
            os.fchmod(temp_fd, 0o600)
            _exact_write(temp_fd, payload)
            os.fsync(temp_fd)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise RetirementError(category)
            os.lseek(current_fd, 0, os.SEEK_SET)
            if os.read(current_fd, len(expected) + 1) != expected:
                raise RetirementError(category)
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        except RetirementError:
            raise
        except OSError as exc:
            raise RetirementError(category) from exc
    finally:
        if current_fd >= 0:
            os.close(current_fd)
        if temp_fd >= 0:
            os.close(temp_fd)
        try:
            if temp_identity is not None:
                _unlink_exact(parent, temporary, temp_identity, category)
        finally:
            os.close(parent)


def _replace_document(
    path: Path, expected: dict[str, Any], value: dict[str, Any], category: str
) -> None:
    _atomic_replace(path, _canonical(expected), _canonical(value), category)


def lock_paths(sops_file: Path, client: str) -> tuple[Path, Path]:
    digest = hashlib.sha256(client.encode("ascii")).hexdigest()[:24]
    return (
        # All supported SOPS writers use this project lock.  Retirement also
        # keeps its narrower client lock so two recovery attempts for the same
        # identity cannot race their journals after another project edit.
        sops_file.with_name(sops_file.name + ".new-client.lock"),
        sops_file.with_name(sops_file.name + f".retire-unbound.{digest}.lock"),
    )


@contextmanager
def _locks(paths: tuple[Path, Path]):
    descriptors: list[int] = []
    try:
        for path in sorted(paths, key=str):
            parent, name = _parent_fd(path, "retirement lock")
            try:
                fd = os.open(
                    name,
                    os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600,
                    dir_fd=parent,
                )
                os.fchmod(fd, 0o600)
            except OSError as exc:
                raise RetirementError("retirement-lock") from exc
            finally:
                os.close(parent)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                ):
                    raise RetirementError("retirement-lock")
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RetirementError("retirement-busy") from None
            except BaseException:
                os.close(fd)
                raise
            descriptors.append(fd)
        yield
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _validate_absence(
    absence: dict[str, Any], manifest: dict[str, Any], manifest_payload: bytes
) -> None:
    fields = {
        "schema_version",
        "status",
        "deadline_status",
        "provider",
        "environment",
        "provider_account_username",
        "manifest_sha256",
        "apply_started_at",
        "expiry_at",
        "observed_at",
        "server_uuid",
        "root_storage_uuid",
        "server_status",
        "root_storage_status",
        "billing_status",
    }
    guard = _guard()
    try:
        created = guard._parse_time(manifest.get("created_at"), "created_at")
        applied = guard._parse_time(absence.get("apply_started_at"), "apply_started_at")
        expiry = guard._parse_time(absence.get("expiry_at"), "expiry_at")
        observed = guard._parse_time(absence.get("observed_at"), "observed_at")
    except Exception as exc:
        raise RetirementError("retirement-absence") from exc
    expired = observed >= expiry
    if (
        set(absence) != fields
        or absence.get("schema_version") != 2
        or absence.get("status") not in {"verified", "verified_after_expiry"}
        or absence.get("deadline_status")
        not in {"within_deadline", "expired_after_apply"}
        or absence.get("provider") != manifest.get("provider")
        or absence.get("environment") != manifest.get("environment")
        or absence.get("provider_account_username")
        != manifest.get("provider_account_username")
        or absence.get("manifest_sha256") != _sha(manifest_payload)
        or absence.get("expiry_at") != manifest.get("expiry_at")
        or absence.get("server_uuid") != manifest.get("server_uuid")
        or absence.get("root_storage_uuid") != manifest.get("root_storage_uuid")
        or absence.get("server_status") != "absent"
        or absence.get("root_storage_status") != "absent"
        or absence.get("billing_status") != "no-active-owned-resources"
        or applied < created
        or applied >= expiry
        or observed < applied
        or absence.get("status") != ("verified_after_expiry" if expired else "verified")
        or absence.get("deadline_status")
        != ("expired_after_apply" if expired else "within_deadline")
    ):
        raise RetirementError("retirement-absence")


def _validate_inputs(
    paths: Mapping[str, Path],
) -> tuple[dict[str, Any], dict[str, Any]]:
    intent, intent_payload = _read_json(paths["intent_path"], "staging intent")
    try:
        promotion.validate_intent(intent)
    except Exception as exc:
        raise RetirementError("retirement-intent") from exc
    manifest, manifest_payload = _read_json(
        paths["cleanup_manifest_path"], "cleanup manifest"
    )
    guard = _guard()
    try:
        guard._validate_manifest_shape(
            manifest,
            now=guard._parse_time(manifest["created_at"], "created_at"),
            allow_expired=True,
        )
    except Exception as exc:
        raise RetirementError("retirement-target") from exc
    absence, absence_payload = _read_json(
        paths["absence_evidence_path"], "provider absence"
    )
    _validate_absence(absence, manifest, manifest_payload)
    if (
        intent.get("host") != f"{manifest['provider']}:{manifest['environment']}"
        or intent.get("target_identity", {}).get("inventory_alias")
        != manifest["hostname"]
        or intent.get("inputs", {}).get("cleanup_manifest")
        != str(paths["cleanup_manifest_path"])
        or intent.get("inputs", {}).get("sops_file") != str(paths["sops_file"])
        or manifest.get("state", {}).get("path") != str(paths["state_path"])
    ):
        raise RetirementError("retirement-target")
    state_payload, _ = _read_bytes(paths["state_path"], "destroyed state", MAX_STATE)
    if _sha(state_payload) != manifest["state"]["sha256"]:
        raise RetirementError("retirement-state")
    try:
        state = json.loads(state_payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RetirementError("retirement-state") from exc
    if (
        not isinstance(state, dict)
        or state.get("version") != 4
        or state.get("resources") != []
        or state.get("outputs") not in (None, {})
    ):
        raise RetirementError("retirement-state")
    for output in intent["outputs"].values():
        if not _absent(Path(output)):
            raise RetirementError("retirement-bound")
    pending = Path(intent["outputs"]["registry"] + ".pending.json")
    if not _absent(pending):
        raise RetirementError("retirement-bound")
    request = {
        "schema_version": 1,
        "intent_sha256": _sha(intent_payload),
        "cleanup_manifest_sha256": _sha(manifest_payload),
        "absence_evidence_sha256": _sha(absence_payload),
        "state_sha256": _sha(state_payload),
        "client_sha256": _sha(intent["client"].encode("ascii")),
        "target_sha256": _sha(
            _canonical(
                {
                    "provider": manifest["provider"],
                    "environment": manifest["environment"],
                    "hostname": manifest["hostname"],
                    "server_uuid": manifest["server_uuid"],
                    "root_storage_uuid": manifest["root_storage_uuid"],
                }
            )
        ),
    }
    return intent, request


def _xray_cohort_references(
    document: dict[str, Any], client: str
) -> list[tuple[int, int]]:
    """Validate the complete Xray client graph and locate one client's edges."""
    xray = document.get("xray")
    clients = xray.get("clients") if isinstance(xray, dict) else None
    if not isinstance(clients, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("name"), str)
        for item in clients
    ):
        raise RetirementError("retirement-secrets")
    names = [item["name"] for item in clients]
    if len(names) != len(set(names)):
        raise RetirementError("retirement-secrets")
    cohorts = xray.get("cohorts", [])
    if not isinstance(cohorts, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("name"), str)
        for item in cohorts
    ):
        raise RetirementError("retirement-secrets")
    cohort_names = [item["name"] for item in cohorts]
    if len(cohort_names) != len(set(cohort_names)):
        raise RetirementError("retirement-secrets")
    references: list[tuple[int, int]] = []
    known = set(names)
    for cohort_index, cohort in enumerate(cohorts):
        values = cohort.get("clients", [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise RetirementError("retirement-secrets")
        if len(values) != len(set(values)) or any(
            value not in known for value in values
        ):
            raise RetirementError("retirement-secrets")
        references.extend(
            (cohort_index, index)
            for index, value in enumerate(values)
            if value == client
        )
    return references


def _secret_plan(
    document: Any, client: str, host: str
) -> tuple[list[str], dict[str, Any]]:
    if not isinstance(document, dict):
        raise RetirementError("retirement-secrets")

    def collection(root: str, field: str) -> tuple[list[Any], int]:
        parent = document.get(root)
        values = parent.get(field) if isinstance(parent, dict) else None
        if not isinstance(values, list) or any(
            not isinstance(item, dict) for item in values
        ):
            raise RetirementError("retirement-secrets")
        matches = [
            index for index, item in enumerate(values) if item.get("name") == client
        ]
        if len(matches) != 1:
            raise RetirementError("retirement-secrets")
        return values, matches[0]

    xray, xray_index = collection("xray", "clients")
    cohort_references = _xray_cohort_references(document, client)
    hysteria, hysteria_index = collection("hysteria", "clients")
    awg, awg_index = collection("amneziawg_secrets", "peers")
    registry = document.get("client_registry")
    entry = registry.get(client) if isinstance(registry, dict) else None
    if (
        not isinstance(entry, dict)
        or entry.get("status") != "issued"
        or entry.get("hosts") != [host]
    ):
        raise RetirementError("retirement-secrets")
    variants_parent = document.get("snell_secrets")
    variants = (
        variants_parent.get("variants") if isinstance(variants_parent, dict) else None
    )
    if not isinstance(variants, list) or any(
        not isinstance(item, dict) for item in variants
    ):
        raise RetirementError("retirement-secrets")
    snell: list[tuple[int, int]] = []
    for variant_index, variant in enumerate(variants):
        users = variant.get("users")
        if not isinstance(users, list) or any(
            not isinstance(item, dict) for item in users
        ):
            raise RetirementError("retirement-secrets")
        matches = [
            index for index, item in enumerate(users) if item.get("name") == client
        ]
        if len(matches) != 1:
            raise RetirementError("retirement-secrets")
        snell.append((variant_index, matches[0]))

    paths = [
        f'["xray"]["cohorts"][{cohort}]["clients"][{reference}]'
        for cohort, reference in reversed(cohort_references)
    ]
    paths.extend(
        [
            f'["xray"]["clients"][{xray_index}]',
            f'["hysteria"]["clients"][{hysteria_index}]',
            f'["amneziawg_secrets"]["peers"][{awg_index}]',
        ]
    )
    paths.extend(
        f'["snell_secrets"]["variants"][{variant}]["users"][{user}]'
        for variant, user in reversed(snell)
    )
    paths.append(f'["client_registry"][{json.dumps(client)}]')
    expected = copy.deepcopy(document)
    for cohort, reference in reversed(cohort_references):
        expected["xray"]["cohorts"][cohort]["clients"].pop(reference)
    expected["xray"]["clients"].pop(xray_index)
    expected["hysteria"]["clients"].pop(hysteria_index)
    expected["amneziawg_secrets"]["peers"].pop(awg_index)
    for variant, user in reversed(snell):
        expected["snell_secrets"]["variants"][variant]["users"].pop(user)
    expected["client_registry"].pop(client)
    if _xray_cohort_references(expected, client):
        raise RetirementError("retirement-secrets")
    return paths, expected


def _decrypt(path: Path, runner: Runner) -> dict[str, Any]:
    try:
        payload = runner(
            ("sops", "--decrypt", "--output-type", "yaml", str(path)), timeout=30
        )
        if len(payload) > MAX_INPUT:
            raise RetirementError("retirement-secrets")
        value = yaml.load(payload, Loader=_UniqueSafeLoader)
    except RetirementError:
        raise
    except Exception as exc:
        raise RetirementError("retirement-secrets") from exc
    if not isinstance(value, dict):
        raise RetirementError("retirement-secrets")
    return value


def _request(paths: Mapping[str, Path]) -> dict[str, Any]:
    _intent, request = _validate_inputs(paths)
    ciphertext, _ = _read_bytes(paths["sops_file"], "SOPS ciphertext", MAX_INPUT)
    return {**request, "ciphertext_before_sha256": _sha(ciphertext)}


def _journal(
    state: str, request: dict[str, Any], candidate: dict[str, Any] | None = None
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "state": state,
        "request": request,
        "request_sha256": _sha(_canonical(request)),
    }
    if candidate is not None:
        value["candidate"] = candidate
    return value


def _validate_journal(value: dict[str, Any], request: dict[str, Any]) -> None:
    state = value.get("state")
    expected = {"schema_version", "state", "request", "request_sha256"}
    if state in {"candidate", "published", "verified"}:
        expected.add("candidate")
    if (
        set(value) != expected
        or value.get("schema_version") != 1
        or state not in {"prepared", "candidate", "published", "verified"}
        or value.get("request") != request
        or value.get("request_sha256") != _sha(_canonical(request))
    ):
        raise RetirementError("retirement-journal")
    if state != "prepared":
        candidate = value.get("candidate")
        if (
            not isinstance(candidate, dict)
            or set(candidate) != {"name", "sha256", "device", "inode"}
            or not isinstance(candidate.get("name"), str)
            or "/" in candidate["name"]
            or not HEX64.fullmatch(str(candidate.get("sha256", "")))
            or type(candidate.get("device")) is not int
            or type(candidate.get("inode")) is not int
            or candidate["inode"] <= 0
        ):
            raise RetirementError("retirement-journal")


def _candidate_pattern(sops_file: Path) -> re.Pattern[str]:
    suffix = sops_file.suffix or ".yaml"
    return re.compile(
        rf"\.{re.escape(sops_file.name)}\.retire-[0-9a-f]{{32}}{re.escape(suffix)}\Z"
    )


def _candidate_names(sops_file: Path) -> set[str]:
    parent, _name = _parent_fd(sops_file, "SOPS ciphertext")
    pattern = _candidate_pattern(sops_file)
    try:
        try:
            return {entry for entry in os.listdir(parent) if pattern.fullmatch(entry)}
        except OSError as exc:
            raise RetirementError("retirement-candidate") from exc
    finally:
        os.close(parent)


def _refuse_replace_namespace(path: Path, category: str) -> None:
    parent, name = _parent_fd(path, category)
    pattern = re.compile(rf"\.{re.escape(name)}\.replace-[0-9a-f]{{32}}\Z")
    try:
        try:
            if any(pattern.fullmatch(entry) for entry in os.listdir(parent)):
                raise RetirementError(category)
        except RetirementError:
            raise
        except OSError as exc:
            raise RetirementError(category) from exc
    finally:
        os.close(parent)


def _create_candidate(
    sops_file: Path,
    before: bytes,
    paths: list[str],
    expected: dict[str, Any],
    runner: Runner,
) -> tuple[dict[str, Any], Path]:
    parent, name = _parent_fd(sops_file, "SOPS ciphertext")
    candidate_name = (
        f".{name}.retire-{secrets.token_hex(16)}{sops_file.suffix or '.yaml'}"
    )
    candidate_path = sops_file.with_name(candidate_name)
    fd = -1
    initial_identity: tuple[int, int] | None = None
    complete = False
    try:
        fd = os.open(
            candidate_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        opened = os.fstat(fd)
        initial_identity = (opened.st_dev, opened.st_ino)
        os.fchmod(fd, 0o600)
        _exact_write(fd, before)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        for path in paths:
            runner(
                ("sops", "unset", "--idempotent", str(candidate_path), path), timeout=30
            )
        candidate_bytes, identity = _read_bytes(
            candidate_path, "SOPS candidate", MAX_INPUT
        )
        if _decrypt(candidate_path, runner) != expected:
            raise RetirementError("retirement-secrets")
        complete = True
        return {
            "name": candidate_name,
            "sha256": _sha(candidate_bytes),
            "device": identity[0],
            "inode": identity[1],
        }, candidate_path
    except RetirementError:
        raise
    except Exception as exc:
        raise RetirementError("retirement-secrets") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if not complete:
            try:
                if initial_identity is not None:
                    _unlink_exact(
                        parent,
                        candidate_name,
                        initial_identity,
                        "retirement-candidate",
                    )
            except RetirementError:
                raise
        os.close(parent)


def _publish_candidate(
    sops_file: Path, before: bytes, candidate: dict[str, Any]
) -> None:
    parent, target = _parent_fd(sops_file, "SOPS ciphertext")
    current_fd = candidate_fd = -1
    try:
        try:
            current_fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            current = os.fstat(current_fd)
            current_bytes = os.read(current_fd, len(before) + 1)
            if (
                current_bytes != before
                or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid()
                or stat.S_IMODE(current.st_mode) != 0o600
                or current.st_nlink != 1
            ):
                raise RetirementError("retirement-ciphertext")
            candidate_fd = os.open(
                candidate["name"], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent
            )
            staged = os.fstat(candidate_fd)
            staged_bytes = os.read(candidate_fd, MAX_INPUT + 1)
            if (
                (staged.st_dev, staged.st_ino)
                != (candidate["device"], candidate["inode"])
                or not stat.S_ISREG(staged.st_mode)
                or staged.st_uid != os.getuid()
                or stat.S_IMODE(staged.st_mode) != 0o600
                or staged.st_nlink != 1
                or _sha(staged_bytes) != candidate["sha256"]
            ):
                raise RetirementError("retirement-candidate")
            target_now = os.stat(target, dir_fd=parent, follow_symlinks=False)
            staged_now = os.stat(
                candidate["name"], dir_fd=parent, follow_symlinks=False
            )
            if (target_now.st_dev, target_now.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise RetirementError("retirement-ciphertext")
            if (staged_now.st_dev, staged_now.st_ino) != (staged.st_dev, staged.st_ino):
                raise RetirementError("retirement-candidate")
            os.replace(candidate["name"], target, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        except RetirementError:
            raise
        except OSError as exc:
            raise RetirementError("retirement-ciphertext") from exc
    finally:
        if current_fd >= 0:
            os.close(current_fd)
        if candidate_fd >= 0:
            os.close(candidate_fd)
        os.close(parent)


def _candidate_state(
    sops_file: Path, before_digest: str, candidate: dict[str, Any]
) -> str:
    candidates = _candidate_names(sops_file)
    if not _candidate_pattern(sops_file).fullmatch(candidate["name"]):
        raise RetirementError("retirement-candidate")
    current, identity = _read_bytes(sops_file, "SOPS ciphertext", MAX_INPUT)
    digest = _sha(current)
    if digest == before_digest:
        if candidates != {candidate["name"]}:
            raise RetirementError("retirement-candidate")
        candidate_path = sops_file.with_name(candidate["name"])
        staged, staged_identity = _read_bytes(
            candidate_path, "SOPS candidate", MAX_INPUT
        )
        if _sha(staged) != candidate["sha256"] or staged_identity != (
            candidate["device"],
            candidate["inode"],
        ):
            raise RetirementError("retirement-candidate")
        return "before"
    if digest == candidate["sha256"] and identity == (
        candidate["device"],
        candidate["inode"],
    ):
        if candidates:
            raise RetirementError("retirement-candidate")
        return "after"
    raise RetirementError("retirement-ciphertext")


def _receipt(request: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "retired",
        "request_sha256": _sha(_canonical(request)),
        "client_sha256": request["client_sha256"],
        "target_sha256": request["target_sha256"],
        "ciphertext_before_sha256": request["ciphertext_before_sha256"],
        "ciphertext_after_sha256": candidate["sha256"],
    }


def _read_optional(path: Path, category: str) -> tuple[dict[str, Any], bytes] | None:
    if _absent(path):
        return None
    try:
        return _read_json(path, category)
    except RetirementError as exc:
        raise RetirementError(category) from exc


def retire(
    *,
    intent_path: Path,
    cleanup_manifest_path: Path,
    absence_evidence_path: Path,
    state_path: Path,
    sops_file: Path,
    journal_path: Path,
    receipt_path: Path,
    runner: Runner,
    failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    paths = {
        "intent_path": intent_path.absolute(),
        "cleanup_manifest_path": cleanup_manifest_path.absolute(),
        "absence_evidence_path": absence_evidence_path.absolute(),
        "state_path": state_path.absolute(),
        "sops_file": sops_file.absolute(),
        "journal_path": journal_path.absolute(),
        "receipt_path": receipt_path.absolute(),
    }
    if len(set(paths.values())) != len(paths):
        raise RetirementError("retirement-input")
    intent, request_base = _validate_inputs(paths)
    client = intent["client"]
    if not NAME.fullmatch(client):
        raise RetirementError("retirement-intent")
    callback = failpoint or (lambda _phase: None)
    with _locks(lock_paths(paths["sops_file"], client)):
        # Inputs and all forbidden artifacts are revalidated under the same
        # lock that serializes every authorized writer of this SOPS project.
        intent, locked_base = _validate_inputs(paths)
        if locked_base != request_base or intent["client"] != client:
            raise RetirementError("retirement-input")
        _refuse_replace_namespace(paths["journal_path"], "retirement-journal")
        journal_item = _read_optional(paths["journal_path"], "retirement-journal")
        receipt_item = _read_optional(paths["receipt_path"], "retirement-receipt")
        current, _ = _read_bytes(paths["sops_file"], "SOPS ciphertext", MAX_INPUT)

        if journal_item is None:
            if receipt_item is not None:
                raise RetirementError("retirement-receipt")
            if _candidate_names(paths["sops_file"]):
                raise RetirementError("retirement-candidate")
            document = _decrypt(paths["sops_file"], runner)
            secret_paths, expected = _secret_plan(document, client, intent["host"])
            request = {**request_base, "ciphertext_before_sha256": _sha(current)}
            journal = _journal("prepared", request)
            _write_new(paths["journal_path"], _canonical(journal), "retirement-journal")
            callback("after-prepared")
        else:
            journal, _journal_payload = journal_item
            request = journal.get("request")
            if not isinstance(request, dict):
                raise RetirementError("retirement-journal")
            if {key: request.get(key) for key in request_base} != request_base:
                raise RetirementError("retirement-journal")
            _validate_journal(journal, request)
            secret_paths = []
            expected = {}

        before_digest = request["ciphertext_before_sha256"]
        state = journal["state"]
        if state in {"prepared", "candidate"} and receipt_item is not None:
            # A terminal receipt cannot precede publication.  Refuse it before
            # candidate creation or ciphertext replacement, even if it happens
            # to contain otherwise well-formed JSON.
            raise RetirementError("retirement-receipt")
        if state in {"published", "verified"}:
            terminal_candidate = journal.get("candidate")
            if not isinstance(terminal_candidate, dict):
                raise RetirementError("retirement-journal")
            expected_receipt = _receipt(request, terminal_candidate)
            if receipt_item is not None and (
                receipt_item[0] != expected_receipt
                or receipt_item[1] != _canonical(expected_receipt)
            ):
                raise RetirementError("retirement-receipt")
            if state == "verified" and receipt_item is None:
                raise RetirementError("retirement-receipt")
        if state == "prepared":
            if _candidate_names(paths["sops_file"]):
                raise RetirementError("retirement-candidate")
            if _sha(current) != before_digest:
                raise RetirementError("retirement-ciphertext")
            document = _decrypt(paths["sops_file"], runner)
            secret_paths, expected = _secret_plan(document, client, intent["host"])
            candidate, _candidate_path = _create_candidate(
                paths["sops_file"], current, secret_paths, expected, runner
            )
            next_journal = _journal("candidate", request, candidate)
            _replace_document(
                paths["journal_path"], journal, next_journal, "retirement-journal"
            )
            journal = next_journal
            state = "candidate"
            callback("after-candidate")

        candidate = journal.get("candidate")
        if not isinstance(candidate, dict):
            raise RetirementError("retirement-journal")
        _validate_journal(journal, request)
        candidate_location = _candidate_state(
            paths["sops_file"], before_digest, candidate
        )
        if state == "candidate":
            if candidate_location == "before":
                callback("before-publish")
                _publish_candidate(paths["sops_file"], current, candidate)
            next_journal = _journal("published", request, candidate)
            _replace_document(
                paths["journal_path"], journal, next_journal, "retirement-journal"
            )
            journal = next_journal
            state = "published"
            callback("after-publish")
        elif candidate_location != "after":
            raise RetirementError("retirement-ciphertext")

        final_document = _decrypt(paths["sops_file"], runner)
        try:
            remaining = executor._client_secret_paths(final_document, client)
        except Exception as exc:
            raise RetirementError("retirement-secrets") from exc
        if remaining or _xray_cohort_references(final_document, client):
            raise RetirementError("retirement-secrets")
        current_after, _ = _read_bytes(paths["sops_file"], "SOPS ciphertext", MAX_INPUT)
        if _sha(current_after) != candidate["sha256"]:
            raise RetirementError("retirement-ciphertext")
        terminal = _receipt(request, candidate)
        if receipt_item is None:
            _write_new(
                paths["receipt_path"], _canonical(terminal), "retirement-receipt"
            )
            callback("after-receipt")
        elif receipt_item[0] != terminal or receipt_item[1] != _canonical(terminal):
            raise RetirementError("retirement-receipt")
        if state == "published":
            next_journal = _journal("verified", request, candidate)
            _replace_document(
                paths["journal_path"], journal, next_journal, "retirement-journal"
            )
            changed = True
        elif state == "verified":
            changed = False
        else:
            raise RetirementError("retirement-journal")
        return {**terminal, "changed": changed}


def _run_command(
    argv: tuple[str, ...],
    *,
    timeout: int = 30,
    input_bytes: bytes = b"",
    environment=None,
) -> bytes:
    clean = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "SOPS_AGE_KEY_FILE", "SOPS_AGE_KEY_CMD"}
    }
    clean.update(LANG="C", LC_ALL="C")
    try:
        result = subprocess.run(
            argv,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=clean,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RetirementError("retirement-command") from exc
    if result.returncode != 0 or len(result.stdout) > MAX_INPUT:
        raise RetirementError("retirement-command")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--cleanup-manifest", required=True, type=Path)
    parser.add_argument("--absence-evidence", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--sops-file", required=True, type=Path)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = retire(
            intent_path=args.intent,
            cleanup_manifest_path=args.cleanup_manifest,
            absence_evidence_path=args.absence_evidence,
            state_path=args.state,
            sops_file=args.sops_file,
            journal_path=args.journal,
            receipt_path=args.receipt,
            runner=_run_command,
        )
        print(
            json.dumps(
                {
                    "changed": result["changed"],
                    "schema_version": result["schema_version"],
                    "status": result["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except RetirementError as exc:
        print(f"retire-unbound-staging-client: {exc}", file=sys.stderr)
        return 1
    except Exception:
        # CLI diagnostics stay categorical even if a local dependency violates
        # its contract; paths, command output and decrypted values remain hidden.
        print("retire-unbound-staging-client: retirement-internal", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
