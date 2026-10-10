#!/usr/bin/env python3
"""Emit and validate the release SBOM against the immutable Python runtime lock."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def locked_components(path):
    return {
        name.lower().replace("_", "-"): version
        for name, version in re.findall(
            r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", path.read_text(), re.MULTILINE
        )
    }


def runtime_dependency_graph(directory, expected):
    """Read the dependency graph from hash-verified native runtime wheels."""
    graph = {}
    for wheel in sorted(directory.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            candidates = [
                name for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(candidates) != 1:
                raise ValueError("runtime wheel metadata is ambiguous")
            metadata = BytesParser().parsebytes(archive.read(candidates[0]))
        name = metadata["Name"].lower().replace("_", "-")
        if name in graph or expected.get(name) != metadata["Version"]:
            raise ValueError("runtime wheel inventory differs from the lock")
        dependencies = set()
        for declaration in metadata.get_all("Requires-Dist", []):
            requirement = Requirement(declaration)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            dependency = requirement.name.lower().replace("_", "-")
            if (
                dependency not in expected
                or expected[dependency] not in requirement.specifier
                or requirement.url
            ):
                raise ValueError("runtime wheel dependency closure differs from the lock")
            dependencies.add(dependency)
        graph[name] = sorted(dependencies)
    if set(graph) != set(expected):
        raise ValueError("runtime wheel inventory is incomplete")
    return graph


def locked_dependency_graph(directory, lock, expected):
    wheels = directory / "wheels"
    wheels.mkdir()
    subprocess.run(
        [
            os.sys.executable, "-m", "pip", "download", "--require-hashes",
            "--only-binary=:all:", "--no-deps", "-r", str(lock),
            "--dest", str(wheels),
        ],
        check=True,
    )
    return runtime_dependency_graph(wheels, expected)


def emit(output):
    lock = ROOT / "vpnd/requirements.txt"
    before = hashlib.sha256(lock.read_bytes()).digest()
    project = ROOT / "vpnd/pyproject.toml"
    metadata = tomllib.loads(project.read_text())["project"]
    expected = locked_components(lock)
    direct = {}
    for dependency in metadata.get("dependencies", []):
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", dependency)
        if match is None:
            raise ValueError("application dependencies must be exact version pins")
        name, version = match.groups()
        name = name.lower().replace("_", "-")
        if expected.get(name) != version:
            raise ValueError("application dependencies and runtime lock differ")
        direct[name] = version
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vpnd-sbom-") as directory:
        graph = locked_dependency_graph(Path(directory), lock, expected)
        candidate = Path(directory) / "sbom.json"
        subprocess.run(
            [
                os.sys.executable,
                "-m",
                "cyclonedx_py",
                "requirements",
                str(lock),
                "--pyproject",
                str(project),
                "--spec-version",
                "1.5",
                "--output-reproducible",
                "--output-file",
                str(candidate),
            ],
            check=True,
        )
        document = json.loads(candidate.read_text())
        component = document["metadata"]["component"]
        actual = {
            entry["name"].lower().replace("_", "-"): entry["version"]
            for entry in document["components"]
        }
        if (
            document["bomFormat"] != "CycloneDX"
            or document["specVersion"] != "1.5"
            or component["name"] != "vpnd"
            or component["version"] != metadata["version"]
            or actual != locked_components(lock)
            or len(document["components"]) != len(expected)
            or not document["dependencies"]
            or any(
                not item.get("purl", "").startswith("pkg:pypi/")
                for item in document["components"]
            )
            or hashlib.sha256(lock.read_bytes()).digest() != before
        ):
            raise ValueError("SBOM does not match the immutable vpnd package/lock")
        references = {
            entry["name"].lower().replace("_", "-"): entry["bom-ref"]
            for entry in document["components"]
        }
        root_reference = component.get("bom-ref", "root-component")
        component["bom-ref"] = root_reference
        root_dependencies = {
            "ref": root_reference,
            "dependsOn": sorted(references[name] for name in direct),
        }
        document["dependencies"] = [
            {"ref": references[name], "dependsOn": sorted(references[dep] for dep in graph[name])}
            for name in sorted(graph)
        ] + [root_dependencies]
        candidate.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n")
        handle, temporary = tempfile.mkstemp(prefix=".sbom-", dir=output.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(candidate.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
        finally:
            Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist/sbom.json")
    arguments = parser.parse_args()
    emit(arguments.out)
