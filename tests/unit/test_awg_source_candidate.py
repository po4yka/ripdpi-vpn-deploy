"""Portable admission and source-selection regressions; real traffic is separate."""

import importlib.util
import json
import subprocess
import sys
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
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "cleanup_container", lambda *args: calls.append(args))
    with pytest.raises(subprocess.TimeoutExpired):
        module.main()
    assert calls[-1][0] == ("docker", "--context", "fixture")
    assert calls[-1][1].startswith("ripdpi-awg-source-")
    assert calls[-1][2] is True


@pytest.mark.parametrize(
    "appears,remove_failure", [(True, False), (True, True), (False, False)]
)
def test_uncertain_start_cleanup_observes_late_creation_or_reports_unknown(
    tmp_path, appears, remove_failure
):
    module = runner()
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"inspect": 0, "remove_attempts": 0, "removed": False}))
    cli = tmp_path / "docker.py"
    cli.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        f"state = Path({str(state)!r})\n"
        "data = json.loads(state.read_text())\n"
        "assert sys.argv[-1] == 'ripdpi-awg-source-owned'\n"
        "if sys.argv[1:3] == ['container', 'inspect']:\n"
        "    data['inspect'] += 1\n"
        "    state.write_text(json.dumps(data))\n"
        f"    raise SystemExit(0 if {appears!r} and data['inspect'] >= 2 else 1)\n"
        "assert sys.argv[1:3] == ['rm', '-f']\n"
        "assert data['inspect'] >= 2\n"
        "data['remove_attempts'] += 1\nstate.write_text(json.dumps(data))\n"
        f"if {remove_failure!r} and data['remove_attempts'] == 1: raise SystemExit(1)\n"
        "data['removed'] = True\nstate.write_text(json.dumps(data))\n"
    )
    docker = (sys.executable, str(cli))
    if appears:
        module.cleanup_container(docker, "ripdpi-awg-source-owned", True, timeout=2)
        assert json.loads(state.read_text())["removed"] is True
        assert json.loads(state.read_text())["remove_attempts"] == (
            2 if remove_failure else 1
        )
    else:
        with pytest.raises(RuntimeError, match="cleanup is unconfirmed.*owned"):
            module.cleanup_container(
                docker, "ripdpi-awg-source-owned", True, timeout=0.1
            )
        assert json.loads(state.read_text())["removed"] is False


def test_candidate_is_separate_from_deployment_and_physical_policy():
    pins = json.loads(
        (ROOT / "tests/integration/awg_source_candidate/sources.json").read_text()
    )
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


def test_package_inputs_are_bound_to_one_signed_immutable_snapshot():
    directory = ROOT / "tests/integration/awg_source_candidate"
    fields = dict(
        line.split(": ", 1)
        for line in (directory / "ubuntu.sources").read_text().splitlines()
    )
    assert fields == {
        "Types": "deb",
        "URIs": "https://snapshot.ubuntu.com/ubuntu/20261015T000000Z/",
        "Suites": "noble noble-updates noble-security",
        "Components": "main universe",
        "Signed-By": "/usr/share/keyrings/ubuntu-archive-keyring.gpg",
    }
    assert "tests/integration/awg_source_candidate/ubuntu.sources" in runner().FILES
    dockerfile = (directory / "Dockerfile").read_text()
    assert (
        "ADD --checksum=sha256:641de77d8f142cfd62a1a6f964ba67b20754d3337c480efb529d086075a06c9a"
        in dockerfile
    )
    assert (
        "https://snapshot.ubuntu.com/ubuntu/20261015T000000Z/pool/main/c/ca-certificates/ca-certificates_20240203_all.deb"
        in dockerfile
    )
    assert dockerfile.index(
        "/etc/apt/sources.list.d/ubuntu.sources"
    ) < dockerfile.index("apt-get update")


def test_source_cache_symlink_refuses_before_context_copy(monkeypatch, tmp_path):
    module = runner()
    pins = json.loads(
        (ROOT / "tests/integration/awg_source_candidate/sources.json").read_text()
    )
    (tmp_path / "tests/integration/awg_source_candidate").mkdir(parents=True)
    (tmp_path / "tests/integration/awg_source_candidate/sources.json").write_text(
        json.dumps(pins)
    )
    cache = tmp_path / ".cache/awg-source-candidate"
    cache.mkdir(parents=True, mode=0o700)
    foreign = tmp_path / "foreign-input"
    foreign.write_text("unrelated private fixture bytes")
    (cache / f"go-{pins['baseline']['go']['commit']}.bundle").symlink_to(foreign)
    work = tmp_path / "context"
    work.mkdir()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "verify_upstream_sources", lambda *args: None)
    monkeypatch.setattr(
        module,
        "run",
        lambda *args, **kwargs: pytest.fail("unsafe cache reached a command"),
    )
    with pytest.raises(RuntimeError, match="unsafe ownership"):
        module.prepare_sources(work)
    assert not list((work / "sources").iterdir())
    assert foreign.read_text() == "unrelated private fixture bytes"


def test_warm_bundle_cache_revalidates_current_lightweight_and_annotated_tags(
    tmp_path, monkeypatch, isolated_synthetic_git_config
):
    module = runner()
    repository = tmp_path / "remote"
    repository.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repository), *args], text=True, stderr=subprocess.PIPE
        ).strip()

    git("init")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    source = repository / "source"
    source.write_text("reviewed")
    git("add", "source")
    git("commit", "-m", "fixture")
    reviewed = git("rev-parse", "HEAD")
    git("tag", "baseline")
    git("tag", "-a", "candidate", "-m", "annotated fixture")
    root = tmp_path / "workspace"
    (root / "tests/integration/awg_source_candidate").mkdir(parents=True)
    pins = {
        pair: {part: {"tag": pair, "commit": reviewed} for part in ("go", "tools")}
        for pair in ("baseline", "candidate")
    }
    (root / "tests/integration/awg_source_candidate/sources.json").write_text(
        json.dumps(pins)
    )
    cache = root / ".cache/awg-source-candidate"
    cache.mkdir(parents=True, mode=0o700)
    for component in ("go", "tools"):
        git("bundle", "create", str(cache / f"{component}-{reviewed}.bundle"), "--all")
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "source_repository", lambda component: str(repository))
    first = tmp_path / "first"
    first.mkdir()
    module.prepare_sources(first)
    assert len(list((first / "sources").glob("*.bundle"))) == 4
    source.write_text("moved")
    git("commit", "-am", "move fixture ref")
    git("tag", "-f", "candidate")
    second = tmp_path / "second"
    second.mkdir()
    with pytest.raises(RuntimeError, match="upstream tag moved"):
        module.prepare_sources(second)
    assert not (second / "sources").exists()


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
    pins = json.loads(
        (ROOT / "tests/integration/awg_source_candidate/sources.json").read_text()
    )
    cohort = yaml.safe_load(
        (
            ROOT / "ansible/roles/amneziawg/vars/cohorts/narrow-junk-sequential.yml"
        ).read_text()
    )["amneziawg_cohort"]
    assert pins["wire_shapes"][1] == cohort
