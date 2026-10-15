"""Portable admission and source-selection regressions; real traffic is separate."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def runner():
    spec = importlib.util.spec_from_file_location(
        "awg_source_candidate_runner", ROOT / "scripts/test-awg-source-candidate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refuses_ungated_execution_before_docker(monkeypatch):
    monkeypatch.delenv("BUILD_GATE_HELD", raising=False)
    with pytest.raises(SystemExit, match="build-gate"):
        runner().main()


@pytest.mark.parametrize(
    "endpoint,override",
    [
        ("ssh://example.invalid", None),
        ("tcp://127.0.0.1:2375", None),
        ("unix:///var/run/docker.sock", "ssh://example.invalid"),
    ],
)
def test_remote_daemon_refuses_before_build(monkeypatch, endpoint, override):
    module = runner()
    monkeypatch.setenv("BUILD_GATE_HELD", "1")
    if override:
        monkeypatch.setenv("DOCKER_HOST", override)
    else:
        monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *a, **k: json.dumps(
            [{"Name": "fixture", "Endpoints": {"docker": {"Host": endpoint}}}]
        ),
    )
    monkeypatch.setattr(
        module, "run", lambda *a, **k: pytest.fail("remote context reached mutation")
    )
    with pytest.raises(SystemExit, match="local Unix-socket"):
        module.main()


def test_remote_buildkit_refuses_before_context_copy_or_build(monkeypatch):
    module = runner()
    monkeypatch.setenv("BUILD_GATE_HELD", "1")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda args, **kwargs: (
            json.dumps(
                [
                    {
                        "Name": "fixture",
                        "Endpoints": {"docker": {"Host": "unix:///run/docker.sock"}},
                    }
                ]
            )
            if args[1] == "context"
            else "Driver: remote\nEndpoint: tcp://example.invalid:1234\n"
        ),
    )
    monkeypatch.setattr(
        module,
        "run",
        lambda *args, **kwargs: pytest.fail("remote builder reached mutation"),
    )
    with pytest.raises(SystemExit, match="local Docker engine builder"):
        module.main()


def test_cleanup_owned_container_after_acceptance_failure(monkeypatch):
    module = runner()
    monkeypatch.setenv("BUILD_GATE_HELD", "1")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda args, **k: (
            json.dumps(
                [
                    {
                        "Name": "fixture",
                        "Endpoints": {"docker": {"Host": "unix:///run/docker.sock"}},
                    }
                ]
            )
            if args[1] == "context"
            else "Driver: docker\nEndpoint: fixture\n"
            if args[1] == "buildx"
            else "owned-container-id\n"
        ),
    )
    monkeypatch.setattr(module, "prepare_sources", lambda work: None)
    calls = []

    def execute(*args, **kwargs):
        calls.append(args)
        if args[-1] == "/lab/acceptance.py":
            raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(module, "run", execute)
    with pytest.raises(subprocess.CalledProcessError):
        module.main()
    assert calls[-1] == (
        "docker",
        "--context",
        "fixture",
        "rm",
        "-f",
        "owned-container-id",
    )
    assert all("foreign" not in " ".join(args) for args in calls)


def test_startup_timeout_retains_unique_cleanup_identity(monkeypatch):
    module = runner()
    monkeypatch.setenv("BUILD_GATE_HELD", "1")
    monkeypatch.delenv("DOCKER_HOST", raising=False)

    def output(args, **kwargs):
        if args[1] == "context":
            return json.dumps(
                [
                    {
                        "Name": "fixture",
                        "Endpoints": {"docker": {"Host": "unix:///run/docker.sock"}},
                    }
                ]
            )
        if args[1] == "buildx":
            return "Driver: docker\nEndpoint: fixture\n"
        raise subprocess.TimeoutExpired(args, 60)

    monkeypatch.setattr(module.subprocess, "check_output", output)
    monkeypatch.setattr(module, "prepare_sources", lambda work: None)
    calls = []
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(subprocess.TimeoutExpired):
        module.main()
    assert calls[-1][:5] == ("docker", "--context", "fixture", "rm", "-f")
    assert calls[-1][5].startswith("ripdpi-awg-source-")


def test_candidate_is_separate_from_deployment_and_physical_policy():
    pins = json.loads((ROOT / "contract/awg-source-candidate.json").read_text())
    deployment = yaml.safe_load(
        (ROOT / "secrets/prod.secrets.example.yaml").read_text()
    )
    for part in ("go", "tools"):
        assert pins["baseline"][part]["tag"] == deployment[f"amneziawg_{part}_version"]
        assert (
            pins["baseline"][part]["commit"] == deployment[f"amneziawg_{part}_commit"]
        )
        assert len(pins["candidate"][part]["commit"]) == 40
    assert pins["eligibility"]["production"] is False
    assert pins["eligibility"]["go_release"] is None
    physical = json.loads(
        (ROOT / "contract/amneziawg-arm64-version-floor.json").read_text()
    )
    assert physical["guard_required"] is True
    assert physical["verified_safe_floor"] is None


def test_explicit_public_build_context_excludes_private_inputs():
    module = runner()
    for relative in module.FILES:
        assert (ROOT / relative).is_file()
        assert relative.startswith(
            ("contract/", "tests/integration/", "ansible/roles/")
        )
        assert "secrets/" not in relative
    dockerfile = (
        ROOT / "tests/integration/awg_source_candidate/Dockerfile"
    ).read_text()
    assert "COPY . " not in dockerfile


def test_source_cache_symlink_refuses_before_context_copy(monkeypatch, tmp_path):
    module = runner()
    pins = json.loads((ROOT / "contract/awg-source-candidate.json").read_text())
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract/awg-source-candidate.json").write_text(json.dumps(pins))
    cache = tmp_path / ".cache/awg-source-candidate"
    cache.mkdir(parents=True, mode=0o700)
    foreign = tmp_path / "foreign-input"
    foreign.write_text("unrelated private fixture bytes")
    (cache / f"go-{pins['baseline']['go']['commit']}.bundle").symlink_to(foreign)
    work = tmp_path / "context"
    work.mkdir()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module,
        "run",
        lambda *args, **kwargs: pytest.fail("unsafe cache reached a command"),
    )
    with pytest.raises(RuntimeError, match="unsafe ownership"):
        module.prepare_sources(work)
    assert not list((work / "sources").iterdir())
    assert foreign.read_text() == "unrelated private fixture bytes"


def builder():
    spec = importlib.util.spec_from_file_location(
        "awg_source_candidate_builder",
        ROOT / "tests/integration/awg_source_candidate/build.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_admission_rejects_drift_and_dirty_real_checkout(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    source = tmp_path / "source.go"
    source.write_text("package main\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "source.go"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    head = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    module = builder()
    module.verify_source(tmp_path, head)
    with pytest.raises(ValueError, match="moved upstream tag"):
        module.verify_source(tmp_path, "0" * 40)
    source.write_text("changed source\n")
    with pytest.raises(subprocess.CalledProcessError):
        module.verify_source(tmp_path, head)


def test_toolchain_digest_rejects_corrupted_bytes(tmp_path):
    module = builder()
    archive = tmp_path / "compiler.tar.gz"
    archive.write_bytes(b"corrupted archive")
    with pytest.raises(ValueError, match="toolchain checksum mismatch"):
        module.verify_digest(archive, "0" * 64)


def test_narrow_wire_shape_matches_canonical_cohort():
    pins = json.loads((ROOT / "contract/awg-source-candidate.json").read_text())
    cohort = yaml.safe_load(
        (
            ROOT / "ansible/roles/amneziawg/vars/cohorts/narrow-junk-sequential.yml"
        ).read_text()
    )["amneziawg_cohort"]
    assert pins["wire_shapes"][1] == cohort
