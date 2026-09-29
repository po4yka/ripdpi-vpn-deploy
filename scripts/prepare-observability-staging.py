#!/usr/bin/env python3
"""Prepare private inputs for disposable observability staging acceptance.

This tool is deliberately local-only.  It creates operator SSH and age keys,
short-lived observability PKI, SOPS ciphertext, and fail-closed acceptance
scaffolding.  It never contacts a provider or Telegram API and never prints a
credential, private path, certificate, endpoint, or command output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "MON-1790650904289505"
CHANGE = "staging-observability-telegram-acceptance"
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
DNS_NAME = re.compile(
    r"^(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
REVISION = re.compile(r"^[0-9a-f]{40,64}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
AGE_RECIPIENT = re.compile(r"^age1[0-9a-z]{50,90}$")
MAX_INPUT = 1 << 20

STEPS = (
    "fresh-metrics",
    "ingestion-negative",
    "agent-wal",
    "staleness",
    "grouping-inhibition",
    "finite-silence",
    "primary-lifecycle",
    "deadman-lifecycle",
    "control-service-loss",
    "control-host-loss",
    "deadman-service-loss",
    "primary-authority-loss",
    "canary-sender-rotation",
    "primary-bot-rotation",
    "secondary-bot-rotation",
    "old-material-rejection",
    "invalid-candidate-refusal",
    "valid-candidate-activation",
    "control-plane-rollback",
    "component-removal",
)
STEP_TARGETS = {
    "fresh-metrics": "control-plane",
    "ingestion-negative": "canary-to-control-plane",
    "agent-wal": "canary-to-control-plane",
    "staleness": "canary-to-control-plane",
    "grouping-inhibition": "primary-route",
    "finite-silence": "primary-route",
    "primary-lifecycle": "primary-route",
    "deadman-lifecycle": "secondary-route",
    "control-service-loss": "control-plane",
    "control-host-loss": "control-plane-host",
    "deadman-service-loss": "deadman",
    "primary-authority-loss": "primary-route",
    "canary-sender-rotation": "canary",
    "primary-bot-rotation": "primary-route",
    "secondary-bot-rotation": "secondary-route",
    "old-material-rejection": "primary-and-secondary-route",
    "invalid-candidate-refusal": "control-plane",
    "valid-candidate-activation": "control-plane",
    "control-plane-rollback": "control-plane",
    "component-removal": "staging-components",
}
STEP_RESTORES = {
    "fresh-metrics": "none",
    "ingestion-negative": "none",
    "agent-wal": "start-control-plane-ingress",
    "staleness": "restore-canary-producer-and-sender",
    "grouping-inhibition": "resolve-staging-matrix-alerts",
    "finite-silence": "expire-delete-staging-silence",
    "primary-lifecycle": "resolve-critical-drill",
    "deadman-lifecycle": "restore-control-plane-pulses",
    "control-service-loss": "start-control-plane-services",
    "control-host-loss": "power-on-control-plane-host",
    "deadman-service-loss": "start-deadman-service",
    "primary-authority-loss": "activate-primary-replacement",
    "canary-sender-rotation": "restore-canary-generation",
    "primary-bot-rotation": "restore-control-plane-generation",
    "secondary-bot-rotation": "restore-deadman-generation",
    "old-material-rejection": "none",
    "invalid-candidate-refusal": "preserve-current-control-plane-generation",
    "valid-candidate-activation": "restore-prior-control-plane-generation",
    "control-plane-rollback": "restore-prior-control-plane-generation",
    "component-removal": "retain-provider-resources",
}
STEP_DEADLINES = {
    "fresh-metrics": 130,
    "ingestion-negative": 120,
    "agent-wal": 600,
    "staleness": 1800,
    "grouping-inhibition": 300,
    "finite-silence": 300,
    "primary-lifecycle": 4800,
    "deadman-lifecycle": 4800,
    "control-service-loss": 1200,
    "control-host-loss": 1800,
    "deadman-service-loss": 1200,
    "primary-authority-loss": 1500,
    "canary-sender-rotation": 600,
    "primary-bot-rotation": 600,
    "secondary-bot-rotation": 600,
    "old-material-rejection": 60,
    "invalid-candidate-refusal": 600,
    "valid-candidate-activation": 600,
    "control-plane-rollback": 600,
    "component-removal": 900,
}
OBSERVATION_STEPS = (
    "primary-lifecycle",
    "deadman-lifecycle",
    "control-service-loss",
    "control-host-loss",
    "deadman-service-loss",
    "primary-authority-loss",
)


class PreparationError(Exception):
    """A categorical, non-sensitive preparation failure."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _absolute_parts(path: Path, category: str) -> tuple[Path, tuple[str, ...]]:
    if not path.is_absolute() or any(
        part in ("", ".", "..") for part in path.parts[1:]
    ):
        raise PreparationError(category)
    absolute = path.absolute()
    return absolute, tuple(absolute.parts[1:])


def _validate_directory(
    metadata: os.stat_result, category: str, *, private: bool
) -> None:
    mode = stat.S_IMODE(metadata.st_mode)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid not in (0, os.getuid()):
        raise PreparationError(category)
    if mode & 0o022 and not mode & stat.S_ISVTX:
        raise PreparationError(category)
    if private and (metadata.st_uid != os.getuid() or mode != 0o700):
        raise PreparationError(category)


def _open_secure_directory(path: Path, category: str, *, private: bool) -> int:
    _absolute, parts = _absolute_parts(path, category)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open("/", flags)
        _validate_directory(
            os.fstat(descriptor), category, private=private and not parts
        )
        for index, part in enumerate(parts):
            child = os.open(part, flags, dir_fd=descriptor)
            try:
                _validate_directory(
                    os.fstat(child),
                    category,
                    private=private and index == len(parts) - 1,
                )
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except PreparationError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise PreparationError(category) from None


def _checked_private_directory(path: Path, category: str) -> Path:
    absolute, _parts = _absolute_parts(path, category)
    descriptor = _open_secure_directory(absolute, category, private=True)
    os.close(descriptor)
    return absolute


def _private_target(path: Path, category: str) -> tuple[Path, int, str]:
    absolute, parts = _absolute_parts(path, category)
    if not parts:
        raise PreparationError(category)
    parent = _open_secure_directory(absolute.parent, category, private=True)
    return absolute, parent, parts[-1]


def _open_private_at(directory: int, name: str, category: str) -> int:
    if not name or "/" in name or name in (".", ".."):
        raise PreparationError(category)
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_size > MAX_INPUT
        ):
            raise PreparationError(category)
        return descriptor
    except PreparationError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise PreparationError(category) from None


def _read_descriptor(descriptor: int, category: str) -> bytes:
    try:
        chunks: list[bytes] = []
        length = 0
        while length <= MAX_INPUT:
            chunk = os.read(descriptor, min(65536, MAX_INPUT + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
        if length > MAX_INPUT:
            raise PreparationError(category)
        return b"".join(chunks)
    except OSError:
        raise PreparationError(category) from None


def _read_private_at(directory: int, name: str, category: str) -> bytes:
    descriptor = -1
    try:
        descriptor = _open_private_at(directory, name, category)
        return _read_descriptor(descriptor, category)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _private_bytes(path: Path, category: str) -> bytes:
    parent = -1
    try:
        _absolute, parent, name = _private_target(path, category)
        return _read_private_at(parent, name, category)
    finally:
        if parent >= 0:
            os.close(parent)


def _private_json(path: Path, category: str) -> dict[str, Any]:
    raw = _private_bytes(path, category)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise PreparationError(category) from None
    if not isinstance(value, dict) or raw != _canonical(value):
        raise PreparationError(category)
    return value


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        offset += os.write(descriptor, raw[offset:])


def _write_private_at(directory: int, name: str, raw: bytes) -> None:
    if not name or "/" in name or name in (".", ".."):
        raise PreparationError("private output rejected")
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=directory,
    )
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private(path: Path, raw: bytes) -> None:
    parent = -1
    try:
        _absolute, parent, name = _private_target(path, "private output rejected")
        _write_private_at(parent, name, raw)
    finally:
        if parent >= 0:
            os.close(parent)


def _write_json(path: Path, value: object) -> None:
    _write_private(path, _canonical(value))


def _open_relative_directory(root: int, relative: Path, category: str) -> int:
    if relative.is_absolute() or any(
        part in ("", ".", "..") for part in relative.parts
    ):
        raise PreparationError(category)
    descriptor = os.dup(root)
    try:
        for part in relative.parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                _validate_directory(os.fstat(child), category, private=True)
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _write_relative(root: int, relative: Path, raw: bytes) -> None:
    parent = _open_relative_directory(root, relative.parent, "private output rejected")
    try:
        _write_private_at(parent, relative.name, raw)
    finally:
        os.close(parent)


def _write_relative_json(root: int, relative: Path, value: object) -> None:
    _write_relative(root, relative, _canonical(value))


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    environment: dict[str, str] | None = None,
    pass_fds: tuple[int, ...] = (),
) -> bytes:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
            input=input_bytes,
            stdin=None if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=60,
            pass_fds=pass_fds,
        )
    except (OSError, subprocess.SubprocessError):
        raise PreparationError("required local tool failed") from None
    if result.returncode or len(result.stdout) > MAX_INPUT:
        raise PreparationError("required local tool failed")
    return result.stdout


def _source_identity() -> tuple[str, str]:
    raw = _run([str(ROOT / "scripts" / "deploy-source-identity.sh"), "--identity"])
    try:
        revision, digest = raw.decode("ascii").strip().split()
    except (UnicodeError, ValueError):
        raise PreparationError("source identity unavailable") from None
    if not REVISION.fullmatch(revision) or not HEX64.fullmatch(digest):
        raise PreparationError("source identity unavailable")
    protected = (
        _run(
            ["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"],
            cwd=ROOT,
        )
        .decode("ascii", "strict")
        .strip()
    )
    status = _run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            "Makefile",
            "ansible",
            "scripts",
            "secrets/schema.json",
            "terraform",
            "requirements.yml",
        ],
        cwd=ROOT,
    )
    if protected != revision or status:
        raise PreparationError("clean protected-main source required")
    return revision, digest


def _load_config(path: Path) -> dict[str, Any]:
    value = _private_json(path, "private preparation config required")
    if set(value) != {
        "schema_version",
        "hosts",
        "sender_ids",
        "pki",
        "silence_operator",
    }:
        raise PreparationError("preparation config rejected")
    hosts = value.get("hosts")
    senders = value.get("sender_ids")
    pki = value.get("pki")
    if (
        value.get("schema_version") != 1
        or not isinstance(hosts, dict)
        or set(hosts) != {"canary", "control-plane", "deadman"}
        or any(
            not isinstance(item, str) or not SLUG.fullmatch(item)
            for item in hosts.values()
        )
        or len(set(hosts.values())) != 3
        or not isinstance(senders, dict)
        or set(senders) != {"canary", "deadman-reverse"}
        or any(
            not isinstance(item, str) or not SLUG.fullmatch(item)
            for item in senders.values()
        )
        or len(set(senders.values())) != 2
        or not isinstance(pki, dict)
        or set(pki) != {"ingress_sni", "control_plane_dns_san", "deadman_pulse_sni"}
        or any(
            not isinstance(item, str) or not DNS_NAME.fullmatch(item)
            for item in pki.values()
        )
        or pki["ingress_sni"] == pki["control_plane_dns_san"]
        or not isinstance(value.get("silence_operator"), str)
        or not SLUG.fullmatch(value["silence_operator"])
    ):
        raise PreparationError("preparation config rejected")
    return value


def _load_telegram(path: Path) -> dict[str, Any]:
    value = _private_json(path, "private Telegram input required")
    if (
        set(value) != {"schema_version", "primary", "secondary"}
        or value.get("schema_version") != 1
    ):
        raise PreparationError("Telegram input rejected")
    for name in ("primary", "secondary"):
        route = value.get(name)
        if (
            not isinstance(route, dict)
            or set(route) != {"bot_token", "chat_id", "topic_id"}
            or not isinstance(route.get("bot_token"), str)
            or not re.fullmatch(
                r"[0-9]{4,16}:[A-Za-z0-9_-]{10,256}", route["bot_token"]
            )
            or not isinstance(route.get("chat_id"), str)
            or not re.fullmatch(r"-?[0-9]{6,20}", route["chat_id"])
            or not isinstance(route.get("topic_id"), int)
            or isinstance(route.get("topic_id"), bool)
            or route["topic_id"] < 0
        ):
            raise PreparationError("Telegram input rejected")
    if value["primary"]["bot_token"] == value["secondary"]["bot_token"]:
        raise PreparationError("distinct Telegram authorities required")
    return value


def _openssl(argv: list[str], directory: Path) -> None:
    _run(["openssl", *argv], cwd=directory)


def _certificate_authority(directory: Path, name: str) -> dict[str, str]:
    _openssl(["genpkey", "-algorithm", "ED25519", "-out", f"{name}.key"], directory)
    _openssl(
        [
            "req",
            "-new",
            "-x509",
            "-key",
            f"{name}.key",
            "-out",
            f"{name}.crt",
            "-days",
            "90",
            "-subj",
            f"/CN={name}",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        ],
        directory,
    )
    (directory / f"{name}-index.txt").write_bytes(b"")
    (directory / f"{name}-serial").write_text("1000\n", encoding="ascii")
    (directory / f"{name}-crlnumber").write_text("1000\n", encoding="ascii")
    (directory / f"{name}-newcerts").mkdir(mode=0o700)
    config = (
        "[ca]\ndefault_ca=default\n[default]\n"
        f"database={name}-index.txt\nserial={name}-serial\n"
        f"crlnumber={name}-crlnumber\nnew_certs_dir={name}-newcerts\n"
        f"private_key={name}.key\ncertificate={name}.crt\n"
        "default_md=default\ndefault_crl_days=90\npolicy=policy\n"
        "[policy]\ncommonName=supplied\n"
    )
    (directory / f"{name}-ca.cnf").write_text(config, encoding="ascii")
    _openssl(
        ["ca", "-gencrl", "-batch", "-config", f"{name}-ca.cnf", "-out", f"{name}.crl"],
        directory,
    )
    return {
        "certificate": (directory / f"{name}.crt").read_text(encoding="ascii"),
        "private_key": (directory / f"{name}.key").read_text(encoding="ascii"),
        "crl": (directory / f"{name}.crl").read_text(encoding="ascii"),
    }


def _certificate(
    directory: Path,
    *,
    ca: str,
    name: str,
    common_name: str,
    purpose: str,
    sans: tuple[str, ...] = (),
) -> dict[str, str]:
    _openssl(["genpkey", "-algorithm", "ED25519", "-out", f"{name}.key"], directory)
    _openssl(
        [
            "req",
            "-new",
            "-key",
            f"{name}.key",
            "-out",
            f"{name}.csr",
            "-subj",
            f"/CN={common_name}",
        ],
        directory,
    )
    extensions = [
        "basicConstraints=critical,CA:FALSE",
        "keyUsage=critical,digitalSignature",
        f"extendedKeyUsage={purpose}",
    ]
    if sans:
        extensions.append("subjectAltName=" + ",".join(sans))
    (directory / f"{name}.ext").write_text(
        "\n".join(extensions) + "\n", encoding="ascii"
    )
    _openssl(
        [
            "x509",
            "-req",
            "-in",
            f"{name}.csr",
            "-CA",
            f"{ca}.crt",
            "-CAkey",
            f"{ca}.key",
            "-CAserial",
            f"{ca}.srl",
            "-CAcreateserial",
            "-out",
            f"{name}.crt",
            "-days",
            "89",
            "-extfile",
            f"{name}.ext",
        ],
        directory,
    )
    return {
        "certificate": (directory / f"{name}.crt").read_text(encoding="ascii"),
        "private_key": (directory / f"{name}.key").read_text(encoding="ascii"),
    }


def _generate_pki(
    config: dict[str, Any], directory: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    receiver = _certificate_authority(directory, "staging-observability-receiver-ca")
    pulse = _certificate_authority(directory, "staging-observability-pulse-ca")
    silence = _certificate_authority(directory, "staging-observability-silence-ca")
    ingress = _certificate(
        directory,
        ca="staging-observability-receiver-ca",
        name="ingress-server",
        common_name=config["pki"]["ingress_sni"],
        purpose="serverAuth",
        sans=(
            "DNS:" + config["pki"]["ingress_sni"],
            "DNS:" + config["pki"]["control_plane_dns_san"],
        ),
    )
    canary = _certificate(
        directory,
        ca="staging-observability-receiver-ca",
        name="canary-sender",
        common_name=config["sender_ids"]["canary"],
        purpose="clientAuth",
    )
    reverse = _certificate(
        directory,
        ca="staging-observability-receiver-ca",
        name="deadman-reverse",
        common_name=config["sender_ids"]["deadman-reverse"],
        purpose="clientAuth",
    )
    pulse_server = _certificate(
        directory,
        ca="staging-observability-pulse-ca",
        name="pulse-server",
        common_name=config["pki"]["deadman_pulse_sni"],
        purpose="serverAuth",
        sans=("DNS:" + config["pki"]["deadman_pulse_sni"],),
    )
    silence_server = _certificate(
        directory,
        ca="staging-observability-silence-ca",
        name="silence-server",
        common_name="staging-silence-server",
        purpose="serverAuth",
        sans=("IP:127.0.0.1",),
    )
    silence_client = _certificate(
        directory,
        ca="staging-observability-silence-ca",
        name="silence-client",
        common_name="staging-silence-client",
        purpose="clientAuth",
    )
    public = {
        "receiver": receiver,
        "pulse": pulse,
        "silence": silence,
        "ingress": ingress,
        "canary": canary,
        "reverse": reverse,
        "pulse_server": pulse_server,
        "silence_server": silence_server,
        "silence_client": silence_client,
    }
    authorities = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "change": CHANGE,
        "receiver": {
            "ca_pem": receiver["certificate"],
            "ca_private_key_pem": receiver["private_key"],
        },
        "pulse": {
            "ca_pem": pulse["certificate"],
            "ca_private_key_pem": pulse["private_key"],
        },
        "silence": {
            "ca_pem": silence["certificate"],
            "ca_private_key_pem": silence["private_key"],
        },
    }
    return public, authorities


def _runtime_document(
    config: dict[str, Any], telegram: dict[str, Any], pki: dict[str, Any]
) -> dict[str, Any]:
    primary = dict(telegram["primary"])
    primary["relay_auth_token"] = secrets.token_hex(32)
    return {
        "observability_secrets": {
            "schema_version": 1,
            "receiver_ca_pem": pki["receiver"]["certificate"],
            "receiver_crl_pem": pki["receiver"]["crl"],
            "ingress_certificate_pem": pki["ingress"]["certificate"],
            "ingress_private_key_pem": pki["ingress"]["private_key"],
            "senders": [
                {
                    "node_id": config["sender_ids"]["canary"],
                    "certificate_pem": pki["canary"]["certificate"],
                    "private_key_pem": pki["canary"]["private_key"],
                },
                {
                    "node_id": config["sender_ids"]["deadman-reverse"],
                    "certificate_pem": pki["reverse"]["certificate"],
                    "private_key_pem": pki["reverse"]["private_key"],
                },
            ],
            "telegram": primary,
            "silence_gateway": {
                "operators": [
                    {
                        "owner": config["silence_operator"],
                        "token": secrets.token_hex(32),
                    }
                ],
                "sender_token": secrets.token_hex(32),
                "backend_ca_pem": pki["silence"]["certificate"],
                "backend_server_cert_pem": pki["silence_server"]["certificate"],
                "backend_server_key_pem": pki["silence_server"]["private_key"],
                "backend_client_cert_pem": pki["silence_client"]["certificate"],
                "backend_client_key_pem": pki["silence_client"]["private_key"],
            },
        },
        "observability_deadman_secrets": {
            "schema_version": 1,
            "pulse_token": secrets.token_hex(32),
            "canary_token": secrets.token_hex(32),
            "pulse_tls": {
                "ca_pem": pki["pulse"]["certificate"],
                "server_cert_pem": pki["pulse_server"]["certificate"],
                "server_key_pem": pki["pulse_server"]["private_key"],
            },
            "telegram": telegram["secondary"],
        },
    }


def _validate_runtime(value: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "secrets" / "schema.json").read_text(encoding="utf-8"))
    fragment = {
        "$schema": schema["$schema"],
        "type": "object",
        "required": ["observability_secrets", "observability_deadman_secrets"],
        "properties": {
            name: schema["properties"][name]
            for name in ("observability_secrets", "observability_deadman_secrets")
        },
        "additionalProperties": False,
        "$defs": schema["$defs"],
    }
    try:
        jsonschema.Draft202012Validator(fragment).validate(value)
    except jsonschema.ValidationError:
        raise PreparationError("generated observability authority rejected") from None


def _tool_environment(**extra: str) -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in ("HOME", "LANG", "LC_ALL", "LC_CTYPE", "PATH", "TMPDIR")
        if key in os.environ
    }
    environment.update(extra)
    return environment


def _encrypt_sops(value: dict[str, Any], recipient: str) -> bytes:
    payload = yaml.safe_dump(value, sort_keys=True).encode("utf-8")
    return _run(
        [
            "sops",
            "--encrypt",
            "--age",
            recipient,
            "--input-type",
            "yaml",
            "--output-type",
            "yaml",
            "/dev/stdin",
        ],
        input_bytes=payload,
        environment=_tool_environment(),
    )


def _generate_ssh(root: Path) -> None:
    private = root / "ssh" / "operator_ed25519"
    _run(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "staging-observability",
            "-f",
            str(private),
        ],
        environment=_tool_environment(),
    )
    private.chmod(0o600)
    private.with_suffix(".pub").chmod(0o600)


def _generate_age(root: Path) -> str:
    identity = root / "age" / "identity.txt"
    _run(["age-keygen", "-o", str(identity)], environment=_tool_environment())
    identity.chmod(0o600)
    try:
        match = re.search(
            r"^# public key: (\S+)$", identity.read_text(encoding="ascii"), re.MULTILINE
        )
    except (OSError, UnicodeError):
        match = None
    if match is None or not AGE_RECIPIENT.fullmatch(match.group(1)):
        raise PreparationError("age authority rejected")
    _write_private(
        root / "age" / "recipient.txt", (match.group(1) + "\n").encode("ascii")
    )
    return match.group(1)


def _scaffold(
    root: Path, root_descriptor: int, config: dict[str, Any], revision: str, digest: str
) -> None:
    acceptance = root / "acceptance"
    approvals = acceptance / "approvals"
    inputs = {
        "control_plane_vars": str(root / "vars" / "control-plane.yml"),
        "control_plane_secrets": str(
            root / "materialized" / "observability-secrets.yml"
        ),
        "candidate_control_plane_vars": str(
            root / "vars" / "candidate-control-plane.yml"
        ),
        "candidate_control_plane_secrets": str(
            root / "materialized" / "candidate-control-plane-secrets.yml"
        ),
        "deadman_vars": str(root / "vars" / "deadman.yml"),
        "deadman_secrets": str(root / "materialized" / "observability-secrets.yml"),
        "canary_vars": str(root / "vars" / "canary.yml"),
        "canary_secrets": str(root / "materialized" / "observability-secrets.yml"),
        "canary_old_generation": str(acceptance / "canary-old-generation.json"),
        "rollback_manifest": str(acceptance / "control-plane-rollback.json"),
        "invalid_control_plane_vars": str(root / "vars" / "invalid-control-plane.yml"),
        "silence_owner": str(acceptance / "silence-owner.json"),
        "hetzner_binding": str(acceptance / "hetzner-binding.json"),
        "primary_old_token": str(acceptance / "primary-old-token.txt"),
        "secondary_old_token": str(acceptance / "secondary-old-token.txt"),
        "observations": str(acceptance / "observations.json"),
    }
    approval_paths: dict[str, str] = {}
    for step in STEPS:
        path = approvals / f"{step}.json"
        _write_relative_json(
            root_descriptor,
            path.relative_to(root),
            {
                "schema_version": 1,
                "task_id": TASK_ID,
                "change": CHANGE,
                "action": step,
                "target": STEP_TARGETS[step],
                "restore_action": STEP_RESTORES[step],
                "approved": False,
                "approved_at": None,
                "expires_at": None,
                "deadline_seconds": STEP_DEADLINES[step],
                "cancellation_condition": "restore-and-stop",
            },
        )
        approval_paths[step] = str(path)
    _write_relative_json(
        root_descriptor,
        Path("acceptance/observations.json"),
        {
            "schema_version": 1,
            "rows": {
                step: {
                    "observed": False,
                    "started_at": None,
                    "observed_at": None,
                    "receipt_sha256": None,
                }
                for step in OBSERVATION_STEPS
            },
        },
    )
    _write_relative_json(
        root_descriptor,
        Path("acceptance/hetzner-binding.json"),
        {
            "schema_version": 1,
            "provider": "hetzner",
            "environment": "staging",
            "account_id": None,
            "state_sha256": None,
            "terraform_address": "hcloud_server.vpn",
            "server_id": None,
        },
    )
    _write_relative_json(
        root_descriptor,
        Path("acceptance/control-plane-rollback.json"),
        {
            "schema_version": 1,
            "host": config["hosts"]["control-plane"],
            "component": "control-plane",
            "previous_generation": None,
            "vars_sha256": None,
            "secrets_sha256": None,
        },
    )
    _write_relative_json(
        root_descriptor,
        Path("acceptance/canary-old-generation.json"),
        {"schema_version": 1, "generation": None},
    )
    _write_relative_json(
        root_descriptor,
        Path("acceptance/silence-owner.json"),
        {"schema_version": 1, "owner": config["silence_operator"]},
    )
    for name in ("primary-old-token.txt", "secondary-old-token.txt"):
        _write_relative(root_descriptor, Path("acceptance") / name, b"")
    for name in (
        "control-plane.yml",
        "deadman.yml",
        "canary.yml",
        "invalid-control-plane.yml",
        "candidate-control-plane.yml",
    ):
        _write_relative(root_descriptor, Path("vars") / name, b"{}\n")
    _write_relative(
        root_descriptor,
        Path("materialized/candidate-control-plane-secrets.yml"),
        b"{}\n",
    )
    _write_relative(root_descriptor, Path("inventory.ini"), b"")
    _write_relative(root_descriptor, Path("known_hosts"), b"")
    _write_relative_json(
        root_descriptor,
        Path("acceptance/manifest.json"),
        {
            "schema_version": 1,
            "task_id": TASK_ID,
            "change": CHANGE,
            "environment": "staging",
            "source_revision": revision,
            "deployable_digest": digest,
            "inventory": str(root / "inventory.ini"),
            "known_hosts": str(root / "known_hosts"),
            "hosts": config["hosts"],
            "inputs": inputs,
            "approvals": approval_paths,
        },
    )


def _mkdir_private_at(parent: int, name: str) -> int:
    if not name or "/" in name or name in (".", ".."):
        raise PreparationError("private output rejected")
    os.mkdir(name, mode=0o700, dir_fd=parent)
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent,
    )
    try:
        _validate_directory(
            os.fstat(descriptor), "private output rejected", private=True
        )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _same_descriptor(left: int, right: int) -> bool:
    left_metadata = os.fstat(left)
    right_metadata = os.fstat(right)
    return (left_metadata.st_dev, left_metadata.st_ino) == (
        right_metadata.st_dev,
        right_metadata.st_ino,
    )


def _verify_root_binding(root: Path, root_descriptor: int) -> None:
    descriptor = -1
    try:
        descriptor = _open_secure_directory(
            root, "private root binding changed", private=True
        )
        if not _same_descriptor(descriptor, root_descriptor):
            raise PreparationError("private root binding changed")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _verify_relative_binding(
    root_descriptor: int, relative: Path, descriptor: int, category: str
) -> None:
    current = _open_relative_directory(root_descriptor, relative, category)
    try:
        if not _same_descriptor(current, descriptor):
            raise PreparationError(category)
    finally:
        os.close(current)


def _remove_contents(directory: int) -> None:
    for entry in list(os.scandir(directory)):
        try:
            if entry.is_dir(follow_symlinks=False):
                child = os.open(
                    entry.name,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory,
                )
                try:
                    _remove_contents(child)
                finally:
                    os.close(child)
                os.rmdir(entry.name, dir_fd=directory)
            else:
                os.unlink(entry.name, dir_fd=directory)
        except FileNotFoundError:
            continue


def prepare(root_path: Path, config_path: Path, telegram_path: Path) -> None:
    root, parent_descriptor, root_name = _private_target(
        root_path, "private parent rejected"
    )
    root_descriptor = -1
    try:
        try:
            os.stat(root_name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise PreparationError("private root already exists")
        config = _load_config(config_path)
        telegram = _load_telegram(telegram_path)
        revision, digest = _source_identity()
        root_descriptor = _mkdir_private_at(parent_descriptor, root_name)
        directories: dict[str, int] = {}
        try:
            for name in ("ssh", "age", "secrets", "materialized", "vars", "acceptance"):
                directories[name] = _mkdir_private_at(root_descriptor, name)
            for name in ("approvals", "receipts"):
                directories[f"acceptance/{name}"] = _mkdir_private_at(
                    directories["acceptance"], name
                )

            with tempfile.TemporaryDirectory(
                prefix=".observability-staging-"
            ) as temporary:
                workspace = Path(temporary).resolve()
                os.chmod(workspace, 0o700)
                (workspace / "ssh").mkdir(mode=0o700)
                (workspace / "age").mkdir(mode=0o700)
                pki_directory = workspace / "pki"
                pki_directory.mkdir(mode=0o700)
                _generate_ssh(workspace)
                recipient = _generate_age(workspace)
                pki, authorities = _generate_pki(config, pki_directory)
                _verify_root_binding(root, root_descriptor)
                for destination, source in (
                    (("ssh", "operator_ed25519"), workspace / "ssh/operator_ed25519"),
                    (
                        ("ssh", "operator_ed25519.pub"),
                        workspace / "ssh/operator_ed25519.pub",
                    ),
                    (("age", "identity.txt"), workspace / "age/identity.txt"),
                    (("age", "recipient.txt"), workspace / "age/recipient.txt"),
                ):
                    _write_private_at(
                        directories[destination[0]],
                        destination[1],
                        _private_bytes(source, "generated private authority rejected"),
                    )

            runtime = _runtime_document(config, telegram, pki)
            _validate_runtime(runtime)
            runtime_ciphertext = _encrypt_sops(runtime, recipient)
            authority_ciphertext = _encrypt_sops(authorities, recipient)
            _write_private_at(
                directories["secrets"],
                "observability-secrets.sops.yaml",
                runtime_ciphertext,
            )
            _write_private_at(
                directories["secrets"],
                "observability-pki-authorities.sops.yaml",
                authority_ciphertext,
            )
            _scaffold(root, root_descriptor, config, revision, digest)
            os.fsync(root_descriptor)
            for relative, descriptor in directories.items():
                _verify_relative_binding(
                    root_descriptor,
                    Path(relative),
                    descriptor,
                    "private root binding changed",
                )
            _verify_root_binding(root, root_descriptor)
        finally:
            for descriptor in directories.values():
                os.close(descriptor)
    except Exception:
        if root_descriptor >= 0:
            try:
                _remove_contents(root_descriptor)
                bound = os.open(
                    root_name,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_descriptor,
                )
                try:
                    if _same_descriptor(bound, root_descriptor):
                        os.rmdir(root_name, dir_fd=parent_descriptor)
                finally:
                    os.close(bound)
            except OSError:
                pass
        raise
    finally:
        if root_descriptor >= 0:
            os.close(root_descriptor)
        os.close(parent_descriptor)


def _existing_private_root(root_path: Path) -> Path:
    return _checked_private_directory(root_path, "private root rejected")


def _atomic_materialized_at(directory: int, name: str, raw: bytes) -> None:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise PreparationError("materialized output rejected")
    temporary = f".{name}.{secrets.token_hex(16)}"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        _write_all(descriptor, raw)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def materialize(root_path: Path) -> None:
    root = _existing_private_root(root_path)
    root_descriptor = _open_secure_directory(
        root, "private root rejected", private=True
    )
    descriptors: list[int] = []
    try:
        age = _open_relative_directory(
            root_descriptor, Path("age"), "age authority rejected"
        )
        secret = _open_relative_directory(
            root_descriptor, Path("secrets"), "encrypted authority rejected"
        )
        output = _open_relative_directory(
            root_descriptor, Path("materialized"), "materialized output rejected"
        )
        descriptors.extend((age, secret, output))
        identity = _open_private_at(age, "identity.txt", "age authority rejected")
        encrypted = _open_private_at(
            secret, "observability-secrets.sops.yaml", "encrypted authority rejected"
        )
        descriptors.extend((identity, encrypted))
        plaintext = _run(
            [
                "sops",
                "--decrypt",
                "--input-type",
                "yaml",
                "--output-type",
                "yaml",
                f"/dev/fd/{encrypted}",
            ],
            environment=_tool_environment(SOPS_AGE_KEY_FILE=f"/dev/fd/{identity}"),
            pass_fds=(identity, encrypted),
        )
        try:
            value = yaml.safe_load(plaintext.decode("utf-8"))
        except (UnicodeError, yaml.YAMLError):
            raise PreparationError("materialized authority rejected") from None
        if not isinstance(value, dict):
            raise PreparationError("materialized authority rejected")
        _validate_runtime(value)
        for relative, descriptor in (
            ("age", age),
            ("secrets", secret),
            ("materialized", output),
        ):
            _verify_relative_binding(
                root_descriptor,
                Path(relative),
                descriptor,
                "private root binding changed",
            )
        _verify_root_binding(root, root_descriptor)
        _atomic_materialized_at(output, "observability-secrets.yml", plaintext)
        for relative, descriptor in (
            ("age", age),
            ("secrets", secret),
            ("materialized", output),
        ):
            _verify_relative_binding(
                root_descriptor,
                Path(relative),
                descriptor,
                "private root binding changed",
            )
        _verify_root_binding(root, root_descriptor)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        os.close(root_descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--root", type=Path, required=True)
    prepare_parser.add_argument("--config", type=Path, required=True)
    prepare_parser.add_argument("--telegram-input", type=Path, required=True)
    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args.root, args.config, args.telegram_input)
            status = "prepared"
        else:
            materialize(args.root)
            status = "materialized"
        print(json.dumps({"schema_version": 1, "status": status}, sort_keys=True))
        return 0
    except PreparationError as exc:
        print(f"observability staging input preparation failed: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print(
            "observability staging input preparation failed: unexpected local failure",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
