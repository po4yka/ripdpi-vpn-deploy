"""Operator CLI for vpn-deploy."""

from importlib.metadata import version as metadata_version
from pathlib import Path
import tomllib


def version():
    package = Path(__file__).resolve().parent
    manifest = package.parents[1] / "pyproject.toml"
    if package.parent.name == "src" and manifest.is_file():
        project = tomllib.loads(manifest.read_text())["project"]
        if project["name"] == "vpnd":
            return project["version"]
    return metadata_version("vpnd")
