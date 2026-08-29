"""Contracts for the bounded cloud-final restart acceptance harness."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import re
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "integration" / "cloud-init-restart"
HARNESS = REPO_ROOT / "scripts" / "cloud-init-restart-acceptance.py"

BASE_IMAGES = {
    "debian13.Dockerfile": (
        "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13",
        "fd0443883979e0879e912231914df2093769d45fcb82af251704b30e2fc5c42e",
    ),
    "ubuntu2404.Dockerfile": (
        "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404",
        "48e1ab7caa1e28148148576cd2f15e46fcd9d44601125bbce7f3056306f40cf1",
    ),
}


@pytest.fixture
def acceptance_module():
    spec = importlib.util.spec_from_file_location(
        "cloud_init_restart_acceptance", HARNESS
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_fixture(root: Path) -> tuple[Path, bytes, str]:
    shared = root / "terraform" / "shared"
    shared.mkdir(parents=True)
    helper = (
        b"def PUBLISH_BOUNDARY_HOOK(phase, target):\n    pass\n\n"
        b"def normalize(config_dir, ssh_port):\n    return True\n"
    )
    (shared / "bootstrap-sshd-ownership.py").write_bytes(helper)
    command = (
        "test -f /var/lib/cloud-init-vpn-bootstrap.done || { "
        "install -d -m 0755 /run/sshd && /usr/bin/python3 -I -B "
        "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py --config-dir /etc/ssh "
        "--ssh-port 2222 && /usr/sbin/sshd -t && systemctl enable --now ssh && "
        "systemctl reload ssh && touch /var/lib/cloud-init-vpn-bootstrap.done; }"
    )
    (shared / "cloud-init.yaml.tftpl").write_text(
        '#cloud-config\nruncmd:\n  - [sh, -c, "' + command + '"]\n',
        encoding="utf-8",
    )
    return root, helper, command


def test_derivative_images_are_digest_pinned_and_install_first_boot_runtime() -> None:
    for filename, (repository, digest) in BASE_IMAGES.items():
        dockerfile = (FIXTURE_ROOT / filename).read_text(encoding="utf-8")

        assert dockerfile.splitlines()[0] == f"FROM {repository}@sha256:{digest}"
        assert len(re.findall(r"^FROM ", dockerfile, flags=re.MULTILINE)) == 1
        assert "ARG " not in dockerfile
        assert "cloud-init" in dockerfile
        assert "openssh-server" in dockerfile
        assert "cloud-init clean --logs --machine-id" in dockerfile
        assert 'CMD ["/lib/systemd/systemd"]' in dockerfile
        assert "curl " not in dockerfile
        assert "http://" not in dockerfile


def test_rendered_clean_and_interrupted_configs_bind_exact_source(
    acceptance_module,
    tmp_path: Path,
) -> None:
    root, helper, production_command = _source_fixture(tmp_path / "source")

    source = acceptance_module.load_source(root, "2222")
    clean = yaml.safe_load(acceptance_module.render_user_data(source, "clean"))
    interrupted = yaml.safe_load(
        acceptance_module.render_user_data(source, "interrupted")
    )

    assert source.helper_sha256 == hashlib.sha256(helper).hexdigest()
    assert clean["runcmd"] == [["sh", "-c", production_command]]
    assert base64.b64decode(clean["write_files"][0]["content"]) == helper
    assert clean["write_files"][0]["permissions"] == "0700"
    assert len(clean["write_files"]) == 1

    assert base64.b64decode(interrupted["write_files"][0]["content"]) == helper
    wrapper = base64.b64decode(interrupted["write_files"][1]["content"])
    assert b"PUBLISH_BOUNDARY_HOOK = publish_boundary" in wrapper
    assert b'phase == "directory-fsync"' in wrapper
    assert b'target == "20-ansible-hardening.conf"' in wrapper
    assert b"os.fsync" in wrapper
    assert b"signal.pause()" in wrapper
    assert interrupted["runcmd"][0][0:2] == ["sh", "-c"]
    assert production_command != interrupted["runcmd"][0][2]
    assert "/usr/bin/python3 -I -B" in interrupted["runcmd"][0][2]


def test_source_loader_rejects_legacy_template_without_new_helper_argv(
    acceptance_module,
    tmp_path: Path,
) -> None:
    root, _helper, _command = _source_fixture(tmp_path / "source")
    template = root / "terraform" / "shared" / "cloud-init.yaml.tftpl"
    template.write_text(
        '#cloud-config\nruncmd:\n  - [sh, -c, "sshd -t"]\n', encoding="utf-8"
    )

    with pytest.raises(acceptance_module.AcceptanceError, match="source-runcmd"):
        acceptance_module.load_source(root, "2222")


def test_nocloud_seed_is_fixed_owned_bounded_and_reproducible(
    acceptance_module,
    tmp_path: Path,
) -> None:
    root, _helper, _command = _source_fixture(tmp_path / "source")
    source = acceptance_module.load_source(root, "2222")
    user_data = acceptance_module.render_user_data(source, "interrupted")

    first = acceptance_module.seed_archive(
        user_data, "vpn-cloud-final-debian13-interrupted"
    )
    second = acceptance_module.seed_archive(
        user_data, "vpn-cloud-final-debian13-interrupted"
    )

    assert first == second
    assert len(first) <= acceptance_module.MAX_SEED_BYTES
    with tarfile.open(fileobj=io.BytesIO(first), mode="r:") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == [
            "etc/cloud/cloud.cfg.d/99-vpn-cloud-final-acceptance.cfg",
            "var/lib/cloud/seed/nocloud/meta-data",
            "var/lib/cloud/seed/nocloud/user-data",
        ]
        assert all(member.isfile() for member in members)
        assert all(member.uid == 0 and member.gid == 0 for member in members)
        assert all(member.mtime == 0 for member in members)
        assert [member.mode for member in members] == [0o644, 0o600, 0o600]
        payloads = {
            member.name: archive.extractfile(member).read() for member in members
        }

    assert payloads["var/lib/cloud/seed/nocloud/meta-data"] == (
        b"instance-id: vpn-cloud-final-debian13-interrupted\n"
        b"local-hostname: vpn-cloud-final-debian13-interrupted\n"
    )
    assert payloads["var/lib/cloud/seed/nocloud/user-data"] == user_data.encode()
    cloud_cfg = yaml.safe_load(
        payloads["etc/cloud/cloud.cfg.d/99-vpn-cloud-final-acceptance.cfg"].decode()
    )
    assert cloud_cfg == {
        "datasource_list": ["NoCloud"],
        "datasource": {"NoCloud": {"seedfrom": "file:///var/lib/cloud/seed/nocloud/"}},
        "network": {"config": "disabled"},
    }


@pytest.mark.parametrize(
    "instance_id",
    ["", "../escape", "with space", "A" * 65, "vpn/cloud", "vpn_cloud"],
)
def test_nocloud_seed_refuses_noncanonical_instance_id(
    acceptance_module,
    instance_id: str,
) -> None:
    with pytest.raises(acceptance_module.AcceptanceError, match="instance-id"):
        acceptance_module.seed_archive("#cloud-config\n", instance_id)


def test_runtime_plan_is_literal_private_and_has_no_host_mounts(
    acceptance_module,
    tmp_path: Path,
) -> None:
    root, _helper, _command = _source_fixture(tmp_path / "source")
    source = acceptance_module.load_source(root, "2222")
    plan = acceptance_module.build_plan(
        source=source,
        source_root=root,
        fixture_root=FIXTURE_ROOT,
        profile="vpn-cloud-final-ci-20260829",
        platform="linux/amd64",
    )

    assert plan.scope == "container-systemd-cloud-final-restart"
    assert plan.profile == "vpn-cloud-final-ci-20260829"
    assert plan.platform == "linux/amd64"
    assert plan.vm_arch == "x86_64"
    assert len(plan.cases) == 4
    assert [(case.distribution, case.mode) for case in plan.cases] == [
        ("debian13", "clean"),
        ("debian13", "interrupted"),
        ("ubuntu2404", "clean"),
        ("ubuntu2404", "interrupted"),
    ]
    for case in plan.cases:
        assert case.instance_id == f"vpn-cloud-final-{case.distribution}-{case.mode}"
        assert case.image_reference.endswith(
            "@sha256:" + BASE_IMAGES[f"{case.distribution}.Dockerfile"][1]
        )
        assert case.container_name.startswith("vpn-cloud-final-")
        assert case.platform == "linux/amd64"
        assert case.seed_sha256 == hashlib.sha256(case.seed).hexdigest()

    start = acceptance_module.colima_start_argv(plan)
    assert start == (
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
    create = acceptance_module.container_create_argv(
        plan.cases[0], "sha256:" + "a" * 64
    )
    assert "--privileged" in create
    assert "--cgroupns=host" in create
    assert "--platform=linux/amd64" in create
    assert "--network=none" in create
    assert "--tmpfs" in create
    assert not any(item in {"-v", "--volume", "--mount"} for item in create)
    assert create[-2:] == ("sha256:" + "a" * 64, "/lib/systemd/systemd")

    with pytest.raises(acceptance_module.AcceptanceError, match="platform"):
        acceptance_module.build_plan(
            source=source,
            source_root=root,
            fixture_root=FIXTURE_ROOT,
            profile="vpn-cloud-final-arm-refused-20260829",
            platform="linux/arm64",
        )


def test_inspection_contract_requires_exact_restart_and_no_replay(
    acceptance_module,
) -> None:
    first = acceptance_module.GuestObservation(
        machine_arch="x86_64",
        instance_id="vpn-cloud-final-debian13-interrupted",
        cloud_final_invocation="1" * 32,
        cloud_final_active="activating",
        cloud_final_result="success",
        runcmd_semaphore=True,
        scripts_user_semaphore=False,
        marker=False,
        barrier=True,
        attempt=1,
        config_sha256={},
        config_modes={},
        config_owners={},
        cloud_owner_safe=False,
        residue=(),
        effective={},
    )
    second = acceptance_module.GuestObservation(
        machine_arch="x86_64",
        instance_id=first.instance_id,
        cloud_final_invocation="2" * 32,
        cloud_final_active="inactive",
        cloud_final_result="success",
        runcmd_semaphore=True,
        scripts_user_semaphore=True,
        marker=True,
        barrier=True,
        attempt=2,
        config_sha256=acceptance_module._expected_config_digests("2222"),
        config_modes={"10": "0644", "20": "0644"},
        config_owners={"10": "0:0", "20": "0:0"},
        cloud_owner_safe=True,
        residue=(),
        effective={
            "port": "2222",
            "passwordauthentication": "no",
            "kbdinteractiveauthentication": "no",
            "permitrootlogin": "no",
            "pubkeyauthentication": "yes",
            "x11forwarding": "no",
        },
    )
    third = second._replace(cloud_final_invocation="3" * 32)

    acceptance_module.validate_interrupted(first, second, third, "2222")

    with pytest.raises(acceptance_module.AcceptanceError, match="third-replay"):
        acceptance_module.validate_interrupted(
            first, second, third._replace(attempt=3), "2222"
        )
    with pytest.raises(acceptance_module.AcceptanceError, match="config-mode"):
        acceptance_module.validate_interrupted(
            first._replace(
                config_sha256={**first.config_sha256, "50": "d" * 64},
                config_modes={**first.config_modes, "50": "0622"},
                config_owners={**first.config_owners, "50": "0:0"},
            ),
            second._replace(
                config_sha256={**second.config_sha256, "50": "c" * 64},
                config_modes={**second.config_modes, "50": "0622"},
                config_owners={**second.config_owners, "50": "0:0"},
            ),
            third,
            "2222",
        )


def test_evidence_is_explicitly_narrow_and_contains_no_guest_bytes(
    acceptance_module,
    tmp_path: Path,
) -> None:
    def case(distribution: str, mode: str) -> dict[str, object]:
        result: dict[str, object] = {
            "distribution": distribution,
            "mode": mode,
            "image_id": "sha256:" + "b" * 64,
            "package_versions": {
                "cloud-init": "24.4-1",
                "openssh-server": "1:9.9p2-1",
            },
            "first_invocation_sha256": "c" * 64,
            "seed_sha256": "f" * 64,
        }
        if mode == "interrupted":
            result.update(
                {
                    "second_invocation_sha256": "d" * 64,
                    "third_invocation_sha256": "e" * 64,
                }
            )
        return result

    cases = [
        case("debian13", "clean"),
        case("debian13", "interrupted"),
        case("ubuntu2404", "clean"),
        case("ubuntu2404", "interrupted"),
    ]
    evidence = acceptance_module.acceptance_evidence(
        source_sha256="a" * 64,
        platform="linux/amd64",
        vm_arch="x86_64",
        cases=cases,
    )
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["scope"] == "container-systemd-cloud-final-restart"
    assert evidence["platform"] == "linux/amd64"
    assert evidence["vm_arch"] == "x86_64"
    assert evidence["claims"] == {
        "container_systemd_cloud_final_restart": True,
        "native_amd64_vm": True,
        "kernel_reboot": False,
        "power_loss": False,
        "provider_first_boot": False,
    }
    assert "/etc/ssh" not in encoded
    assert "PasswordAuthentication" not in encoded
    assert "InvocationID" not in encoded
    with pytest.raises(acceptance_module.AcceptanceError, match="evidence"):
        acceptance_module.acceptance_evidence(
            source_sha256="a" * 64,
            platform="linux/amd64",
            vm_arch="x86_64",
            cases=[cases[0]],
        )
    with pytest.raises(acceptance_module.AcceptanceError, match="evidence"):
        acceptance_module.acceptance_evidence(
            source_sha256="a" * 64,
            platform="linux/amd64",
            vm_arch="x86_64",
            cases=list(reversed(cases)),
        )
    with pytest.raises(acceptance_module.AcceptanceError, match="evidence"):
        acceptance_module.acceptance_evidence(
            source_sha256="a" * 64,
            platform="linux/arm64",
            vm_arch="x86_64",
            cases=cases,
        )


class _FakeRuntime:
    def __init__(self, module, *, fail_case: str | None = None) -> None:
        self.module = module
        self.fail_case = fail_case
        self.events: list[str] = []
        self.context_reads = 0

    def current_context(self) -> str:
        self.context_reads += 1
        self.events.append("context")
        return "operator-context"

    def claim(self, plan) -> None:
        self.events.append("claim:" + plan.profile)

    def start(self, plan) -> None:
        self.events.append("start:" + plan.profile)

    def assert_no_host_mounts(self, plan) -> None:
        self.events.append("no-mounts:" + plan.profile)

    def build(self, plan, distribution: str):
        self.events.append("build:" + distribution)
        return self.module.BuiltImage(
            image_id="sha256:" + ("a" if distribution == "debian13" else "b") * 64,
            package_versions={
                "cloud-init": "24.4-1",
                "openssh-server": "1:9.9p2-1",
            },
        )

    def run_case(self, plan, case, image):
        self.events.append("case:" + case.distribution + ":" + case.mode)
        if self.fail_case == case.mode:
            raise RuntimeError("fixture failure")
        result = {
            "distribution": case.distribution,
            "mode": case.mode,
            "image_id": image.image_id,
            "package_versions": dict(image.package_versions),
            "first_invocation_sha256": "c" * 64,
            "seed_sha256": case.seed_sha256,
        }
        if case.mode == "interrupted":
            result.update(
                {
                    "second_invocation_sha256": "d" * 64,
                    "third_invocation_sha256": "e" * 64,
                }
            )
        return result

    def cleanup(self, plan) -> None:
        self.events.append("cleanup:" + plan.profile)

    def stop_delete(self, plan) -> None:
        self.events.append("stop-delete:" + plan.profile)


def test_execute_acceptance_serializes_distros_and_always_releases_profile(
    acceptance_module,
    tmp_path: Path,
) -> None:
    root, _helper, _command = _source_fixture(tmp_path / "source")
    source = acceptance_module.load_source(root, "2222")
    plan = acceptance_module.build_plan(
        source=source,
        source_root=root,
        fixture_root=FIXTURE_ROOT,
        profile="vpn-cloud-final-ci-20260829",
        platform="linux/amd64",
    )
    runtime = _FakeRuntime(acceptance_module)

    evidence = acceptance_module.execute_acceptance(plan, source, runtime)

    assert [event for event in runtime.events if event.startswith("build:")] == [
        "build:debian13",
        "build:ubuntu2404",
    ]
    assert [event for event in runtime.events if event.startswith("case:")] == [
        "case:debian13:clean",
        "case:debian13:interrupted",
        "case:ubuntu2404:clean",
        "case:ubuntu2404:interrupted",
    ]
    assert runtime.events[-3:] == [
        "cleanup:vpn-cloud-final-ci-20260829",
        "stop-delete:vpn-cloud-final-ci-20260829",
        "context",
    ]
    assert runtime.context_reads == 2
    assert len(evidence["cases"]) == 4


def test_execute_acceptance_cleans_up_after_case_failure(
    acceptance_module,
    tmp_path: Path,
) -> None:
    root, _helper, _command = _source_fixture(tmp_path / "source")
    source = acceptance_module.load_source(root, "2222")
    plan = acceptance_module.build_plan(
        source=source,
        source_root=root,
        fixture_root=FIXTURE_ROOT,
        profile="vpn-cloud-final-ci-20260829",
        platform="linux/amd64",
    )
    runtime = _FakeRuntime(acceptance_module, fail_case="interrupted")

    with pytest.raises(RuntimeError, match="fixture failure"):
        acceptance_module.execute_acceptance(plan, source, runtime)

    assert runtime.events[-3:] == [
        "cleanup:vpn-cloud-final-ci-20260829",
        "stop-delete:vpn-cloud-final-ci-20260829",
        "context",
    ]


def test_runtime_claim_requires_machine_gate_and_absent_owned_paths(
    acceptance_module,
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    output_parent = tmp_path / "evidence"
    home.mkdir(mode=0o700)
    output_parent.mkdir(mode=0o700)
    root, _helper, _command = _source_fixture(tmp_path / "source")
    source = acceptance_module.load_source(root, "2222")
    plan = acceptance_module.build_plan(
        source=source,
        source_root=root,
        fixture_root=FIXTURE_ROOT,
        profile="vpn-cloud-final-ci-20260829",
        platform="linux/amd64",
    )
    runtime = acceptance_module.DockerColimaRuntime(
        home=home, output=output_parent / "result.json"
    )

    monkeypatch.delenv("BUILD_GATE_HELD", raising=False)
    with pytest.raises(acceptance_module.AcceptanceError, match="build-gate-required"):
        runtime.claim(plan)

    monkeypatch.setenv("BUILD_GATE_HELD", "1")
    runtime.claim(plan)
    assert runtime.runtime_root == (
        home / ".cache/ripdpi-cloud-final-restart/vpn-cloud-final-ci-20260829"
    )
    assert not runtime.runtime_root.exists()

    profile = home / ".colima" / plan.profile
    profile.mkdir(parents=True)
    with pytest.raises(acceptance_module.AcceptanceError, match="profile-exists"):
        runtime.claim(plan)


def test_observation_parser_is_exact_and_evidence_write_never_overwrites(
    acceptance_module,
    tmp_path: Path,
) -> None:
    raw = json.dumps(
        {
            "instance_id": "vpn-cloud-final-debian13-clean",
            "machine_arch": "x86_64",
            "cloud_final_invocation": "1" * 32,
            "cloud_final_active": "active",
            "cloud_final_result": "success",
            "runcmd_semaphore": True,
            "scripts_user_semaphore": True,
            "marker": True,
            "barrier": False,
            "attempt": 0,
            "config_sha256": acceptance_module._expected_config_digests("2222"),
            "config_modes": {"10": "0644", "20": "0644"},
            "config_owners": {"10": "0:0", "20": "0:0"},
            "cloud_owner_safe": True,
            "residue": [],
            "effective": {
                "port": "2222",
                "passwordauthentication": "no",
                "kbdinteractiveauthentication": "no",
                "permitrootlogin": "no",
                "pubkeyauthentication": "yes",
                "x11forwarding": "no",
            },
        },
        separators=(",", ":"),
    ).encode()
    observation = acceptance_module.parse_observation(raw)
    acceptance_module._validate_converged(observation, "2222")

    invalid = json.loads(raw)
    invalid["raw_config"] = "PasswordAuthentication yes"
    with pytest.raises(acceptance_module.AcceptanceError, match="guest-observation"):
        acceptance_module.parse_observation(json.dumps(invalid).encode())

    output_parent = tmp_path / "private"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "evidence.json"
    evidence = acceptance_module.acceptance_evidence(
        source_sha256="a" * 64,
        platform="linux/amd64",
        vm_arch="x86_64",
        cases=[
            {
                "distribution": distribution,
                "mode": mode,
                "image_id": "sha256:" + "b" * 64,
                "package_versions": {
                    "cloud-init": "24.4-1",
                    "openssh-server": "1:9.9p2-1",
                },
                "first_invocation_sha256": "c" * 64,
                **(
                    {
                        "second_invocation_sha256": "d" * 64,
                        "third_invocation_sha256": "e" * 64,
                    }
                    if mode == "interrupted"
                    else {}
                ),
                "seed_sha256": "f" * 64,
            }
            for distribution, mode in (
                ("debian13", "clean"),
                ("debian13", "interrupted"),
                ("ubuntu2404", "clean"),
                ("ubuntu2404", "interrupted"),
            )
        ],
    )
    acceptance_module._write_evidence(output, evidence)
    before = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(acceptance_module.AcceptanceError, match="evidence-exists"):
        acceptance_module._write_evidence(output, evidence)
    assert output.read_bytes() == before


def _diagnostic_document(*, status_code: int = 2) -> dict[str, object]:
    return {
        "machine_arch": "x86_64",
        "instance_id_match": True,
        "cloud_init_status_code": status_code,
        "cloud_final_invocation_sha256": "1" * 64,
        "cloud_final_active": "failed",
        "cloud_final_substate": "failed",
        "cloud_final_result": "exit-code",
        "cloud_final_exec_code": "exited",
        "cloud_final_exec_status": 1,
        "runcmd_semaphore": True,
        "scripts_user_semaphore": False,
        "marker": False,
        "barrier": False,
        "attempt": 0,
        "fragment_states": {"10": "safe", "20": "absent", "50": "safe"},
        "cloud_result_state": "valid",
        "error_count": 1,
        "recoverable_error_count": 0,
        "runcmd_script_present": True,
    }


def test_cloud_final_diagnostic_is_exact_bounded_and_redacted(
    acceptance_module,
) -> None:
    document = _diagnostic_document()

    diagnostic = acceptance_module.parse_cloud_final_diagnostic(
        json.dumps(document, separators=(",", ":")).encode()
    )

    assert diagnostic.cloud_init_status_code == 2
    assert diagnostic.fragment_states == {"10": "safe", "20": "absent", "50": "safe"}
    forbidden = (
        "journal",
        "user-data",
        "PasswordAuthentication",
        "/etc/ssh",
        "datasource",
    )
    assert all(token not in json.dumps(diagnostic._asdict()) for token in forbidden)

    for key, value in (
        ("journal", "raw guest log"),
        ("user_data", "#cloud-config"),
        ("raw_config", "PasswordAuthentication yes"),
    ):
        invalid = dict(document)
        invalid[key] = value
        with pytest.raises(
            acceptance_module.AcceptanceError, match="cloud-final-diagnostic"
        ):
            acceptance_module.parse_cloud_final_diagnostic(json.dumps(invalid).encode())

    with pytest.raises(
        acceptance_module.AcceptanceError, match="cloud-final-diagnostic"
    ):
        acceptance_module.parse_cloud_final_diagnostic(b"{" + b" " * (65536 + 1))


def test_nonzero_cloud_init_status_preserves_redacted_guest_diagnostic(
    acceptance_module,
) -> None:
    runtime = object.__new__(acceptance_module.DockerColimaRuntime)
    case = type(
        "Case",
        (),
        {
            "distribution": "debian13",
            "mode": "clean",
            "container_name": "vpn-cloud-final-debian13-clean",
        },
    )()
    calls: list[str] = []

    def docker(*_args, **_kwargs):
        calls.append("status")
        return acceptance_module.CommandResult(2, b"ignored", b"secret diagnostic")

    diagnostic = acceptance_module.parse_cloud_final_diagnostic(
        json.dumps(_diagnostic_document()).encode()
    )
    runtime._docker = docker
    runtime._diagnose_cloud_final = lambda _case, status: (
        calls.append(f"diagnose:{status}") or diagnostic
    )
    runtime._poll_observation = lambda *_args, **_kwargs: pytest.fail(
        "strict success observation must not run after a nonzero cloud-init status"
    )

    with pytest.raises(
        acceptance_module.CloudFinalFailure, match="cloud-init-recoverable-error"
    ) as raised:
        runtime._wait_cloud_final(case)

    assert calls == ["status", "diagnose:2"]
    assert raised.value.distribution == "debian13"
    assert raised.value.mode == "clean"
    assert raised.value.diagnostic == diagnostic


def test_failure_evidence_is_explicitly_failed_and_contains_no_guest_output(
    acceptance_module,
) -> None:
    diagnostic = acceptance_module.parse_cloud_final_diagnostic(
        json.dumps(_diagnostic_document()).encode()
    )
    failure = acceptance_module.CloudFinalFailure(
        "cloud-init-recoverable-error", "debian13", "clean", diagnostic
    )

    evidence = acceptance_module.failure_evidence(
        source_sha256="a" * 64,
        platform="linux/amd64",
        vm_arch="x86_64",
        failure=failure,
    )
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["conclusion"] == "failure"
    assert evidence["category"] == "cloud-init-recoverable-error"
    assert evidence["distribution"] == "debian13"
    assert evidence["mode"] == "clean"
    assert not any(evidence["claims"].values())
    for forbidden in (
        "secret diagnostic",
        "journal",
        "user-data",
        "PasswordAuthentication",
        "/etc/ssh",
    ):
        assert forbidden not in encoded


def test_main_persists_private_failure_sidecar_after_cleanup(
    acceptance_module,
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_parent = tmp_path / "private"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "acceptance.json"
    diagnostic = acceptance_module.parse_cloud_final_diagnostic(
        json.dumps(_diagnostic_document()).encode()
    )
    failure = acceptance_module.CloudFinalFailure(
        "cloud-init-recoverable-error", "debian13", "clean", diagnostic
    )
    monkeypatch.setattr(
        acceptance_module,
        "load_source",
        lambda *_args: SimpleNamespace(helper_sha256="a" * 64),
    )
    monkeypatch.setattr(
        acceptance_module,
        "build_plan",
        lambda **_kwargs: SimpleNamespace(platform="linux/amd64", vm_arch="x86_64"),
    )
    monkeypatch.setattr(
        acceptance_module, "DockerColimaRuntime", lambda **_kwargs: object()
    )
    monkeypatch.setattr(
        acceptance_module,
        "execute_acceptance",
        lambda *_args: (_ for _ in ()).throw(failure),
    )

    result = acceptance_module.main(
        [
            "--source-root",
            str(tmp_path),
            "--fixture-root",
            str(FIXTURE_ROOT),
            "--output",
            str(output),
            "--profile",
            "vpn-cloud-final-ci-20260829",
        ]
    )

    failure_output = output_parent / "acceptance.json.failure.json"
    assert result == 1
    assert not output.exists()
    assert failure_output.stat().st_mode & 0o777 == 0o600
    persisted = json.loads(failure_output.read_bytes())
    assert persisted["category"] == "cloud-init-recoverable-error"
    assert persisted["diagnostic"] == _diagnostic_document()
