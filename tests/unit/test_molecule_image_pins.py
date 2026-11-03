import json
import os
import shutil
import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MOLECULE_IMAGE = re.compile(
    r"(?P<name>ghcr\.io/po4yka/ripdpi-vpn-deploy/molecule-(?:debian13|ubuntu2404))@"
    r"sha256:(?P<digest>[0-9a-f]{64})"
)

EXPECTED_DIGESTS = {
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13": {
        "cc316a12f7673b5606decb1154e4437ecf25f842c281cf9474889fb7539525fc"
    },
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404": {
        "c9277039a651a9a211ab0d1676c7001c78cf95a5ea83d46e1542c386cfe6f040"
    },
}


def test_molecule_base_images_use_the_verified_scan_clean_digests() -> None:
    observed = {name: set() for name in EXPECTED_DIGESTS}

    consumers = [
        *(ROOT / "ansible").glob("**/molecule.yml"),
        *(ROOT / ".github/workflows").glob("*.yml"),
    ]
    for consumer in consumers:
        for match in MOLECULE_IMAGE.finditer(consumer.read_text()):
            observed[match.group("name")].add(match.group("digest"))

    assert observed == EXPECTED_DIGESTS


def test_image_scan_sarif_category_survives_a_digest_repin(tmp_path: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/image-scan.yml").read_text())
    scan = workflow["jobs"]["scan"]
    upload = next(step for step in scan["steps"] if step.get("name") == "Upload Trivy SARIF results")
    assert upload["with"]["category"] == "${{ matrix.category }}"
    assert scan["strategy"]["matrix"]["include"] == "${{ fromJson(needs.enumerate-images.outputs.matrix) }}"
    collect = next(step for step in workflow["jobs"]["enumerate-images"]["steps"] if step.get("id") == "images")
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/list-container-images.py", tmp_path / "scripts/list-container-images.py")
    defaults = tmp_path / "ansible/roles/observability_kuma/defaults"
    defaults.mkdir(parents=True)
    scenario = tmp_path / "ansible/molecule/full-stack"
    scenario.mkdir(parents=True)
    expected = {"trivy-" + image for image in EXPECTED_DIGESTS}
    expected.update({"trivy-observability-kuma-aarch64", "trivy-observability-kuma-x86_64"})
    for digest in ["a" * 64, "b" * 64]:
        (scenario / "molecule.yml").write_text(yaml.safe_dump({"platforms": [
            {"image": image + "@sha256:" + digest} for image in EXPECTED_DIGESTS]}))
        (defaults / "main.yml").write_text(yaml.safe_dump({"observability_kuma": {
            "image_repository": "example.invalid/observer", "image_digests": {
                "aarch64": "sha256:" + digest, "x86_64": "sha256:" + digest}}}))
        output = tmp_path / "github-output"
        subprocess.run(["bash", "-c", collect["run"]], cwd=tmp_path, check=True,
            env={**os.environ, "GITHUB_OUTPUT": str(output)})
        matrix = json.loads(output.read_text().removeprefix("matrix="))
        assert len(matrix) == 4
        assert {row["category"] for row in matrix} == expected
        assert all(row["image"].endswith("@sha256:" + digest) for row in matrix)
        output.unlink()
