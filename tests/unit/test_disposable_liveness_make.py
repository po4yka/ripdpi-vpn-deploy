"""Canonical Make boundary for the disposable liveness executor."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOALS = (
    "prepare-disposable-liveness",
    "install-disposable-liveness-sentinel",
    "protocol-liveness-disposable",
    "deonboard-disposable-liveness",
)
GOAL_FIELDS = {
    "prepare-disposable-liveness": {"EXECUTOR_PROFILE", "EXECUTOR_MANIFEST"},
    "install-disposable-liveness-sentinel": {
        "LIVENESS_CONFIG",
        "SENTINEL",
        "CLIENT",
        "EXECUTOR_MANIFEST",
        "EXECUTOR_BINDING",
        "STAGING_CLEANUP_MANIFEST",
    },
    "protocol-liveness-disposable": {
        "LIVENESS_CONFIG",
        "EXECUTOR_MANIFEST",
        "EXECUTOR_BINDING",
    },
    "deonboard-disposable-liveness": {
        "EXECUTOR_MANIFEST",
        "EXECUTOR_BINDING",
        "STAGING_POST_DESTROY_EVIDENCE",
        "LIVENESS_SENTINEL_REGISTRY",
        "LIVENESS_CONFIG",
        "SOPS_FILE",
        "DEONBOARD_EVIDENCE",
    },
}


def _workspace(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    tools = tmp_path / "bin"
    scripts.mkdir(parents=True)
    tools.mkdir()
    shutil.copy2(ROOT / "Makefile", root / "Makefile")

    logger = """#!/usr/bin/env python3
import json
import os
import sys

record = {
    "program": os.path.basename(sys.argv[0]),
    "argv": sys.argv[1:],
    "build_gate_held": os.environ.get("BUILD_GATE_HELD"),
    "source_revision": os.environ.get("DEPLOY_SOURCE_REVISION"),
    "source_digest": os.environ.get("DEPLOYABLE_SOURCE_DIGEST"),
}
if record["program"] == "install_liveness_sentinel.py":
    record["stdin"] = sys.stdin.read()
with open(os.environ["DISPOSABLE_MAKE_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, sort_keys=True) + "\\n")
"""
    for name in (
        "disposable_liveness_executor.py",
        "install_liveness_sentinel.py",
        "protocol-liveness.py",
    ):
        path = scripts / name
        path.write_text(logger)
        path.chmod(0o755)

    identity = scripts / "deploy-source-identity.sh"
    identity.write_text('#!/usr/bin/env bash\nprintf called >> "$DISPOSABLE_GIT_SPY"\n')
    identity.chmod(0o755)

    gate = tools / "build-gate"
    gate.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        '[[ "${1:-}" == -- ]] && shift\n'
        "printf 'called\\n' >> \"$DISPOSABLE_GATE_LOG\"\n"
        "export BUILD_GATE_HELD=1\n"
        'exec "$@"\n'
    )
    gate.chmod(0o755)

    env = os.environ.copy()
    for field in (
        "EXECUTOR_PROFILE",
        "EXECUTOR_MANIFEST",
        "EXECUTOR_BINDING",
        "STAGING_CLEANUP_MANIFEST",
        "STAGING_POST_DESTROY_EVIDENCE",
        "DEONBOARD_EVIDENCE",
        "LIVENESS_CONFIG",
        "LIVENESS_SENTINEL_REGISTRY",
        "SENTINEL",
        "CLIENT",
        "SOPS_FILE",
        "HOSTS",
        "COHORTS",
        "SOPS_FILES",
    ):
        env.pop(field, None)
    env.update(
        {
            "PATH": str(tools) + os.pathsep + env["PATH"],
            "HOME": str(tmp_path / "home"),
            "DISPOSABLE_MAKE_LOG": str(tmp_path / "commands.jsonl"),
            "DISPOSABLE_GATE_LOG": str(tmp_path / "gate.log"),
            "DISPOSABLE_GIT_SPY": str(tmp_path / "git-spy.log"),
        }
    )
    return root, env


def _fields(tmp_path: Path) -> dict[str, str]:
    private = tmp_path / "private"
    return {
        "EXECUTOR_PROFILE": "vpn-liveness-one-shot",
        "EXECUTOR_MANIFEST": str(private / "executor.json"),
        "EXECUTOR_BINDING": str(private / "binding.json"),
        "STAGING_CLEANUP_MANIFEST": str(private / "cleanup.json"),
        "STAGING_POST_DESTROY_EVIDENCE": str(private / "absence.json"),
        "DEONBOARD_EVIDENCE": str(private / "deonboard.json"),
        "LIVENESS_CONFIG": str(private / "liveness.yaml"),
        "LIVENESS_SENTINEL_REGISTRY": str(private / "registry.json"),
        "SENTINEL": "disposable-consumer",
        "CLIENT": "disposable-consumer-client",
        "SOPS_FILE": str(private / "prod.sops.yaml"),
    }


def _run(
    root: Path,
    env: dict[str, str],
    goal: str,
    fields: dict[str, str],
    *,
    stdin: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "make",
            goal,
            *(
                f"{key}={value}"
                for key, value in fields.items()
                if key in GOAL_FIELDS[goal]
            ),
        ],
        cwd=root,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=20,
    )


def _record(tmp_path: Path) -> dict[str, object]:
    lines = (tmp_path / "commands.jsonl").read_text().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


@pytest.mark.parametrize("goal", GOALS)
def test_make_rejects_unowned_command_variable_before_expansion(
    tmp_path: Path, goal: str
) -> None:
    root, env = _workspace(tmp_path)
    marker = tmp_path / "unowned-expanded"
    result = subprocess.run(
        ["make", goal, f"UNOWNED=$(shell touch {marker})"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "only its documented command-line fields" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "commands.jsonl").exists()
    assert not (tmp_path / "git-spy.log").exists()


@pytest.mark.parametrize("goal", GOALS)
@pytest.mark.parametrize("value", ["$(shell touch MARKER)", "'quoted", '"quoted'])
def test_make_rejects_nonliteral_owned_fields_before_any_child(
    tmp_path: Path, goal: str, value: str
) -> None:
    root, env = _workspace(tmp_path)
    marker = tmp_path / "owned-expanded"
    fields = _fields(tmp_path)
    fields["EXECUTOR_MANIFEST"] = value.replace("MARKER", str(marker))

    result = _run(root, env, goal, fields)

    assert result.returncode != 0
    assert "inputs must be literal values" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "commands.jsonl").exists()
    assert not (tmp_path / "git-spy.log").exists()


@pytest.mark.parametrize(
    "goals",
    [
        ["prepare-disposable-liveness", "help"],
        ["protocol-liveness-disposable", "protocol-liveness-disposable"],
        ["install-disposable-liveness-sentinel", "deonboard-disposable-liveness"],
    ],
)
def test_make_requires_one_disposable_goal_before_any_child(
    tmp_path: Path, goals: list[str]
) -> None:
    root, env = _workspace(tmp_path)
    result = subprocess.run(
        ["make", *goals], cwd=root, env=env, text=True, capture_output=True
    )

    assert result.returncode != 0
    assert "requires exactly one Make goal" in result.stderr
    assert not (tmp_path / "commands.jsonl").exists()
    assert not (tmp_path / "git-spy.log").exists()


def test_prepare_uses_the_machine_gate_and_fixed_six_hour_lease(tmp_path: Path) -> None:
    root, env = _workspace(tmp_path)
    fields = _fields(tmp_path)

    result = _run(root, env, "prepare-disposable-liveness", fields)

    assert result.returncode == 0, result.stderr
    record = _record(tmp_path)
    assert record == {
        "argv": [
            "prepare",
            "--profile",
            fields["EXECUTOR_PROFILE"],
            "--manifest",
            fields["EXECUTOR_MANIFEST"],
            "--ttl-seconds",
            "21600",
        ],
        "build_gate_held": "1",
        "program": "disposable_liveness_executor.py",
        "source_digest": "",
        "source_revision": "",
    }
    assert (tmp_path / "gate.log").read_text() == "called\n"
    assert not (tmp_path / "git-spy.log").exists()


def test_install_passes_exact_binding_and_private_key_only_on_stdin(
    tmp_path: Path,
) -> None:
    root, env = _workspace(tmp_path)
    fields = _fields(tmp_path)

    result = _run(
        root,
        env,
        "install-disposable-liveness-sentinel",
        fields,
        stdin="synthetic-awg-private-key\n",
    )

    assert result.returncode == 0, result.stderr
    record = _record(tmp_path)
    assert record["argv"] == [
        "--config",
        fields["LIVENESS_CONFIG"],
        "--sentinel",
        fields["SENTINEL"],
        "--client",
        fields["CLIENT"],
        "--awg-private-key-stdin",
        "--executor-manifest",
        fields["EXECUTOR_MANIFEST"],
        "--executor-binding",
        fields["EXECUTOR_BINDING"],
        "--cleanup-manifest",
        fields["STAGING_CLEANUP_MANIFEST"],
    ]
    assert record["stdin"] == "synthetic-awg-private-key\n"
    assert record["build_gate_held"] is None
    assert not (tmp_path / "gate.log").exists()
    assert not (tmp_path / "git-spy.log").exists()


def test_protocol_evaluates_only_the_exact_private_binding(tmp_path: Path) -> None:
    root, env = _workspace(tmp_path)
    fields = _fields(tmp_path)

    result = _run(root, env, "protocol-liveness-disposable", fields)

    assert result.returncode == 0, result.stderr
    record = _record(tmp_path)
    assert record["argv"] == [
        "--config",
        fields["LIVENESS_CONFIG"],
        "--executor-manifest",
        fields["EXECUTOR_MANIFEST"],
        "--executor-binding",
        fields["EXECUTOR_BINDING"],
    ]
    assert record["build_gate_held"] is None
    assert not (tmp_path / "gate.log").exists()
    assert not (tmp_path / "git-spy.log").exists()


def test_deonboard_is_gated_and_requires_exact_provider_absence(tmp_path: Path) -> None:
    root, env = _workspace(tmp_path)
    fields = _fields(tmp_path)

    result = _run(root, env, "deonboard-disposable-liveness", fields)

    assert result.returncode == 0, result.stderr
    record = _record(tmp_path)
    assert record["argv"] == [
        "deonboard",
        "--binding",
        fields["EXECUTOR_BINDING"],
        "--manifest",
        fields["EXECUTOR_MANIFEST"],
        "--absence-evidence",
        fields["STAGING_POST_DESTROY_EVIDENCE"],
        "--registry",
        fields["LIVENESS_SENTINEL_REGISTRY"],
        "--config",
        fields["LIVENESS_CONFIG"],
        "--sops-file",
        fields["SOPS_FILE"],
        "--output",
        fields["DEONBOARD_EVIDENCE"],
    ]
    assert record["build_gate_held"] == "1"
    assert (tmp_path / "gate.log").read_text() == "called\n"
    assert not (tmp_path / "git-spy.log").exists()


def test_makefile_declares_every_disposable_goal_phony() -> None:
    makefile = (ROOT / "Makefile").read_text()
    phony = " ".join(
        line.strip().removesuffix("\\")
        for line in makefile.splitlines()
        if line.startswith(".PHONY:") or line.startswith("        ")
    )
    for goal in GOALS:
        assert goal in phony
