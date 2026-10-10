#!/usr/bin/env python3
"""Preserve repository-relative paths in mutmut's generated execution tree."""

import sys
import tomllib
from pathlib import Path

import tomli_w


def prepare(root):
    package = root / "vpnd/pyproject.toml"
    metadata = tomllib.loads(package.read_text())
    configuration = metadata["tool"]["mutmut"]
    selected = configuration["source_paths"]
    patterns = []
    for value in selected:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("mutation source paths must stay inside vpnd")
        source = root / "vpnd" / path
        if not source.exists():
            raise ValueError("mutation source input is missing")
        patterns.append(path.as_posix() + ("/*" if source.is_dir() else ""))
    # Offline distribution acceptance deliberately seals out mutation tooling;
    # instrumented source imports mutmut and cannot satisfy that artifact gate.
    # Keep those new tests in the complete ordinary/package lanes, while every
    # transferred Rust test remains eligible for mutation statistics/execution.
    ignored = []
    for name in ("test_delivery_installer.py", "test_delivery_builder.py"):
        artifact_test = root / "vpnd/tests" / name
        if artifact_test.exists():
            if "# Rust test:" in artifact_test.read_text():
                raise ValueError(
                    "cannot exclude an inherited test from mutation checks"
                )
            ignored.append(f"--ignore=vpnd/tests/{name}")
    copied = [
        "vpnd/tests",
        "vpnd/config",
        "vpnd/templates",
        "vpnd/pyproject.toml",
        "vpnd/requirements.txt",
        "scripts",
        "docs",
        "tests/fixtures",
    ]
    if any(not (root / path).exists() for path in copied):
        raise ValueError("required mutation input is missing")
    target = root / "pyproject.toml"
    if target.exists():
        raise ValueError("scratch root already has a project configuration")
    source_alias = root / "src"
    if source_alias.exists():
        raise ValueError("scratch root source projection already exists")
    source_alias.symlink_to("vpnd/src", target_is_directory=True)
    # PYTHONPATH must exist before interpreter startup: otherwise Python
    # caches a None importer for the future src directory and falls through
    # to the repository's data-only vpnd namespace during stats collection.
    (root / "mutants/src").mkdir(parents=True, exist_ok=True)
    generated_package = root / "mutants/vpnd"
    generated_package.mkdir(parents=True, exist_ok=True)
    (generated_package / "src").symlink_to("../src", target_is_directory=True)
    target.write_text(
        tomli_w.dumps(
            {
                "project": metadata.get("project", {}),
                "tool": {
                    "mutmut": {
                        "source_paths": ["src/vpnd/"],
                        "only_mutate": patterns,
                        "also_copy": copied,
                        "pytest_add_cli_args": [
                            "-x",
                            "-q",
                            "-c",
                            "pyproject.toml",
                            *ignored,
                        ],
                        "pytest_add_cli_args_test_selection": ["vpnd/tests/"],
                        "timeout_multiplier": configuration.get(
                            "timeout_multiplier", 5.0
                        ),
                    },
                    "pytest": {
                        "ini_options": {
                            "testpaths": ["vpnd/tests"],
                            "pythonpath": ["src"],
                            "addopts": "-ra",
                        }
                    },
                },
            }
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Expected one scratch repository path")
    prepare(Path(sys.argv[1]))
