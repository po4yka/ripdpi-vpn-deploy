#!/usr/bin/env python3
"""Exercise cloud-final restart semantics in digest-pinned systemd containers.

This is a container PID1 restart acceptance, not a kernel reboot, provider, or
power-loss proof. The runtime entry point is implemented below; pure rendering
helpers remain importable for lightweight source-contract tests.
"""

from __future__ import annotations

import base64
import argparse
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import signal
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Callable, Mapping, NamedTuple, Sequence

import yaml

MAX_SOURCE_BYTES = 256 * 1024
MAX_SEED_BYTES = 1024 * 1024
MAX_COMMAND_OUTPUT = 2 * 1024 * 1024
HELPER_RELATIVE = Path("terraform/shared/bootstrap-sshd-ownership.py")
TEMPLATE_RELATIVE = Path("terraform/shared/cloud-init.yaml.tftpl")
HELPER_GUEST = "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"
WRAPPER_GUEST = "/usr/local/libexec/vpn-bootstrap-cloud-final-acceptance.py"
MARKER = "/var/lib/cloud-init-vpn-bootstrap.done"


class AcceptanceError(ValueError):
    """Categorical refusal without source or guest configuration disclosure."""


class SourceInputs(NamedTuple):
    helper: bytes
    helper_sha256: str
    ssh_port: str
    production_command: str


class AcceptanceCase(NamedTuple):
    distribution: str
    mode: str
    dockerfile: Path
    image_reference: str
    container_name: str
    instance_id: str
    ssh_port: str
    platform: str
    seed: bytes
    seed_sha256: str


class AcceptancePlan(NamedTuple):
    scope: str
    profile: str
    platform: str
    vm_arch: str
    ssh_port: str
    source_root: Path
    cases: tuple[AcceptanceCase, ...]


class BuiltImage(NamedTuple):
    image_id: str
    package_versions: Mapping[str, str]


class CommandResult(NamedTuple):
    returncode: int
    stdout: bytes
    stderr: bytes


class GuestObservation(NamedTuple):
    machine_arch: str
    instance_id: str
    cloud_final_invocation: str
    cloud_final_active: str
    cloud_final_result: str
    runcmd_semaphore: bool
    scripts_user_semaphore: bool
    marker: bool
    barrier: bool
    attempt: int
    config_sha256: Mapping[str, str]
    config_modes: Mapping[str, str]
    config_owners: Mapping[str, str]
    cloud_owner_safe: bool
    residue: tuple[str, ...]
    effective: Mapping[str, str]


class CloudFinalDiagnostic(NamedTuple):
    """Bounded state summary that cannot carry guest configuration or logs."""

    machine_arch: str
    instance_id_match: bool
    cloud_init_status_code: int
    cloud_final_invocation_sha256: str
    cloud_final_active: str
    cloud_final_substate: str
    cloud_final_result: str
    cloud_final_exec_code: str
    cloud_final_exec_status: int
    runcmd_semaphore: bool
    scripts_user_semaphore: bool
    marker: bool
    barrier: bool
    attempt: int
    fragment_states: Mapping[str, str]
    cloud_result_state: str
    error_count: int
    recoverable_error_count: int
    runcmd_script_present: bool


class CloudFinalFailure(AcceptanceError):
    """Strict cloud-final refusal carrying only the redacted diagnostic schema."""

    def __init__(
        self,
        category: str,
        distribution: str,
        mode: str,
        diagnostic: CloudFinalDiagnostic,
    ) -> None:
        super().__init__(category)
        self.distribution = distribution
        self.mode = mode
        self.diagnostic = diagnostic


def _read_source(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AcceptanceError("source-input") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_size <= 0
            or before.st_size > MAX_SOURCE_BYTES
        ):
            raise AcceptanceError("source-input")
        data = os.read(descriptor, MAX_SOURCE_BYTES + 1)
        after = os.fstat(descriptor)
        if (
            len(data) != before.st_size
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise AcceptanceError("source-input")
        return data
    finally:
        os.close(descriptor)


def _port(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdigit()
        or len(value) > 5
        or value != str(int(value))
        or not 1 <= int(value) <= 65535
    ):
        raise AcceptanceError("ssh-port")
    return value


def production_command(port: str) -> str:
    return (
        f"test -f {MARKER} || {{ install -d -m 0755 /run/sshd && "
        f"/usr/bin/python3 -I -B {HELPER_GUEST} --config-dir /etc/ssh "
        f"--ssh-port {port} && /usr/sbin/sshd -t && systemctl enable --now ssh "
        f"&& systemctl reload ssh && touch {MARKER}; }}"
    )


def load_source(root: Path, ssh_port: str) -> SourceInputs:
    port = _port(ssh_port)
    helper = _read_source(root / HELPER_RELATIVE)
    template = _read_source(root / TEMPLATE_RELATIVE)
    if b"def PUBLISH_BOUNDARY_HOOK(" not in helper or b"def normalize(" not in helper:
        raise AcceptanceError("source-helper")
    try:
        rendered = template.decode("utf-8").replace("${ssh_port}", port)
    except UnicodeDecodeError as exc:
        raise AcceptanceError("source-template") from exc
    expected = production_command(port)
    command_lines = re.findall(
        r'^\s*- \[sh, -c, "([^"\n]+)"\]\s*$', rendered, re.MULTILINE
    )
    if command_lines != [expected]:
        raise AcceptanceError("source-runcmd")
    return SourceInputs(helper, hashlib.sha256(helper).hexdigest(), port, expected)


def _interruption_wrapper(port: str) -> bytes:
    source = f"""#!/usr/bin/python3
import importlib.util
import os
from pathlib import Path
import signal
import stat

STATE = Path("/var/lib/cloud-init-restart-acceptance")
COUNTER = STATE / "attempt"
BARRIER = STATE / "interrupted-after-20-directory-fsync"
HELPER = Path("{HELPER_GUEST}")

def durable_write(path, content):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = STATE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError("unsafe acceptance state")
    temporary = STATE / (path.name + ".new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RuntimeError("short acceptance write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

attempt = 1
try:
    descriptor = os.open(COUNTER, os.O_RDONLY | os.O_NOFOLLOW)
except FileNotFoundError:
    descriptor = -1
if descriptor >= 0:
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_size > 8:
            raise RuntimeError("invalid acceptance counter")
        raw = os.read(descriptor, 9).decode("ascii").strip()
    finally:
        os.close(descriptor)
    if not raw.isdigit() or not 1 <= int(raw) <= 2:
        raise RuntimeError("invalid acceptance counter")
    attempt = int(raw) + 1
durable_write(COUNTER, f"{{attempt}}\\n".encode("ascii"))

spec = importlib.util.spec_from_file_location("bootstrap_sshd_ownership", HELPER)
if spec is None or spec.loader is None:
    raise RuntimeError("helper import failed")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if attempt == 1:
    def publish_boundary(phase, target):
        if phase == "directory-fsync" and target == "20-ansible-hardening.conf":
            durable_write(BARRIER, b"ready\\n")
            while True:
                signal.pause()
    module.PUBLISH_BOUNDARY_HOOK = publish_boundary

module.normalize(Path("/etc/ssh"), "{port}")
"""
    return source.encode("utf-8")


def _interrupted_command(port: str) -> str:
    return (
        f"test -f {MARKER} || {{ install -d -m 0755 /run/sshd && "
        f"/usr/bin/python3 -I -B {WRAPPER_GUEST} && /usr/sbin/sshd -t && "
        f"systemctl enable --now ssh && systemctl reload ssh && touch {MARKER}; }}"
    )


def render_user_data(source: SourceInputs, mode: str) -> str:
    if mode not in {"clean", "interrupted"}:
        raise AcceptanceError("mode")
    files = [
        {
            "path": HELPER_GUEST,
            "owner": "root:root",
            "permissions": "0700",
            "encoding": "b64",
            "content": base64.b64encode(source.helper).decode("ascii"),
        }
    ]
    command = source.production_command
    if mode == "interrupted":
        files.append(
            {
                "path": WRAPPER_GUEST,
                "owner": "root:root",
                "permissions": "0700",
                "encoding": "b64",
                "content": base64.b64encode(
                    _interruption_wrapper(source.ssh_port)
                ).decode("ascii"),
            }
        )
        command = _interrupted_command(source.ssh_port)
    document = {
        "ssh_pwauth": False,
        "disable_root": True,
        "write_files": files,
        "runcmd": [["sh", "-c", command]],
    }
    return "#cloud-config\n" + yaml.safe_dump(document, sort_keys=False)


def _instance_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 64
        or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None
    ):
        raise AcceptanceError("instance-id")
    return value


def seed_archive(user_data: str, instance_id: str) -> bytes:
    identifier = _instance_id(instance_id)
    if not isinstance(user_data, str) or not user_data.startswith("#cloud-config\n"):
        raise AcceptanceError("user-data")
    try:
        encoded_user_data = user_data.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AcceptanceError("user-data") from exc
    if len(encoded_user_data) > MAX_SOURCE_BYTES:
        raise AcceptanceError("user-data")
    cloud_configuration = yaml.safe_dump(
        {
            "datasource_list": ["NoCloud"],
            "datasource": {
                "NoCloud": {"seedfrom": "file:///var/lib/cloud/seed/nocloud/"}
            },
            "network": {"config": "disabled"},
        },
        sort_keys=False,
    ).encode("utf-8")
    metadata = (f"instance-id: {identifier}\nlocal-hostname: {identifier}\n").encode(
        "ascii"
    )
    members = (
        (
            "etc/cloud/cloud.cfg.d/99-vpn-cloud-final-acceptance.cfg",
            cloud_configuration,
            0o644,
        ),
        ("var/lib/cloud/seed/nocloud/meta-data", metadata, 0o600),
        ("var/lib/cloud/seed/nocloud/user-data", encoded_user_data, 0o600),
    )
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content, mode in members:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = mode
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
    result = output.getvalue()
    if len(result) > MAX_SEED_BYTES:
        raise AcceptanceError("seed-size")
    return result


_IMAGE_REFERENCES = {
    "debian13": (
        "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13"
        "@sha256:fd0443883979e0879e912231914df2093769d45fcb82af251704b30e2fc5c42e"
    ),
    "ubuntu2404": (
        "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404"
        "@sha256:48e1ab7caa1e28148148576cd2f15e46fcd9d44601125bbce7f3056306f40cf1"
    ),
}


def _profile(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 63
        or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None
    ):
        raise AcceptanceError("profile")
    return value


def build_plan(
    *,
    source: SourceInputs,
    source_root: Path,
    fixture_root: Path,
    profile: str,
    platform: str,
) -> AcceptancePlan:
    name = _profile(profile)
    if platform != "linux/amd64":
        raise AcceptanceError("platform")
    cases: list[AcceptanceCase] = []
    for distribution in ("debian13", "ubuntu2404"):
        dockerfile = fixture_root / f"{distribution}.Dockerfile"
        dockerfile_bytes = _read_source(dockerfile)
        expected_from = f"FROM {_IMAGE_REFERENCES[distribution]}\n".encode("ascii")
        if not dockerfile_bytes.startswith(expected_from):
            raise AcceptanceError("dockerfile-base")
        for mode in ("clean", "interrupted"):
            identifier = f"vpn-cloud-final-{distribution}-{mode}"
            seed = seed_archive(render_user_data(source, mode), identifier)
            cases.append(
                AcceptanceCase(
                    distribution=distribution,
                    mode=mode,
                    dockerfile=dockerfile,
                    image_reference=_IMAGE_REFERENCES[distribution],
                    container_name=f"{identifier}-{source.helper_sha256[:12]}",
                    instance_id=identifier,
                    ssh_port=source.ssh_port,
                    platform=platform,
                    seed=seed,
                    seed_sha256=hashlib.sha256(seed).hexdigest(),
                )
            )
    return AcceptancePlan(
        scope="container-systemd-cloud-final-restart",
        profile=name,
        platform=platform,
        vm_arch="x86_64",
        ssh_port=source.ssh_port,
        source_root=source_root.resolve(strict=True),
        cases=tuple(cases),
    )


def colima_start_argv(plan: AcceptancePlan) -> tuple[str, ...]:
    return (
        "colima",
        "start",
        "--profile",
        plan.profile,
        "--activate=false",
        "--arch",
        "x86_64",
        "--runtime",
        "docker",
        "--cpus",
        "2",
        "--memory",
        "4",
        "--disk",
        "20",
        "--mount",
        "none",
        "--network-address=false",
        "--port-forwarder",
        "none",
        "--ssh-agent=false",
        "--ssh-config=false",
        "--kubernetes=false",
    )


def container_create_argv(
    case: AcceptanceCase,
    image_id: str,
) -> tuple[str, ...]:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise AcceptanceError("image-id")
    return (
        "docker",
        "create",
        "--name",
        case.container_name,
        "--hostname",
        case.instance_id,
        "--network=none",
        f"--platform={case.platform}",
        "--privileged",
        "--cgroupns=host",
        "--tmpfs",
        "/run:rw,nosuid,nodev,mode=755",
        "--tmpfs",
        "/run/lock:rw,nosuid,nodev,noexec,mode=755",
        image_id,
        "/lib/systemd/systemd",
    )


_EFFECTIVE = {
    "passwordauthentication": "no",
    "kbdinteractiveauthentication": "no",
    "permitrootlogin": "no",
    "pubkeyauthentication": "yes",
    "x11forwarding": "no",
}


def _expected_config_digests(port: str) -> dict[str, str]:
    boot = (
        f"Port {port}\n"
        "PasswordAuthentication no\n"
        "KbdInteractiveAuthentication no\n"
        "PermitRootLogin no\n"
        "PubkeyAuthentication yes\n"
    ).encode("ascii")
    managed = b"# first-boot runtime owner\nX11Forwarding no\n"
    return {
        "10": hashlib.sha256(boot).hexdigest(),
        "20": hashlib.sha256(managed).hexdigest(),
    }


def _digest(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_config_observation(observation: GuestObservation, port: str) -> None:
    expected = _expected_config_digests(port)
    if {key: observation.config_sha256.get(key) for key in expected} != expected:
        raise AcceptanceError("config-digest")
    keys = set(observation.config_sha256)
    if keys not in ({"10", "20"}, {"10", "20", "50"}):
        raise AcceptanceError("config-digest")
    if set(observation.config_modes) != keys or set(observation.config_owners) != keys:
        raise AcceptanceError("config-metadata")
    if any(observation.config_modes[key] != "0644" for key in {"10", "20"}):
        raise AcceptanceError("config-mode")
    if any(observation.config_owners[key] != "0:0" for key in {"10", "20"}):
        raise AcceptanceError("config-owner")
    if "50" in keys:
        if not _digest(observation.config_sha256["50"]):
            raise AcceptanceError("config-digest")
        try:
            mode = int(observation.config_modes["50"], 8)
        except ValueError as exc:
            raise AcceptanceError("config-mode") from exc
        if not 0 <= mode <= 0o777 or mode & 0o022:
            raise AcceptanceError("config-mode")
        if re.fullmatch(r"0:[0-9]{1,10}", observation.config_owners["50"]) is None:
            raise AcceptanceError("config-owner")
    if not observation.cloud_owner_safe:
        raise AcceptanceError("cloud-owner")


def validate_interrupted(
    first: GuestObservation,
    second: GuestObservation,
    third: GuestObservation,
    ssh_port: str,
) -> None:
    port = _port(ssh_port)
    if any(item.machine_arch != "x86_64" for item in (first, second, third)):
        raise AcceptanceError("machine-architecture")
    if (
        first.instance_id != second.instance_id
        or second.instance_id != third.instance_id
    ):
        raise AcceptanceError("instance-changed")
    if (
        not first.runcmd_semaphore
        or first.scripts_user_semaphore
        or first.marker
        or not first.barrier
        or first.attempt != 1
        or first.cloud_final_active not in {"active", "activating"}
    ):
        raise AcceptanceError("interruption-boundary")
    first_has_cloud = "50" in first.config_sha256
    if first_has_cloud != ("50" in second.config_sha256) or (
        first_has_cloud
        and (
            first.config_modes.get("50") != second.config_modes.get("50")
            or first.config_owners.get("50") != second.config_owners.get("50")
        )
    ):
        raise AcceptanceError("cloud-owner-metadata")
    if (
        not second.runcmd_semaphore
        or not second.scripts_user_semaphore
        or not second.marker
        or not second.barrier
        or second.attempt != 2
        or second.cloud_final_active not in {"active", "inactive"}
        or second.cloud_final_result != "success"
    ):
        raise AcceptanceError("restart-convergence")
    if second.residue:
        raise AcceptanceError("publication-residue")
    _validate_config_observation(second, port)
    expected_effective = {"port": port, **_EFFECTIVE}
    if second.effective != expected_effective:
        raise AcceptanceError("sshd-effective")
    if len(
        {
            first.cloud_final_invocation,
            second.cloud_final_invocation,
            third.cloud_final_invocation,
        }
    ) != 3 or not all(
        re.fullmatch(r"[0-9a-f]{32}", value)
        for value in (
            first.cloud_final_invocation,
            second.cloud_final_invocation,
            third.cloud_final_invocation,
        )
    ):
        raise AcceptanceError("invocation-id")
    immutable_fields = (
        "machine_arch",
        "instance_id",
        "runcmd_semaphore",
        "scripts_user_semaphore",
        "marker",
        "barrier",
        "attempt",
        "config_sha256",
        "config_modes",
        "config_owners",
        "cloud_owner_safe",
        "residue",
        "effective",
    )
    if any(
        getattr(second, field) != getattr(third, field) for field in immutable_fields
    ):
        raise AcceptanceError("third-replay")
    if third.cloud_final_result != "success":
        raise AcceptanceError("third-cloud-final")


def acceptance_evidence(
    *,
    source_sha256: str,
    platform: str,
    vm_arch: str,
    cases: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if (
        not _digest(source_sha256)
        or platform != "linux/amd64"
        or vm_arch != "x86_64"
        or len(cases) != 4
    ):
        raise AcceptanceError("evidence")
    expected_sequence = (
        ("debian13", "clean"),
        ("debian13", "interrupted"),
        ("ubuntu2404", "clean"),
        ("ubuntu2404", "interrupted"),
    )
    for case, (distribution, mode) in zip(cases, expected_sequence, strict=True):
        expected_keys = {
            "distribution",
            "mode",
            "image_id",
            "package_versions",
            "first_invocation_sha256",
            "seed_sha256",
        }
        if mode == "interrupted":
            expected_keys.update(
                {"second_invocation_sha256", "third_invocation_sha256"}
            )
        versions = case.get("package_versions")
        if (
            set(case) != expected_keys
            or case.get("distribution") != distribution
            or case.get("mode") != mode
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(case.get("image_id"))) is None
            or not isinstance(versions, Mapping)
            or set(versions) != {"cloud-init", "openssh-server"}
            or any(
                not isinstance(value, str) or not value or len(value) > 128
                for value in versions.values()
            )
            or any(
                not isinstance(case.get(key), str) or not _digest(case[key])
                for key in expected_keys
                if key.endswith("_sha256")
            )
        ):
            raise AcceptanceError("evidence")
    return {
        "schema_version": 1,
        "scope": "container-systemd-cloud-final-restart",
        "platform": platform,
        "vm_arch": vm_arch,
        "claims": {
            "container_systemd_cloud_final_restart": True,
            "native_amd64_vm": True,
            "kernel_reboot": False,
            "power_loss": False,
            "provider_first_boot": False,
        },
        "source_helper_sha256": source_sha256,
        "cases": [dict(case) for case in cases],
    }


def failure_evidence(
    *,
    source_sha256: str,
    platform: str,
    vm_arch: str,
    failure: CloudFinalFailure,
) -> dict[str, object]:
    if (
        not _digest(source_sha256)
        or platform != "linux/amd64"
        or vm_arch != "x86_64"
        or failure.distribution not in {"debian13", "ubuntu2404"}
        or failure.mode not in {"clean", "interrupted"}
        or str(failure)
        not in {
            "cloud-init-error",
            "cloud-init-recoverable-error",
            "cloud-init-timeout",
            "cloud-init-status",
        }
    ):
        raise AcceptanceError("failure-evidence")
    return {
        "schema_version": 1,
        "scope": "container-systemd-cloud-final-restart",
        "conclusion": "failure",
        "category": str(failure),
        "distribution": failure.distribution,
        "mode": failure.mode,
        "platform": platform,
        "vm_arch": vm_arch,
        "claims": {
            "container_systemd_cloud_final_restart": False,
            "native_amd64_vm": False,
            "kernel_reboot": False,
            "power_loss": False,
            "provider_first_boot": False,
        },
        "source_helper_sha256": source_sha256,
        "diagnostic": failure.diagnostic._asdict(),
    }


def _failure_path(output: Path) -> Path:
    return output.with_name(output.name + ".failure.json")


def _kill_process_group_if_running(process: subprocess.Popen[bytes]) -> bool:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return False
    except OSError as exc:
        if exc.errno != errno.ESRCH:
            raise AcceptanceError("command-cleanup") from exc
        return False
    return True


def _kill_and_reap(process: subprocess.Popen[bytes]) -> None:
    _kill_process_group_if_running(process)
    try:
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceError("command-cleanup") from exc


class BoundedRunner:
    """Literal argv runner with bounded time, input, and captured output."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        input_bytes: bytes | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        command = tuple(argv)
        if (
            not command
            or len(command) > 96
            or timeout <= 0
            or timeout > 1800
            or any(
                not isinstance(item, str)
                or not item
                or "\0" in item
                or len(item) > 128 * 1024
                for item in command
            )
        ):
            raise AcceptanceError("command-argv")
        if input_bytes is not None and len(input_bytes) > MAX_SEED_BYTES:
            raise AcceptanceError("command-input")
        child_env = dict(env) if env is not None else None
        if child_env is not None and any(
            re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) is None
            or "\0" in value
            or len(value) > 4096
            for key, value in child_env.items()
        ):
            raise AcceptanceError("command-env")
        with tempfile.TemporaryFile() as input_file:
            if input_bytes is not None:
                input_file.write(input_bytes)
                input_file.seek(0)
            try:
                process = subprocess.Popen(
                    command,
                    stdin=input_file if input_bytes is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=child_env,
                    close_fds=True,
                    start_new_session=True,
                )
            except OSError as exc:
                raise AcceptanceError("command-start") from exc
            assert process.stdout is not None and process.stderr is not None
            selector = selectors.DefaultSelector()
            output = {process.stdout: bytearray(), process.stderr: bytearray()}
            try:
                selector.register(process.stdout, selectors.EVENT_READ)
                selector.register(process.stderr, selectors.EVENT_READ)
                deadline = time.monotonic() + timeout
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _kill_and_reap(process)
                        raise AcceptanceError("command-timeout")
                    events = selector.select(min(remaining, 0.2))
                    for key, _ in events:
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        output[key.fileobj].extend(chunk)
                        if len(output[key.fileobj]) > MAX_COMMAND_OUTPUT:
                            _kill_and_reap(process)
                            raise AcceptanceError("command-output")
                try:
                    returncode = process.wait(
                        timeout=min(2.0, max(0.1, deadline - time.monotonic()))
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    _kill_and_reap(process)
                    raise AcceptanceError("command-timeout") from exc
                return CommandResult(
                    returncode,
                    bytes(output[process.stdout]),
                    bytes(output[process.stderr]),
                )
            finally:
                selector.close()
                process.stdout.close()
                process.stderr.close()


def _require(result: CommandResult, category: str) -> bytes:
    if result.returncode != 0:
        raise AcceptanceError(category)
    return result.stdout


_DIAGNOSTIC_INSPECTOR = r"""import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

EXPECTED_INSTANCE = sys.argv[1]
STATUS_CODE = int(sys.argv[2])

def path_state(path, maximum=65536):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return "absent"
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0
            or info.st_size < 0 or info.st_size > maximum or info.st_mode & 0o022):
        return "unsafe"
    return "safe"

def safe_exists(path):
    return path_state(path, 65536) == "safe"

def safe_read(path, maximum):
    if path_state(path, maximum) != "safe":
        return None
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        data = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
        if (len(data) != before.st_size or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            return None
        return data
    finally:
        os.close(descriptor)

instance = safe_read(Path("/var/lib/cloud/data/instance-id"), 128)
instance_match = False
if instance is not None:
    try:
        instance_match = instance.decode("ascii").strip() == EXPECTED_INSTANCE
    except UnicodeDecodeError:
        pass

unit = {
    "InvocationID": "",
    "ActiveState": "unknown",
    "SubState": "unknown",
    "Result": "unknown",
    "ExecMainCode": "unknown",
    "ExecMainStatus": "-1",
}
show = subprocess.run(
    ["/usr/bin/systemctl", "show", "cloud-final.service", "--no-pager",
     "--property=InvocationID", "--property=ActiveState", "--property=SubState",
     "--property=Result", "--property=ExecMainCode", "--property=ExecMainStatus"],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    timeout=5, check=False, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
)
if show.returncode == 0 and len(show.stdout) <= 8192:
    parsed = {}
    try:
        lines = show.stdout.decode("ascii").splitlines()
    except UnicodeDecodeError:
        lines = []
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key in unit and key not in parsed and len(value) <= 64:
            parsed[key] = value
    if set(parsed) == set(unit):
        unit = parsed

invocation = unit["InvocationID"].lower()
invocation_digest = ""
if len(invocation) == 32 and all(character in "0123456789abcdef" for character in invocation):
    invocation_digest = hashlib.sha256(invocation.encode("ascii")).hexdigest()
try:
    exec_status = int(unit["ExecMainStatus"])
except ValueError:
    exec_status = -1

counter = 0
counter_raw = safe_read(Path("/var/lib/cloud-init-restart-acceptance/attempt"), 8)
if counter_raw is not None:
    try:
        candidate = counter_raw.decode("ascii").strip()
    except UnicodeDecodeError:
        candidate = ""
    counter = int(candidate) if candidate in {"1", "2"} else -1

result_path = Path("/var/lib/cloud/data/result.json")
result_state = path_state(result_path, 65536)
error_count = 0
recoverable_count = 0
if result_state == "safe":
    result_raw = safe_read(result_path, 65536)
    try:
        result_doc = json.loads(result_raw) if result_raw is not None else None
        version = result_doc["v1"]
        if not isinstance(version, dict):
            raise ValueError
        errors = version.get("errors", [])
        recoverable = version.get("recoverable_errors", {})
        if not isinstance(errors, list) or not isinstance(recoverable, dict):
            raise ValueError
        error_count = min(len(errors), 1024)
        for value in recoverable.values():
            if not isinstance(value, list):
                raise ValueError
            recoverable_count = min(1024, recoverable_count + len(value))
        result_state = "valid"
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        result_state = "invalid"

root = Path("/etc/ssh/sshd_config.d")
fragments = {
    "10": path_state(root / "10-cloud-init-hardening.conf"),
    "20": path_state(root / "20-ansible-hardening.conf"),
    "50": path_state(root / "50-cloud-init.conf"),
}

print(json.dumps({
    "machine_arch": os.uname().machine,
    "instance_id_match": instance_match,
    "cloud_init_status_code": STATUS_CODE,
    "cloud_final_invocation_sha256": invocation_digest,
    "cloud_final_active": unit["ActiveState"],
    "cloud_final_substate": unit["SubState"],
    "cloud_final_result": unit["Result"],
    "cloud_final_exec_code": unit["ExecMainCode"],
    "cloud_final_exec_status": exec_status,
    "runcmd_semaphore": safe_exists(Path("/var/lib/cloud/instance/sem/config_runcmd")),
    "scripts_user_semaphore": safe_exists(Path("/var/lib/cloud/instance/sem/config_scripts_user")),
    "marker": safe_exists(Path("/var/lib/cloud-init-vpn-bootstrap.done")),
    "barrier": safe_exists(Path("/var/lib/cloud-init-restart-acceptance/interrupted-after-20-directory-fsync")),
    "attempt": counter,
    "fragment_states": fragments,
    "cloud_result_state": result_state,
    "error_count": error_count,
    "recoverable_error_count": recoverable_count,
    "runcmd_script_present": safe_exists(Path("/var/lib/cloud/instance/scripts/runcmd")),
}, sort_keys=True, separators=(",", ":")))"""


def parse_cloud_final_diagnostic(raw: bytes) -> CloudFinalDiagnostic:
    if len(raw) > 64 * 1024:
        raise AcceptanceError("cloud-final-diagnostic")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError("cloud-final-diagnostic") from exc
    if not isinstance(document, dict) or set(document) != set(
        CloudFinalDiagnostic._fields
    ):
        raise AcceptanceError("cloud-final-diagnostic")
    bounded_tokens = (
        "machine_arch",
        "cloud_final_active",
        "cloud_final_substate",
        "cloud_final_result",
        "cloud_final_exec_code",
        "cloud_result_state",
    )
    if any(
        not isinstance(document[key], str)
        or re.fullmatch(r"[a-z0-9_.-]{0,32}", document[key]) is None
        for key in bounded_tokens
    ):
        raise AcceptanceError("cloud-final-diagnostic")
    digest = document["cloud_final_invocation_sha256"]
    if not isinstance(digest, str) or (digest and not _digest(digest)):
        raise AcceptanceError("cloud-final-diagnostic")
    for key in (
        "instance_id_match",
        "runcmd_semaphore",
        "scripts_user_semaphore",
        "marker",
        "barrier",
        "runcmd_script_present",
    ):
        if type(document[key]) is not bool:
            raise AcceptanceError("cloud-final-diagnostic")
    for key, lower, upper in (
        ("cloud_init_status_code", -1, 255),
        ("cloud_final_exec_status", -1, 255),
        ("attempt", -1, 2),
        ("error_count", 0, 1024),
        ("recoverable_error_count", 0, 1024),
    ):
        value = document[key]
        if type(value) is not int or not lower <= value <= upper:
            raise AcceptanceError("cloud-final-diagnostic")
    fragments = document["fragment_states"]
    if (
        not isinstance(fragments, dict)
        or set(fragments) != {"10", "20", "50"}
        or any(
            value not in {"absent", "safe", "unsafe"} for value in fragments.values()
        )
    ):
        raise AcceptanceError("cloud-final-diagnostic")
    return CloudFinalDiagnostic(
        document["machine_arch"],
        document["instance_id_match"],
        document["cloud_init_status_code"],
        digest,
        document["cloud_final_active"],
        document["cloud_final_substate"],
        document["cloud_final_result"],
        document["cloud_final_exec_code"],
        document["cloud_final_exec_status"],
        document["runcmd_semaphore"],
        document["scripts_user_semaphore"],
        document["marker"],
        document["barrier"],
        document["attempt"],
        dict(fragments),
        document["cloud_result_state"],
        document["error_count"],
        document["recoverable_error_count"],
        document["runcmd_script_present"],
    )


_INSPECTOR = r"""import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

PORT = sys.argv[1]
EXPECTED_INSTANCE = sys.argv[2]
ROOT = Path("/etc/ssh/sshd_config.d")

def regular(path, maximum=65536):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0 or info.st_size > maximum:
            raise RuntimeError("unsafe file")
        data = os.read(descriptor, maximum + 1)
        if len(data) != info.st_size:
            raise RuntimeError("read race")
        return data, info
    finally:
        os.close(descriptor)

def exists(path):
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True

instance, _ = regular(Path("/var/lib/cloud/data/instance-id"), 128)
instance_id = instance.decode("ascii").strip()
if instance_id != EXPECTED_INSTANCE:
    raise RuntimeError("instance mismatch")

members = sorted(entry.name for entry in os.scandir(ROOT))
if len(members) > 64 or any(name.endswith(".conf") and name not in {
    "10-cloud-init-hardening.conf", "20-ansible-hardening.conf", "50-cloud-init.conf"
} for name in members):
    raise RuntimeError("unexpected membership")
residue = tuple(name for name in members if name.startswith(".bootstrap-sshd-"))

digests = {}
modes = {}
owners = {}
for key, name in (("10", "10-cloud-init-hardening.conf"), ("20", "20-ansible-hardening.conf")):
    data, info = regular(ROOT / name)
    digests[key] = hashlib.sha256(data).hexdigest()
    modes[key] = format(stat.S_IMODE(info.st_mode), "04o")
    owners[key] = f"{info.st_uid}:{info.st_gid}"

cloud = ROOT / "50-cloud-init.conf"
cloud_safe = True
if exists(cloud):
    data, info = regular(cloud)
    digests["50"] = hashlib.sha256(data).hexdigest()
    modes["50"] = format(stat.S_IMODE(info.st_mode), "04o")
    owners["50"] = f"{info.st_uid}:{info.st_gid}"
    if info.st_mode & 0o022:
        cloud_safe = False
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError:
        cloud_safe = False
    else:
        cloud_safe = cloud_safe and all(not line.strip() or line.lstrip().startswith("#") for line in lines)

show = subprocess.run(
    ["/usr/bin/systemctl", "show", "cloud-final.service", "--no-pager",
     "--property=InvocationID", "--property=ActiveState", "--property=Result"],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    timeout=5, check=True, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
).stdout.decode("ascii")
unit = {}
for line in show.splitlines():
    key, separator, value = line.partition("=")
    if not separator or key in unit:
        raise RuntimeError("invalid systemd show")
    unit[key] = value
if set(unit) != {"InvocationID", "ActiveState", "Result"}:
    raise RuntimeError("invalid systemd show")

marker = exists(Path("/var/lib/cloud-init-vpn-bootstrap.done"))
effective = {}
if marker:
    subprocess.run(
        ["/usr/sbin/sshd", "-t", "-f", "/etc/ssh/sshd_config"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=5, check=True, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    )
    raw = subprocess.run(
        ["/usr/sbin/sshd", "-T", "-f", "/etc/ssh/sshd_config"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=5, check=True, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    ).stdout
    if len(raw) > 65536:
        raise RuntimeError("sshd output")
    wanted = {"port", "passwordauthentication", "kbdinteractiveauthentication", "permitrootlogin", "pubkeyauthentication", "x11forwarding"}
    for line in raw.decode("ascii").splitlines():
        fields = line.split(None, 1)
        if fields and fields[0] in wanted:
            if len(fields) != 2 or fields[0] in effective:
                raise RuntimeError("sshd duplicate")
            effective[fields[0]] = fields[1].strip().lower()

counter = 0
counter_path = Path("/var/lib/cloud-init-restart-acceptance/attempt")
if exists(counter_path):
    raw, _ = regular(counter_path, 8)
    value = raw.decode("ascii").strip()
    if value not in {"1", "2"}:
        raise RuntimeError("invalid counter")
    counter = int(value)

print(json.dumps({
    "machine_arch": os.uname().machine,
    "instance_id": instance_id,
    "cloud_final_invocation": unit["InvocationID"].lower(),
    "cloud_final_active": unit["ActiveState"],
    "cloud_final_result": unit["Result"],
    "runcmd_semaphore": exists(Path("/var/lib/cloud/instance/sem/config_runcmd")),
    "scripts_user_semaphore": exists(Path("/var/lib/cloud/instance/sem/config_scripts_user")),
    "marker": marker,
    "barrier": exists(Path("/var/lib/cloud-init-restart-acceptance/interrupted-after-20-directory-fsync")),
    "attempt": counter,
    "config_sha256": digests,
    "config_modes": modes,
    "config_owners": owners,
    "cloud_owner_safe": cloud_safe,
    "residue": residue,
    "effective": effective,
}, sort_keys=True, separators=(",", ":")))"""


def parse_observation(raw: bytes) -> GuestObservation:
    if len(raw) > 64 * 1024:
        raise AcceptanceError("guest-observation")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError("guest-observation") from exc
    expected_keys = set(GuestObservation._fields)
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise AcceptanceError("guest-observation")
    scalar_strings = (
        "machine_arch",
        "instance_id",
        "cloud_final_invocation",
        "cloud_final_active",
        "cloud_final_result",
    )
    if any(not isinstance(document[key], str) for key in scalar_strings):
        raise AcceptanceError("guest-observation")
    for key in (
        "runcmd_semaphore",
        "scripts_user_semaphore",
        "marker",
        "barrier",
        "cloud_owner_safe",
    ):
        if type(document[key]) is not bool:
            raise AcceptanceError("guest-observation")
    if type(document["attempt"]) is not int or document["attempt"] not in {0, 1, 2}:
        raise AcceptanceError("guest-observation")
    mappings: dict[str, dict[str, str]] = {}
    for key in ("config_sha256", "config_modes", "config_owners", "effective"):
        value = document[key]
        if (
            not isinstance(value, dict)
            or len(value) > 8
            or any(
                not isinstance(name, str)
                or not isinstance(item, str)
                or len(name) > 32
                or len(item) > 128
                for name, item in value.items()
            )
        ):
            raise AcceptanceError("guest-observation")
        mappings[key] = dict(value)
    residue = document["residue"]
    if (
        not isinstance(residue, list)
        or len(residue) > 12
        or any(not isinstance(item, str) or len(item) > 128 for item in residue)
    ):
        raise AcceptanceError("guest-observation")
    return GuestObservation(
        document["machine_arch"],
        document["instance_id"],
        document["cloud_final_invocation"],
        document["cloud_final_active"],
        document["cloud_final_result"],
        document["runcmd_semaphore"],
        document["scripts_user_semaphore"],
        document["marker"],
        document["barrier"],
        document["attempt"],
        mappings["config_sha256"],
        mappings["config_modes"],
        mappings["config_owners"],
        document["cloud_owner_safe"],
        tuple(residue),
        mappings["effective"],
    )


def _validate_converged(observation: GuestObservation, port: str) -> None:
    if (
        observation.machine_arch != "x86_64"
        or not observation.runcmd_semaphore
        or not observation.scripts_user_semaphore
        or not observation.marker
        or observation.cloud_final_active not in {"active", "inactive"}
        or observation.cloud_final_result != "success"
        or observation.residue
        or observation.effective != {"port": port, **_EFFECTIVE}
        or re.fullmatch(r"[0-9a-f]{32}", observation.cloud_final_invocation) is None
    ):
        raise AcceptanceError("clean-convergence")
    _validate_config_observation(observation, port)


def _invocation_digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class DockerColimaRuntime:
    """Owned no-mount Colima profile implementing the acceptance plan."""

    def __init__(
        self,
        *,
        home: Path,
        output: Path,
        runner: BoundedRunner | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.home = home.resolve(strict=True)
        self.output = output
        self.runner = runner or BoundedRunner()
        self.sleep = sleep
        self.runtime_root: Path | None = None
        self.docker_config: Path | None = None
        self.docker_env: dict[str, str] | None = None
        self.owned_containers: list[str] = []
        self.owned_images: list[str] = []
        self.profile_claimed = False

    def _base_env(self) -> dict[str, str]:
        path = os.environ.get("PATH")
        if not path:
            raise AcceptanceError("host-path")
        return {
            "PATH": path,
            "HOME": str(self.home),
            "LANG": "C",
            "LC_ALL": "C",
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        }

    def current_context(self) -> str:
        environment = self._base_env()
        for key in ("DOCKER_HOST", "DOCKER_CONTEXT"):
            if key in os.environ:
                environment[key] = os.environ[key]
        raw = _require(
            self.runner.run(("docker", "context", "show"), timeout=10, env=environment),
            "docker-context",
        )
        try:
            value = raw.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise AcceptanceError("docker-context") from exc
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value) is None:
            raise AcceptanceError("docker-context")
        return value

    def claim(self, plan: AcceptancePlan) -> None:
        if os.environ.get("BUILD_GATE_HELD") != "1":
            raise AcceptanceError("build-gate-required")
        profile_path = self.home / ".colima" / plan.profile
        if profile_path.exists() or profile_path.is_symlink():
            raise AcceptanceError("profile-exists")
        failure_output = _failure_path(self.output)
        if (
            self.output.exists()
            or self.output.is_symlink()
            or failure_output.exists()
            or failure_output.is_symlink()
        ):
            raise AcceptanceError("evidence-exists")
        parent = self.output.parent.resolve(strict=True)
        info = parent.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise AcceptanceError("evidence-parent")
        runtime_parent = self.home / ".cache" / "ripdpi-cloud-final-restart"
        if runtime_parent.exists():
            info = runtime_parent.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise AcceptanceError("runtime-parent")
        runtime = runtime_parent / plan.profile
        if runtime.exists() or runtime.is_symlink():
            raise AcceptanceError("runtime-exists")
        self.runtime_root = runtime

    def start(self, plan: AcceptancePlan) -> None:
        assert self.runtime_root is not None
        try:
            self.runtime_root.parent.mkdir(mode=0o700, parents=True)
        except FileExistsError:
            info = self.runtime_root.parent.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise AcceptanceError("runtime-parent")
        self.runtime_root.mkdir(mode=0o700)
        self.docker_config = self.runtime_root / "docker-config"
        self.docker_config.mkdir(mode=0o700)
        self.profile_claimed = True
        _require(
            self.runner.run(colima_start_argv(plan), timeout=600, env=self._base_env()),
            "profile-start",
        )
        socket_path = self.home / ".colima" / plan.profile / "docker.sock"
        info = socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise AcceptanceError("docker-socket")
        self.docker_env = self._base_env()
        self.docker_env.update(
            {
                "DOCKER_HOST": f"unix://{socket_path}",
                "DOCKER_CONFIG": str(self.docker_config),
            }
        )

    def assert_no_host_mounts(self, plan: AcceptancePlan) -> None:
        architecture = _require(
            self.runner.run(
                (
                    "colima",
                    "ssh",
                    "--profile",
                    plan.profile,
                    "--",
                    "uname",
                    "-m",
                ),
                timeout=30,
                env=self._base_env(),
            ),
            "profile-architecture",
        )
        if architecture != b"x86_64\n":
            raise AcceptanceError("profile-architecture")
        raw = _require(
            self.runner.run(
                ("colima", "ssh", "--profile", plan.profile, "--", "mount"),
                timeout=30,
                env=self._base_env(),
            ),
            "profile-mount-inspection",
        )
        lowered = raw.lower()
        if any(
            token in lowered
            for token in (
                b" on /users/",
                b" on /volumes/",
                b" type 9p ",
                b" type virtiofs ",
                b" type fuse.sshfs ",
            )
        ):
            raise AcceptanceError("profile-host-mount")

    def _docker(
        self, argv: Sequence[str], *, timeout: float, input_bytes: bytes | None = None
    ) -> CommandResult:
        if self.docker_env is None:
            raise AcceptanceError("profile-not-started")
        return self.runner.run(
            argv, timeout=timeout, input_bytes=input_bytes, env=self.docker_env
        )

    def build(self, plan: AcceptancePlan, distribution: str) -> BuiltImage:
        cases = [case for case in plan.cases if case.distribution == distribution]
        if len(cases) != 2:
            raise AcceptanceError("plan-distribution")
        case = cases[0]
        tag = f"vpn-cloud-final-acceptance:{distribution}-{case.seed_sha256[:12]}"
        _require(
            self._docker(
                (
                    "docker",
                    "build",
                    "--pull",
                    "--platform",
                    plan.platform,
                    "--tag",
                    tag,
                    "--file",
                    str(case.dockerfile),
                    str(case.dockerfile.parent),
                ),
                timeout=1200,
            ),
            "image-build",
        )
        self.owned_images.append(tag)
        raw_id = _require(
            self._docker(
                ("docker", "image", "inspect", "--format={{.Id}}", tag),
                timeout=30,
            ),
            "image-inspect",
        )
        try:
            image_id = raw_id.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise AcceptanceError("image-id") from exc
        if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
            raise AcceptanceError("image-id")
        versions_raw = _require(
            self._docker(
                (
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    image_id,
                    "/usr/bin/dpkg-query",
                    "--show",
                    "--showformat=${Package}=${Version}\\n",
                    "cloud-init",
                    "openssh-server",
                ),
                timeout=30,
            ),
            "package-versions",
        )
        try:
            lines = versions_raw.decode("ascii").splitlines()
            versions = dict(line.split("=", 1) for line in lines)
        except (UnicodeDecodeError, ValueError) as exc:
            raise AcceptanceError("package-versions") from exc
        if set(versions) != {"cloud-init", "openssh-server"} or any(
            not value or len(value) > 128 for value in versions.values()
        ):
            raise AcceptanceError("package-versions")
        return BuiltImage(image_id, versions)

    def _observe(self, case: AcceptanceCase) -> GuestObservation:
        raw = _require(
            self._docker(
                (
                    "docker",
                    "exec",
                    case.container_name,
                    "/usr/bin/python3",
                    "-I",
                    "-B",
                    "-c",
                    _INSPECTOR,
                    case.ssh_port,
                    case.instance_id,
                ),
                timeout=20,
            ),
            "guest-inspection",
        )
        return parse_observation(raw)

    def _diagnose_cloud_final(
        self, case: AcceptanceCase, status_code: int
    ) -> CloudFinalDiagnostic:
        raw = _require(
            self._docker(
                (
                    "docker",
                    "exec",
                    case.container_name,
                    "/usr/bin/python3",
                    "-I",
                    "-B",
                    "-c",
                    _DIAGNOSTIC_INSPECTOR,
                    case.instance_id,
                    str(status_code),
                ),
                timeout=20,
            ),
            "cloud-final-diagnostic",
        )
        return parse_cloud_final_diagnostic(raw)

    def _poll_observation(
        self,
        case: AcceptanceCase,
        predicate: Callable[[GuestObservation], bool],
        *,
        timeout: float,
    ) -> GuestObservation:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                observation = self._observe(case)
            except AcceptanceError as exc:
                if str(exc) != "guest-inspection":
                    raise
            else:
                if predicate(observation):
                    return observation
            self.sleep(1.0)
        raise AcceptanceError("guest-observation-timeout")

    def _wait_cloud_final(self, case: AcceptanceCase) -> GuestObservation:
        status = self._docker(
            (
                "docker",
                "exec",
                case.container_name,
                "/usr/bin/timeout",
                "--kill-after=2",
                "150",
                "/usr/bin/cloud-init",
                "status",
                "--wait",
            ),
            timeout=160,
        )
        if status.returncode != 0:
            diagnostic = self._diagnose_cloud_final(case, status.returncode)
            if diagnostic.cloud_init_status_code != status.returncode:
                raise AcceptanceError("cloud-final-diagnostic")
            category = {
                1: "cloud-init-error",
                2: "cloud-init-recoverable-error",
                124: "cloud-init-timeout",
                137: "cloud-init-timeout",
            }.get(status.returncode, "cloud-init-status")
            raise CloudFinalFailure(category, case.distribution, case.mode, diagnostic)
        return self._poll_observation(
            case,
            lambda item: item.cloud_final_result == "success"
            and item.cloud_final_active in {"active", "inactive"},
            timeout=20,
        )

    def _restart(self, case: AcceptanceCase) -> None:
        _require(
            self._docker(
                ("docker", "kill", "--signal=KILL", case.container_name),
                timeout=30,
            ),
            "container-kill",
        )
        _require(
            self._docker(("docker", "start", case.container_name), timeout=30),
            "container-restart",
        )

    def run_case(
        self,
        plan: AcceptancePlan,
        case: AcceptanceCase,
        image: BuiltImage,
    ) -> Mapping[str, object]:
        names = _require(
            self._docker(
                ("docker", "container", "ls", "-a", "--format={{.Names}}"),
                timeout=30,
            ),
            "container-list",
        )
        try:
            existing = names.decode("ascii").splitlines()
        except UnicodeDecodeError as exc:
            raise AcceptanceError("container-list") from exc
        if case.container_name in existing:
            raise AcceptanceError("container-exists")
        _require(
            self._docker(container_create_argv(case, image.image_id), timeout=30),
            "container-create",
        )
        self.owned_containers.append(case.container_name)
        _require(
            self._docker(
                ("docker", "cp", "-", f"{case.container_name}:/"),
                timeout=30,
                input_bytes=case.seed,
            ),
            "seed-copy",
        )
        _require(
            self._docker(("docker", "start", case.container_name), timeout=30),
            "container-start",
        )
        if case.mode == "clean":
            observation = self._wait_cloud_final(case)
            _validate_converged(observation, case.ssh_port)
            if observation.attempt != 0 or observation.barrier:
                raise AcceptanceError("clean-wrapper-ran")
            return {
                "distribution": case.distribution,
                "mode": case.mode,
                "image_id": image.image_id,
                "package_versions": dict(image.package_versions),
                "first_invocation_sha256": _invocation_digest(
                    observation.cloud_final_invocation
                ),
                "seed_sha256": case.seed_sha256,
            }
        first = self._poll_observation(
            case,
            lambda item: item.barrier and item.attempt == 1,
            timeout=180,
        )
        self._restart(case)
        second = self._wait_cloud_final(case)
        self._restart(case)
        third = self._wait_cloud_final(case)
        validate_interrupted(first, second, third, case.ssh_port)
        return {
            "distribution": case.distribution,
            "mode": case.mode,
            "image_id": image.image_id,
            "package_versions": dict(image.package_versions),
            "first_invocation_sha256": _invocation_digest(first.cloud_final_invocation),
            "second_invocation_sha256": _invocation_digest(
                second.cloud_final_invocation
            ),
            "third_invocation_sha256": _invocation_digest(third.cloud_final_invocation),
            "seed_sha256": case.seed_sha256,
        }

    def cleanup(self, plan: AcceptancePlan) -> None:
        failures = False
        for container in reversed(self.owned_containers):
            result = self._docker(
                ("docker", "container", "rm", "--force", container), timeout=30
            )
            failures = failures or result.returncode != 0
        self.owned_containers.clear()
        for tag in reversed(self.owned_images):
            result = self._docker(("docker", "image", "rm", "--force", tag), timeout=60)
            failures = failures or result.returncode != 0
        self.owned_images.clear()
        if failures:
            raise AcceptanceError("docker-cleanup")

    def stop_delete(self, plan: AcceptancePlan) -> None:
        failure = False
        if self.profile_claimed:
            stop = self.runner.run(
                ("colima", "stop", "--profile", plan.profile),
                timeout=180,
                env=self._base_env(),
            )
            delete = self.runner.run(
                ("colima", "delete", "--profile", plan.profile, "--force", "--data"),
                timeout=180,
                env=self._base_env(),
            )
            failure = stop.returncode != 0 or delete.returncode != 0
        profile_path = self.home / ".colima" / plan.profile
        if profile_path.exists() or profile_path.is_symlink():
            failure = True
        if self.runtime_root is not None and self.runtime_root.exists():
            shutil.rmtree(self.runtime_root)
        if failure:
            raise AcceptanceError("profile-cleanup")


def _write_evidence(path: Path, evidence: Mapping[str, object]) -> None:
    data = (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )
    if len(data) > 256 * 1024:
        raise AcceptanceError("evidence-size")
    parent = path.parent.resolve(strict=True)
    name = path.name
    if not name or name in {".", ".."} or "/" in name:
        raise AcceptanceError("evidence-path")
    temporary = parent / f".{name}.new"
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise AcceptanceError("evidence-write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise AcceptanceError("evidence-exists") from exc
        temporary.unlink()
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        _unlink_path_if_present(temporary)


def _unlink_path_if_present(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _capture_cleanup_error(action: Callable[[], None]) -> BaseException | None:
    """Finish all owned cleanup steps even when the operator cancels one of them."""
    try:
        action()
    except (Exception, KeyboardInterrupt, SystemExit, GeneratorExit) as exc:
        return exc
    return None


def execute_acceptance(
    plan: AcceptancePlan, source: SourceInputs, runtime
) -> dict[str, object]:
    """Execute all cases serially and release every owned host resource."""
    context_before = runtime.current_context()
    runtime.claim(plan)
    built: dict[str, BuiltImage] = {}
    case_evidence: list[Mapping[str, object]] = []
    try:
        runtime.start(plan)
        runtime.assert_no_host_mounts(plan)
        for distribution in ("debian13", "ubuntu2404"):
            built[distribution] = runtime.build(plan, distribution)
        for case in plan.cases:
            case_evidence.append(runtime.run_case(plan, case, built[case.distribution]))
    finally:
        cleanup_error = _capture_cleanup_error(lambda: runtime.cleanup(plan))
        stop_error = _capture_cleanup_error(lambda: runtime.stop_delete(plan))
        cleanup_error = cleanup_error or stop_error

        def assert_context() -> None:
            if runtime.current_context() != context_before:
                raise AcceptanceError("docker-context-changed")

        context_error = _capture_cleanup_error(assert_context)
        cleanup_error = cleanup_error or context_error
        if cleanup_error is not None:
            raise AcceptanceError("acceptance-cleanup") from cleanup_error
    return acceptance_evidence(
        source_sha256=source.helper_sha256,
        platform=plan.platform,
        vm_arch=plan.vm_arch,
        cases=case_evidence,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--ssh-port", default="2222")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument(
        "--fixture-root",
        default=str(
            Path(__file__).resolve().parents[1] / "tests/integration/cloud-init-restart"
        ),
    )
    arguments = parser.parse_args(argv)
    source: SourceInputs | None = None
    plan: AcceptancePlan | None = None
    output: Path | None = None
    try:
        source_root = Path(arguments.source_root).resolve(strict=True)
        fixture_root = Path(arguments.fixture_root).resolve(strict=True)
        output = Path(arguments.output)
        if not output.is_absolute():
            raise AcceptanceError("evidence-path")
        source = load_source(source_root, arguments.ssh_port)
        plan = build_plan(
            source=source,
            source_root=source_root,
            fixture_root=fixture_root,
            profile=arguments.profile,
            platform=arguments.platform,
        )
        runtime = DockerColimaRuntime(home=Path.home(), output=output)
        evidence = execute_acceptance(plan, source, runtime)
        _write_evidence(output, evidence)
    except CloudFinalFailure as exc:
        if source is None or plan is None or output is None:
            print(
                "cloud-final restart acceptance refused: internal-error",
                file=sys.stderr,
            )
            return 1
        try:
            _write_evidence(
                _failure_path(output),
                failure_evidence(
                    source_sha256=source.helper_sha256,
                    platform=plan.platform,
                    vm_arch=plan.vm_arch,
                    failure=exc,
                ),
            )
        except AcceptanceError as evidence_error:
            print(
                f"cloud-final restart acceptance refused: {evidence_error}",
                file=sys.stderr,
            )
            return 1
        print(f"cloud-final restart acceptance refused: {exc}", file=sys.stderr)
        return 1
    except AcceptanceError as exc:
        print(f"cloud-final restart acceptance refused: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("cloud-final restart acceptance refused: internal-error", file=sys.stderr)
        return 1
    print("cloud-final restart acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
