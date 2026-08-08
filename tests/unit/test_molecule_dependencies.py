"""Fail-closed checks for Molecule's offline dependency contract."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_role_molecule_requirements_file_exists_from_role_cwd() -> None:
    configs = sorted(
        (REPO_ROOT / "ansible" / "roles").glob("*/molecule/*/molecule.yml")
    )
    assert configs

    for config_path in configs:
        config = yaml.safe_load(config_path.read_text())
        options = (config.get("dependency") or {}).get("options", {})
        for option in ("requirements-file", "role-file"):
            requirements = options.get(option)
            assert requirements, f"{config_path}: missing dependency option {option}"
            role_working_directory = config_path.parents[2]
            resolved = (role_working_directory / requirements).resolve()
            assert resolved.is_file(), f"{config_path}: missing {resolved}"


def test_molecule_driver_collection_is_pinned_before_scenarios_run() -> None:
    requirements = yaml.safe_load((REPO_ROOT / "requirements.yml").read_text())
    collections = {
        item["name"]: item["version"] for item in requirements["collections"]
    }

    assert collections["community.docker"] == "5.2.0"
