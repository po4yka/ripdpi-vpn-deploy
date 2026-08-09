#!/usr/bin/env python3
"""Exercise the real Make-based zizmor boundary against temporary repositories."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"


class ZizmorGateRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("zizmor") is None:
            raise unittest.SkipTest("zizmor is not installed")

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self._temporary_directory.name)
        (self.repository / ".github" / "workflows").mkdir(parents=True)
        (self.repository / ".pre-commit-config.yaml").write_text(
            """repos:
  - repo: local
    hooks:
      - id: noop
        name: noop
        entry: /usr/bin/true
        language: system
"""
        )

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def run_gate(self, *, output_format: str = "plain") -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["ZIZMOR_FORMAT"] = output_format
        return subprocess.run(
            ["make", "--no-print-directory", "-f", str(MAKEFILE), "zizmor-check"],
            cwd=self.repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_workflow(self, relative_path: str, contents: str) -> None:
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    def test_actionable_finding_fails(self) -> None:
        self.write_workflow(
            ".github/workflows/unsafe.yml",
            """name: unsafe
on: pull_request_target
jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
""",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_malformed_owned_yaml_fails_collection(self) -> None:
        self.write_workflow(".github/workflows/malformed.yml", "name: [\n")

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_vendored_nested_workflow_is_out_of_scope(self) -> None:
        self.write_workflow(
            ".github/workflows/safe.yml",
            """name: safe
on: workflow_dispatch
jobs: {}
""",
        )
        self.write_workflow(
            "vendor/package/.github/workflows/unsafe.yml",
            """name: vendored
on: pull_request_target
jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
""",
        )

        result = self.run_gate()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sarif_output_is_rejected_before_audit(self) -> None:
        self.write_workflow(
            ".github/workflows/safe.yml",
            """name: safe
on: workflow_dispatch
jobs: {}
""",
        )

        result = self.run_gate(output_format="sarif")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SARIF does not fail on findings", result.stderr)


if __name__ == "__main__":
    unittest.main()
