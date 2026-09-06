"""CI caches preserve pinned installs and consolidated validator coverage."""

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]
SETUP = "./.github/actions/setup-ci-python"
GALAXY_JOBS = {"ansible", "molecule", "molecule-failure-scenarios", "molecule-full-stack"}
PYTHON_JOBS = GALAXY_JOBS | {"python-validators", "unit-tests", "native-runtime"}
VALIDATORS = {
    "yamllint -c .yamllint.yml .",
    "python3 scripts/check-secrets-coverage.py",
    "python3 scripts/check-templates-render.py",
    "python3 scripts/check-xray-breaking-changes.py",
    "python3 scripts/render-snapshots.py",
    "python3 scripts/validate-secrets.py",
    "python3 scripts/validate-bundle.py",
}
OLD_CONTEXTS = {
    "yamllint", "secrets-coverage", "templates-render", "jinja snapshot diff",
    "secrets schema (lenient on example)",
}


def test_all_ci_python_consumers_share_the_pinned_cached_install():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    consumers = {
        name: [step for step in job.get("steps", []) if step.get("uses") == SETUP]
        for name, job in jobs.items()
    }
    assert {name for name, steps in consumers.items() if steps} == PYTHON_JOBS
    for name in PYTHON_JOBS:
        assert len(consumers[name]) == 1
        assert consumers[name][0].get("with", {}).get("galaxy", "false") == (
            "true" if name in GALAXY_JOBS else "false"
        )
        if name in GALAXY_JOBS:
            assert jobs[name]["env"]["ANSIBLE_COLLECTIONS_PATH"] == "${{ github.workspace }}/.ansible/collections"
    assert not any(
        "pip install" in step.get("run", "")
        for job in jobs.values() for step in job.get("steps", [])
    )


def test_cache_keys_follow_locks_and_never_skip_dependency_validation():
    action = yaml.safe_load((ROOT / ".github/actions/setup-ci-python/action.yml").read_text())
    steps = action["runs"]["steps"]
    python = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
    assert python["with"] == {
        "python-version": "3.12", "cache": "pip", "cache-dependency-path": "requirements.txt",
    }
    pip = next(step for step in steps if "pip install" in step.get("run", ""))
    assert "if" not in pip
    assert pip["run"] == "python -m pip install --require-hashes --no-deps -r requirements.txt"
    cache = next(step for step in steps if step.get("uses", "").startswith("actions/cache@"))
    assert re.fullmatch(r"actions/cache@[0-9a-f]{40}", cache["uses"])
    assert cache["with"]["path"] == "${{ github.workspace }}/.ansible/collections"
    key = cache["with"]["key"]
    for value in ("runner.os", "runner.arch", "steps.python.outputs.python-version",
                  "hashFiles('requirements.txt', 'requirements.yml')"):
        assert value in key
    assert "restore-keys" not in cache["with"]
    galaxy = next(step for step in steps if "ansible-galaxy collection install" in step.get("run", ""))
    assert galaxy["if"] == "inputs.galaxy == 'true'"
    assert '--collections-path "$ANSIBLE_COLLECTIONS_PATH"' in galaxy["run"]
    assert "exit 1" in galaxy["run"]
    assert galaxy["env"]["ANSIBLE_COLLECTIONS_PATH"] == cache["with"]["path"]


def test_combined_validators_preserve_every_check_and_required_context():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    job = jobs["python-validators"]
    assert "python-validators" in jobs["required"]["needs"]
    assert "if" not in job and "continue-on-error" not in job
    steps = job["steps"]
    for command in VALIDATORS:
        matching = [step for step in steps if step.get("run") == command]
        assert len(matching) == 1
        assert matching[0]["if"] == "${{ !cancelled() }}"
        assert "continue-on-error" not in matching[0]
    assert not OLD_CONTEXTS.intersection(item.get("name") for item in jobs.values())
    protection = (ROOT / ".github/workflows/branch-protection.yml").read_text()
    assert f'"{job["name"]}"' in protection
    assert not any(f'"{name}"' in protection for name in OLD_CONTEXTS)
